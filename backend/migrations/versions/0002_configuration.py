"""Persist administrative safety configuration."""
from alembic import op
from app.platform.database import SystemConfig
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    SystemConfig.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():
    SystemConfig.__table__.drop(op.get_bind(),checkfirst=True)
