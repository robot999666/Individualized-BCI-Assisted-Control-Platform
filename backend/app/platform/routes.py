import hashlib
import asyncio
from datetime import datetime
import io
import json
import pickle
from pathlib import Path
import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import numpy as np
import psutil
from sqlalchemy import select, text, delete, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import bci_service
from app.core.config import get_settings
from app.core.resource_guard import WindowLimiter, password_slots, run_blocking
from app.platform import runtime
from app.platform.database import (Alert, Audit, Command, Device, Experiment, InferenceSession,
    LoginSession, Profile, Session, Subject, User, UserRole, SystemConfig, engine, now, record_audit, serialize, uid)
from app.platform.inference import PIPELINE_VERSION, calibrate, fingerprint
from app.platform.security import DUMMY_HASH, current_user, digest, hasher, require, verify, user_from_token
from app.services.bci_model_service import CHANNEL_NAMES
from app.services.npz_reader import read_bci_npz
from app.services.array_uploads import read_numeric_npz, read_numeric_npy
from app.platform.sources import PRESETS, directory, load_source, check_pair

router = APIRouter()
settings = get_settings()
login_limiter = WindowLimiter(2000)
login_attempts = login_limiter.entries


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def own(row, user):
    if not row or (user['role'] != 'admin' and row.owner_id != user['id']):
        raise HTTPException(404, '记录不存在')
    return row


def artifact_path(relative):
    root = settings.artifact_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(422, '非法路径')
    return path


def demo(split):
    return load_source('a01-3ch', split)


@router.get('/data-sources')
async def data_sources(user=Depends(current_user)):
    result = []
    for source_id, (name, _) in PRESETS.items():
        try:
            _, calibration = load_source(source_id, 'calibration')
            _, evaluation = load_source(source_id, 'evaluation')
            root = directory(source_id)
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            pairing = manifest['eog_pairing']
            available = sha(root / 'eog_demo.npz') == pairing['sha256']
            result.append({'id': source_id, 'name': name, 'available': available,
                'subject': calibration['subject'], 'channels': len(calibration['channels']),
                'calibration_trials': len(calibration['trials']), 'evaluation_trials': len(evaluation['trials']),
                'eog_protocol': pairing['protocol']})
        except (HTTPException, OSError, KeyError, ValueError):
            result.append({'id': source_id, 'name': name, 'available': False})
    return result


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


@router.post('/auth/login')
async def login(body: Credentials, request: Request, response: Response):
    ip = request.client.host if request.client else 'unknown'
    if not login_limiter.allow(ip, 8):
        raise HTTPException(429, '登录尝试过多，请稍后重试')
    with Session() as db:
        user = db.scalar(select(User).where(User.username == body.username))
        async with password_slots.slot():
            valid = await run_blocking(verify, body.password, user.password_hash if user else DUMMY_HASH)
        if user:
            db.rollback()  # End a MySQL repeatable-read snapshot before checking revocation.
            db.refresh(user)
        if not valid or not user or not user.active:
            record_audit(db, user.id if user else None, 'login_failed')
            db.commit()
            raise HTTPException(401, '账号或密码错误')
        token = secrets.token_urlsafe(32)
        db.execute(delete(LoginSession).where(LoginSession.expires < time.time()))
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(request.cookies.get('bci_session', ''))))
        old_tokens = list(db.scalars(select(LoginSession).where(LoginSession.user_id == user.id)
                                    .order_by(LoginSession.last_seen.desc())))
        for old in old_tokens[settings.max_login_sessions_per_user-1:]:
            db.delete(old)
        db.add(LoginSession(token_hash=digest(token), user_id=user.id,
                            expires=time.time()+settings.session_hours*3600, last_seen=time.time()))
        role = db.scalar(select(UserRole.role).where(UserRole.user_id == user.id))
        record_audit(db, user.id, 'login')
        db.commit()
        response.set_cookie('bci_session', token, httponly=True, secure=settings.secure_cookie,
                            samesite='strict', max_age=settings.session_hours*3600, path='/')
        return {'id': user.id, 'username': user.username, 'role': role}


@router.get('/auth/me')
async def me(user=Depends(current_user)):
    return user


@router.get('/auth/demo-access')
async def demo_access():
    if not settings.bci_guest_password:
        raise HTTPException(503, '演示访客账号未配置')
    return {'username': 'demo_guest', 'password': settings.bci_guest_password, 'role': 'guest'}


@router.post('/auth/logout')
async def logout(request: Request, response: Response, user=Depends(current_user)):
    with Session() as db:
        token_hash=digest(request.cookies.get('bci_session',''))
        row = db.get(LoginSession, token_hash)
        if row:
            db.delete(row)
        for replay in list(runtime.live.values()):
            if replay.owner == user['id'] and replay.auth_session == token_hash:
                replay.generation+=1
                runtime.stop_all(db, replay, 'LOGOUT')
                replay.running = False
                db.get(InferenceSession,replay.id).status='CLOSED'
                runtime.live.pop(replay.id,None)
        record_audit(db, user['id'], 'logout')
        db.commit()
    response.delete_cookie('bci_session', path='/')
    return {'status':'ok'}


class NewUser(Credentials):
    role: Literal['admin','researcher','caregiver','guest']


@router.get('/users')
async def users(user=Depends(require('admin'))):
    with Session() as db:
        return [{**serialize(u), 'role': db.get(UserRole,u.id).role} for u in db.scalars(select(User))]


