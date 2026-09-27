"""One worker owns replay clocks and simulators. Restart fails closed; sessions never auto-resume."""
import asyncio
from collections import deque
from dataclasses import dataclass, field
import time

import numpy as np
from sqlalchemy import select

from app.platform.database import (Alert, Command, Device, InferenceRecord, InferenceSession,
                                   Session, now, record_audit, serialize, uid)
from app.platform.inference import predict
from app.platform.safety import SafetyController, SimulatorAdapter
from app.platform.eog import RealEOGProvider, analyze_batch

live = {}
request_metrics = deque(maxlen=2000)
inference_metrics = deque(maxlen=1000)
inference_semaphore = asyncio.Semaphore(1)
request_count = 0
error_count = 0


@dataclass
class Replay:
    id: str
    owner: str
    x: np.ndarray
    reference: np.ndarray
    profile: str
    speed: int = 1
    cursor: int = 0
    accumulated: float = 0
    started: float = 0
    running: bool = False
    last_poll: float = field(default_factory=time.monotonic)
    prediction_time: float = 0
    last: dict = field(default_factory=dict)
    controller: SafetyController = field(default_factory=SafetyController)
    confirmed: int = -1
    selected_device: str = ""
    pending: dict = field(default_factory=dict)
    motion_deadline: float = 0
    event: str = "NO_SIGNAL"
    personalized: object = None
    eog_data: object = None
    eog_processed: int = 0
    eog_provider: object = field(default_factory=RealEOGProvider)
    eog_last: dict = field(default_factory=dict)
    eog_starts: list = field(default_factory=list)
    eog_sequence: bool = False
    eog_prefiltered: bool = False
    eog_protocol: str = "未配对真实EOG输入；仅显示EEG推理，不产生移动确认。"
    generation: int = 0
    lock: object = field(default_factory=asyncio.Lock)
    streams: int = 0

    def samples_due(self):
        elapsed = self.accumulated + (time.monotonic() - self.started if self.running else 0)
        return min(int(elapsed * 250 * self.speed), len(self.x) * 501)


def alarm(db, replay, kind):
    # Deduplicate unresolved alerts, keep audit events for each decision.
    existing = db.scalar(select(Alert).where(Alert.session_id == replay.id, Alert.kind == kind, Alert.status == "OPEN"))
    if not existing:
        db.add(Alert(owner_id=replay.owner, session_id=replay.id, kind=kind))


def stop_all(db, replay, reason):
    replay.pending.clear()
    replay.motion_deadline = 0
    for device in db.scalars(select(Device).where(Device.session_id == replay.id)):
        was_moving = device.data.get("action") not in (None, "STOP") or device.state == "BUSY"
        device.data = {**device.data, "action": "STOP", "mode": "SIMULATED"}
        if device.state == "BUSY":
            device.state = "ONLINE"
        if was_moving:
            db.add(Command(device_id=device.id, owner_id=replay.owner, data={
                "action": "STOP", "source": "WATCHDOG", "reason": reason, "mode": "SIMULATED",
                "timestamp": now(), "execution_status": "LOCAL_STOP", "latency_ms": 0,
                "confidence": None, "confirmation": "NO_SIGNAL"}))
    for cmd in db.scalars(select(Command).where(Command.owner_id == replay.owner)):
        if cmd.data.get("session_id") == replay.id and cmd.data.get("execution_status") == "PENDING":
            cmd.data = {**cmd.data, "execution_status": "CANCELLED", "reason": reason}


def snapshot(db, replay, begin=None, chunk=None):
    row = db.get(InferenceSession, replay.id)
    return {"id": replay.id, "cursor": replay.cursor,
            "sample_start": replay.cursor if begin is None else begin,
            "samples": [[] for _ in range(replay.x.shape[1])] if chunk is None else chunk,
            "sampling_rate": 250, "speed": replay.speed, "running": replay.running,
            "status": row.status, "generation": replay.generation,
            "emergency_latched": replay.controller.emergency,
            "stable_count": replay.controller.count, "selected_device": replay.selected_device,
            "eog_available": replay.eog_data is not None,
            "total_samples": len(replay.x)*501, "last": replay.last, "eog": replay.eog_last,
            "eog_protocol": replay.eog_protocol,
            "devices": [serialize(d) for d in sorted(db.scalars(select(Device).where(Device.session_id == replay.id)),
                        key=lambda d:(d.id!=replay.selected_device,d.kind))]}


def interrupted(db, replay):
    # A control request committed while inference released the event loop. Discard stale writes.
    db.rollback()
    db.expire_all()
    return snapshot(db, replay)


