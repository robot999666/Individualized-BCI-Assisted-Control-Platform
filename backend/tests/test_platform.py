"""Integration against configured MySQL; true model predictions, no generated EEG scores."""
import io
import time
import uuid
import asyncio
import threading
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.main import app
from app.platform import runtime
from app.platform.database import Session, User, UserRole, Role, Profile, Device, Command, engine, SystemConfig
from app.platform.security import hasher
from app.platform.safety import SafetyController
from app.platform.inference import calibrate, predict


@pytest.fixture
def clients():
    result={}
    with Session() as db:
        for role in ['admin','researcher','caregiver','guest']:
            if not db.get(Role,role):
                db.add(Role(name=role))
        db.flush()
        for role in ['admin','researcher','caregiver','guest']:
            name='test_'+role+'_'+uuid.uuid4().hex[:10]
            user=User(username=name,password_hash=hasher.hash('test-only-'+name))
            db.add(user);db.flush();db.add(UserRole(user_id=user.id,role=role));db.commit()
            client=TestClient(app)
            response=client.post('/api/v1/auth/login',json={'username':name,'password':'test-only-'+name})
            # Tests use distinct client addresses to avoid sharing login attempt limits.
            from app.platform.routes import login_attempts
            login_attempts.clear()
            assert response.status_code==200,response.text
            result[role]=client
    yield result
    runtime.live.clear()


def post(client,path,body=None):
    response=client.post('/api/v1'+path,json=body or {})
    assert response.status_code==200,response.text
    return response.json()


def setup_demo(client):
    subject=post(client,'/subjects',{'name':'Automated Demo','is_demo':True})
    profile=post(client,f"/subjects/{subject['id']}/calibrate-demo")
    experiment=post(client,f"/subjects/{subject['id']}/experiments/demo")
    session=post(client,'/sessions',{'profile_id':profile['id'],'experiment_id':experiment['id']})
    return subject,profile,experiment,session


def complete_window(client,session,index):
    replay=runtime.live[session['id']]
    replay.accumulated=(index+1)*501/250+.01
    replay.started=time.monotonic()
    target=(index+1)*501
    replay.samples_due=lambda: target
    try:
        while replay.cursor < target:
            response=client.get(f"/api/v1/sessions/{session['id']}/tick")
            assert response.status_code==200,response.text
        return response.json()
    finally:
        del replay.samples_due


def test_mysql_health_and_rbac(clients):
    with engine.connect() as connection:
        assert connection.execute(text('SELECT 1')).scalar()==1
    assert clients['guest'].get('/api/v1/health/live').json()=={'status':'ok'}
    assert set(clients['guest'].get('/api/v1/health/live').json())=={'status'}
    assert clients['guest'].get('/api/v1/health/detail').status_code==403
    assert clients['admin'].get('/api/v1/health/detail').json()['database']=='ok'
    assert clients['admin'].get('/api/v1/users').status_code==200
    for role in ['researcher','caregiver','guest']:
        assert clients[role].get('/api/v1/users').status_code==403
    assert TestClient(app).get('/api/v1/profiles').status_code==401
    assert clients['caregiver'].post('/api/v1/subjects',json={'name':'denied'}).status_code==403
    assert clients['guest'].post('/api/v1/subjects',json={'name':'private','is_demo':False}).status_code==403
    assert clients['guest'].post('/api/v1/subjects/x/calibrate-upload',files={'file':('test.npz',b'x')}).status_code==403
    assert 'real' not in clients['guest'].get('/api/v1/operations').json()
    assert 'real' in clients['admin'].get('/api/v1/operations').json()


def release_eog_confirmation(client,session):
    replay=runtime.live[session['id']]
    data=None
    for sample in (1750,2000):
        replay.accumulated=sample/250+.001
        replay.started=time.monotonic()
        replay.samples_due=lambda: sample
        try:
            while replay.cursor < sample:
                response=client.get(f"/api/v1/sessions/{session['id']}/tick")
                assert response.status_code==200,response.text
            data=response.json()
        finally:
            del replay.samples_due
    return data