@router.post('/users')
async def new_user(body: NewUser, user=Depends(require('admin'))):
    if len(body.password) < 12:
        raise HTTPException(422, '密码至少12位')
    async with password_slots.slot():
        password_hash = await run_blocking(hasher.hash, body.password)
    with Session() as db:
        if db.scalar(select(User).where(User.username==body.username)):
            raise HTTPException(409, '账号已存在')
        row = User(username=body.username,password_hash=password_hash)
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, '账号已存在') from exc
        db.add(UserRole(user_id=row.id,role=body.role))
        record_audit(db,user['id'],'user_created',user_id=row.id,role=body.role)
        db.commit()
        return serialize(row)


class UserUpdate(BaseModel):
    role: Literal['admin','researcher','caregiver','guest']
    active: bool = True


@router.patch('/users/{user_id}')
async def update_user(user_id: str, body: UserUpdate, user=Depends(require('admin'))):
    if user_id == user['id']:
        raise HTTPException(409,'不能在此禁用或修改自己的权限')
    with Session() as db:
        row=db.get(User,user_id)
        if not row:
            raise HTTPException(404,'账号不存在')
        row.active=body.active
        db.get(UserRole,user_id).role=body.role
        for session in db.scalars(select(LoginSession).where(LoginSession.user_id==user_id)):
            db.delete(session)
        for replay in list(runtime.live.values()):
            if replay.owner==user_id:
                replay.generation+=1
                runtime.stop_all(db,replay,'PERMISSION_CHANGED')
                replay.running=False
                db.get(InferenceSession,replay.id).status='CLOSED'
                runtime.live.pop(replay.id,None)
        record_audit(db,user['id'],'permissions_changed',user_id=user_id,role=body.role,active=body.active)
        db.commit()
        return {'status':'ok'}


class NewSubject(BaseModel):
    name: str = Field(min_length=1,max_length=80)
    is_demo: bool = True

    def model_post_init(self, context):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('用户名称不能为空')


@router.get('/subjects')
async def subjects(user=Depends(current_user)):
    with Session() as db:
        query=select(Subject)
        if user['role']!='admin':
            query=query.where(Subject.owner_id==user['id'])
        return [serialize(row) for row in db.scalars(query)]


@router.post('/subjects')
async def new_subject(body: NewSubject,user=Depends(require('admin','researcher','guest'))):
    if user['role']=='guest' and not body.is_demo:
        raise HTTPException(403,'访客只允许脱敏Demo')
    with Session() as db:
        row=Subject(owner_id=user['id'],name=body.name,is_demo=body.is_demo)
        db.add(row)
        db.flush()
        record_audit(db,user['id'],'subject_created',subject_id=row.id,is_demo=row.is_demo)
        db.commit()
        return serialize(row)


async def save_profile(db,subject,user,x,source,y=None):
    if not bci_service.ready:
        raise HTTPException(503,'真实模型未就绪')
    started=time.perf_counter()
    profile_id=uid()
    trained = y is not None
    relative=f"{user['id']}/{profile_id}.{'pkl' if trained else 'npz'}"
    path=artifact_path(relative)
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        if trained:
            if any(np.sum(y==c)<10 for c in range(4)):
                raise ValueError('有标签个体化训练要求每类至少10个trial')
            from algorithms.system_integration.core import EEGClassifier
            model=EEGClassifier(calibrated=True,n_channels=x.shape[1])
            async with runtime.bulk_semaphore:
                await run_blocking(model.calibrate,x,y)
            with path.open('wb') as stream:
                pickle.dump(model,stream)
        else:
            async with runtime.bulk_semaphore:
                matrix=await run_blocking(calibrate,x)
            np.savez_compressed(path,ea_reference=matrix)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise HTTPException(422,str(exc)) from exc
    source={**source,'trial_hashes':[fingerprint(trial) for trial in x],
            'artifact_kind':'PERSONALIZED_FBCSP_LDA' if trained else 'EA_INVERSE_SQRT',
            'classifier_retrained':trained,'pipeline_version':PIPELINE_VERSION}
    row=Profile(id=profile_id,user_id=subject.id,owner_id=user['id'],
                model_version=sha(path) if trained else bci_service.models[x.shape[1]].checksum,channel_layout=list(CHANNEL_NAMES[x.shape[1]]),
                calibration_sample_count=len(x),artifact_path=relative,artifact_sha256=sha(path),source=source)
    db.add(row)
    record_audit(db,user['id'],'calibration_completed',profile_id=profile_id,subject_id=subject.id)
    db.commit()
    return {**serialize(row),'calibration_ms':(time.perf_counter()-started)*1000}


@router.get('/profiles')
async def profiles(user=Depends(current_user)):
    with Session() as db:
        query=select(Profile)
        if user['role']!='admin':
            query=query.where(Profile.owner_id==user['id'])
        return [serialize(row) for row in db.scalars(query)]


@router.post('/subjects/{subject_id}/calibrate-demo')
async def calibrate_demo(subject_id:str,source_id:str=Query('a01-3ch',max_length=80),user=Depends(require('admin','researcher','guest'))):
    with Session() as db:
        subject=own(db.get(Subject,subject_id),user)
        if not subject.is_demo:
            raise HTTPException(422,'请选择Demo用户，避免把公开数据归为真实用户校准')
        x,source=load_source(source_id,'calibration')
        return await save_profile(db,subject,user,x,source)


