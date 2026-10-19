"""Idempotent starter bank. Company-specific facts must be verified by organizers."""
import argparse
import secrets

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Question
from app.schemas import CategoryInput, QuestionInput, RoomInput, RoomQuestionsInput
from app.services.admin import AdminService
from app.services.leaderboard import LeaderboardService

CATEGORIES = [
    ("Программирование", "programming"), ("О компании", "company"),
    ("Интерактивные задания", "interactive"), ("IT и технологии", "technology"),
]
# category, question, correct answer, distractors, explanation
BANK = [
    ("programming", "Какой HTTP-метод предназначен для частичного обновления ресурса?", "PATCH", ["GET", "POST", "DELETE"],
     "PATCH передаёт набор частичных изменений ресурса. PUT обычно заменяет его представление целиком."),
    ("programming", "Какая структура данных работает по принципу «первым пришёл — первым вышел»?", "Очередь", ["Стек", "Множество", "Дерево"],
     "Очередь использует принцип FIFO: первым извлекается элемент, который добавили раньше остальных."),
    ("programming", "Какой код HTTP означает, что ресурс не найден?", "404", ["200", "301", "500"],
     "404 Not Found сообщает, что сервер не нашёл запрошенный ресурс."),
    ("programming", "Что делает команда git commit?", "Сохраняет снимок подготовленных изменений", ["Удаляет историю", "Загружает зависимости", "Отправляет изменения на сервер"],
     "Коммит сохраняет подготовленные изменения в локальной истории. Для отправки на сервер используется git push."),
    ("programming", "Какое ограничение БД запрещает повторяющиеся значения в столбце?", "UNIQUE", ["DEFAULT", "NOT NULL", "FOREIGN KEY"],
     "UNIQUE обеспечивает уникальность значений. NOT NULL запрещает только отсутствие значения."),
    ("programming", "Какой SQL-оператор выбирает данные из таблицы?", "SELECT", ["INSERT", "UPDATE", "DELETE"],
     "SELECT используется для чтения данных. INSERT, UPDATE и DELETE изменяют содержимое таблицы."),
    ("technology", "Для чего используется DNS?", "Для сопоставления доменных имён с сетевыми адресами", ["Для шифрования диска", "Для компиляции кода", "Для сжатия изображений"],
     "DNS позволяет находить адреса серверов по понятным человеку доменным именам."),
    ("technology", "Что защищает HTTPS при передаче данных?", "Соединение между клиентом и сервером", ["От всех ошибок в программе", "От потери питания", "От удаления файлов на устройстве"],
     "HTTPS использует TLS для шифрования и защиты целостности данных, передаваемых по соединению."),
    ("technology", "Для чего нужна двухфакторная аутентификация?", "Для дополнительной проверки личности", ["Для удвоения скорости сети", "Для хранения двух паролей в браузере", "Для создания резервной копии"],
     "Второй фактор добавляет независимое доказательство личности, например подтверждение с устройства."),
    ("technology", "Что такое API?", "Интерфейс взаимодействия программ", ["Тип монитора", "Формат фотографии", "Название процессора"],
     "API задаёт правила, по которым программы обращаются к функциям и данным друг друга."),
    ("technology", "Что означает принцип наименьших привилегий?", "Выдавать только необходимые права", ["Выдавать всем права администратора", "Отключать проверку доступа", "Использовать один пароль для всех"],
     "Минимально необходимые права ограничивают последствия ошибки или компрометации учётной записи."),
    ("technology", "Что помогает восстановить данные после случайного удаления?", "Проверенная резервная копия", ["Увеличение яркости экрана", "Смена языка интерфейса", "Переименование файла"],
     "Резервная копия позволяет восстановить данные. Возможность восстановления нужно регулярно проверять."),
    ("company", "Сколько компаний объединяет «Питерский мостик»?", "Четыре", ["Две", "Три", "Пять"],
     "«Питерский мостик» объединяет четыре компании: Связьком, Sensory Hub, Систематикс и Galaxy."),
    ("company", "Какая из этих компаний входит в «Питерский мостик»?", "Sensory Hub", ["Example Cloud", "Demo Systems", "Sample Labs"],
     "Sensory Hub входит в объединение вместе со Связьком, Систематикс и Galaxy."),
    ("technology", "Что означает IoT?", "Интернет вещей", ["Оптический кабель", "Вид базы данных", "Метод сортировки"],
     "Internet of Things — сеть физических устройств, которые собирают данные и обмениваются ими."),
    ("programming", "Что обеспечивает атомарность транзакции?", "Все операции выполняются целиком или откатываются", ["Все запросы всегда быстрые", "Данные никогда не меняются", "Можно обойти ограничения БД"],
     "Атомарность не допускает частичного сохранения транзакции: фиксируются все её изменения либо ни одно."),
]


def seed(demo_room=False, activate=False):
    settings = get_settings()
    admin = AdminService(SessionLocal, settings)
    existing = {c["slug"]: c["id"] for c in admin.categories()}
    for name, slug in CATEGORIES:
        if slug not in existing:
            existing[slug] = admin.create_category(CategoryInput(name=name, slug=slug))
    with SessionLocal() as session:
        present = set(session.scalars(select(Question.text)))
    for slug, text, correct, distractors, explanation in BANK:
        if text in present:
            continue
        options = [{"text": correct, "is_correct": True}] + [{"text": d} for d in distractors]
        secrets.SystemRandom().shuffle(options)
        admin.save_question(QuestionInput(
            category_id=existing[slug], text=text, explanation=explanation,
            options=options,
        ))
    print("Starter bank ready: 4 categories, 16 questions. No fictional participants created.")
    if demo_room:
        public = LeaderboardService(SessionLocal, settings)
        room = next((r for r in public.rooms(admin=True) if r["title"] == "День партнёров · IT Challenge"), None)
        if room is None:
            room_id = admin.create_room(RoomInput(title="День партнёров · IT Challenge"))
            admin.assign_questions(room_id, RoomQuestionsInput(question_ids=[q["id"] for q in admin.questions() if q["is_active"]]))
        else:
            room_id = room["id"]
        if activate and public.room(room_id)["status"] == "draft":
            admin.start_room(room_id)
        print(public.room(room_id)["public_url"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-room", action="store_true", help="Create a sample draft room")
    parser.add_argument("--activate", action="store_true", help="Also start the sample room")
    args = parser.parse_args()
    seed(args.demo_room, args.activate)
