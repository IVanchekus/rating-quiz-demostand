from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def render_state(state):
    """Telegram presentation intentionally has no rank or public leaderboard data."""
    if state["status"] != "playing":
        heading = "🎉 Игра завершена!" if state["status"] == "completed" else "🏁 Комната завершена!"
        return (
            f"{heading}\n\nВы прошли {state['closed_questions']} из {state['questions_count']} вопросов.\n"
            f"Ваш результат: {state['total_score']} из {state['maximum_score']} баллов.\n\n"
            "Спасибо за участие! Итоговый рейтинг смотрите на экране мероприятия.", None,
        )
    heading = f"Вопрос {state['position']} из {state['questions_count']}\n\n{state['text']}"
    if state["question_status"] in ("pending", "active"):
        timer = f"\n\nНа ответ: до {state['time_limit_seconds']} секунд."
        if state.get("expires_at"):
            timer = f"\n\nОтвет принимается до {state['expires_at'][11:19]} UTC."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(o["text"], callback_data=f"answer:{state['assignment_id']}:{o['id']}")]
            for o in state["options"]
        ])
        return heading + timer, keyboard
    verdict = "⌛ Время вышло" if state["question_status"] == "expired" else (
        "✅ Правильно" if state["is_correct"] else "❌ Неправильный ответ"
    )
    choice = f"\nВаш выбор: {state['selected_option']}" if state["selected_option"] else ""
    return (
        f"{heading}\n\n{verdict}{choice}\nПравильный ответ: {state['correct_option']}\n\n"
        f"Почему это правильно: {state['explanation']}\n\n"
        f"Получено: {state['points']} из {state['max_points']} баллов",
        InlineKeyboardMarkup([[InlineKeyboardButton("Далее →", callback_data=f"next:{state['assignment_id']}")]]),
    )