async def upload_batch(file):
    data=await file.read(settings.max_upload_mb*1024*1024+1)
    batch=await run_blocking(read_bci_npz,file.filename or '',data,250,'uV')
    return batch,hashlib.sha256(data).hexdigest()


@router.post('/subjects/{subject_id}/calibrate-upload')
async def calibrate_upload(subject_id:str,file:UploadFile=File(...),source_id:str=Form('default',min_length=1,max_length=80),user=Depends(require('admin','researcher'))):
    if not source_id.strip():
        raise HTTPException(422,'采集来源标识不能为空')
    with Session() as db:
        subject=own(db.get(Subject,subject_id),user)
        if subject.is_demo:
            raise HTTPException(422,'上传数据请选择私有研究用户；Demo只使用内置公开数据')
        batch,checksum=await upload_batch(file)
        return await save_profile(db,subject,user,batch.x,{'dataset':'USER_UPLOAD','sha256':checksum,'split':'calibration',
                                                   'source_id':f'upload:{subject.id}:{source_id.strip()}',
                                                   'protocol':'User-supplied; independent validation not verified'},batch.y)


@router.delete('/profiles/{profile_id}')
async def reset_profile(profile_id:str,user=Depends(require('admin','researcher','guest'))):
    with Session() as db:
        profile=own(db.get(Profile,profile_id),user)
        profile.status='REVOKED'
        for replay in list(runtime.live.values()):
            if replay.profile==profile_id:
                replay.generation+=1
                runtime.stop_all(db,replay,'PROFILE_REVOKED')
                replay.running=False
                db.get(InferenceSession,replay.id).status='CLOSED'
                runtime.live.pop(replay.id,None)
        record_audit(db,user['id'],'profile_revoked',profile_id=profile.id)
        db.commit()
    return {'status':'REVOKED'}


def save_experiment(db,subject,user,x,source,y=None):
    row=Experiment(id=uid(),owner_id=user['id'],subject_id=subject.id,source=source,artifact_path='')
    row.artifact_path=f"{user['id']}/{row.id}-evaluation.npz"
    path=artifact_path(row.artifact_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path,X=x,**({'y':y} if y is not None else {}))
    row.source={**source,'sha256':sha(path),'samples':len(x),'channels':x.shape[1]}
    if source.get('dataset')=='BCI IV 2a':
        root=directory(source.get('source_id','a01-3ch'))
        eog_path=root/'eog_demo.npz'
        manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        if not eog_path.exists() or sha(eog_path)!=manifest['eog_pairing']['sha256']:
            raise HTTPException(503,'真实EOG数据缺失或checksum不符')
        relative=f"{user['id']}/{row.id}-eog.npz"
        artifact_path(relative).write_bytes(eog_path.read_bytes())
        row.source={**row.source,'eog_path':relative,'eog_sha256':sha(eog_path),
                    'eog_source':manifest['eog_pairing'],
                    'eog_sequence':manifest['eog_pairing'].get('sequence',True),
                    'eog_prefiltered':manifest['eog_pairing'].get('prefiltered',True),
                    'eog_starts':manifest['eog_pairing'].get('sample_starts',[])}
    db.add(row)
    record_audit(db,user['id'],'experiment_created',experiment_id=row.id)
    db.commit()
    return serialize(row)


@router.post('/subjects/{subject_id}/experiments/demo')
async def demo_experiment(subject_id:str,source_id:str=Query('a01-3ch',max_length=80),user=Depends(require('admin','researcher','guest'))):
    with Session() as db:
        subject=own(db.get(Subject,subject_id),user)
        if not subject.is_demo:
            raise HTTPException(422,'请选择Demo用户')
        x,source=load_source(source_id,'evaluation')
        return save_experiment(db,subject,user,x,source)


@router.post('/subjects/{subject_id}/experiments/upload')
async def upload_experiment(subject_id:str,file:UploadFile=File(...),source_id:str=Form('default',min_length=1,max_length=80),user=Depends(require('admin','researcher'))):
    if not source_id.strip():
        raise HTTPException(422,'采集来源标识不能为空')
    with Session() as db:
        subject=own(db.get(Subject,subject_id),user)
        if subject.is_demo:
            raise HTTPException(422,'上传数据请选择私有研究用户；Demo只使用内置公开数据')
        batch,checksum=await upload_batch(file)
        return save_experiment(db,subject,user,batch.x,{'dataset':'USER_UPLOAD','upload_sha256':checksum,
            'source_id':f'upload:{subject.id}:{source_id.strip()}',
            'split':'evaluation','labels_present':batch.y is not None,'protocol':'Unverified provenance; no independent accuracy claim'},batch.y)


@router.get('/experiments')
async def experiments(user=Depends(current_user)):
    with Session() as db:
        query=select(Experiment)
        if user['role']!='admin':
            query=query.where(Experiment.owner_id==user['id'])
        return [serialize(row) for row in db.scalars(query)]


class NewSession(BaseModel):
    profile_id:str = Field(min_length=1, max_length=32)
    experiment_id:str = Field(min_length=1, max_length=32)
    speed:Literal[1,2]=1


