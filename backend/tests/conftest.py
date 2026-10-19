import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import make_engine
from app.models import Base, ParticipantQuestion, QuestionOption
from app.schemas import CategoryInput, QuestionInput, RoomInput, RoomQuestionsInput
from app.services.admin import AdminService
from app.services.game import GameService


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 19, 12)

    def __call__(self):
        return self.now

    def advance(self, seconds=0, milliseconds=0):
        self.now += timedelta(seconds=seconds, milliseconds=milliseconds)


@pytest.fixture
def env(tmp_path):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'game.db'}")
    if make_url(url).get_backend_name() == "mysql" and not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must use a dedicated database ending in _test")
    engine = make_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None, admin_secret="test-admin-secret-" + "x" * 40)
    clock = Clock()
    admin = AdminService(sessions, settings, clock)
    game = GameService(sessions, clock)
    category_id = admin.create_category(CategoryInput(name="Технологии", slug="technology"))
    questions = []
    for i in range(12):
        questions.append(admin.save_question(QuestionInput(
            category_id=category_id, text=f"Вопрос {i}?", explanation=f"Объяснение {i}.",
            options=[{"text": "Да", "is_correct": True}, {"text": "Нет", "is_correct": False}],
        )))
    room_id = admin.create_room(RoomInput(title="Тестовая комната"))
    admin.assign_questions(room_id, RoomQuestionsInput(question_ids=questions))
    admin.start_room(room_id)
    from app.models import Room
    with sessions() as session:
        code = session.get(Room, room_id).join_code
    result = dict(engine=engine, sessions=sessions, settings=settings, clock=clock, admin=admin, game=game,
                  room_id=room_id, code=code, questions=questions, category_id=category_id)
    yield result
    Base.metadata.drop_all(engine)
    engine.dispose()


def enroll(env, telegram_id=123, name="Иван", username=None):
    return env["game"].enroll(env["code"], telegram_id, name, username)


def activate(env, state, telegram_id=123):
    game = env["game"]
    token = game.reserve_delivery(telegram_id, state["assignment_id"])
    assert token
    assert game.confirm_delivery(telegram_id, state["assignment_id"], token, 77)
    return game.resume(telegram_id, state["participant_id"])


def option(env, state, correct=True):
    with env["sessions"]() as session:
        assignment = session.get(ParticipantQuestion, state["assignment_id"])
        return session.scalar(select(QuestionOption.id).where(
            QuestionOption.question_id == assignment.question_id, QuestionOption.is_correct.is_(correct),
        ))