def test_real_closed_loop_profile_reload_and_offline(clients):
    client=clients['guest']
    subject,profile,experiment,session=setup_demo(client)
    assert profile['calibration_sample_count']==40
    assert profile['validation_metric'] is None
    assert profile['source']['classifier_retrained'] is False
    assert clients['researcher'].post('/api/v1/sessions',json={'profile_id':profile['id'],'experiment_id':experiment['id']}).status_code==404
    # Creating a second session reads the saved file; no recalibration.
    old_reference=runtime.live[session['id']].reference.copy()
    post(client,f"/sessions/{session['id']}/control",{'action':'close'})
    session=post(client,'/sessions',{'profile_id':profile['id'],'experiment_id':experiment['id']})
    assert np.array_equal(runtime.live[session['id']].reference,old_reference)
    post(client,f"/sessions/{session['id']}/control",{'action':'play'})
    assert client.get(f"/api/v1/sessions/{session['id']}/tick").json()['last']=={}
    for i in range(3):
        data=complete_window(client,session,i)
        assert data['last']['window']==i
        assert len(data['samples'][0])<=501
        assert sum(data['last']['probabilities'])==pytest.approx(1)
        assert data['last']['end_to_end_processing_ms']>0
    assert data['last']['prediction']==1
    assert data['last']['reason']=='WAIT_EOG_CONFIRM'
    response=release_eog_confirmation(client,session)
    assert response['last']['decision']=='RIGHT'
    assert response['eog']['event']=='CONFIRM'
    assert response['eog']['mode']=='REAL_MODEL'
    commands=client.get('/api/v1/operations').json()['commands']
    assert any(c['data']['execution_status']=='ACK' and c['data']['source']=='EEG+REAL_EOG' for c in commands)
    device=data['devices'][0]
    post(client,f"/sessions/{session['id']}/devices/{device['id']}",{'scenario':'OFFLINE'})
    response=complete_window(client,session,3)
    assert response['last']['decision']=='STOP'
    assert response['last']['reason']=='DEVICE_OFFLINE'
    operations=client.get('/api/v1/operations').json()
    offline_alert=next(a for a in operations['alerts'] if a['kind']=='DEVICE_OFFLINE')
    assert offline_alert['acknowledged_at'] is None
    response=clients['caregiver'].post(f"/api/v1/alerts/{offline_alert['id']}/ack",json={'result':'已处理','notes':'评委演示确认'})
    assert response.status_code==200,response.text
    acknowledged=response.json()
    assert acknowledged['acknowledged_at'] and acknowledged['acknowledged_by']
    assert acknowledged['resolution']=='已处理：评委演示确认'
    assert acknowledged['response_time_seconds']>=0
    updated=client.get('/api/v1/operations').json()
    row=next(a for a in updated['alerts'] if a['id']==offline_alert['id'])
    assert row['acknowledged_by_username'].startswith('test_caregiver_')
    assert updated['alert_response']['acknowledged']>=1
    assert clients['caregiver'].post(f"/api/v1/alerts/{offline_alert['id']}/ack",json={'result':'已处理'}).status_code==409
    assert any(a['action']=='safety_decision' for a in operations['audit_logs'])
    assert any(c['data']['execution_status']=='ACK' for c in operations['commands'])
    emergency=post(client,f"/sessions/{session['id']}/emergency-stop")
    assert emergency['decision']['reason']=='EMERGENCY_LATCHED'
    assert client.post(f"/api/v1/sessions/{session['id']}/control",json={'action':'play'}).status_code==409
    post(client,f"/sessions/{session['id']}/control",{'action':'reset'})
    assert runtime.live[session['id']].controller.emergency is False


def test_reset_reloads_saved_safety_configuration(clients):
    admin, guest = clients['admin'], clients['guest']
    original = admin.get('/api/v1/configuration').json()['safety']
    target = {'threshold': .83, 'stable_required': 4}
    try:
        assert admin.put('/api/v1/configuration', json=target).status_code == 200
        _, _, _, session = setup_demo(guest)
        controller = runtime.live[session['id']].controller
        assert (controller.threshold, controller.stable_required) == (.83, 4)
        post(guest, f"/sessions/{session['id']}/emergency-stop")
        post(guest, f"/sessions/{session['id']}/control", {'action':'reset'})
        controller = runtime.live[session['id']].controller
        assert (controller.threshold, controller.stable_required) == (.83, 4)
        assert controller.emergency is False
    finally:
        admin.put('/api/v1/configuration', json=original)