@router.post('/sessions')
async def new_session(body:NewSession,request:Request,user=Depends(require('admin','researcher','guest'))):
    token_hash=digest(request.cookies.get('bci_session',''))
    others = [r for r in runtime.live.values() if r.owner != user['id'] or r.auth_session != token_hash]
    if len(others) >= settings.max_live_sessions:
        raise HTTPException(503,'会话容量已满，请关闭旧会话')
    with Session() as db:
        profile=own(db.get(Profile,body.profile_id),user)
        exp=own(db.get(Experiment,body.experiment_id),user)
        check_pair(profile,exp)
        channels=len(profile.channel_layout)
        trained=profile.source.get('classifier_retrained',False)
        if profile.source.get('pipeline_version')!=PIPELINE_VERSION:
            raise HTTPException(409,'算法预处理版本已更新，请重新校准')
        if not bci_service.ready or (not trained and profile.model_version!=bci_service.models[channels].checksum):
            raise HTTPException(409,'模型版本已变更，请重新校准')
        path=artifact_path(profile.artifact_path)
        data_path=artifact_path(exp.artifact_path)
        if sha(path)!=profile.artifact_sha256 or sha(data_path)!=exp.source['sha256']:
            raise HTTPException(409,'Artifact checksum不匹配')
        personalized=None
        if trained:
            # Only server-generated, checksum-verified artifacts, never uploaded pickle.
            with path.open('rb') as stream:
                personalized=pickle.load(stream)
            reference=np.eye(channels)
        else:
            with np.load(path,allow_pickle=False) as payload:
                reference=payload['ea_reference'].copy()
        with np.load(data_path,allow_pickle=False) as payload:
            x=payload['X'].copy()
        if x.shape[1]!=channels:
            raise HTTPException(422,'校准与回放通道布局不一致')
        if set(profile.source['trial_hashes']) & {fingerprint(t) for t in x}:
            raise HTTPException(422,'校准与Evaluation存在重复trial，拒绝数据泄漏')
        row=InferenceSession(id=uid(),owner_id=user['id'],profile_id=profile.id,experiment_id=exp.id)
        db.add(row)
        db.flush()
        replay=runtime.Replay(row.id,user['id'],x,reference,profile.id,speed=body.speed)
        replay.auth_session=token_hash
        replay.personalized=personalized
        if exp.source.get('eog_path'):
            eog_path=artifact_path(exp.source['eog_path'])
            if sha(eog_path)!=exp.source['eog_sha256']:
                raise HTTPException(409,'EOG artifact checksum不匹配')
            with np.load(eog_path,allow_pickle=False) as payload:
                replay.eog_data=payload['X'].copy()
            replay.eog_sequence=exp.source.get('eog_sequence',False)
            replay.eog_prefiltered=exp.source.get('eog_prefiltered',False)
            expected=(len(x)*2,250) if replay.eog_sequence else (len(x),501)
            if replay.eog_data.shape!=expected or not np.isfinite(replay.eog_data).all():
                raise HTTPException(422,'EOG与EEG窗口不匹配')
            replay.eog_starts=exp.source.get('eog_starts',[])
            replay.eog_protocol=exp.source.get('eog_source',{}).get('protocol','Uploaded EOG paired with EEG; chronology provided by uploader')
        if sum(runtime.array_bytes(r) for r in others)+runtime.array_bytes(replay) > settings.max_live_array_mb*1024*1024:
            raise HTTPException(503,'会话内存容量已满，请关闭旧会话后重试')
        config=db.get(SystemConfig,'safety')
        if config:
            replay.controller=runtime.SafetyController(**config.value)
        else:
            replay.controller=runtime.SafetyController(**SafetyConfig().model_dump())
        for kind in ['wheelchair','care_bed','emergency_call','smart_home']:
            device=Device(id=uid(),session_id=row.id,owner_id=user['id'],kind=kind,
                          data={'mode':'SIMULATED','action':'STOP'})
            db.add(device)
            if kind=='wheelchair':
                replay.selected_device=device.id
        # Validate the new input completely before retiring the current working session.
        for old in list(runtime.live.values()):
            if old.owner==user['id'] and old.auth_session==token_hash:
                old.generation+=1
                runtime.stop_all(db,old,'NEW_SESSION')
                old.running=False
                db.get(InferenceSession,old.id).status='CLOSED'
                runtime.live.pop(old.id,None)
        record_audit(db,user['id'],'session_created',session_id=row.id,profile_id=profile.id)
        db.commit()
        runtime.live[row.id]=replay
        return {'id':row.id,'profile_id':profile.id,'model_version':profile.model_version,'sampling_rate':250,
                'trial_count':len(x),'speed':body.speed,'device_mode':'SIMULATED',
                'source_id':exp.source.get('source_id'), 'eog_mode':'REAL_MODEL' if replay.eog_data is not None else 'MISSING',
                'safety':{'threshold':replay.controller.threshold,'stable_required':replay.controller.stable_required}}


def get_replay(db,session_id,user):
    row=own(db.get(InferenceSession,session_id),user)
    replay=runtime.live.get(row.id)
    if not replay or row.status=='CLOSED':
        raise HTTPException(409,'会话已关闭或服务器重启，请创建新会话')
    if db.get(Profile,row.profile_id).status!='READY':
        raise HTTPException(409,'Profile已撤销')
    return replay


@router.get('/sessions/{session_id}/tick')
async def tick(session_id:str,user=Depends(require('admin','researcher','guest'))):
    with Session() as db:
        replay=get_replay(db,session_id,user)
        async with replay.lock:
            return await runtime.tick(db,replay)


