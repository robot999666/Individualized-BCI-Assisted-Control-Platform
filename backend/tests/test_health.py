import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.platform.database import Role, Session, User, UserRole
from app.platform.security import hasher
from app.platform.routes import login_attempts


def test_health_live_is_public_and_detail_is_admin_only() -> None:
    name = 'health_admin_' + uuid.uuid4().hex[:10]
    with Session() as db:
        if not db.get(Role, 'admin'):
            db.add(Role(name='admin'))
        user = User(username=name, password_hash=hasher.hash('health-test-password'))
        db.add(user); db.flush(); db.add(UserRole(user_id=user.id, role='admin')); db.commit()

    with TestClient(app) as client:
        assert client.get('/api/v1/health/live').json() == {'status':'ok'}
        assert client.get('/api/v1/health/detail').status_code == 401
        login_attempts.clear()
        assert client.post('/api/v1/auth/login', json={
            'username':name, 'password':'health-test-password'
        }).status_code == 200
        response = client.get('/api/v1/health/detail')

    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['service'] == 'als-bci-4class'
    assert data['model_ready'] is True
    assert data['loaded_layouts'] == ['3ch', '22ch']
    assert set(data['model_checksums']) == {'3ch', '22ch'}
    assert data['model_error'] is None
    assert data['eog']['status'] == 'ok'
    assert data['eog']['mode'] == 'REAL_MODEL'


def test_root() -> None:
    response = TestClient(app).get('/')
    assert response.status_code == 200
    assert '/docs' in response.json()['docs']
