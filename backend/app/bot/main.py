import asyncio
import logging

from telegram import BotCommand, Update
from telegram.constants import ChatType
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.bot.delivery import deliver
from app.config import get_settings
from app.database import SessionLocal
from app.services.game import GameError, GameService

log = logging.getLogger(__name__)
game = GameService(SessionLocal)
HELP = (
    "Питерский мостик IT Challenge\n\n"
    "Откройте QR-ссылку комнаты и пройдите вопросы. У каждого участника своя последовательность. "
    "Выбрать ответ можно один раз. За правильный ответ баллы зависят от скорости. "
    "Поздний правильный ответ даёт минимум баллов из настроек комнаты. "
    "После ответа появятся объяснение и кнопка «Далее».\n\n"
    "/start — продолжить игру\n/score — личные баллы и прогресс\n/help — правила\n\n"
    "Общий рейтинг доступен на экране мероприятия."
)


async def private(update):
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        return True
    if update.effective_message:
        await update.effective_message.reply_text("Для участия откройте личный диалог с ботом по QR-ссылке.")
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await private(update):
        return
    user = update.effective_user
    try:
        if context.args:
            code = context.args[0]
            if not code.startswith("room_"):
                raise GameError("Откройте ссылку из QR-кода комнаты")
            context.user_data["pending_room_code"] = code[5:]
            await update.message.reply_text(
                "Перед началом опроса напишите, пожалуйста, имя и фамилию через пробел.\n"
                "Например: Иван Петров"
            )
            return
        else:
            context.user_data.pop("pending_room_code", None)
            state = await asyncio.to_thread(game.resume, user.id)
        if state is None:
            await update.message.reply_text("Добро пожаловать! Отсканируйте QR-код на стойке, чтобы войти в комнату.\n\n" + HELP)
        else:
            if state.get("question_status") == "pending" and state.get("position") == 1:
                await update.message.reply_text(f"Добро пожаловать в «{state['room_title']}»!\n\n" + HELP)
            await deliver(context.bot, game, state)
    except GameError as error:
        await update.message.reply_text(error.message)


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await private(update):
        return
    code = context.user_data.get("pending_room_code")
    if not code:
        return
    parts = (update.effective_message.text or "").split()
    if len(parts) != 2:
        await update.effective_message.reply_text(
            "Введите имя и фамилию через пробел. Например: Иван Петров"
        )
        return

    user = update.effective_user
    try:
        state = await asyncio.to_thread(
            game.enroll, code, user.id, parts[0], user.username, parts[1]
        )
    except GameError as error:
        context.user_data.pop("pending_room_code", None)
        await update.effective_message.reply_text(error.message)
        return

    context.user_data.pop("pending_room_code", None)
    if state.get("question_status") == "pending" and state.get("position") == 1:
        await update.effective_message.reply_text(f"Добро пожаловать в «{state['room_title']}»!\n\n" + HELP)
    await deliver(context.bot, game, state)


async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await private(update):
        return
    state = await asyncio.to_thread(game.resume, update.effective_user.id)
    if not state:
        await update.message.reply_text("Сначала войдите в комнату по QR-ссылке.")
        return
    await update.message.reply_text(
        f"Ваш результат: {state['total_score']} из {state['maximum_score']} баллов.\n"
        f"Пройдено вопросов: {state['closed_questions']} из {state['questions_count']}."
    )
    if state["status"] != "playing" or state.get("question_status") in ("answered", "expired"):
        await deliver(context.bot, game, state)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await private(update):
        await update.message.reply_text(HELP)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await private(update):
        return
    try:
        parts = query.data.split(":")
        if parts[0] == "answer" and len(parts) == 3:
            state = await asyncio.to_thread(game.submit_answer, query.from_user.id, int(parts[1]), int(parts[2]))
        elif parts[0] == "next" and len(parts) == 2:
            state = await asyncio.to_thread(game.next_question, query.from_user.id, int(parts[1]))
            # Remove the result card before sending the next question to keep the chat tidy.
            try:
                await query.message.delete()
            except Exception:
                log.debug("result_message_not_deletable")
        else:
            raise GameError("Неизвестная кнопка. Повторите /start")
        await deliver(context.bot, game, state)
    except (GameError, ValueError) as error:
        await query.message.reply_text(error.message if isinstance(error, GameError) else "Некорректная кнопка")


async def error_handler(update, context):
    # Telegram exceptions may contain request URLs. Never log bot token-bearing URLs.
    log.error("telegram_handler_failed type=%s", type(context.error).__name__)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Не удалось обновить сообщение. Повторите /start — прогресс сохранён.")
        except Exception:
            pass


async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Начать или продолжить"), BotCommand("score", "Мои баллы"), BotCommand("help", "Правила"),
    ])


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    if not settings.telegram_bot_token or settings.telegram_bot_token.startswith("replace"):
        raise SystemExit("Set TELEGRAM_BOT_TOKEN before starting the bot")
    app = Application.builder().token(settings.telegram_bot_token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_error_handler(error_handler)
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
