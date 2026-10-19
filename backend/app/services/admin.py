import secrets
from datetime import timedelta

from sqlalchemy import delete, or_, select

from app.models import Category, ParticipantQuestion, Question, QuestionOption, Room, RoomQuestion, utcnow
from app.services.game import GameError


class AdminService:
    def __init__(self, sessions, settings, clock=utcnow):
        self.sessions, self.settings, self.clock = sessions, settings, clock

    def _room(self, session, room_id):
        room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
        if not room:
            raise GameError("Комната не найдена", 404)
        return room

    def _draft(self, room):
        if room.status != "draft":
            raise GameError("Настройки можно менять только в черновике")

    def create_room(self, data):
        defaults = dict(
            duration_minutes=self.settings.room_duration_minutes,
            questions_count=self.settings.questions_per_game,
            question_time_limit_seconds=self.settings.question_time_limit_seconds,
            max_points_per_question=self.settings.max_points_per_question,
            min_correct_points=self.settings.min_correct_points,
        )
        defaults.update(data.model_dump(exclude_none=True))
        if defaults["min_correct_points"] > defaults["max_points_per_question"]:
            raise GameError("Минимум баллов превышает максимум", 422)
        with self.sessions.begin() as session:
            room = Room(**defaults, join_code=secrets.token_urlsafe(18))
            session.add(room)
            session.flush()
            return room.id

    def update_room(self, room_id, data):
        with self.sessions.begin() as session:
            room = self._room(session, room_id)
            self._draft(room)
            for key, value in data.model_dump(exclude_none=True).items():
                setattr(room, key, value)
            if room.min_correct_points > room.max_points_per_question:
                raise GameError("Минимум баллов превышает максимум", 422)

    def assign_questions(self, room_id, data):
        with self.sessions.begin() as session:
            room = self._room(session, room_id)
            self._draft(room)
            question_ids = set(data.question_ids)
            if data.category_ids:
                question_ids.update(session.scalars(select(Question.id).join(Category).where(
                    Question.category_id.in_(data.category_ids), Question.is_active.is_(True), Category.is_active.is_(True),
                )))
            questions = list(session.scalars(select(Question).where(Question.id.in_(question_ids)).order_by(Question.id).with_for_update()))
            if len(questions) != len(question_ids) or any(not q.is_active for q in questions):
                raise GameError("Выбраны отсутствующие или неактивные вопросы", 422)
            session.execute(delete(RoomQuestion).where(RoomQuestion.room_id == room_id))
            session.add_all([RoomQuestion(room_id=room_id, question_id=q.id) for q in questions])
            return len(questions)

    def start_room(self, room_id):
        with self.sessions.begin() as session:
            room = self._room(session, room_id)
            self._draft(room)
            questions = list(session.scalars(select(Question).join(RoomQuestion).where(
                RoomQuestion.room_id == room_id, Question.is_active.is_(True),
            ).order_by(Question.id).with_for_update()))
            if len(questions) < room.questions_count:
                raise GameError(f"Нужно не менее {room.questions_count} активных вопросов")
            for question in questions:
                options = list(session.scalars(select(QuestionOption).where(QuestionOption.question_id == question.id)))
                if not question.explanation.strip() or len(options) < 2 or sum(o.is_correct for o in options) != 1:
                    raise GameError("В банке есть вопрос без объяснения или с неверными вариантами")
            now = self.clock()
            room.status, room.starts_at = "active", now
            room.ends_at = now + timedelta(minutes=room.duration_minutes)

    def finish_room(self, room_id):
        with self.sessions.begin() as session:
            room = self._room(session, room_id)
            if room.status == "draft":
                raise GameError("Комната ещё не запущена")
            if room.status == "active":
                room.status = "finished"
                room.ends_at = min(room.ends_at, self.clock())

    def create_category(self, data):
        with self.sessions.begin() as session:
            if session.scalar(select(Category.id).where(Category.slug == data.slug)):
                raise GameError("Категория с таким кодом уже существует")
            category = Category(**data.model_dump())
            session.add(category)
            session.flush()
            return category.id

    def categories(self):
        with self.sessions() as session:
            return [dict(id=c.id, name=c.name, slug=c.slug, description=c.description, is_active=c.is_active)
                    for c in session.scalars(select(Category).order_by(Category.id))]

    def save_question(self, data, question_id=None):
        with self.sessions.begin() as session:
            category = session.get(Category, data.category_id)
            if not category or not category.is_active:
                raise GameError("Выберите активную категорию", 422)
            if question_id:
                question = session.scalar(select(Question).where(Question.id == question_id).with_for_update())
                if not question:
                    raise GameError("Вопрос не найден", 404)
                # Freeze linked questions, including finished games, to preserve historical results.
                if (session.scalar(select(RoomQuestion.id).where(RoomQuestion.question_id == question_id).limit(1))
                        or session.scalar(select(ParticipantQuestion.id).where(ParticipantQuestion.question_id == question_id).limit(1))):
                    raise GameError("Вопрос используется в комнате. Создайте копию для новой редакции")
                session.execute(delete(QuestionOption).where(QuestionOption.question_id == question_id))
                for key, value in data.model_dump(exclude={"options"}).items():
                    setattr(question, key, value)
            else:
                question = Question(**data.model_dump(exclude={"options"}))
                session.add(question)
                session.flush()
            session.add_all([QuestionOption(question_id=question.id, sort_order=i, **option.model_dump())
                             for i, option in enumerate(data.options)])
            return question.id

    def questions(self, search=None):
        with self.sessions() as session:
            statement = select(Question).order_by(Question.id.desc())
            if search:
                statement = statement.where(or_(Question.text.contains(search, autoescape=True), Question.explanation.contains(search, autoescape=True)))
            questions = list(session.scalars(statement))
            ids = [q.id for q in questions]
            options = list(session.scalars(select(QuestionOption).where(QuestionOption.question_id.in_(ids)).order_by(QuestionOption.sort_order)))
            frozen = set(session.scalars(select(RoomQuestion.question_id).where(RoomQuestion.question_id.in_(ids))))
            frozen.update(session.scalars(select(ParticipantQuestion.question_id).where(ParticipantQuestion.question_id.in_(ids))))
            return [dict(
                id=q.id, category_id=q.category_id, text=q.text, explanation=q.explanation,
                company=q.company, difficulty=q.difficulty, time_limit_seconds=q.time_limit_seconds,
                is_active=q.is_active, locked=q.id in frozen,
                options=[dict(id=o.id, text=o.text, is_correct=o.is_correct) for o in options if o.question_id == q.id],
            ) for q in questions]
