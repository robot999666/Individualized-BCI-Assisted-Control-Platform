"""Regression coverage for source consistency, real pipelines and control races."""
import asyncio
import io
import threading
import time

import numpy as np
import pytest
from sqlalchemy import select

from backend.tests.test_platform import clients, post, setup_demo, complete_window
from app.platform import routes, runtime
from app.platform.database import Session, InferenceSession, Experiment, InferenceRecord, Device


def npz(x, **arrays):
    content = io.BytesIO()
    np.savez_compressed(content, X=x, **arrays)
    return ('data.npz', content.getvalue())


@pytest.mark.parametrize('source_id', ['a01-3ch', 'a01-22ch', 'a02-3ch', 'a02-22ch'])
def test_presets_run_real_models_and_remain_same_source(clients, source_id):
    client = clients['guest']
    catalog = client.get('/api/v1/data-sources').json()
    source = next(item for item in catalog if item['id'] == source_id)
    assert source['available'], source
    subject = post(client, '/subjects', {'name': source_id, 'is_demo': True})
    profile = post(client, f"/subjects/{subject['id']}/calibrate-demo?source_id={source_id}")
    experiment = post(client, f"/subjects/{subject['id']}/experiments/demo?source_id={source_id}")
    session = post(client, '/sessions', {'profile_id': profile['id'], 'experiment_id': experiment['id']})
    assert session['source_id'] == source_id
    assert profile['source']['source_id'] == experiment['source']['source_id']
    assert len(profile['channel_layout']) == source['channels']
    replay = runtime.live[session['id']]
    if source_id.startswith('a02'):
        assert replay.eog_data.shape == (24, 501)
        assert not replay.eog_sequence and not replay.eog_prefiltered
    post(client, f"/sessions/{session['id']}/control", {'action':'play'})
    result = complete_window(client, session, 0)
    assert result['last']['mode'] == 'REAL'
    assert len(result['last']['probabilities']) == 4
    assert result['eog']['mode'] == 'REAL_MODEL'


def test_mismatched_source_or_user_cannot_replace_live_session(clients):
    client = clients['guest']
    subject, profile, _, session = setup_demo(client)
    wrong = post(client, f"/subjects/{subject['id']}/experiments/demo?source_id=a02-3ch")
    response = client.post('/api/v1/sessions', json={'profile_id':profile['id'],'experiment_id':wrong['id']})
    assert response.status_code == 422 and '来源' in response.json()['detail']
    assert session['id'] in runtime.live
    post(client, f"/sessions/{session['id']}/control", {'action':'play'})
    assert runtime.live[session['id']].running
    wrong_user = post(client, '/subjects', {'name':'Other participant'})
    other = post(client, f"/subjects/{wrong_user['id']}/experiments/demo")
    assert client.post('/api/v1/sessions',json={'profile_id':profile['id'],'experiment_id':other['id']}).status_code == 422
    assert client.post(f"/api/v1/subjects/{subject['id']}/experiments/demo?source_id=../../bad").status_code == 422


def test_private_upload_and_eog_pair_validation(clients):
    client = clients['researcher']
    subject = post(client, '/subjects', {'name':'Private participant','is_demo':False})
    calibration, _ = routes.demo('calibration')
    evaluation, _ = routes.demo('evaluation')
    base = f"/api/v1/subjects/{subject['id']}"
    profile = client.post(base+'/calibrate-upload', files={'file':npz(calibration)},data={'source_id':'recording-a'}).json()
    experiment = client.post(base+'/experiments/upload',files={'file':npz(evaluation)},data={'source_id':'recording-b'}).json()
    assert client.post('/api/v1/sessions',json={'profile_id':profile['id'],'experiment_id':experiment['id']}).status_code == 422
    exp = client.post(base+'/experiments/upload',files={'file':npz(evaluation)},data={'source_id':'recording-a'}).json()
    endpoint = f"/api/v1/experiments/{exp['id']}/eog-upload"
    for invalid in (np.ones((24,501)),np.ones((24,250)),np.full((24,501),np.nan)):
        assert client.post(endpoint,files={'file':npz(invalid)}).status_code == 422
    with np.load(routes.settings.demo_data_dir/'eog_demo.npz',allow_pickle=False) as data:
        eog = data['X'].copy()
    assert client.post(endpoint,files={'file':npz(eog)},data={'prefiltered':'true'}).status_code == 200
    session = post(client,'/sessions',{'profile_id':profile['id'],'experiment_id':exp['id']})
    assert session['eog_mode'] == 'REAL_MODEL'
    assert client.post(endpoint,files={'file':npz(eog)}).status_code == 409
    post(client,f"/sessions/{session['id']}/control",{'action':'close'})
    assert client.post(endpoint,files={'file':npz(eog)},data={'prefiltered':'true'}).status_code == 200
    no_eog = client.post(base+'/experiments/upload',files={'file':npz(evaluation)},data={'source_id':'recording-a'}).json()
    session = post(client,'/sessions',{'profile_id':profile['id'],'experiment_id':no_eog['id']})
    assert session['eog_mode'] == 'MISSING'
    post(client,f"/sessions/{session['id']}/control",{'action':'play'})
    result = complete_window(client,session,0)
    assert not result['eog_available']
    assert all(d['data']['action']=='STOP' for d in result['devices'])