@pytest.mark.parametrize('scenario,expected',[('DELAY','ACK'),('DROP','TIMEOUT'),('TIMEOUT','TIMEOUT'),('FAILURE','FAILED')])
def test_gateway_scenarios(clients,scenario,expected):
    client=clients['guest']
    _,_,_,session=setup_demo(client)
    post(client,f"/sessions/{session['id']}/control",{'action':'play'})
    for i in range(3):
        data=complete_window(client,session,i)
    device=data['devices'][0]
    post(client,f"/sessions/{session['id']}/devices/{device['id']}",{'scenario':scenario})
    release_eog_confirmation(client,session)
    commands=client.get('/api/v1/operations').json()['commands']
    response={'command':next(c for c in commands if c['data'].get('confirmation')=='CONFIRM')}
    replay=runtime.live[session['id']]
    for key,(start,delay,timeout) in list(replay.pending.items()):
        replay.pending[key]=(start-3,delay,timeout)
    with Session() as db:
        runtime.advance_devices(db,replay);db.commit()
        command=db.get(Command,response['command']['id'])
        assert command.data['execution_status']==expected
        if expected=='ACK':
            replay.motion_deadline=time.monotonic()-1
            runtime.advance_devices(db,replay);db.commit()
        assert db.get(Device,device['id']).data['action']=='STOP'


def test_calibration_evaluation_leak_rejected(clients):
    client=clients['researcher']
    subject=post(client,'/subjects',{'name':'Private study','is_demo':False})
    # Same genuine EEG in both sets is rejected, regardless of filename.
    from app.platform.routes import demo
    x,_=demo('calibration'); buf=io.BytesIO();np.savez_compressed(buf,X=x)
    profile=client.post(f"/api/v1/subjects/{subject['id']}/calibrate-upload",files={'file':('a.npz',buf.getvalue())}).json()
    exp=client.post(f"/api/v1/subjects/{subject['id']}/experiments/upload",files={'file':('b.npz',buf.getvalue())}).json()
    assert client.post('/api/v1/sessions',json={'profile_id':profile['id'],'experiment_id':exp['id']}).status_code==422
    assert all(s['id']!=subject['id'] for s in clients['guest'].get('/api/v1/subjects').json())


def test_ea_single_window_batch_invariance():
    from app.platform.routes import demo
    calibration,_=demo('calibration');evaluation,_=demo('evaluation')
    reference=calibrate(calibration)
    batch,_=predict(evaluation,reference)
    single,_=predict(evaluation[1:2],reference)
    assert np.allclose(single,batch[1:2],atol=1e-12)
    assert np.isfinite(reference).all()


def test_integration_pipeline_parity():
    from algorithms.system_integration.core import EEGClassifier
    from app.platform.routes import demo
    x,_=demo('calibration')
    actual,_=predict(x,calibrate(x))
    assert np.allclose(actual,EEGClassifier(n_channels=3).predict_proba(x),atol=1e-10)


def test_personalized_classifier_saved_and_reloaded(clients):
    from app.platform.routes import demo
    from pathlib import Path
    # Genuine S3 labels; this is persistence/parity verification, not independent scoring.
    with np.load(Path(__file__).resolve().parents[2]/'algorithms/bci_4class/data/S3_3ch.npz') as data:
        x,y=data['X'],data['y']
        if y.min()==1:y=y-1
        chosen=np.concatenate([np.flatnonzero(y==c)[:10] for c in range(4)])
        buf=io.BytesIO();np.savez_compressed(buf,X=x[chosen],y=y[chosen])
    client=clients['researcher']
    subject=post(client,'/subjects',{'name':'Personal training','is_demo':False})
    response=client.post(f"/api/v1/subjects/{subject['id']}/calibrate-upload",files={'file':('calibration.npz',buf.getvalue())})
    assert response.status_code==200,response.text
    profile=response.json()
    assert profile['source']['classifier_retrained'] is True
    evaluation,_=demo('evaluation');buf=io.BytesIO();np.savez_compressed(buf,X=evaluation)
    exp=client.post(f"/api/v1/subjects/{subject['id']}/experiments/upload",files={'file':('evaluation.npz',buf.getvalue())}).json()
    body={'profile_id':profile['id'],'experiment_id':exp['id']}
    a=post(client,'/sessions',body);model=runtime.live[a['id']].personalized
    expected=model.predict_proba(evaluation)
    b=post(client,'/sessions',body);replay=runtime.live[b['id']]
    actual,_=predict(evaluation,replay.reference,replay.personalized)
    assert np.allclose(actual,expected,atol=1e-10)


