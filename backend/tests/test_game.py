import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Answer, Participant, ParticipantQuestion, Room, RoomQuestion, User
from app.schemas import QuestionInput, RoomInput, RoomPatch, RoomQuestionsInput
from app.services.game import GameError, GameService
from app.services.leaderboard import LeaderboardService
from app.services.scoring import calculate_points
from conftest import activate, enroll, option


def test_duplicate_registration_keeps_assignment_and_progress(env):
    first = activate(env, enroll(env))
    env["game"].submit_answer(123, first["assignment_id"], option(env, first))
    again = enroll(env)
    assert again["assignment_id"] == first["assignment_id"]
    assert again["question_status"] == "answered"
    assert again["total_score"] == 100
    with env["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(Participant)) == 1
        rows = list(session.scalars(select(ParticipantQuestion)))
        assert len(rows) == len({r.question_id for r in rows}) == 10


def test_first_answer_wins(env):
    state = activate(env, enroll(env))
    wrong = option(env, state, False)
    good = option(env, state)
    first = env["game"].submit_answer(123, state["assignment_id"], wrong)
    second = env["game"].submit_answer(123, state["assignment_id"], good)
    assert first == second
    assert first["total_score"] == first["points"] == 0
    assert first["correct_option"] == "Да" and first["explanation"]
    assert "options" not in first
    with env["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(Answer)) == 1
        assert session.scalar(select(Answer.selected_option_id)) == wrong


def test_score_uses_server_time_and_persists_across_service_restart(env):
    state = activate(env, enroll(env))
    env["clock"].advance(seconds=6)
    result = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    assert result["points"] == result["total_score"] == 80
    restarted = GameService(env["sessions"], env["clock"])
    assert restarted.resume(123) == result


@pytest.mark.parametrize("seconds", [30, 31, 120])
def test_deadline_is_strict_and_does_not_need_worker(env, seconds):
    state = activate(env, enroll(env))
    env["clock"].advance(seconds=seconds)
    result = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    assert result["question_status"] == "expired"
    assert result["points"] == 0
    with env["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(Answer)) == 0


def test_next_double_click_does_not_skip_or_start_timer(env):
    state = activate(env, enroll(env))
    env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    env["clock"].advance(seconds=100)
    first = env["game"].next_question(123, state["assignment_id"])
    second = env["game"].next_question(123, state["assignment_id"])
    assert first == second
    assert first["position"] == 2 and first["question_status"] == "pending" and first["expires_at"] is None
    with env["sessions"]() as session:
        assert not session.scalars(select(ParticipantQuestion).where(ParticipantQuestion.status == "active")).all()
    token = env["game"].reserve_delivery(123, first["assignment_id"])
    assert token and env["game"].reserve_delivery(123, first["assignment_id"]) is None


def test_delivery_failure_can_retry_and_timer_starts_on_confirmation(env):
    state = enroll(env)
    token = env["game"].reserve_delivery(123, state["assignment_id"])
    env["clock"].advance(seconds=100)
    env["game"].release_delivery(123, state["assignment_id"], token)
    state = activate(env, state)
    env["clock"].advance(seconds=3)
    result = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    assert result["points"] == 90


def test_stale_delivery_lease_and_token_cannot_activate(env):
    state = enroll(env)
    old = env["game"].reserve_delivery(123, state["assignment_id"])
    env["clock"].advance(seconds=61)
    new = env["game"].reserve_delivery(123, state["assignment_id"])
    assert not env["game"].confirm_delivery(123, state["assignment_id"], old, 76)
    assert env["game"].confirm_delivery(123, state["assignment_id"], new, 77)


def test_next_requires_closed_current_and_checks_owner(env):
    state = activate(env, enroll(env))
    with pytest.raises(GameError):
        env["game"].next_question(123, state["assignment_id"])
    for operation in [lambda: env["game"].next_question(999, state["assignment_id"]),
                      lambda: env["game"].submit_answer(999, state["assignment_id"], option(env, state))]:
        with pytest.raises(GameError) as error:
            operation()
        assert error.value.status_code == 403


def test_foreign_option_rejected_without_score(env):
    state = activate(env, enroll(env))
    with env["sessions"]() as session:
        foreign_question = session.scalar(select(ParticipantQuestion).where(ParticipantQuestion.position == 2))
        from app.models import QuestionOption
        foreign_option = session.scalar(select(QuestionOption.id).where(QuestionOption.question_id == foreign_question.question_id))
    with pytest.raises(GameError):
        env["game"].submit_answer(123, state["assignment_id"], foreign_option)
    assert env["game"].resume(123)["total_score"] == 0


def test_all_ten_questions_complete_and_old_next_is_harmless(env):
    state = enroll(env)
    original_id = state["assignment_id"]
    for position in range(1, 11):
        state = activate(env, state)
        assert state["position"] == position
        state = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
        state = env["game"].next_question(123, state["assignment_id"])
    assert state["status"] == "completed" and state["total_score"] == 1000 and state["closed_questions"] == 10
    assert env["game"].next_question(123, original_id) == state
    assert enroll(env) == state


def test_room_timeout_closes_remaining_questions_and_rejects_progress(env):
    state = activate(env, enroll(env))
    env["clock"].advance(seconds=3600)
    final = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    assert final["status"] == "expired" and final["total_score"] == 0
    assert env["game"].next_question(123, state["assignment_id"]) == final
    env["game"].expire_due()
    with env["sessions"]() as session:
        assert session.get(Room, env["room_id"]).status == "finished"
        assert all(q.status == "expired" for q in session.scalars(select(ParticipantQuestion)))
    with pytest.raises(GameError, match="завершена"):
        enroll(env, 456)


def test_manual_finish_and_worker_preserve_earned_score(env):
    state = activate(env, enroll(env))
    env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    env["admin"].finish_room(env["room_id"])
    env["game"].expire_due()
    assert env["game"].resume(123)["total_score"] == 100
    assert env["game"].resume(123)["status"] == "expired"


def test_expiration_notifications_are_durable(env):
    state = activate(env, enroll(env))
    env["clock"].advance(seconds=30)
    env["game"].expire_due()
    pending = env["game"].pending_notifications()
    assert pending["results"] == [(state["assignment_id"], 123)]
    env["game"].mark_notified(123, assignment_id=state["assignment_id"])
    assert not env["game"].pending_notifications()["results"]


def test_duplicate_question_assignment_is_database_error(env):
    state = enroll(env)
    with pytest.raises(IntegrityError), env["sessions"].begin() as session:
        assignment = session.get(ParticipantQuestion, state["assignment_id"])
        session.add(ParticipantQuestion(participant_id=assignment.participant_id, question_id=assignment.question_id, position=99))


@pytest.mark.parametrize("explanation,correct", [("", [True, False]), ("   ", [True, False]), ("OK", [False, False]), ("OK", [True, True])])
def test_question_validation_requires_explanation_and_one_correct(explanation, correct):
    with pytest.raises(ValidationError):
        QuestionInput(category_id=1, text="Вопрос", explanation=explanation,
                      options=[{"text": str(i), "is_correct": c} for i, c in enumerate(correct)])


def test_active_room_settings_and_historical_questions_are_immutable(env):
    with pytest.raises(GameError):
        env["admin"].update_room(env["room_id"], RoomPatch(title="Changed"))
    payload = QuestionInput(category_id=env["category_id"], text="New", explanation="Why",
                            options=[{"text": "A", "is_correct": True}, {"text": "B"}])
    for _ in range(2):
        with pytest.raises(GameError, match="копию"):
            env["admin"].save_question(payload, env["questions"][0])
        env["admin"].finish_room(env["room_id"])


def test_same_user_may_play_in_another_room_and_names_need_not_be_unique(env):
    first = enroll(env, username="same")
    enroll(env, 456, "Анна", "same")
    new_room = env["admin"].create_room(RoomInput(title="Другая комната"))
    env["admin"].assign_questions(new_room, RoomQuestionsInput(question_ids=env["questions"]))
    env["admin"].start_room(new_room)
    with env["sessions"]() as session:
        code = session.get(Room, new_room).join_code
    second = env["game"].enroll(code, 123, "Иван", "same")
    assert first["participant_id"] != second["participant_id"]
    with env["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 2


def test_bank_must_have_enough_questions(env):
    room_id = env["admin"].create_room(RoomInput(title="Пустая"))
    with pytest.raises(GameError, match="не менее"):
        env["admin"].start_room(room_id)


def test_leaderboard_ties_use_correct_response_duration_then_join_time(env):
    a = activate(env, enroll(env, 123, "Иван"), 123)
    env["clock"].advance(milliseconds=10)
    b = activate(env, enroll(env, 456, "Анна", "anna"), 456)
    env["clock"].advance(milliseconds=10)
    env["game"].submit_answer(123, a["assignment_id"], option(env, a))
    env["game"].submit_answer(456, b["assignment_id"], option(env, b))
    public = LeaderboardService(env["sessions"], env["settings"], env["clock"])
    result = public.leaderboard(env["room_id"])
    assert [p["display_name"] for p in result["leaderboard"]] == ["@anna", "Иван"]
    assert [p["place"] for p in result["leaderboard"]] == [1, 2]
    assert "telegram_id" not in str(result) and "explanation" not in str(result) and "is_correct" not in str(result)


@pytest.mark.parametrize("elapsed,expected", [(0, 100), (6000, 80), (15000, 50), (29999, 0), (30000, 0), (-100, 100)])
def test_scoring_formula(elapsed, expected):
    assert calculate_points(correct=True, elapsed_ms=elapsed, limit_seconds=30, maximum=100, minimum=0) == expected


def test_interactive_question_uses_own_timer(env):
    from app.models import Question
    state = enroll(env)
    # Direct fixture preparation bypasses the intentionally locked admin endpoint.
    with env["sessions"].begin() as session:
        assignment = session.get(ParticipantQuestion, state["assignment_id"])
        session.get(Question, assignment.question_id).time_limit_seconds = 120
    state = activate(env, state)
    env["clock"].advance(seconds=60)
    assert env["game"].submit_answer(123, state["assignment_id"], option(env, state))["points"] == 50


def test_mysql_concurrent_answers_and_next(env):
    if env["engine"].dialect.name != "mysql":
        pytest.skip("Row locking requires MySQL integration database")
    state = activate(env, enroll(env))
    good, bad = option(env, state), option(env, state, False)
    barrier = Barrier(2)

    def answer(option_id):
        barrier.wait()
        return env["game"].submit_answer(123, state["assignment_id"], option_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(answer, [good, bad]))
    assert responses[0] == responses[1]
    with env["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(Answer)) == 1
        assert session.scalar(select(Answer.points_awarded)) == session.scalar(select(Participant.total_score))
    barrier = Barrier(2)

    def advance(_):
        barrier.wait()
        return env["game"].next_question(123, state["assignment_id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(advance, [1, 2]))
    assert responses[0] == responses[1]
    assert responses[0]["position"] == 2


def test_mysql_concurrent_enrollment(env):
    if env["engine"].dialect.name != "mysql":
        pytest.skip("Row locking requires MySQL integration database")
    barrier = Barrier(2)

    def register(_):
        barrier.wait()
        return enroll(env)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(register, [1, 2]))
    assert responses[0] == responses[1]
    with env["sessions"]() as session:
        assert session.scalar(select(func.count()).select_from(Participant)) == 1
        assert session.scalar(select(func.count()).select_from(ParticipantQuestion)) == 10
