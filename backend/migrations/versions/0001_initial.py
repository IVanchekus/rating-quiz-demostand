"""Initial nine-table game schema.

Revision ID: 0001
"""
from alembic import op
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, Enum, ForeignKey, Index, Integer, MetaData, SmallInteger, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy import DateTime

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def schema():
    # Frozen schema: future model edits must never change an already released migration.
    m = MetaData()
    key = BigInteger().with_variant(BIGINT(unsigned=True), "mysql").with_variant(Integer, "sqlite")
    date = DateTime().with_variant(DATETIME(fsp=3), "mysql")

    def table(name, *columns):
        return Table(name, m, Column("id", key, primary_key=True, autoincrement=True), *columns,
                     mysql_engine="InnoDB", mysql_charset="utf8mb4")

    def times():
        return [Column("created_at", date, nullable=False), Column("updated_at", date, nullable=False)]

    def fk(name, target):
        return Column(name, key, ForeignKey(target), nullable=False)

    table("users", Column("telegram_id", BigInteger, nullable=False, unique=True), Column("username", String(32)),
          Column("first_name", String(255), nullable=False), Column("last_name", String(255)), *times())
    table("rooms", Column("title", String(255), nullable=False), Column("join_code", String(64), nullable=False, unique=True),
          Column("status", Enum("draft", "active", "finished", "cancelled", name="room_status"), nullable=False),
          Column("starts_at", date), Column("ends_at", date),
          *[Column(n, t, nullable=False) for n, t in [("duration_minutes", Integer), ("questions_count", SmallInteger),
            ("question_time_limit_seconds", Integer), ("max_points_per_question", SmallInteger), ("min_correct_points", SmallInteger)]],
          *times(), CheckConstraint("questions_count > 0 AND duration_minutes > 0 AND question_time_limit_seconds > 0"),
          CheckConstraint("min_correct_points >= 0 AND max_points_per_question >= min_correct_points"))
    table("categories", Column("name", String(100), nullable=False), Column("slug", String(100), unique=True, nullable=False),
          Column("description", Text), Column("is_active", Boolean, nullable=False), *times())
    table("questions", fk("category_id", "categories.id"), Column("text", Text, nullable=False), Column("explanation", Text, nullable=False),
          Column("company", Enum("svyazkom", "sensory_hub", "systematics", "galaxy", name="company")),
          Column("difficulty", SmallInteger, nullable=False), Column("time_limit_seconds", Integer), Column("is_active", Boolean, nullable=False),
          *times(), CheckConstraint("difficulty BETWEEN 1 AND 5"), CheckConstraint("length(trim(explanation)) > 0"),
          Index("ix_questions_category_active", "category_id", "is_active"))
    table("question_options", fk("question_id", "questions.id"), Column("text", Text, nullable=False),
          Column("is_correct", Boolean, nullable=False), Column("sort_order", SmallInteger, nullable=False),
          UniqueConstraint("question_id", "sort_order"), Index("ix_question_options_question_id", "question_id"))
    table("room_questions", fk("room_id", "rooms.id"), fk("question_id", "questions.id"), Column("created_at", date, nullable=False),
          UniqueConstraint("room_id", "question_id"))
    table("participants", fk("room_id", "rooms.id"), fk("user_id", "users.id"),
          Column("status", Enum("playing", "completed", "expired", name="participant_status"), nullable=False),
          Column("total_score", Integer, nullable=False), Column("current_question_number", SmallInteger, nullable=False),
          Column("joined_at", date, nullable=False), Column("completed_at", date), Column("final_notified_at", date),
          UniqueConstraint("room_id", "user_id"), Index("ix_participants_room_score", "room_id", "total_score"))
    table("participant_questions", fk("participant_id", "participants.id"), fk("question_id", "questions.id"),
          Column("position", SmallInteger, nullable=False),
          Column("status", Enum("pending", "active", "answered", "expired", name="assignment_status"), nullable=False),
          Column("sent_at", date), Column("expires_at", date), Column("telegram_message_id", BigInteger), Column("completed_at", date),
          Column("delivery_token", String(64)), Column("delivery_lease_until", date), Column("result_notified_at", date),
          UniqueConstraint("participant_id", "position"), UniqueConstraint("participant_id", "question_id"),
          Index("ix_assignment_expiration", "status", "expires_at"))
    table("answers", fk("participant_question_id", "participant_questions.id"), fk("selected_option_id", "question_options.id"),
          Column("is_correct", Boolean, nullable=False), Column("response_time_ms", Integer, nullable=False),
          Column("points_awarded", SmallInteger, nullable=False), Column("answered_at", date, nullable=False),
          UniqueConstraint("participant_question_id"))
    return m


def upgrade():
    schema().create_all(bind=op.get_bind())


def downgrade():
    schema().drop_all(bind=op.get_bind())
