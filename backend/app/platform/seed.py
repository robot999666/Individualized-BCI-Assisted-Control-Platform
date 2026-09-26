"""Provision accounts using an environment-supplied password; never print it."""
import os
from sqlalchemy import select
from app.platform.database import Session, User, Role, UserRole
from app.platform.security import hasher


def main():
    with Session() as db:
        for role in ['admin','researcher','caregiver','guest']:
            if not db.get(Role, role):
                db.add(Role(name=role))
        db.flush()
        for role in ['admin','researcher','caregiver','guest']:
            password = os.environ.get('BCI_' + role.upper() + '_PASSWORD')
            if not password or len(password) < 12:
                raise ValueError('Each BCI_<ROLE>_PASSWORD must be set with >=12 characters')
            username = 'demo_' + role
            if not db.scalar(select(User).where(User.username == username)):
                user = User(username=username, password_hash=hasher.hash(password))
                db.add(user)
                db.flush()
                db.add(UserRole(user_id=user.id, role=role))
        db.commit()
    print('Four accounts provisioned; existing passwords preserved.')

if __name__ == '__main__':
    main()