@router.websocket('/sessions/{session_id}/stream')
async def session_stream(websocket: WebSocket, session_id: str):
    origin = websocket.headers.get('origin')
    if (settings.production and not origin) or (origin and origin not in settings.effective_cors_origins):
        await websocket.close(code=4403)
        return
    try:
        user = user_from_token(websocket.cookies.get('bci_session', ''))
        if user['role'] not in {'admin', 'researcher', 'guest'}:
            await websocket.close(code=4403)
            return
    except HTTPException:
        await websocket.close(code=4401)
        return
    connected_replay=None
    try:
        with Session() as db:
            replay = get_replay(db, session_id, user)
            if replay.streams >= settings.max_session_streams:
                await websocket.close(code=4429)
                return
            connected_replay=replay
            replay.streams+=1
        await websocket.accept()
        while True:
            user = user_from_token(websocket.cookies.get('bci_session', ''))
            if user['role'] not in {'admin', 'researcher', 'guest'}:
                raise HTTPException(403, '会话权限已撤销')
            with Session() as db:
                replay = get_replay(db, session_id, user)
                async with replay.lock:
                    payload = await runtime.tick(db, replay)
            await asyncio.wait_for(websocket.send_json(payload), timeout=5)
            await asyncio.sleep(.1)
    except (WebSocketDisconnect, TimeoutError):
        return
    except HTTPException as exc:
        await websocket.close(code=4401 if exc.status_code == 401 else 4403 if exc.status_code == 403 else 4404 if exc.status_code == 404 else 4409)
    finally:
        if connected_replay is not None:
            connected_replay.streams=max(0,connected_replay.streams-1)
            if connected_replay.streams==0 and connected_replay.running:
                connected_replay.generation+=1
                connected_replay.accumulated+=time.monotonic()-connected_replay.started
                connected_replay.running=False
                connected_replay.controller.count=0
                connected_replay.eog_provider=runtime.RealEOGProvider()
                connected_replay.last={**connected_replay.last,'decision':'STOP','reason':'STREAM_DISCONNECTED'}
                with Session() as db:
                    runtime.stop_all(db,connected_replay,'STREAM_DISCONNECTED')
                    db.get(InferenceSession,session_id).status='PAUSED'
                    record_audit(db,user['id'],'stream_disconnected',session_id=session_id)
                    db.commit()


class Control(BaseModel):
    action:Literal['play','pause','reset','close']


@router.post('/sessions/{session_id}/control')
async def control(session_id:str,body:Control,user=Depends(require('admin','researcher','guest'))):
    with Session() as db:
        replay=get_replay(db,session_id,user)
        if body.action=='play':
            if replay.controller.emergency:
                raise HTTPException(409,'紧急停止已锁定，请重置后再开始')
            if replay.cursor==len(replay.x)*501:
                raise HTTPException(409,'回放完成，请重置')
            if not replay.running:
                replay.started=time.monotonic()
                replay.last_poll=time.monotonic()
                replay.running=True
        else:
            replay.generation+=1
            if replay.running:
                replay.accumulated+=time.monotonic()-replay.started
            replay.running=False
            runtime.stop_all(db,replay,body.action.upper())
            replay.controller.count=0
            replay.prediction_time=0
            replay.eog_provider=runtime.RealEOGProvider()
            replay.last={**replay.last,'decision':'STOP','reason':body.action.upper()}
            if body.action=='reset':
                for device in db.scalars(select(Device).where(Device.session_id==session_id)):
                    device.data={'mode':'SIMULATED','action':'STOP','x':0,'heading':0,
                                 'position_x':0,'position_z':0,'angle':0,'call':'IDLE','light':False}
                replay.cursor=0
                replay.accumulated=0
                replay.last={}
                config=db.get(SystemConfig,'safety')
                replay.controller=runtime.SafetyController(**(config.value if config else SafetyConfig().model_dump()))
                replay.confirmed=-1
                replay.eog_processed=0
                replay.eog_provider=runtime.RealEOGProvider()
                replay.eog_last={}
        db.get(InferenceSession,session_id).status='CLOSED' if body.action=='close' else 'RUNNING' if replay.running else 'PAUSED'
        record_audit(db,user['id'],'replay_'+body.action,session_id=session_id)
        db.commit()
        if body.action=='close':
            runtime.live.pop(session_id,None)
        current=runtime.snapshot(db,replay)
    return {'status':body.action,'safety':{'threshold':replay.controller.threshold,
        'stable_required':replay.controller.stable_required},'snapshot':current}


@router.post('/sessions/{session_id}/emergency-stop')
async def emergency_stop(session_id:str,user=Depends(require('admin','researcher','guest'))):
    with Session() as db:
        replay=get_replay(db,session_id,user)
        replay.generation+=1
        if replay.running:
            replay.accumulated+=time.monotonic()-replay.started
        command=runtime.issue(db,replay,'EMERGENCY')
        command.data={**command.data,'source':'MANUAL_EMERGENCY'}
        replay.running=False
        db.get(InferenceSession,session_id).status='PAUSED'
        record_audit(db,user['id'],'manual_emergency_stop',session_id=session_id)
        runtime.advance_devices(db,replay)
        db.commit()
        return {'mode':'MANUAL_STOP','decision':replay.last,'command':serialize(command),
                'snapshot':runtime.snapshot(db,replay)}


class DeviceConfig(BaseModel):
    scenario:Literal['ACK','DELAY','DROP','OFFLINE','TIMEOUT','FAILURE','BUSY']
    select_device:bool=True


