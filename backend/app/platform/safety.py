from dataclasses import dataclass
from typing import Protocol


class EOGProvider(Protocol):
    def reset_candidate(self, candidate: int | None) -> None: ...
    def consume(self, result: dict, start_sample: int, signal_time: float) -> str: ...


@dataclass
class SafetyController:
    threshold: float = .55
    stable_required: int = 2
    last_prediction: int = -1
    count: int = 0
    emergency: bool = False

    def observe(self, prediction, confidence):
        self.count = self.count + 1 if prediction == self.last_prediction and confidence >= self.threshold else 1
        if confidence < self.threshold:
            self.count = 0
        self.last_prediction = prediction

    def decide(self, prediction, confidence, event, state, age):
        if event == "EMERGENCY":
            self.emergency = True
        if self.emergency:
            return "STOP", "EMERGENCY_LATCHED"
        if state != "ONLINE":
            return "STOP", "DEVICE_" + state
        if age > 5:
            return "STOP", "PREDICTION_TIMEOUT"
        if event == "CANCEL":
            return "STOP", "CANCELLED"
        if confidence < self.threshold:
            return "STOP", "LOW_CONFIDENCE"
        if prediction == 3:
            return "STOP", "MODEL_STOP"
        if self.count < self.stable_required:
            return "STOP", "UNSTABLE"
        if event != "CONFIRM":
            return "STOP", "WAIT_EOG_CONFIRM"
        return ("LEFT", "RIGHT", "FORWARD", "STOP")[prediction], "ACCEPTED"


class DeviceAdapter(Protocol):
    def execute(self, action: str, state: dict) -> dict: ...


class SimulatorAdapter:
    """Replace with HTTP/MQTT/WebSocket/Serial adapter only after hardware validation."""
    mode = "SIMULATED"

    def __init__(self, kind):
        self.kind = kind

    def execute(self, action, state):
        result = dict(state)
        result["action"] = action
        if action != "STOP":
            if self.kind == "wheelchair":
                result["x"] = result.get("x", 0) + (1 if action == "FORWARD" else 0)
                result["heading"] = result.get("heading", 0) + (-30 if action == "LEFT" else 30 if action == "RIGHT" else 0)
            elif self.kind == "care_bed":
                result["angle"] = max(0, min(60, result.get("angle", 0) + (-5 if action == "LEFT" else 5)))
            elif self.kind == "emergency_call":
                result["call"] = "REQUESTED"
            elif self.kind == "smart_home":
                result["light"] = action != "LEFT"
        return result