def issue(db, replay, event="NO_SIGNAL"):
    started = time.perf_counter()
    device = db.get(Device, replay.selected_device)
    prediction = replay.last.get("prediction", 3)
    confidence = replay.last.get("confidence", 0)
    age = time.monotonic() - replay.prediction_time
    action, reason = replay.controller.decide(prediction, confidence, event, device.state, age)
    if event == "CONFIRM" and replay.confirmed == replay.last.get("window"):
        action, reason = "STOP", "CONFIRM_ALREADY_CONSUMED"
    if reason == "ACCEPTED":
        replay.confirmed = replay.last["window"]
    safety_ms = (time.perf_counter() - started) * 1000
    replay.last.update({"decision": action, "reason": reason, "safety_decision_ms": safety_ms})
    if action == "STOP":
        stop_all(db, replay, reason)
    if reason.startswith("DEVICE_") or reason in {"EMERGENCY_LATCHED", "PREDICTION_TIMEOUT"}:
        alarm(db, replay, reason)
    command = Command(id=uid(), device_id=device.id, owner_id=replay.owner, data={
        "session_id": replay.id, "action": action, "source": "EEG+REAL_EOG" if event != "EMERGENCY_MANUAL" else "MANUAL_EMERGENCY", "timestamp": now(),
        "confidence": confidence, "confirmation": event, "mode": "SIMULATED", "reason": reason,
        "execution_status": ("REJECTED" if reason.startswith("DEVICE_") or reason in {"LOW_CONFIDENCE", "UNSTABLE", "PREDICTION_TIMEOUT"} else "STOPPED") if action == "STOP" else "PENDING", "latency_ms": None,
        "simulated_scenario": device.scenario})
    db.add(command)
    if action != "STOP":
        if device.scenario == "FAILURE":
            device.state = "ERROR"
            command.data = {**command.data, "execution_status": "FAILED", "latency_ms": 0}
            stop_all(db, replay, "EXECUTION_FAILURE")
            alarm(db, replay, "EXECUTION_FAILURE")
        else:
            delay = .8 if device.scenario == "DELAY" else 0
            timeout = device.scenario in {"DROP", "TIMEOUT"}
            replay.pending[command.id] = (time.monotonic(), 2 if timeout else delay, timeout)
            device.state = "BUSY"
    record_audit(db, replay.owner, "safety_decision", session_id=replay.id, command_action=action, reason=reason, command_id=command.id)
    return command


def advance_devices(db, replay):
    current = time.monotonic()
    for command_id, (started, delay, timeout) in list(replay.pending.items()):
        if current - started < delay:
            continue
        command = db.get(Command, command_id)
        device = db.get(Device, command.device_id)
        replay.pending.pop(command_id, None)
        command.data = {**command.data, "execution_status": "TIMEOUT" if timeout else "ACK",
                        "latency_ms": (current-started)*1000}
        if timeout:
            stop_all(db, replay, "COMMAND_TIMEOUT")
            alarm(db, replay, "COMMAND_TIMEOUT")
        else:
            device.state = "ONLINE"
            device.data = {**SimulatorAdapter(device.kind).execute(command.data["action"], device.data), "mode": "SIMULATED",
                           "ack_command_id":command.id,"ack_action":command.data["action"],
                           "ack_latency_ms":command.data["latency_ms"],"ack_at":now()}
            replay.motion_deadline = current + 3
        record_audit(db, replay.owner, "device_result", command_id=command_id, status=command.data["execution_status"])
    if replay.motion_deadline and current > replay.motion_deadline:
        stop_all(db, replay, "MOTION_LEASE_EXPIRED")
        record_audit(db, replay.owner, "watchdog_stop", session_id=replay.id)