@router.post('/sessions/{session_id}/devices/{device_id}')
async def configure_device(session_id:str,device_id:str,body:DeviceConfig,user=Depends(require('admin','researcher','guest'))):
    with Session() as db:
        replay=get_replay(db,session_id,user)
        device=own(db.get(Device,device_id),user)
        if device.session_id!=session_id:
            raise HTTPException(404,'设备不属于该会话')
        replay.generation+=1
        if body.select_device and replay.selected_device!=device.id:
            replay.controller.count=0
        replay.eog_provider=runtime.RealEOGProvider()
        if replay.controller.count>=replay.controller.stable_required and replay.last.get('confidence',0)>=replay.controller.threshold and replay.last.get('prediction',3)!=3:
            replay.eog_provider.reset_candidate(replay.last['prediction'])
        replay.last={**replay.last,'decision':'STOP','reason':'DEVICE_CONFIGURATION'}
        runtime.stop_all(db,replay,'DEVICE_CONFIGURATION')
        device.scenario=body.scenario
        device.state='OFFLINE' if body.scenario=='OFFLINE' else 'BUSY' if body.scenario=='BUSY' else 'ONLINE'
        if body.select_device:
            replay.selected_device=device.id
        if device.state=='OFFLINE':
            runtime.alarm(db,replay,'DEVICE_OFFLINE')
        record_audit(db,user['id'],'simulator_configured',device_id=device.id,scenario=body.scenario)
        db.commit()
        return serialize(device)


async def _health_detail():
    database='ok'
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            connection.execute(text('SELECT version_num FROM alembic_version'))
    except Exception:
        database='error'
    filesystem='ok'
    try:
        probe=settings.artifact_dir / ('.health-'+secrets.token_hex(8))
        probe.write_bytes(b'health')
        probe.unlink()
    except OSError:
        filesystem='error'
    from app.platform.eog import health as eog_health
    eog_state=eog_health()
    good=database=='ok' and filesystem=='ok' and bci_service.ready and eog_state['status']=='ok'
    return {'status':'ok' if good else 'degraded','service':'als-bci-4class','backend':'ok',
            'database':database,'database_engine':engine.dialect.name,'filesystem':filesystem,
            'model':'ok' if bci_service.ready else 'error','model_ready':bci_service.ready,
            'model_error':None if bci_service.ready else 'model unavailable; inspect server logs',
            'model_checksums':bci_service.checksums,'loaded_layouts':[f'{c}ch' for c in sorted(bci_service.models)],
            'runtime_versions':bci_service.versions,'gateway':{'status':'ok','mode':'SIMULATED'},
            'eog':eog_state,'time':now()}


@router.get('/health/live')
@router.get('/health')
async def health_live():
    return {'status': 'ok'}


@router.get('/health/detail')
async def health_detail(user=Depends(require('admin'))):
    return await _health_detail()


@router.get('/operations')
async def operations(session_id:str|None=Query(None,max_length=32),user=Depends(current_user)):
    with Session() as db:
        result={'session_id':session_id}
        if session_id:
            row=db.get(InferenceSession,session_id)
            if user['role']=='caregiver':
                if not row or not db.get(Subject,db.get(Experiment,row.experiment_id).subject_id).is_demo:
                    raise HTTPException(404,'记录不存在')
            else:
                own(row,user)
        for key,model in [('alerts',Alert),('audit_logs',Audit),('commands',Command),('devices',Device),('sessions',InferenceSession)]:
            query=select(model)
            if user['role']!='admin':
                if user['role']=='caregiver' and model in (Alert,Command,Device,InferenceSession):
                    demo_sessions=select(InferenceSession.id).join(Experiment,InferenceSession.experiment_id==Experiment.id).join(Subject,Experiment.subject_id==Subject.id).where(Subject.is_demo.is_(True))
                    if model==InferenceSession:
                        query=query.where(InferenceSession.id.in_(demo_sessions))
                    elif model==Command:
                        query=query.where(Command.device_id.in_(select(Device.id).where(Device.session_id.in_(demo_sessions))))
                    else:
                        query=query.where(model.session_id.in_(demo_sessions))
                else:
                    query=query.where(model.owner_id==user['id'])
            if hasattr(model,'created_at'):
                query=query.order_by(model.created_at.desc())
            if session_id:
                if model==InferenceSession:
                    query=query.where(model.id==session_id)
                elif model==Command:
                    query=query.where(Command.device_id.in_(select(Device.id).where(Device.session_id==session_id)))
                elif model!=Audit:
                    query=query.where(model.session_id==session_id)
            rows=[serialize(row) for row in db.scalars(query.limit(100))]
            if model is Alert:
                for item in rows:
                    item['response_time_seconds'] = (
                        max(0, (datetime.fromisoformat(item['acknowledged_at']) - datetime.fromisoformat(item['created_at'])).total_seconds())
                        if item.get('acknowledged_at') else None
                    )
                    item['acknowledged_by_username'] = db.get(User, item['acknowledged_by']).username if item.get('acknowledged_by') and db.get(User, item['acknowledged_by']) else None
            result[key]=rows
        if user['role']=='admin':
            values=list(runtime.request_metrics)
            result['real']={'api_requests':runtime.request_count,'api_latency_ms_mean':float(np.mean(values)) if values else None,
                'error_count':runtime.error_count,'cpu_percent':psutil.cpu_percent(),
                'memory_percent':psutil.virtual_memory().percent,'process_memory_mb':psutil.Process().memory_info().rss/1024**2,
                'online_users':len(set(db.scalars(select(LoginSession.user_id).where(LoginSession.last_seen>time.time()-300,LoginSession.expires>time.time())))),
                'live_sessions':len(runtime.live),'recent_inference':list(runtime.inference_metrics)[-10:],
                'metrics_scope':'single backend process since restart; bounded recent windows'}
        result['health']={'status':'ok'}
        if user['role']=='admin':
            result['health']=await _health_detail()
        acknowledged=[a for a in result['alerts'] if a.get('acknowledged_at')]
        response_times=[a['response_time_seconds'] for a in acknowledged if a.get('response_time_seconds') is not None]
        result['alert_response']={'total':len(result['alerts']),'acknowledged':len(acknowledged),
            'open':sum(a['status']=='OPEN' for a in result['alerts']),
            'average_seconds':float(np.mean(response_times)) if response_times else None,
            'fastest_seconds':min(response_times) if response_times else None}
        result['simulated']={'mode':'SIMULATED','device_count':len(result['devices']),
                             'failures_in_recent_commands':sum(c['data'].get('execution_status') in ('FAILED','TIMEOUT') for c in result['commands'])}
        return result