def test_real_eog_model_and_peak_deduplication():
    from app.platform.eog import analyze_batch,RealEOGProvider
    from app.core.config import get_settings
    with np.load(get_settings().demo_data_dir/'eog_demo.npz') as data:
        results=analyze_batch(data['X'][6:8],prefiltered=True)
    assert all(r['blink'] and r['sklearn_version']=='1.9.1' for r in results)
    provider=RealEOGProvider();provider.reset_candidate(1)
    assert provider.consume(results[0],1500,7)=='NO_SIGNAL'
    assert provider.consume(results[0],1500,7)=='NO_SIGNAL'
    assert provider.consume(results[1],1750,8)=='CONFIRM'
    with pytest.raises(ValueError):analyze_batch(np.zeros((1,250)))


def test_eog_emergency_rule_and_filtered_boundary():
    from app.platform.eog import RealEOGProvider
    provider=RealEOGProvider()
    result={'peak_index':0,'blink':False,'mean_uv':30,'prefiltered':False}
    assert provider.consume(result,0,1)=='NO_SIGNAL'
    assert provider.consume(result,375,2.5)=='EMERGENCY'
    result['prefiltered']=True
    assert provider.consume(result,750,4)=='NO_SIGNAL'


@pytest.mark.parametrize('prediction,confidence,event,state,age,reason',[
    (0,.4,'CONFIRM','ONLINE',0,'LOW_CONFIDENCE'),
    (0,.9,'NO_SIGNAL','ONLINE',0,'WAIT_EOG_CONFIRM'),
    (0,.9,'CONFIRM','OFFLINE',0,'DEVICE_OFFLINE'),
    (0,.9,'CONFIRM','BUSY',0,'DEVICE_BUSY'),
    (0,.9,'CONFIRM','ONLINE',6,'PREDICTION_TIMEOUT'),
    (0,.9,'CANCEL','ONLINE',0,'CANCELLED'),
    (0,.9,'EMERGENCY','OFFLINE',6,'EMERGENCY_LATCHED'),
])
def test_safety_fail_closed(prediction,confidence,event,state,age,reason):
    controller=SafetyController(count=2)
    action,actual=controller.decide(prediction,confidence,event,state,age)
    assert (action,actual)==('STOP',reason)


def test_stability_and_revoke(clients):
    c=SafetyController()
    c.observe(0,.8);assert c.decide(0,.8,'CONFIRM','ONLINE',0)[1]=='UNSTABLE'
    c.observe(1,.8);assert c.count==1
    c.observe(1,.8);assert c.decide(1,.8,'CONFIRM','ONLINE',0)[0]=='RIGHT'
    c.observe(1,.1);assert c.count==0
    client=clients['guest'];_,profile,_,session=setup_demo(client)
    assert client.delete('/api/v1/profiles/'+profile['id']).status_code==200
    assert client.get(f"/api/v1/sessions/{session['id']}/tick").status_code==409

