"""Adversarial requests and resource bounds, alongside the existing real-model flows."""
import asyncio
import io
import threading
import time
import zipfile

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.resource_guard import RequestLimitsMiddleware, WindowLimiter, run_blocking
from app.main import app
from app.platform import routes, runtime
from app.platform.database import Session, InferenceSession, LoginSession
from app.services.array_uploads import read_numeric_npy, read_numeric_npz
from app.services.npz_reader import read_bci_npz
from backend.tests.test_platform import clients, post, setup_demo


def array_header(shape, dtype='<f8'):
    buffer = io.BytesIO()
    np.lib.format.write_array_header_1_0(buffer, {'descr': dtype, 'fortran_order': False, 'shape': shape})
    return buffer.getvalue()


def archive_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize('shape', [(2**40,3,501), (2**62,4), (2**62,2**62)])
def test_forged_array_shape_rejected_before_allocation(shape, monkeypatch):
    data=archive_bytes([('X.npy',array_header(shape))])
    def forbidden(*args, **kwargs):
        pytest.fail('np.load must not be called for a forged oversized header')
    monkeypatch.setattr(np,'load',forbidden)
    with pytest.raises(HTTPException) as error:
        read_numeric_npz(data,64*1024*1024)
    assert error.value.status_code==413
    with pytest.raises(HTTPException) as error:
        read_numeric_npy(array_header(shape),16384)
    assert error.value.status_code==413


@pytest.mark.parametrize('entries', [
    [('X.npy',array_header((2,3,501)))],
    [('X.npy',array_header((2,3,501))),('X.npy',array_header((2,3,501)))],
    [('../X.npy',b'x')], [('X.npy',b'x'),('metadata.npy',b'x')],
])
def test_truncated_duplicate_and_unexpected_archive_members(entries):
    with pytest.raises(HTTPException) as error:
        read_numeric_npz(archive_bytes(entries),64*1024*1024)
    assert error.value.status_code==422


def test_unsigned_labels_cannot_wrap_into_valid_labels():
    buffer=io.BytesIO()
    np.savez_compressed(buffer,X=np.ones((2,3,501)),y=np.array([2**64-1,0],dtype=np.uint64))
    with pytest.raises(HTTPException):
        read_bci_npz('valid.npz',buffer.getvalue(),250,'uV')


def test_corrupt_deflate_is_a_validation_error():
    buffer=io.BytesIO();np.save(buffer,np.ones((2,3,501)))
    content=bytearray(archive_bytes([('X.npy',buffer.getvalue())]))
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        member=archive.infolist()[0]
        start=member.header_offset+30+len(member.filename.encode())+len(member.extra)
    content[start]=(content[start]&~6)|6  # DEFLATE reserved block type.
    with pytest.raises(HTTPException) as error:
        read_numeric_npz(bytes(content),64*1024*1024)
    assert error.value.status_code==422


def test_production_csrf_header_and_cross_site_requests(clients,monkeypatch):
    guest=clients['guest']
    monkeypatch.setattr(routes.settings,'production',True)
    assert guest.post('/api/v1/auth/logout',json={}).status_code==403
    assert guest.post('/api/v1/auth/logout',json={},headers={'X-BCI-Request':'1','Origin':'https://evil.example'}).status_code==403
    assert guest.post('/api/v1/auth/logout',json={},headers={'X-BCI-Request':'1','Sec-Fetch-Site':'cross-site'}).status_code==403
    assert guest.get('/api/v1/auth/me').status_code==200


def test_limiter_does_not_reset_on_key_flood():
    limiter=WindowLimiter(2)
    assert limiter.allow('attacker',1)
    assert limiter.allow('other',1)
    assert not limiter.allow('third',1)
    assert not limiter.allow('attacker',1)
    assert len(limiter.entries)==2


