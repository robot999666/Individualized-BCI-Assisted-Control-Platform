"""Verify a deployed release over HTTP using private account credentials.

Never prints passwords, cookies, raw EEG/EOG, or full API bodies.
Run locally on the server with root's private accounts file.
"""
import argparse
import http.cookiejar
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


parser = argparse.ArgumentParser()
parser.add_argument('--base', default='http://127.0.0.1')
parser.add_argument('--accounts', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--reload-profile', type=Path)
args = parser.parse_args()
accounts = json.loads(args.accounts.read_text())


class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, body=None, expected=200):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(args.base+'/api/v1'+path, data=data,
            headers={'Content-Type':'application/json','X-BCI-Request':'1'})
        try:
            response = self.opener.open(request, timeout=45)
        except urllib.error.HTTPError as exc:
            assert exc.code == expected, f'{path}: status {exc.code}, expected {expected}'
            return None
        assert response.status == expected, f'{path}: status {response.status}'
        return json.load(response)


clients = {}
for role, credentials in accounts.items():
    client = Client()
    result = client.request('/auth/login', credentials)
    assert result['role'] == role
    client.request('/users', expected=200 if role=='admin' else 403)
    clients[role] = client
guest=clients['guest']
health=guest.request('/health')
assert health['status']=='ok' and health['database_engine']=='mysql'
assert health['eog']['status']=='ok' and health['eog']['mode']=='REAL_MODEL'
report={'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'health':health,
        'roles_verified':list(clients),'eog_mode':'REAL_MODEL','device_mode':'SIMULATED'}
if args.reload_profile:
    previous=json.loads(args.reload_profile.read_text())
    profile_id,experiment_id=previous['profile_id'],previous['experiment_id']
    profiles=guest.request('/profiles')
    assert any(p['id']==profile_id and p['status']=='READY' for p in profiles)
    session=guest.request('/sessions',{'profile_id':profile_id,'experiment_id':experiment_id})
    guest.request(f"/sessions/{session['id']}/control",{'action':'close'})
    report.update({'persisted_profile_reloaded':True,'profile_id':profile_id,'experiment_id':experiment_id})
else:
    subject=guest.request('/subjects',{'name':'Production real-model acceptance','is_demo':True})
    profile=guest.request(f"/subjects/{subject['id']}/calibrate-demo",{})
    experiment=guest.request(f"/subjects/{subject['id']}/experiments/demo",{})
    profile_id,experiment_id=profile['id'],experiment['id']
    session=guest.request('/sessions',{'profile_id':profile_id,'experiment_id':experiment_id})
    sid=session['id'];guest.request(f'/sessions/{sid}/control',{'action':'play'})
    deadline=time.monotonic()+18;confirmed=False;seen=[]
    while time.monotonic()<deadline:
        data=guest.request(f'/sessions/{sid}/tick')
        if data['last'] and (not seen or seen[-1]['window']!=data['last'].get('window')):
            seen.append(data['last'])
        if data['eog'].get('event')=='CONFIRM':
            assert data['last']['decision']=='RIGHT' and data['last']['reason']=='ACCEPTED'
            confirmed=True;break
        time.sleep(.08)
    assert confirmed,'Real EOG confirmation was not observed'
    ops=guest.request('/operations')
    assert any(c['data'].get('session_id')==sid and c['data']['source']=='EEG+REAL_EOG'
               and c['data']['execution_status']=='ACK' for c in ops['commands'])
    device=data['devices'][0]
    guest.request(f"/sessions/{sid}/devices/{device['id']}",{'scenario':'OFFLINE'})
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        data=guest.request(f'/sessions/{sid}/tick')
        if data['last'].get('reason')=='DEVICE_OFFLINE':break
        time.sleep(.08)
    assert data['last']['reason']=='DEVICE_OFFLINE'
    guest.request(f'/sessions/{sid}/control',{'action':'pause'})
    ops=guest.request('/operations')
    alert=next(a for a in ops['alerts'] if a['kind']=='DEVICE_OFFLINE' and a['session_id']==sid)
    clients['caregiver'].request(f"/alerts/{alert['id']}/ack",{})
    assert any(a['action']=='safety_decision' for a in ops['audit_logs'])
    assert 'real' not in ops and 'real' in clients['admin'].request('/operations')
    guest.request('/configuration', expected=403)
    emergency=guest.request(f'/sessions/{sid}/emergency-stop',{})
    assert emergency['decision']['reason']=='EMERGENCY_LATCHED'
    guest.request(f'/sessions/{sid}/control',{'action':'play'},expected=409)
    report.update({'profile_id':profile_id,'experiment_id':experiment_id,
        'session_id':sid,'calibration_trials':profile['calibration_sample_count'],
        'profile_kind':profile['source']['artifact_kind'],'real_predictions':seen,
        'real_eog_confirmation':True,'simulated_ack':True,'offline_rejected':True,
        'alert_acknowledged':True,'audit_verified':True,'emergency_latched':True})
args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps({k:v for k,v in report.items() if k not in {'health','real_predictions','profile_id','experiment_id','session_id'}},ensure_ascii=False))
