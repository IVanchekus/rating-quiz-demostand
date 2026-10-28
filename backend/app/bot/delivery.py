import asyncio
import logging
import random

from telegram.error import BadRequest, TelegramError

from app.bot.presentation import render_state

log = logging.getLogger(__name__)
COMPLETION_STICKERS = (
    "CAACAgIAAxkBAAESHONq4beyCXZ9pOelHI5Ztqbc-MK6qQACMhQAAj6r6EtdMwJVMBohFz0E",
    "CAACAgIAAxkBAAESHOVq4be8eDrtcZ6tbYiHDg_FCGNghQACZBQAAiK6YEgY9ZScdsA62z0E",
    "CAACAgIAAxkBAAESHOdq4bfDq6KR3VkRUKQ16dRs1oWRMAACBRcAAsno6EsmvtEpe1IkcD0E",
    "CAACAgIAAxkBAAESHOlq4bfKhl2MWiaYIH5nX_6Oh6g75wACbxQAAh8q8Eupmekcwm_mej0E",
)


async def deliver(bot, game, state):
    telegram_id = state["telegram_id"]
    text, keyboard = render_state(state)
    if state["status"] == "playing" and state["question_status"] == "pending":
        token = await asyncio.to_thread(game.reserve_delivery, telegram_id, state["assignment_id"])
        if not token:
            return
        try:
            message = await bot.send_message(telegram_id, text, reply_markup=keyboard)
            accepted = await asyncio.to_thread(
                game.confirm_delivery, telegram_id, state["assignment_id"], token, message.message_id,
            )
            if not accepted:
                # Room could close or delivery lease could be superseded while sending.
                await message.edit_reply_markup(reply_markup=None)
        except Exception:
            await asyncio.to_thread(game.release_delivery, telegram_id, state["assignment_id"], token)
            raise
        return
    message_id = state.get("message_id")
    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=telegram_id, message_id=message_id, reply_markup=keyboard)
        except BadRequest as error:
            if "message is not modified" not in str(error).lower():
                await bot.send_message(telegram_id, text, reply_markup=keyboard)
        except TelegramError:
            # Network errors can be ambiguous; retry through /start or the durable worker queue.
            raise
    else:
        await bot.send_message(telegram_id, text, reply_markup=keyboard)
    if state["status"] == "completed" and not state.get("final_notified"):
        await bot.send_sticker(telegram_id, sticker=random.choice(COMPLETION_STICKERS))
    if state["status"] != "playing":
        await asyncio.to_thread(game.mark_notified, telegram_id, participant_id=state["participant_id"])
    elif state["question_status"] in ("answered", "expired"):
        await asyncio.to_thread(game.mark_notified, telegram_id, assignment_id=state["assignment_id"])
