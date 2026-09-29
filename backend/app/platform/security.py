import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from app.platform.database import LoginSession, Session, User, UserRole

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))


def verify(password, encoded):
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def current_user(request: Request):
    return user_from_token(request.cookies.get("bci_session", ""))


def user_from_token(token):
    if len(token) != 43 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in token):
        raise HTTPException(401, "请先登录")
    with Session() as db:
        login = db.get(LoginSession, digest(token))
        if not login or login.expires < time.time():
            raise HTTPException(401, "请先登录")
        user = db.get(User, login.user_id)
        if not user or not user.active:
            raise HTTPException(401, "账号不可用")
        role = db.scalar(select(UserRole.role).where(UserRole.user_id == user.id))
        if time.time()-login.last_seen >= 60:
            login.last_seen = time.time()
            db.commit()
        return {"id": user.id, "username": user.username, "role": role}


def require(*roles):
    def check(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "此角色无权执行该操作")
        return user
    return check