@pytest.mark.parametrize('action', ['pause', 'reset', 'emergency'])
def test_control_interrupts_inflight_eeg_without_stale_writes(clients, monkeypatch, action):
    client = clients['guest']
    _, _, _, session = setup_demo(client)
    replay = runtime.live[session['id']]
    replay.eog_data = None
    replay.running = True
    replay.started = time.monotonic()
    replay.samples_due = lambda:501
    entered = threading.Event()
    release = threading.Event()
    original = runtime.predict
    def slow(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(runtime,'predict',slow)
    async def exercise():
        with Session() as db:
            work = asyncio.create_task(runtime.tick(db,replay))
            assert await asyncio.to_thread(entered.wait,3)
            user = {'id':replay.owner,'role':'guest'}
            if action == 'emergency':
                await routes.emergency_stop(replay.id,user)
            else:
                await routes.control(replay.id,routes.Control(action=action),user)
            release.set()
            result = await asyncio.wait_for(work,5)
            assert not result['running']
            assert result['status']=='PAUSED'
            assert result['last'].get('decision','STOP')=='STOP'
            assert all(d['data']['action']=='STOP' for d in result['devices'])
            if action == 'reset':
                assert result['cursor']==0 and result['last']=={}
            if action == 'emergency':
                assert result['emergency_latched']
        with Session() as db:
            assert not db.scalar(select(InferenceRecord).where(InferenceRecord.session_id==replay.id))
    try:
        asyncio.run(exercise())
    finally:
        release.set()
        del replay.samples_due


def test_pause_freezes_cursor_and_completion_stops_devices(clients):
    client = clients['guest']
    _, _, _, session = setup_demo(client)
    replay = runtime.live[session['id']]
    replay.accumulated = 5
    paused = client.get(f"/api/v1/sessions/{replay.id}/tick").json()
    assert paused['cursor']==0 and paused['last']=={}
    post(client,f"/sessions/{replay.id}/control",{'action':'reset'})
    replay.eog_data = None
    replay.cursor = len(replay.x)*501-1
    replay.accumulated = len(replay.x)*501/250+1
    replay.started = time.monotonic()
    replay.running = True
    with Session() as db:
        device=db.get(Device,replay.selected_device)
        device.data={**device.data,'action':'RIGHT'}
        replay.motion_deadline=time.monotonic()+100
        db.commit()
    result=client.get(f"/api/v1/sessions/{replay.id}/tick").json()
    assert result['status']=='COMPLETE' and not result['running']
    assert result['last']['reason']=='REPLAY_COMPLETE'
    assert replay.motion_deadline==0
    assert all(d['data']['action']=='STOP' for d in result['devices'])


def test_bad_replacement_eog_does_not_close_existing_session(clients):
    client = clients['guest']
    subject, profile, _, session=setup_demo(client)
    replacement=post(client,f"/subjects/{subject['id']}/experiments/demo")
    with Session() as db:
        row=db.get(Experiment,replacement['id'])
        row.source={**row.source,'eog_sha256':'bad'}
        db.commit()
    response=client.post('/api/v1/sessions',json={'profile_id':profile['id'],'experiment_id':replacement['id']})
    assert response.status_code==409
    assert session['id'] in runtime.live
    with Session() as db:
        assert db.get(InferenceSession,session['id']).status!='CLOSED'


def test_labeled_calibration_trains_and_reloads_personal_model(clients):
    client=clients['researcher']
    subject=post(client,'/subjects',{'name':'Personal model regression','is_demo':False})
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    with np.load(root/'algorithms/bci_4class/data/S3_3ch.npz',allow_pickle=False) as data:
        x=data['X'].copy();y=data['y'].copy()
    # These are recorded, labeled trials. Training overlap is not an accuracy claim.
    indices=np.concatenate([np.flatnonzero(y==label)[:10] for label in range(4)])
    holdout=np.setdiff1d(np.arange(len(x)),indices)[:4]
    endpoint=f"/api/v1/subjects/{subject['id']}"
    response=client.post(endpoint+'/calibrate-upload',files={'file':npz(x[indices],y=y[indices])})
    assert response.status_code==200,response.text
    profile=response.json()
    assert profile['source']['classifier_retrained']
    assert profile['source']['artifact_kind']=='PERSONALIZED_FBCSP_LDA'
    response=client.post(endpoint+'/experiments/upload',files={'file':npz(x[holdout],y=y[holdout])})
    assert response.status_code==200,response.text
    experiment=response.json()
    session=post(client,'/sessions',{'profile_id':profile['id'],'experiment_id':experiment['id']})
    assert runtime.live[session['id']].personalized is not None
    post(client,f"/sessions/{session['id']}/control",{'action':'play'})
    result=complete_window(client,session,0)
    assert result['last']['mode']=='REAL'
    evaluation=post(client,f"/experiments/{experiment['id']}/evaluate",{'profile_id':profile['id']})
    assert 0<=evaluation['accuracy']<=1 and evaluation['trials']==4
    assert not evaluation['independent_validation']


def test_operations_are_scoped_and_authorized(clients):
    client=clients['guest']
    _,_,_,first=setup_demo(client)
    post(client,f"/sessions/{first['id']}/emergency-stop")
    _,_,_,second=setup_demo(client)
    result=client.get(f"/api/v1/operations?session_id={second['id']}").json()
    assert result['session_id']==second['id']
    assert result['commands']==[] and result['alerts']==[]
    assert {s['id'] for s in result['sessions']}=={second['id']}
    assert clients['researcher'].get(f"/api/v1/operations?session_id={second['id']}").status_code==404
    assert clients['caregiver'].get(f"/api/v1/operations?session_id={second['id']}").status_code==200


def test_stream_disconnect_pauses_and_logout_releases_session(clients):
    client=clients['guest']
    _,_,_,session=setup_demo(client)
    replay=runtime.live[session['id']]
    with client.websocket_connect(f"/api/v1/sessions/{replay.id}/stream",headers={'Origin':'http://localhost:3000'}) as socket:
        socket.receive_json()
        post(client,f"/sessions/{replay.id}/control",{'action':'play'})
        socket.receive_json()
    assert not replay.running
    assert replay.last['reason']=='STREAM_DISCONNECTED'
    with Session() as db:
        assert db.get(InferenceSession,replay.id).status=='PAUSED'
    post(client,'/auth/logout')
    assert replay.id not in runtime.live
    with Session() as db:
        assert db.get(InferenceSession,replay.id).status=='CLOSED'


def test_account_disable_and_reenable_preserve_role(clients):
    researcher=clients['researcher'];admin=clients['admin']
    _,_,_,session=setup_demo(researcher)
    replay=runtime.live[session['id']]
    account=researcher.get('/api/v1/auth/me').json()
    response=admin.patch('/api/v1/users/'+account['id'],json={'role':'researcher','active':False})
    assert response.status_code==200
    assert researcher.get('/api/v1/profiles').status_code==401
    assert replay.id not in runtime.live
    with Session() as db:
        assert db.get(InferenceSession,replay.id).status=='CLOSED'
    response=admin.patch('/api/v1/users/'+account['id'],json={'role':'researcher','active':True})
    assert response.status_code==200
    from app.platform.routes import login_attempts
    login_attempts.clear()
    result=researcher.post('/api/v1/auth/login',json={'username':account['username'],'password':'test-only-'+account['username']})
    assert result.status_code==200 and result.json()['role']=='researcher'


def test_eeg_failure_requires_reset_before_resuming(clients,monkeypatch):
    client=clients['guest']
    _,_,_,session=setup_demo(client)
    replay=runtime.live[session['id']]
    replay.eog_data=None
    post(client,f"/sessions/{replay.id}/control",{'action':'play'})
    def fail(*args):
        raise ValueError('Model failure for this test')
    monkeypatch.setattr(runtime,'predict',fail)
    result=complete_window(client,session,0)
    assert result['last']['reason']=='INFERENCE_ERROR'
    assert result['emergency_latched'] and not result['running']
    assert client.post(f"/api/v1/sessions/{replay.id}/control",json={'action':'play'}).status_code==409
    post(client,f"/sessions/{replay.id}/control",{'action':'reset'})
    assert not replay.controller.emergency and replay.cursor==0