class AlertAcknowledgement(BaseModel):
    result: Literal['已处理','已转交','无法处理'] = '已处理'
    notes: str = Field(default='', max_length=900)


@router.post('/alerts/{alert_id}/ack')
async def acknowledge(alert_id:str,body:AlertAcknowledgement,user=Depends(require('admin','caregiver','researcher'))):
    with Session() as db:
        alert=db.get(Alert,alert_id)
        if user['role']=='caregiver' and alert:
            session=db.get(InferenceSession,alert.session_id)
            exp=db.get(Experiment,session.experiment_id)
            if not db.get(Subject,exp.subject_id).is_demo:
                raise HTTPException(403,'当前照护账号仅获授权处理脱敏Demo告警')
        else:
            own(alert,user)
        if not alert:
            raise HTTPException(404,'告警不存在')
        if alert.acknowledged_at:
            raise HTTPException(409,'此告警已记录处理结果')
        changed=db.execute(update(Alert).where(Alert.id==alert.id, Alert.acknowledged_at.is_(None))
                           .values(status='ACKNOWLEDGED', acknowledged_at=now(), acknowledged_by=user['id'],
                                   resolution=body.result + (f'：{body.notes.strip()}' if body.notes.strip() else '')))
        if changed.rowcount != 1:
            raise HTTPException(409,'此告警已记录处理结果')
        db.refresh(alert)
        record_audit(db,user['id'],'alert_acknowledged',alert_id=alert.id)
        db.commit()
        return {**serialize(alert),'response_time_seconds':max(0,(datetime.fromisoformat(alert.acknowledged_at)-datetime.fromisoformat(alert.created_at)).total_seconds())}

class SafetyConfig(BaseModel):
    threshold:float=Field(default=.55,ge=.5,le=.99)
    stable_required:int=Field(default=2,ge=2,le=5)


@router.get('/configuration')
async def configuration(user=Depends(require('admin'))):
    with Session() as db:
        row=db.get(SystemConfig,'safety')
        return {'safety':row.value if row else SafetyConfig().model_dump(),
                'model_checksums':bci_service.checksums,'model_mode':'REAL / EA+FBCSP+LDA',
                'eog_mode':'REAL_MODEL','device_mode':'SIMULATED'}


@router.put('/configuration')
async def set_configuration(body:SafetyConfig,user=Depends(require('admin'))):
    with Session() as db:
        row=db.get(SystemConfig,'safety')
        if not row:
            row=SystemConfig(key='safety',value=body.model_dump());db.add(row)
        else:
            row.value=body.model_dump()
        record_audit(db,user['id'],'configuration_updated',safety=body.model_dump())
        db.commit()
    return {'status':'saved','applies_to':'new sessions and sessions after reset',**body.model_dump()}


class EvaluationRequest(BaseModel):
    profile_id:str = Field(min_length=1, max_length=32)


@router.post('/experiments/{experiment_id}/evaluate')
async def evaluate_experiment(experiment_id:str,body:EvaluationRequest,user=Depends(require('admin','researcher'))):
    from app.platform.inference import predict
    with Session() as db:
        exp=own(db.get(Experiment,experiment_id),user)
        profile=own(db.get(Profile,body.profile_id),user)
        check_pair(profile,exp)
        path=artifact_path(exp.artifact_path);ref_path=artifact_path(profile.artifact_path)
        if sha(path)!=exp.source['sha256'] or sha(ref_path)!=profile.artifact_sha256:
            raise HTTPException(409,'Checksum不匹配')
        with np.load(path,allow_pickle=False) as payload:
            x=payload['X']; y=payload['y'] if 'y' in payload else None
        if y is None:
            raise HTTPException(422,'无真实标签，不计算准确率')
        channels=x.shape[1]
        trained=profile.source.get('classifier_retrained',False)
        if profile.source.get('pipeline_version')!=PIPELINE_VERSION:
            raise HTTPException(409,'算法预处理版本已更新，请重新校准')
        if channels!=len(profile.channel_layout) or not bci_service.ready or (not trained and profile.model_version!=bci_service.models[channels].checksum):
            raise HTTPException(409,'通道或模型版本不匹配')
        if set(profile.source['trial_hashes']) & {fingerprint(t) for t in x}:
            raise HTTPException(422,'校准与Evaluation存在重复trial')
        personalized=None
        if trained:
            with ref_path.open('rb') as stream:
                personalized=pickle.load(stream)
            reference=np.eye(channels)
        else:
            with np.load(ref_path,allow_pickle=False) as payload:
                reference=payload['ea_reference']
        async with runtime.bulk_semaphore:
            p,latency=await run_blocking(predict,x,reference,personalized)
        result={'accuracy':float(np.mean(p.argmax(1)==y)),'trials':len(x),'latency':latency,
                'mode':'REAL','protocol':'Uploaded labeled evaluation with fixed calibration EA; pretraining overlap unknown',
                'independent_validation':False,'profile_id':profile.id,'model_version':profile.model_version}
        exp.source={**exp.source,'evaluation':result}
        record_audit(db,user['id'],'experiment_evaluated',experiment_id=exp.id,profile_id=profile.id)
        db.commit()
        return result

