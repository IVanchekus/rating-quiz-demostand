"""Allow one administrator-issued retry per participant.

Revision ID: 0002
"""
from alembic import op
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, inspect
from sqlalchemy.dialects.mysql import BIGINT, DATETIME

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _key():
    return BigInteger().with_variant(BIGINT(unsigned=True), "mysql").with_variant(Integer, "sqlite")


def upgrade():
    bind = op.get_bind()
    unique = next(item for item in inspect(bind).get_unique_constraints("participants")
                  if item["column_names"] == ["room_id", "user_id"])
    if bind.dialect.name == "sqlite" and unique["name"] is None:
        with op.batch_alter_table(
            "participants", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
        ) as batch:
            batch.drop_constraint("uq_participants_room_id", type_="unique")
            batch.create_index("ix_participants_room_user", ["room_id", "user_id"])
    else:
        op.drop_constraint(unique["name"], "participants", type_="unique")
        op.create_index("ix_participants_room_user", "participants", ["room_id", "user_id"])

    date = DateTime().with_variant(DATETIME(fsp=3), "mysql")
    op.create_table(
        "user_access_grants",
        Column("id", _key(), primary_key=True, autoincrement=True),
        Column("user_id", _key(), ForeignKey("users.id"), nullable=False),
        Column("granted_at", date, nullable=False),
        Column("used_at", date),
        Column("participant_id", _key(), ForeignKey("participants.id"), unique=True),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_user_access_grants_user_id", "user_access_grants", ["user_id"])


def downgrade():
    op.drop_index("ix_user_access_grants_user_id", table_name="user_access_grants")
    op.drop_table("user_access_grants")
    op.drop_index("ix_participants_room_user", table_name="participants")
    op.create_unique_constraint("room_id", "participants", ["room_id", "user_id"])
