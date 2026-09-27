"""Persist alert response ownership and outcome."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('alerts')}
    for name, length in [('acknowledged_at', 40), ('acknowledged_by', 32), ('resolution', 1000)]:
        if name not in columns:
            op.add_column('alerts', sa.Column(name, sa.String(length=length), nullable=True))


def downgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('alerts')}
    for name in ('resolution', 'acknowledged_by', 'acknowledged_at'):
        if name in columns:
            op.drop_column('alerts', name)
