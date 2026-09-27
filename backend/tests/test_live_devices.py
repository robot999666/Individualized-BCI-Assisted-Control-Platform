"""Real closed-loop ACK state consumed by the live scene; no browser animation timer."""
import pytest
from sqlalchemy import select

from backend.tests.test_platform import clients, post, setup_demo, complete_window, release_eog_confirmation
from app.platform.database import Session, Device
from app.platform.safety import SimulatorAdapter


def test_wheelchair_forward_follows_heading_and_stop_keeps_pose():
    simulator = SimulatorAdapter('wheelchair')
    state = simulator.execute('RIGHT', {})
    assert state['heading'] == 30
    state = simulator.execute('FORWARD', state)
    assert state['position_x'] == pytest.approx(.4)
    assert state['position_z'] == pytest.approx(-.8 * 3**.5 / 2)
    stopped = simulator.execute('STOP', state)
    assert stopped == {**state, 'action':'STOP'}
    state = simulator.execute('LEFT', stopped)
    state = simulator.execute('FORWARD', state)
    assert state['position_x'] == pytest.approx(.4)
    assert state['position_z'] == pytest.approx(stopped['position_z']-.8)


@pytest.mark.parametrize('kind,field,value', [('wheelchair','heading',30),('care_bed','angle',5),
                                            ('emergency_call','call','REQUESTED'),('smart_home','light',True)])
def test_four_devices_ack_from_real_eeg_eog_and_reset(clients, kind, field, value):
    client=clients['guest']
    _, _, _, session=setup_demo(client)
    base=f"/sessions/{session['id']}"
    tick=client.get('/api/v1'+base+'/tick').json()
    device=next(d for d in tick['devices'] if d['kind']==kind)
    post(client,base+f"/devices/{device['id']}",{'scenario':'ACK','select_device':True})
    post(client,base+'/control',{'action':'play'})
    for i in range(3):
        complete_window(client,session,i)
    result=release_eog_confirmation(client,session)
    d=next(d for d in result['devices'] if d['id']==device['id'])
    assert d['data'][field]==value
    assert d['data']['ack_action']=='RIGHT'
    assert d['data']['ack_latency_ms']>=0 and d['data']['ack_command_id']
    post(client,base+'/control',{'action':'pause'})
    paused=client.get('/api/v1'+base+'/tick').json()
    assert next(d for d in paused['devices'] if d['id']==device['id'])['data'][field]==value
    reset=post(client,base+'/control',{'action':'reset'})['snapshot']
    assert reset['cursor']==0 and not reset['running']
    d=next(d for d in reset['devices'] if d['id']==device['id'])
    assert d['data'][field] in (0,False,'IDLE')
    assert 'ack_command_id' not in d['data']


def test_reset_preserves_fault_scenario_and_cancels_pending(clients):
    client=clients['guest']
    _, _, _, session=setup_demo(client)
    base=f"/sessions/{session['id']}"
    with Session() as db:
        device=db.scalars(select(Device).where(Device.session_id==session['id'])).first()
        device.data={**device.data,'heading':90,'position_x':2,'position_z':-1,'angle':25}
        db.commit()
        device_id=device.id
    post(client,base+f'/devices/{device_id}',{'scenario':'OFFLINE','select_device':True})
    result=post(client,base+'/control',{'action':'reset'})['snapshot']
    device=next(d for d in result['devices'] if d['id']==device_id)
    assert device['state']=='OFFLINE' and device['scenario']=='OFFLINE'
    assert device['data']['position_x']==0 and device['data']['heading']==0