async def tick(db, replay):
    generation=replay.generation
    replay.last_poll = time.monotonic()
    advance_devices(db, replay)
    due = replay.samples_due() if replay.running else replay.cursor
    # Never skip a completed window when a polling client falls behind.
    end = min(due, (replay.cursor // 501 + 1) * 501)
    # Process signal events in sample order even when a poll spans both streams.
    # Otherwise a newer EEG candidate can erase an earlier EOG confirmation.
    if replay.eog_data is not None and replay.running:
        if replay.eog_sequence:
            eog_end = (replay.eog_processed + 1) * 250
            remaining = replay.eog_processed < len(replay.eog_data)
        else:
            trial, part = divmod(replay.eog_processed, 3)
            eog_end = trial * 501 + part * 125 + 250
            remaining = trial < len(replay.x)
        if remaining:
            end = min(end, eog_end)
    begin = replay.cursor
    flattened = replay.x.transpose(1, 0, 2).reshape(replay.x.shape[1], -1)
    chunk = flattened[:, begin:end].tolist()
    replay.cursor = end
    if end > begin and end % 501 == 0:
        index = end // 501 - 1
        started = time.perf_counter()
        try:
            async with inference_semaphore:
                proba, latency = await asyncio.to_thread(
                    predict, replay.x[index:index+1], replay.reference, replay.personalized
                )
            if replay.generation != generation or not replay.running:
                return interrupted(db, replay)
            prediction = int(proba[0].argmax())
            confidence = float(proba[0].max())
            replay.controller.observe(prediction, confidence)
            replay.eog_provider.reset_candidate(prediction if confidence >= replay.controller.threshold and replay.controller.count >= replay.controller.stable_required and prediction != 3 else None)
            replay.prediction_time = time.monotonic()
            replay.last = {"window": index, "prediction": prediction, "confidence": confidence,
                           "probabilities": proba[0].tolist(), "profile_id": replay.profile,
                           "mode": "REAL", **latency}
            issue(db, replay)
            replay.last["end_to_end_processing_ms"] = (time.perf_counter()-started)*1000
            inference_metrics.append(dict(replay.last))
            db.add(InferenceRecord(session_id=replay.id, owner_id=replay.owner, data=dict(replay.last)))
        except Exception:
            if replay.generation != generation:
                return interrupted(db, replay)
            stop_all(db, replay, "INFERENCE_ERROR")
            alarm(db, replay, "INFERENCE_ERROR")
            replay.running = False
            replay.controller.emergency = True
            db.get(InferenceSession, replay.id).status = "PAUSED"
            replay.last = {"decision": "STOP", "reason": "INFERENCE_ERROR"}
            record_audit(db, replay.owner, "inference_error", session_id=replay.id)
    # EOG inference only receives windows that have actually arrived at replay time.
    if replay.eog_data is not None and replay.running:
        windows=[]
        offsets=[]
        while replay.eog_processed < (len(replay.eog_data) if replay.eog_sequence else len(replay.x)*3):
            if replay.eog_sequence:
                i=replay.eog_processed
                if (i+1)*250>end:break
                windows.append(replay.eog_data[i])
                offsets.append((i,0))
                replay.eog_processed+=1
                continue
            trial,part=divmod(replay.eog_processed,3)
            offset=part*125
            if trial*501+offset+250>end:
                break
            windows.append(replay.eog_data[trial,offset:offset+250])
            offsets.append((trial,offset))
            replay.eog_processed+=1
        if windows:
            try:
                results=await asyncio.to_thread(analyze_batch,windows,replay.eog_prefiltered)
                if replay.generation!=generation or not replay.running:
                    return interrupted(db, replay)
                for result,(trial,offset) in zip(results,offsets):
                    original_start=trial*250 if replay.eog_sequence else replay.eog_starts[trial]+offset if replay.eog_starts else trial*501+offset
                    event=replay.eog_provider.consume(result,original_start,(original_start+250)/250)
                    replay.eog_last={**result,'event':event,'trial':trial,'window_offset':offset,
                                     'mode':'REAL_MODEL','waveform':windows[offsets.index((trial,offset))].tolist()}
                    if event in {'CONFIRM','EMERGENCY'}:
                        issue(db,replay,event)
                        advance_devices(db,replay)
                        record_audit(db,replay.owner,'eog_model_event',session_id=replay.id,event=event,probability=result['probability'])
                        if event == 'EMERGENCY':
                            replay.accumulated += time.monotonic() - replay.started
                            replay.running = False
                            db.get(InferenceSession, replay.id).status = 'PAUSED'
                            break
            except Exception:
                if replay.generation != generation:
                    return interrupted(db, replay)
                replay.running=False
                replay.controller.emergency=True
                stop_all(db,replay,'EOG_MODEL_ERROR')
                alarm(db,replay,'EOG_MODEL_ERROR')
                replay.eog_last={'mode':'REAL_MODEL','event':'ERROR','reason':'EOG_MODEL_ERROR'}
                replay.last={**replay.last,'decision':'STOP','reason':'EOG_MODEL_ERROR'}
                db.get(InferenceSession, replay.id).status = 'PAUSED'
    if end == len(replay.x)*501 and replay.running:
        replay.running = False
        stop_all(db, replay, 'REPLAY_COMPLETE')
        replay.last={**replay.last,'decision':'STOP','reason':'REPLAY_COMPLETE'}
        db.get(InferenceSession, replay.id).status = "COMPLETE"
    db.commit()
    return snapshot(db, replay, begin, chunk)


async def watchdog():
    while True:
        await asyncio.sleep(.2)
        try:
            with Session() as db:
                for replay in list(live.values()):
                    advance_devices(db, replay)
                    if replay.running and time.monotonic() - replay.last_poll > 6:
                        replay.generation += 1
                        replay.accumulated += time.monotonic() - replay.started
                        replay.running = False
                        replay.controller.count = 0
                        replay.eog_provider = RealEOGProvider()
                        replay.last = {**replay.last, 'decision':'STOP', 'reason':'CLIENT_TIMEOUT'}
                        stop_all(db, replay, "CLIENT_TIMEOUT")
                        alarm(db, replay, "CLIENT_TIMEOUT")
                        db.get(InferenceSession, replay.id).status = "PAUSED"
                db.commit()
        except Exception:
            # DB failure is fail-closed even if persistence is unavailable.
            for replay in live.values():
                replay.running = False
                replay.pending.clear()
                replay.controller.emergency = True