async def raw_request(guard, chunks, headers=(), path='/test', method='POST'):
    scope={'type':'http','path':path,'method':method,'headers':list(headers),
           'query_string':b'', 'client':('local',1), 'http_version':'1.1'}
    messages=[]
    iterator=iter(chunks)
    async def receive():
        return next(iterator)
    async def send(message):
        messages.append(message)
    await guard(scope,receive,send)
    return next(message['status'] for message in messages if message['type']=='http.response.start')


def test_chunked_and_declared_oversize_are_rejected_before_parsing():
    called=[]
    async def target(scope,receive,send):
        called.append(True)
        await JSONResponse({})(scope,receive,send)
    guard=RequestLimitsMiddleware(target)
    async def exercise():
        assert await raw_request(guard,[{'type':'http.request','body':b'x'*9000,'more_body':True},
                                        {'type':'http.request','body':b'x'*9000}])==413
        assert await raw_request(guard,[],headers=[(b'content-length',b'2147483647')])==413
        assert await raw_request(guard,[],headers=[(b'content-length',b'-1')])==400
        assert await raw_request(guard,[],headers=[(b'content-length',b'0'),(b'content-length',b'1')])==400
        assert guard.active==0
    asyncio.run(exercise())
    assert called==[]


def test_slow_body_times_out_and_releases_slot():
    async def target(scope,receive,send):
        pytest.fail('Timed out body must not reach the application')
    guard=RequestLimitsMiddleware(target)
    guard.settings=Settings(_env_file=None,request_body_timeout_seconds=.02)
    async def exercise():
        messages=[]
        async def receive():
            await asyncio.sleep(.2)
        async def send(message):
            messages.append(message)
        await guard({'type':'http','path':'/test','method':'POST','headers':[],
                     'query_string':b'', 'client':('local',1)},receive,send)
        assert messages[0]['status']==408
        assert guard.active==0
    asyncio.run(exercise())


def test_bulk_saturation_keeps_stop_available():
    async def target(scope,receive,send):
        await JSONResponse({'ok':True})(scope,receive,send)
    guard=RequestLimitsMiddleware(target)
    guard.heavy=guard.settings.max_bulk_requests
    guard.active=guard.settings.max_active_requests
    async def exercise():
        assert await raw_request(guard,[],path='/api/v1/analyze')==503
        guard.active=guard.settings.max_active_requests
        assert await raw_request(guard,[{'type':'http.request','body':b''}],path='/api/v1/sessions/id/emergency-stop')==200
    asyncio.run(exercise())


def test_cancelling_cpu_work_keeps_admission_until_thread_finishes():
    entered=threading.Event(); release=threading.Event()
    def worker():
        entered.set(); release.wait(2)
    async def exercise():
        task=asyncio.create_task(run_blocking(worker))
        assert await asyncio.to_thread(entered.wait,1)
        task.cancel()
        await asyncio.sleep(.03)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    try:asyncio.run(exercise())
    finally:release.set()


@pytest.mark.parametrize('username',["' OR 1=1 --",'admin"; DROP TABLE users; --',"' UNION SELECT 1,2,3 --"])
def test_sql_payload_cannot_authenticate(clients,username):
    response=TestClient(app).post('/api/v1/auth/login',json={'username':username,'password':'incorrect'})
    assert response.status_code==401
    assert clients['admin'].get('/api/v1/users').status_code==200


def test_validation_never_echoes_passwords_or_oversized_input():
    secret='private-password-'*20
    response=TestClient(app).post('/api/v1/auth/login',json={'username':'x','password':secret})
    assert response.status_code==422
    assert secret not in response.text
    assert 'input' not in response.json()['detail'][0]
    assert response.headers['x-content-type-options']=='nosniff'
    assert TestClient(app).post('/api/v1/auth/login',content=b'x'*17000).status_code==413


