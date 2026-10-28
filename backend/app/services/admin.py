import secrets
from datetime import timedelta

from sqlalchemy import String, case, delete, func, or_, select

from app.models import Answer, Category, Participant, ParticipantQuestion, Question, QuestionOption, Room, RoomQuestion, User, UserAccessGrant, utcnow
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

    def users(self, search=None):
        with self.sessions() as session:
            grants = select(
                UserAccessGrant.user_id.label("user_id"),
                func.sum(case((UserAccessGrant.used_at.is_(None), 1), else_=0)).label("available"),
            ).group_by(UserAccessGrant.user_id).subquery()
            activity = select(
                Participant.user_id.label("user_id"),
                func.count(func.distinct(Participant.id)).label("attempts"),
                func.count(func.distinct(Participant.room_id)).label("rooms"),
                func.max(Participant.joined_at).label("last_seen"),
                func.count(func.distinct(case((Participant.status == "completed", Participant.id)))).label("completed"),
                func.sum(case((Answer.id.is_not(None), 1), else_=0)).label("answers"),
            ).outerjoin(ParticipantQuestion, ParticipantQuestion.participant_id == Participant.id).outerjoin(
                Answer, Answer.participant_question_id == ParticipantQuestion.id,
            ).group_by(Participant.user_id).subquery()
            statement = select(User, activity.c.attempts, activity.c.rooms, activity.c.last_seen, activity.c.completed,
                               activity.c.answers, grants.c.available).outerjoin(
                activity, activity.c.user_id == User.id,
            ).outerjoin(grants, grants.c.user_id == User.id)
            if search:
                term = f"%{search.strip()}%"
                statement = statement.where(or_(User.username.ilike(term), User.first_name.ilike(term),
                                                User.last_name.ilike(term), func.cast(User.telegram_id, String).like(term)))
            rows = session.execute(statement.order_by(User.created_at.desc(), User.id.desc())).all()
            return [dict(
                id=user.id, telegram_id=user.telegram_id, username=user.username, first_name=user.first_name,
                last_name=user.last_name, attempts_count=int(attempts or 0), rooms_count=int(room_count or 0),
                completed_count=int(completed or 0),
                answered_count=int(answers or 0), last_seen=last_seen.isoformat() + "Z" if last_seen else None,
                available_grants=int(available or 0),
            ) for user, attempts, room_count, last_seen, completed, answers, available in rows]

    def user_detail(self, user_id):
        with self.sessions() as session:
            user = session.get(User, user_id)
            if not user:
                raise GameError("Пользователь не найден", 404)
            grant_rows = list(session.scalars(select(UserAccessGrant).where(
                UserAccessGrant.user_id == user_id,
            ).order_by(UserAccessGrant.id.desc())))
            attempts = list(session.scalars(select(Participant).where(
                Participant.user_id == user_id,
            ).order_by(Participant.joined_at.desc(), Participant.id.desc())))
            history = []
            for participant in attempts:
                room = session.get(Room, participant.room_id)
                assignments = list(session.scalars(select(ParticipantQuestion).where(
                    ParticipantQuestion.participant_id == participant.id,
                ).order_by(ParticipantQuestion.position)))
                questions = []
                for assignment in assignments:
                    question = session.get(Question, assignment.question_id)
                    options = list(session.scalars(select(QuestionOption).where(
                        QuestionOption.question_id == question.id,
                    ).order_by(QuestionOption.sort_order)))
                    answer = session.scalar(select(Answer).where(Answer.participant_question_id == assignment.id))
                    selected = next((option for option in options if answer and option.id == answer.selected_option_id), None)
                    correct = next((option for option in options if option.is_correct), None)
                    questions.append(dict(
                        position=assignment.position, text=question.text, explanation=question.explanation,
                        status=assignment.status, sent_at=assignment.sent_at.isoformat() + "Z" if assignment.sent_at else None,
                        selected_option=selected.text if selected else None, correct_option=correct.text if correct else None,
                        is_correct=answer.is_correct if answer else None, points=answer.points_awarded if answer else None,
                        response_time_ms=answer.response_time_ms if answer else None,
                    ))
                history.append(dict(
                    participant_id=participant.id, room_id=room.id, room_title=room.title,
                    room_status=room.status, status=participant.status, total_score=participant.total_score,
                    current_question_number=participant.current_question_number, questions_count=len(questions),
                    deadline_at=participant.deadline_at.isoformat() + "Z" if participant.deadline_at else None,
                    answered_count=sum(question["selected_option"] is not None for question in questions),
                    joined_at=participant.joined_at.isoformat() + "Z", completed_at=participant.completed_at.isoformat() + "Z" if participant.completed_at else None,
                    questions=questions,
                ))
            return dict(
                user=dict(id=user.id, telegram_id=user.telegram_id, username=user.username,
                          first_name=user.first_name, last_name=user.last_name,
                          created_at=user.created_at.isoformat() + "Z"),
                grants=dict(available=sum(grant.used_at is None for grant in grant_rows),
                            issued=len(grant_rows), consumed=sum(grant.used_at is not None for grant in grant_rows),
                            history=[dict(id=grant.id, granted_at=grant.granted_at.isoformat() + "Z",
                                          used_at=grant.used_at.isoformat() + "Z" if grant.used_at else None,
                                          participant_id=grant.participant_id) for grant in grant_rows]),
                attempts=history,
            )

    def grant_user_access(self, user_id):
        with self.sessions.begin() as session:
            user = session.scalar(select(User).where(User.id == user_id).with_for_update())
            if not user:
                raise GameError("Пользователь не найден", 404)
            grant = UserAccessGrant(user_id=user.id, granted_at=self.clock())
            session.add(grant)
            session.flush()
            return dict(available=int(session.scalar(select(func.count()).select_from(UserAccessGrant).where(
                UserAccessGrant.user_id == user.id, UserAccessGrant.used_at.is_(None),
            ))), granted_at=grant.granted_at.isoformat() + "Z")

    def revoke_user_access(self, user_id, grant_id):
        with self.sessions.begin() as session:
            grant = session.scalar(select(UserAccessGrant).where(
                UserAccessGrant.id == grant_id,
                UserAccessGrant.user_id == user_id,
            ).with_for_update())
            if not grant:
                raise GameError("Выданный доступ не найден", 404)
            if grant.used_at is not None:
                raise GameError("Использованный доступ нельзя забрать", 409)
            session.delete(grant)
            available = session.scalar(select(func.count()).select_from(UserAccessGrant).where(
                UserAccessGrant.user_id == user_id,
                UserAccessGrant.used_at.is_(None),
            ))
            return dict(available=int(available))

    def create_room(self, data):
        defaults = dict(
            duration_minutes=self.settings.room_duration_minutes,
            questions_count=self.settings.questions_per_game,
            question_time_limit_seconds=self.settings.question_time_limit_seconds,
            max_points_per_question=self.settings.max_points_per_question,
            min_correct_points=self.settings.min_correct_points,
            no_penalty_seconds=0,
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
