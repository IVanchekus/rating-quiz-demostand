"""Move answer grace period from questions to rooms.

Revision ID: 0006
"""
from alembic import op
from sqlalchemy import Column, Integer, text

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rooms", Column(
        "no_penalty_seconds", Integer(), nullable=False, server_default=text("0"),
    ))
    op.create_check_constraint(
        "ck_rooms_no_penalty_seconds", "rooms", "no_penalty_seconds BETWEEN 0 AND 3600",
    )
    op.drop_constraint("ck_questions_no_penalty_seconds", "questions", type_="check")
    op.drop_column("questions", "no_penalty_seconds")


def downgrade():
    op.add_column("questions", Column(
        "no_penalty_seconds", Integer(), nullable=False, server_default=text("0"),
    ))
    op.create_check_constraint(
        "ck_questions_no_penalty_seconds", "questions", "no_penalty_seconds BETWEEN 0 AND 3600",
    )
    op.drop_constraint("ck_rooms_no_penalty_seconds", "rooms", type_="check")
    op.drop_column("rooms", "no_penalty_seconds")
