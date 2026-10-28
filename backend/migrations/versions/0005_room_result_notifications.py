"""Track delivery of final room rankings.

Revision ID: 0005
"""
from alembic import op
from sqlalchemy import Column, DateTime

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("participants", Column("room_result_notified_at", DateTime(), nullable=True))


def downgrade():
    op.drop_column("participants", "room_result_notified_at")