@router.post('/eog/demo-analyze')
async def eog_demo_analysis(user=Depends(require('admin','researcher'))):
    from app.platform.eog import analyze_batch, lock
    path=settings.demo_data_dir/'eog_evaluation.npz'
    manifest=json.loads((settings.demo_data_dir/'manifest.json').read_text(encoding='utf-8'))
    if not path.exists() or sha(path)!=manifest.get('eog_diagnostic',{}).get('sha256'):
        raise HTTPException(503,'EOG诊断数据缺失或checksum不符')
    try:
        with np.load(path,allow_pickle=False) as payload:
            windows=payload['X'][:,:250].copy()
        import asyncio
        async with lock:
            results=await run_blocking(analyze_batch,windows)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    with Session() as db:
        record_audit(db,user['id'],'eog_offline_model_validation',windows=len(results))
        db.commit()
    return {'mode':'REAL_MODEL','input_source':manifest['eog_diagnostic'],'results':results,
            'device_control':False,'accuracy':None,'confirmation_provider':'REAL_MODEL'}


@router.post('/eog/analyze-upload')
async def eog_upload_analysis(file:UploadFile=File(...),user=Depends(require('admin','researcher'))):
    from app.platform.eog import analyze_batch, lock
    content=await file.read(16385)
    if not (file.filename or '').lower().endswith('.npy') or len(content)>16384:
        raise HTTPException(422,'仅接受小于16KiB、250点、μV的EOG .npy')
    try:
        window=await run_blocking(read_numeric_npy,content,16384)
        import asyncio
        async with lock:
            result=(await run_blocking(analyze_batch,np.asarray(window)[None,:]))[0]
    except (ValueError,OSError,EOFError) as exc:
        raise HTTPException(422,'EOG格式或模型输出无效') from exc
    with Session() as db:
        record_audit(db,user['id'],'eog_uploaded_model_validation')
        db.commit()
    return result

@router.post('/experiments/{experiment_id}/eog-upload')
async def upload_eog_pair(experiment_id:str,file:UploadFile=File(...),prefiltered:bool=Form(False),user=Depends(require('admin','researcher'))):
    content=await file.read(16*1024*1024+1)
    if not (file.filename or '').lower().endswith('.npz') or len(content)>16*1024*1024:
        raise HTTPException(422,'EOG配对要求16MiB以内NPZ，仅包含X')
    with Session() as db:
        exp=own(db.get(Experiment,experiment_id),user)
        if db.get(Subject,exp.subject_id).is_demo:
            raise HTTPException(422,'不能覆盖内置公开Demo数据')
        if any(r.owner==user['id'] and db.get(InferenceSession,r.id).experiment_id==exp.id for r in runtime.live.values()):
            raise HTTPException(409,'请先关闭使用该实验的会话，再更新EOG数据')
        try:
            arrays=await run_blocking(read_numeric_npz,content,64*1024*1024,('X',))
            x=np.asarray(arrays['X'],dtype=np.float64)
            n=exp.source['samples']
            if x.shape not in {(n,501),(2*n,250)} or not np.isfinite(x).all():
                raise ValueError('EOG shape mismatch')
            windows=x if x.shape[1]==250 else np.concatenate([x[:,offset:offset+250] for offset in (0,125,250)])
            if np.any(np.std(windows,axis=1)<1e-8):
                raise ValueError('Constant EOG window')
        except (ValueError,KeyError,OSError) as exc:
            raise HTTPException(422,'EOG X须为数值(N,501)同步窗口或(2N,250)片段序列，250Hz/μV、全部有限且窗口非恒定') from exc
        relative=f"{user['id']}/{uid()}-eog.npz"
        path=artifact_path(relative);path.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(path,X=x)
        exp.source={**exp.source,'eog_path':relative,'eog_sha256':sha(path),
            'eog_sequence':x.shape[1]==250,'eog_prefiltered':prefiltered,
            'eog_source':{'protocol':'用户上传EEG/EOG配对；来源与同步关系由上传者声明，未独立验证。',
                          'prefiltered':prefiltered,'unit':'uV','sampling_rate':250}}
        record_audit(db,user['id'],'eog_paired',experiment_id=exp.id)
        db.commit()
        return {'status':'READY','windows':len(x),'mode':'REAL_DATA','prefiltered':prefiltered}
