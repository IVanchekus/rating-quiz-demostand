import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from telegram.error import BadRequest
from telegram.constants import ChatType
from sqlalchemy import select
from app.models import Participant, Room, User, UserAccessGrant
from app.schemas import RoomInput, RoomQuestionsInput

from app.bot.delivery import COMPLETION_STICKERS, deliver
from app.bot.main import callback
from app.bot.presentation import render_state
from app.main import create_app
from app.services.game import GameError
from conftest import activate, enroll, option


def test_admin_requires_bearer_and_public_never_exposes_answers(env):
    with TestClient(create_app(env["sessions"], env["settings"])) as client:
        assert client.get("/api/admin/questions").status_code == 401
        auth = {"Authorization": f"Bearer {env['settings'].admin_secret}"}
        assert client.get("/api/admin/questions", headers=auth).status_code == 200
        assert client.get("/api/rooms/active").status_code == 200
        result = client.get(f"/api/rooms/{env['code']}/leaderboard")
        assert result.status_code == 200
        assert all(s not in result.text for s in ["telegram_id", "explanation", "is_correct", "options"])
        assert client.get(f"/api/rooms/{env['room_id']}/stats").json()["participants_count"] == 0
        assert client.get("/api/rooms/missing").status_code == 404
        cors = client.options("/api/rooms/active", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in cors.headers


def test_api_validation_and_room_workflow(env):
    with TestClient(create_app(env["sessions"], env["settings"])) as client:
        auth = {"Authorization": f"Bearer {env['settings'].admin_secret}"}
        assert client.post("/api/admin/questions", headers=auth, json={"text": "Invalid"}).status_code == 422
        response = client.post("/api/admin/rooms", headers=auth, json={"title": "Новая"})
        assert response.status_code == 201
        room_id = response.json()["id"]
        assert client.post(f"/api/admin/rooms/{room_id}/start", headers=auth).status_code == 409
        assert client.post(f"/api/admin/rooms/{room_id}/questions", headers=auth, json={"category_ids": [env["category_id"]]}).json()["assigned"] == 12
        assert client.post(f"/api/admin/rooms/{room_id}/start", headers=auth).status_code == 200
        assert client.patch(f"/api/admin/rooms/{room_id}", headers=auth, json={"title": "Change"}).status_code == 409
        assert client.post(f"/api/admin/rooms/{room_id}/finish", headers=auth).json()["status"] == "finished"


def test_admin_user_history_and_each_grant_allows_exactly_one_replay(env):
    first = enroll(env, telegram_id=456, name="Мария", username="maria")
    with env["sessions"].begin() as session:
        attempt = session.get(Participant, first["participant_id"])
        attempt.status = "completed"
        attempt.completed_at = env["clock"]()

    auth = {"Authorization": f"Bearer {env['settings'].admin_secret}"}
    with TestClient(create_app(env["sessions"], env["settings"])) as client:
        assert client.get("/api/admin/users").status_code == 401
        listed = client.get("/api/admin/users", headers=auth).json()
        user = next(row for row in listed if row["telegram_id"] == 456)
        assert (user["attempts_count"], user["rooms_count"], user["available_grants"]) == (1, 1, 0)

        detail = client.get(f"/api/admin/users/{user['id']}", headers=auth).json()
        assert detail["user"]["username"] == "maria"
        assert len(detail["attempts"]) == 1
        assert detail["attempts"][0]["questions_count"] == first["questions_count"]
        assert detail["attempts"][0]["questions"][0]["text"].startswith("Вопрос")

    second_room_id = env["admin"].create_room(RoomInput(title="Следующая комната", questions_count=10))
    env["admin"].assign_questions(second_room_id, RoomQuestionsInput(question_ids=env["questions"]))
    env["admin"].start_room(second_room_id)
    with env["sessions"]() as session:
        second_code = session.get(Room, second_room_id).join_code
    with pytest.raises(GameError, match="выдать повторный доступ"):
        env["game"].enroll(second_code, 456, "Мария", "maria")

    auth = {"Authorization": f"Bearer {env['settings'].admin_secret}"}
    with TestClient(create_app(env["sessions"], env["settings"])) as client:
        assert client.post(f"/api/admin/users/{user['id']}/grant", headers=auth).json()["available"] == 1

    # Returning through the old room link does not consume a grant for the next room.
    assert env["game"].enroll(env["code"], 456, "Мария", "maria")["participant_id"] == first["participant_id"]
    assert env["admin"].user_detail(user["id"])["grants"]["available"] == 1
    replay = env["game"].enroll(second_code, 456, "Мария", "maria")
    assert replay["participant_id"] != first["participant_id"]
    with env["sessions"]() as session:
        assert session.get(Participant, replay["participant_id"]).deadline_at == env["clock"]() + timedelta(minutes=60)
    with env["sessions"].begin() as session:
        session.get(Participant, replay["participant_id"]).status = "completed"
    assert env["game"].enroll(second_code, 456, "Мария", "maria")["participant_id"] == replay["participant_id"]

    third_room_id = env["admin"].create_room(RoomInput(title="Ещё одна комната", questions_count=10))
    env["admin"].assign_questions(third_room_id, RoomQuestionsInput(question_ids=env["questions"]))
    env["admin"].start_room(third_room_id)
    with env["sessions"]() as session:
        third_code = session.get(Room, third_room_id).join_code
    with TestClient(create_app(env["sessions"], env["settings"])) as client:
        assert client.post(f"/api/admin/users/{user['id']}/grant", headers=auth).json()["available"] == 1
    second_replay = env["game"].enroll(third_code, 456, "Мария", "maria")
    assert second_replay["participant_id"] not in (first["participant_id"], replay["participant_id"])
    detail = env["admin"].user_detail(user["id"])
    assert len(detail["attempts"]) == 3
    assert detail["grants"]["issued"] == detail["grants"]["consumed"] == 2
    assert detail["grants"]["available"] == 0


def test_admin_can_revoke_unused_grant_but_not_a_consumed_grant(env):
    state = enroll(env, telegram_id=654, name="Ирина")
    with env["sessions"]() as session:
        user_id = session.scalar(select(User.id).where(User.telegram_id == 654))
    env["admin"].grant_user_access(user_id)
    auth = {"Authorization": f"Bearer {env['settings'].admin_secret}"}
    with TestClient(create_app(env["sessions"], env["settings"])) as client:
        history = client.get(f"/api/admin/users/{user_id}", headers=auth).json()["grants"]["history"]
        grant_id = history[0]["id"]
        response = client.delete(f"/api/admin/users/{user_id}/grants/{grant_id}", headers=auth)
        assert response.status_code == 200
        detail = client.get(f"/api/admin/users/{user_id}", headers=auth).json()
        assert detail["grants"]["available"] == detail["grants"]["issued"] == 0

        env["admin"].grant_user_access(user_id)
        with env["sessions"].begin() as session:
            grant = session.scalar(select(UserAccessGrant).where(UserAccessGrant.user_id == user_id))
            grant.used_at = env["clock"]()
            grant.participant_id = state["participant_id"]
            used_grant_id = grant.id
        response = client.delete(f"/api/admin/users/{user_id}/grants/{used_grant_id}", headers=auth)
        assert response.status_code == 409
        retained = client.get(f"/api/admin/users/{user_id}", headers=auth).json()["grants"]["history"]
        assert len(retained) == 1 and retained[0]["used_at"] is not None


def test_bot_result_keyboard_no_repeat_and_no_position(env):
    state = activate(env, enroll(env))
    text, keyboard = render_state(state)
    assert "🧩 Вопрос" in text
    assert "На ответ:" not in text and "Ответ принимается до" not in text and "UTC" not in text
    for row in keyboard.inline_keyboard:
        assert len(row[0].callback_data.encode()) <= 64
        assert "correct" not in row[0].callback_data
    result = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    text, keyboard = render_state(result)
    assert "Правильный ответ: Да" in text and "Почему это правильно:" in text
    assert all(emoji in text for emoji in ("✅", "🎯", "💡", "⭐"))
    assert len(keyboard.inline_keyboard) == 1
    assert keyboard.inline_keyboard[0][0].callback_data == f"next:{state['assignment_id']}"
    assert "место" not in text.lower() and "place" not in text.lower()


def test_bot_incorrect_answer_shows_cross(env):
    state = activate(env, enroll(env))
    result = env["game"].submit_answer(123, state["assignment_id"], option(env, state, correct=False))
    text, _ = render_state(result)
    assert "❌ Неправильный ответ" in text and "💡 Почему это правильно:" in text


def test_next_button_deletes_result_message_before_sending_question(env):
    state = activate(env, enroll(env))
    env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    message = SimpleNamespace(delete=AsyncMock(), reply_text=AsyncMock())
    query = SimpleNamespace(
        answer=AsyncMock(), data=f"next:{state['assignment_id']}",
        from_user=SimpleNamespace(id=123), message=message,
    )
    update = SimpleNamespace(
        callback_query=query, effective_chat=SimpleNamespace(type=ChatType.PRIVATE),
        effective_message=message,
    )
    bot = AsyncMock()
    bot.send_message.return_value = SimpleNamespace(message_id=88)
    context = SimpleNamespace(bot=bot)

    with patch("app.bot.main.game", env["game"]):
        asyncio.run(callback(update, context))

    message.delete.assert_awaited_once()
    bot.send_message.assert_awaited_once()
    assert "🧩 Вопрос 2" in bot.send_message.call_args.args[1]


def test_completed_attempt_sends_one_random_completion_sticker(env):
    state = enroll(env)
    with env["sessions"].begin() as session:
        participant = session.get(Participant, state["participant_id"])
        participant.status = "completed"
    bot = AsyncMock()
    completed = env["game"].resume(123, state["participant_id"])
    asyncio.run(deliver(bot, env["game"], completed))
    asyncio.run(deliver(bot, env["game"], env["game"].resume(123, state["participant_id"])))
    bot.send_sticker.assert_awaited_once()
    assert bot.send_sticker.call_args.kwargs["sticker"] in COMPLETION_STICKERS


def test_finished_room_sends_rank_and_thanks_to_every_participant_once(env):
    for telegram_id, (name, score) in enumerate(
        [("Первый", 120), ("Второй", 100), ("Третий", 90), ("Четвёртый", 80)], 100,
    ):
        state = env["game"].enroll(env["code"], telegram_id, name)
        with env["sessions"].begin() as session:
            participant = session.get(Participant, state["participant_id"])
            participant.status = "completed"
            participant.total_score = score
    env["admin"].finish_room(env["room_id"])
    from app.worker.expiration import tick
    bot = AsyncMock()
    asyncio.run(tick(env["game"], bot))
    rank_messages = [call.args[1] for call in bot.send_message.call_args_list if "место" in call.args[1]]
    assert any("Первый" in message and "1-е место" in message and "Поздравляем" in message for message in rank_messages)
    assert any("Второй" in message and "2-е место" in message and "Поздравляем" in message for message in rank_messages)
    assert any("Третий" in message and "3-е место" in message and "Поздравляем" in message for message in rank_messages)
    assert any("Четвёртый" in message and "4-е место" in message for message in rank_messages), rank_messages
    assert all("Спасибо за игру" in message for message in rank_messages)
    message_count = bot.send_message.await_count
    asyncio.run(tick(env["game"], bot))
    assert bot.send_message.await_count == message_count


def test_pending_and_overdue_bot_messages_have_no_timer_and_keep_answers(env):
    state = enroll(env)
    for current in [state, activate(env, state)]:
        text, keyboard = render_state(current)
        assert "На ответ:" not in text and "Ответ принимается до" not in text
        assert all(row[0].callback_data.startswith("answer:") for row in keyboard.inline_keyboard)
    env["clock"].advance(seconds=60)
    bot = AsyncMock()
    from app.worker.expiration import tick
    asyncio.run(tick(env["game"], bot))
    bot.send_message.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()
    restored = env["game"].resume(123)
    text, keyboard = render_state(restored)
    assert restored["question_status"] == "active"
    assert "Правильный ответ:" not in text and len(keyboard.inline_keyboard) == 2


def test_public_api_hides_score_until_test_completed(env):
    state = activate(env, enroll(env))
    env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    with TestClient(create_app(env["sessions"], env["settings"])) as client:
        row = client.get(f"/api/rooms/{env['code']}/leaderboard").json()["leaderboard"][0]
        assert row["total_score"] is None and row["place"] is None and not row["completed"]


def test_telegram_edit_failure_sends_saved_result_without_rescoring(env):
    state = activate(env, enroll(env))
    env["clock"].advance(seconds=6)
    result = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    bot = AsyncMock()
    bot.edit_message_text.side_effect = BadRequest("Message can't be edited")
    asyncio.run(deliver(bot, env["game"], result))
    bot.send_message.assert_awaited_once()
    assert "80" in bot.send_message.call_args.args[1]
    assert env["game"].resume(123)["total_score"] == 80


def test_failed_telegram_send_leaves_question_pending(env):
    state = enroll(env)
    bot = AsyncMock()
    bot.send_message.side_effect = BadRequest("Failed")
    try:
        asyncio.run(deliver(bot, env["game"], state))
    except BadRequest:
        pass
    restored = env["game"].resume(123)
    assert restored["question_status"] == "pending" and restored["expires_at"] is None
    assert env["game"].reserve_delivery(123, state["assignment_id"])
