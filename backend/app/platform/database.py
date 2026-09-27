from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, JSON, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

Base = declarative_base()


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid4().hex


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True, default=uid)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(String(40), default=now)


class Role(Base):
    __tablename__ = "roles"
    name = Column(String(24), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id = Column(String(32), ForeignKey("users.id"), primary_key=True)
    role = Column(String(24), ForeignKey("roles.name"), nullable=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    expires = Column(Float, nullable=False)
    last_seen = Column(Float, nullable=False)


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(String(32), primary_key=True, default=uid)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    name = Column(String(80), nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(String(40), default=now)


class Profile(Base):
    __tablename__ = "calibration_profiles"
    id = Column(String(32), primary_key=True, default=uid)
    user_id = Column(String(32), ForeignKey("subjects.id"), nullable=False)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    model_version = Column(String(64), nullable=False)
    channel_layout = Column(JSON, nullable=False)
    calibration_sample_count = Column(Integer, nullable=False)
    artifact_path = Column(String(255), nullable=False)
    artifact_sha256 = Column(String(64), nullable=False)
    source = Column(JSON, nullable=False)
    validation_metric = Column(JSON, nullable=True)
    created_at = Column(String(40), default=now)
    status = Column(String(24), default="READY")


class Experiment(Base):
    __tablename__ = "experiments"
    id = Column(String(32), primary_key=True, default=uid)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    subject_id = Column(String(32), ForeignKey("subjects.id"), nullable=False)
    source = Column(JSON, nullable=False)
    artifact_path = Column(String(255), nullable=False)
    created_at = Column(String(40), default=now)


class InferenceSession(Base):
    __tablename__ = "inference_sessions"
    id = Column(String(32), primary_key=True, default=uid)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    profile_id = Column(String(32), ForeignKey("calibration_profiles.id"), nullable=False)
    experiment_id = Column(String(32), ForeignKey("experiments.id"), nullable=False)
    status = Column(String(24), default="PAUSED")
    created_at = Column(String(40), default=now)


class InferenceRecord(Base):
    __tablename__ = "inference_records"
    id = Column(String(32), primary_key=True, default=uid)
    session_id = Column(String(32), ForeignKey("inference_sessions.id"), nullable=False)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(String(40), default=now)


class Device(Base):
    __tablename__ = "devices"
    id = Column(String(32), primary_key=True, default=uid)
    session_id = Column(String(32), ForeignKey("inference_sessions.id"), nullable=False)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    kind = Column(String(32), nullable=False)
    state = Column(String(16), default="ONLINE")
    scenario = Column(String(24), default="ACK")
    data = Column(JSON, default=dict)


class Command(Base):
    __tablename__ = "device_commands"
    id = Column(String(32), primary_key=True, default=uid)
    device_id = Column(String(32), ForeignKey("devices.id"), nullable=False)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(String(40), default=now)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(String(32), primary_key=True, default=uid)
    owner_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    session_id = Column(String(32), ForeignKey("inference_sessions.id"), nullable=False)
    kind = Column(String(48), nullable=False)
    status = Column(String(24), default="OPEN")
    created_at = Column(String(40), default=now)
    acknowledged_at = Column(String(40), nullable=True)
    acknowledged_by = Column(String(32), ForeignKey("users.id"), nullable=True)
    resolution = Column(String(1000), nullable=True)


class Audit(Base):
    __tablename__ = "audit_logs"
    id = Column(String(32), primary_key=True, default=uid)
    owner_id = Column(String(32), nullable=True, index=True)
    action = Column(String(80), nullable=False)
    detail = Column(JSON, default=dict)
    created_at = Column(String(40), default=now)


class SystemConfig(Base):
    __tablename__ = "system_configuration"
    key = Column(String(40), primary_key=True)
    value = Column(JSON, nullable=False)


settings = get_settings()
if settings.production and not settings.database_url.startswith("mysql+pymysql://"):
    raise RuntimeError("Production requires MySQL")
settings.artifact_dir.mkdir(parents=True, exist_ok=True)
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       **({"connect_args": {"check_same_thread": False}} if settings.database_url.startswith("sqlite") else {}))
Session = sessionmaker(engine, expire_on_commit=False)


def record_audit(db, actor, action, **detail):
    db.add(Audit(owner_id=actor, action=action, detail=detail))


def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != "password_hash"}