def test_configuration_permissions_and_model_evaluation(clients):
    admin=clients['admin'];researcher=clients['researcher']
    assert clients['guest'].get('/api/v1/configuration').status_code==403
    assert researcher.put('/api/v1/configuration',json={'threshold':.6,'stable_required':2}).status_code==403
    assert admin.put('/api/v1/configuration',json={'threshold':.2,'stable_required':1}).status_code==422
    assert admin.put('/api/v1/configuration',json={'threshold':.55,'stable_required':2}).status_code==200
    assert len(admin.get('/api/v1/configuration').json()['model_checksums'])==2
    subject=post(researcher,'/subjects',{'name':'Evaluation study','is_demo':False})
    from app.platform.routes import demo
    c,_=demo('calibration');x,_=demo('evaluation')
    buffer=io.BytesIO();np.savez_compressed(buffer,X=c)
    profile=researcher.post(f"/api/v1/subjects/{subject['id']}/calibrate-upload",files={'file':('c.npz',buffer.getvalue())}).json()
    # Synthetic labels exist ONLY in this test fixture to verify metric arithmetic, never in Demo data.
    y=np.arange(len(x))%4;buffer=io.BytesIO();np.savez_compressed(buffer,X=x,y=y)
    experiment=researcher.post(f"/api/v1/subjects/{subject['id']}/experiments/upload",files={'file':('e.npz',buffer.getvalue())}).json()
    response=post(researcher,f"/experiments/{experiment['id']}/evaluate",{'profile_id':profile['id']})
    p,_=predict(x,calibrate(c))
    assert response['accuracy']==pytest.approx(float(np.mean(p.argmax(1)==y)))
    assert response['independent_validation'] is False


def test_artifact_tamper_and_zero_signal(clients):
    client=clients['researcher'];subject,profile,exp,session=setup_demo(client)
    from app.platform.routes import artifact_path
    path=artifact_path(profile['artifact_path']);original=path.read_bytes()
    try:
        path.write_bytes(b'tampered')
        assert client.post('/api/v1/sessions',json={'profile_id':profile['id'],'experiment_id':exp['id']}).status_code==409
    finally:
        path.write_bytes(original)
    with pytest.raises(ValueError):
        calibrate(np.zeros((4,3,501)))
    # Private EEG cannot be uploaded into public Demo subjects visible to caregivers.
    buffer=io.BytesIO();np.savez_compressed(buffer,X=np.ones((3,3,501)))
    assert client.post(f"/api/v1/subjects/{subject['id']}/calibrate-upload",files={'file':('x.npz',buffer.getvalue())}).status_code==422


def test_watchdog_client_disconnect_and_csrf(clients):
    import asyncio
    client=clients['guest'];_,_,_,session=setup_demo(client)
    post(client,f"/sessions/{session['id']}/control",{'action':'play'})
    replay=runtime.live[session['id']];replay.last_poll=time.monotonic()-10
    async def check():
        task=asyncio.create_task(runtime.watchdog())
        await asyncio.sleep(.3);task.cancel()
        try:await task
        except asyncio.CancelledError:pass
    asyncio.run(check())
    assert replay.running is False
    assert any(a['kind']=='CLIENT_TIMEOUT' for a in client.get('/api/v1/operations').json()['alerts'])
    assert client.post('/api/v1/auth/logout',headers={'Origin':'https://untrusted.example'}).status_code==403


def test_session_stream_pushes_ticks_without_http_polling(clients):
    client=clients['guest'];_,_,_,session=setup_demo(client)
    with client.websocket_connect(
        f"/api/v1/sessions/{session['id']}/stream",
        headers={'Origin':'http://localhost:3000'},
    ) as socket:
        frame=socket.receive_json()
        assert frame['id']==session['id']
        assert 'cursor' in frame and 'last' in frame


def test_model_inference_runs_off_event_loop(clients,monkeypatch):
    import app.platform.runtime as replay_runtime
    client=clients['guest'];_,_,_,session=setup_demo(client)
    replay=runtime.live[session['id']]
    replay.running=True;replay.started=time.monotonic()-3
    replay.eog_data=None
    replay.samples_due=lambda:501
    entered=threading.Event();release=threading.Event()
    original=replay_runtime.predict
    def slow_prediction(*args):
        entered.set()
        if not release.wait(3):raise TimeoutError('test release was not set')
        return original(*args)
    monkeypatch.setattr(replay_runtime,'predict',slow_prediction)

    async def exercise():
        with Session() as db:
            task=asyncio.create_task(replay_runtime.tick(db,replay))
            assert await asyncio.to_thread(entered.wait,2)
            await asyncio.wait_for(asyncio.sleep(.05),.2)
            assert not task.done()
            release.set()
            await asyncio.wait_for(task,5)
    try:asyncio.run(exercise())
    finally:
        release.set()
        if hasattr(replay,'samples_due'):del replay.samples_due
