"""Persistent game state. MySQL uses InnoDB, unsigned keys and millisecond UTC dates."""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer,
    SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    # MySQL DATETIME has no timezone; the entire application uses naive UTC internally.
    return datetime.now(timezone.utc).replace(tzinfo=None)


ID = BigInteger().with_variant(BIGINT(unsigned=True), "mysql").with_variant(Integer, "sqlite")
DATE = DateTime().with_variant(DATETIME(fsp=3), "mysql")


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DATE, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DATE, default=utcnow, onupdate=utcnow)


class User(Timestamps, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))


class Room(Timestamps, Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    join_code: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(Enum("draft", "active", "finished", "cancelled", name="room_status"), default="draft")
    starts_at: Mapped[datetime | None] = mapped_column(DATE)
    ends_at: Mapped[datetime | None] = mapped_column(DATE)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    questions_count: Mapped[int] = mapped_column(SmallInteger, default=10)
    question_time_limit_seconds: Mapped[int] = mapped_column(Integer, default=30)
    max_points_per_question: Mapped[int] = mapped_column(SmallInteger, default=100)
    min_correct_points: Mapped[int] = mapped_column(SmallInteger, default=0)
    __table_args__ = (
        CheckConstraint("questions_count > 0 AND duration_minutes > 0 AND question_time_limit_seconds > 0"),
        CheckConstraint("min_correct_points >= 0 AND max_points_per_question >= min_correct_points"),
    )


class Category(Timestamps, Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Question(Timestamps, Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    text: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Enum("svyazkom", "sensory_hub", "systematics", "galaxy", name="company"))
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=1)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        Index("ix_questions_category_active", "category_id", "is_active"),
        CheckConstraint("difficulty BETWEEN 1 AND 5"),
        CheckConstraint("length(trim(explanation)) > 0"),
    )


class QuestionOption(Base):
    __tablename__ = "question_options"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    __table_args__ = (UniqueConstraint("question_id", "sort_order"),)


class RoomQuestion(Base):
    __tablename__ = "room_questions"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    created_at: Mapped[datetime] = mapped_column(DATE, default=utcnow)
    __table_args__ = (UniqueConstraint("room_id", "question_id"),)


class Participant(Base):
    __tablename__ = "participants"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(Enum("playing", "completed", "expired", name="participant_status"), default="playing")
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    current_question_number: Mapped[int] = mapped_column(SmallInteger, default=1)
    joined_at: Mapped[datetime] = mapped_column(DATE, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DATE)
    # Durable worker notification retry; no in-memory timer is authoritative.
    final_notified_at: Mapped[datetime | None] = mapped_column(DATE)
    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
        Index("ix_participants_room_score", "room_id", "total_score"),
    )


class ParticipantQuestion(Base):
    __tablename__ = "participant_questions"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(Enum("pending", "active", "answered", "expired", name="assignment_status"), default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DATE)
    expires_at: Mapped[datetime | None] = mapped_column(DATE)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    completed_at: Mapped[datetime | None] = mapped_column(DATE)
    delivery_token: Mapped[str | None] = mapped_column(String(64))
    delivery_lease_until: Mapped[datetime | None] = mapped_column(DATE)
    result_notified_at: Mapped[datetime | None] = mapped_column(DATE)
    __table_args__ = (
        UniqueConstraint("participant_id", "position"),
        UniqueConstraint("participant_id", "question_id"),
        Index("ix_assignment_expiration", "status", "expires_at"),
    )


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    participant_question_id: Mapped[int] = mapped_column(ForeignKey("participant_questions.id"), unique=True)
    selected_option_id: Mapped[int] = mapped_column(ForeignKey("question_options.id"))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    response_time_ms: Mapped[int] = mapped_column(Integer)
    points_awarded: Mapped[int] = mapped_column(SmallInteger)
    answered_at: Mapped[datetime] = mapped_column(DATE)


for table in Base.metadata.tables.values():
    table.dialect_options["mysql"]["engine"] = "InnoDB"
    table.dialect_options["mysql"]["charset"] = "utf8mb4"
