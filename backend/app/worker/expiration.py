import asyncio
import logging

from telegram import Bot
from telegram.error import Forbidden

from app.bot.delivery import deliver
from app.config import get_settings
from app.database import SessionLocal
from app.services.game import GameService

log = logging.getLogger(__name__)


async def tick(game, bot=None):
    await asyncio.to_thread(game.expire_due)
    if bot is None:
        return
    pending = await asyncio.to_thread(game.pending_notifications)
    for assignment_id, telegram_id in pending["results"]:
        try:
            state = await asyncio.to_thread(game.question_state, telegram_id, assignment_id)
            await deliver(bot, game, state)
        except Forbidden:
            await asyncio.to_thread(game.mark_notified, telegram_id, assignment_id=assignment_id)
        except Exception as error:
            log.warning("result_delivery_retry assignment=%s type=%s", assignment_id, type(error).__name__)
    for participant_id, telegram_id in pending["finals"]:
        try:
            state = await asyncio.to_thread(game.resume, telegram_id, participant_id)
            await deliver(bot, game, state)
        except Forbidden:
            await asyncio.to_thread(game.mark_notified, telegram_id, participant_id=participant_id)
        except Exception as error:
            log.warning("final_delivery_retry participant=%s type=%s", participant_id, type(error).__name__)
    for result in await asyncio.to_thread(game.pending_room_results):
        participant_id, telegram_id = result["participant_id"], result["telegram_id"]
        if result["place"] is not None:
            greeting = (
                f"🎉 Поздравляем, {result['display_name']}! Вы заняли {result['place']}-е место "
                f"в комнате «{result['room_title']}»! 🏆\n\nСпасибо за игру!"
                if result["place"] <= 3 else
                f"Спасибо за игру, {result['display_name']}! Вы заняли {result['place']}-е место "
                f"в комнате «{result['room_title']}»."
            )
        else:
            greeting = (
                f"Спасибо за игру, {result['display_name']}! Комната «{result['room_title']}» завершена.\n"
                f"Ваш результат: {result['total_score']} баллов."
            )
        try:
            await bot.send_message(telegram_id, greeting)
            await asyncio.to_thread(game.mark_room_result_notified, telegram_id, participant_id)
        except Forbidden:
            await asyncio.to_thread(game.mark_room_result_notified, telegram_id, participant_id)
        except Exception as error:
            log.warning("room_result_delivery_retry participant=%s type=%s", participant_id, type(error).__name__)


async def run():
    settings = get_settings()
    game = GameService(SessionLocal)
    token = settings.telegram_bot_token
    bot = Bot(token) if token and not token.startswith("replace") else None
    if bot:
        await bot.initialize()
    try:
        while True:
            try:
                await tick(game, bot)
            except Exception as error:
                log.error("expiration_tick_failed type=%s", type(error).__name__)
            await asyncio.sleep(settings.question_expiration_check_seconds)
    finally:
        if bot:
            await bot.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run())