def test_stored_input_is_literal_and_scoped_to_owner(clients):
    payload='<img src=x onerror=alert(1)>\' OR 1=1 --'
    created=post(clients['researcher'],'/subjects',{'name':payload,'is_demo':False})
    assert created['name']==payload
    assert all(subject['id']!=created['id'] for subject in clients['guest'].get('/api/v1/subjects').json())
    assert clients['guest'].post(f"/api/v1/subjects/{created['id']}/calibrate-demo").status_code==404
    assert clients['guest'].post('/api/v1/sessions',json={'profile_id':'x'*33,'experiment_id':'y'}).status_code==422


def test_deep_json_does_not_interrupt_other_sessions(clients):
    guest=clients['guest']; _,_,_,created=setup_demo(guest)
    post(guest,f"/sessions/{created['id']}/control",{'action':'play'})
    response=TestClient(app).post('/api/v1/auth/login',content=b'['*1500+b'0'+b']'*1500,
                                  headers={'Content-Type':'application/json'})
    assert response.status_code==422
    assert runtime.live[created['id']].running


def test_websocket_owner_origin_and_capacity(clients):
    guest=clients['guest']; _,_,_,created=setup_demo(guest)
    url=f"/api/v1/sessions/{created['id']}/stream"
    with pytest.raises(WebSocketDisconnect) as error:
        with clients['researcher'].websocket_connect(url,headers={'Origin':'http://localhost:3000'}):pass
    assert error.value.code==4404
    with pytest.raises(WebSocketDisconnect) as error:
        with guest.websocket_connect(url,headers={'Origin':'https://attacker.example'}):pass
    assert error.value.code==4403
    replay=runtime.live[created['id']]
    replay.streams=routes.settings.max_session_streams
    with pytest.raises(WebSocketDisconnect) as error:
        with guest.websocket_connect(url,headers={'Origin':'http://localhost:3000'}):pass
    assert error.value.code==4429
    assert replay.streams==routes.settings.max_session_streams


def test_memory_rejection_preserves_current_session(clients,monkeypatch):
    guest=clients['guest']; _,profile,experiment,created=setup_demo(guest)
    replay=runtime.live[created['id']]
    monkeypatch.setattr(routes.settings,'max_live_array_mb',0)
    response=guest.post('/api/v1/sessions',json={'profile_id':profile['id'],'experiment_id':experiment['id']})
    assert response.status_code==503
    assert runtime.live[created['id']] is replay
    assert guest.get(f"/api/v1/sessions/{created['id']}/tick").status_code==200


def test_shared_demo_account_browsers_do_not_replace_or_logout_each_other(clients):
    first=clients['guest']; _,profile,experiment,created=setup_demo(first)
    username=first.get('/api/v1/auth/me').json()['username']
    second=TestClient(app)
    login=second.post('/api/v1/auth/login',json={'username':username,'password':'test-only-'+username})
    assert login.status_code==200
    other=post(second,'/sessions',{'profile_id':profile['id'],'experiment_id':experiment['id']})
    assert created['id'] in runtime.live and other['id'] in runtime.live
    replacement=post(first,'/sessions',{'profile_id':profile['id'],'experiment_id':experiment['id']})
    assert created['id'] not in runtime.live
    assert replacement['id'] in runtime.live and other['id'] in runtime.live
    post(second,'/auth/logout')
    assert other['id'] not in runtime.live
    assert first.get(f"/api/v1/sessions/{replacement['id']}/tick").status_code==200


def test_watchdog_releases_idle_arrays_and_expired_tokens(clients):
    guest=clients['guest']; _,_,_,created=setup_demo(guest)
    runtime.live[created['id']].last_poll=time.monotonic()-routes.settings.idle_session_seconds-1
    with Session() as db:
        db.add(LoginSession(token_hash='expired-test',user_id=guest.get('/api/v1/auth/me').json()['id'],
                            expires=time.time()-1,last_seen=0));db.commit()
    async def exercise():
        task=asyncio.create_task(runtime.watchdog())
        await asyncio.sleep(.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(exercise())
    assert created['id'] not in runtime.live
    with Session() as db:
        assert db.get(InferenceSession,created['id']).status=='CLOSED'
        assert db.get(LoginSession,'expired-test') is None
