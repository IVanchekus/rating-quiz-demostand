import asyncio
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from telegram.error import BadRequest

from app.bot.delivery import deliver
from app.bot.presentation import render_state
from app.main import create_app
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


def test_bot_result_keyboard_no_repeat_and_no_position(env):
    state = activate(env, enroll(env))
    text, keyboard = render_state(state)
    for row in keyboard.inline_keyboard:
        assert len(row[0].callback_data.encode()) <= 64
        assert "correct" not in row[0].callback_data
    result = env["game"].submit_answer(123, state["assignment_id"], option(env, state))
    text, keyboard = render_state(result)
    assert "Правильный ответ: Да" in text and "Почему это правильно:" in text
    assert len(keyboard.inline_keyboard) == 1
    assert keyboard.inline_keyboard[0][0].callback_data == f"next:{state['assignment_id']}"
    assert "место" not in text.lower() and "place" not in text.lower()


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
