"""Give administrator-authorized replays an independent room-length deadline.

Revision ID: 0003
"""
from alembic import op
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.mysql import DATETIME

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("participants", Column(
        "deadline_at", DateTime().with_variant(DATETIME(fsp=3), "mysql"), nullable=True,
    ))


def downgrade():
    op.drop_column("participants", "deadline_at")
