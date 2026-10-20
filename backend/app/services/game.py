"""Game operations shared by Telegram and the worker.

All progress mutations lock participant first, assignment second. Wall clock is read
after acquiring locks. Room administration never waits for a room lock from a game
operation, so closing a room and processing a callback cannot deadlock each other.
"""
import logging
import secrets
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import (
    Answer, Participant, ParticipantQuestion, Question, QuestionOption, Room, RoomQuestion, User, UserAccessGrant, utcnow,
)
from app.services.scoring import calculate_points

log = logging.getLogger(__name__)


class GameError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def iso(value):
    return value.isoformat(timespec="milliseconds") + "Z" if value else None


def room_is_open(room, now):
    return room.status == "active" and room.starts_at <= now < room.ends_at


class GameService:
    def __init__(self, sessions, clock=utcnow):
        self.sessions = sessions
        self.clock = clock

    def _participant(self, session, participant_id, telegram_id=None):
        participant = session.scalar(
            select(Participant).where(Participant.id == participant_id).with_for_update()
        )
        if not participant:
            raise GameError("Участие не найдено", 404)
        user = session.get(User, participant.user_id)
        if telegram_id is not None and user.telegram_id != telegram_id:
            raise GameError("Этот вопрос принадлежит другому участнику", 403)
        return participant

    def _assignment(self, session, assignment_id, telegram_id):
        participant_id = session.scalar(
            select(ParticipantQuestion.participant_id).where(ParticipantQuestion.id == assignment_id)
        )
        if participant_id is None:
            raise GameError("Вопрос не найден", 404)
        participant = self._participant(session, participant_id, telegram_id)
        assignment = session.scalar(
            select(ParticipantQuestion).where(ParticipantQuestion.id == assignment_id).with_for_update()
        )
        return participant, assignment

    def _sync_deadlines(self, session, participant, room, now):
        if participant.status != "playing":
            return
        if participant.deadline_at is not None:
            attempt_open = now < participant.deadline_at
        else:
            attempt_open = room_is_open(room, now)
        if not attempt_open:
            participant.status = "expired"
            participant.completed_at = now
            for item in session.scalars(select(ParticipantQuestion).where(
                ParticipantQuestion.participant_id == participant.id,
                ParticipantQuestion.status.in_(["pending", "active"]),
            ).with_for_update()):
                item.status = "expired"
                item.completed_at = now
                item.delivery_token = None
                item.delivery_lease_until = None
            log.info("participant_closed participant=%s", participant.id)
            return
        # A question's expires_at is a scoring threshold, not an answer cutoff.
        # Only the room deadline closes an unanswered question and its buttons.

    def _view(self, session, participant, assignment=None):
        session.flush()
        room = session.get(Room, participant.room_id)
        user = session.get(User, participant.user_id)
        closed = session.scalar(select(func.count()).select_from(ParticipantQuestion).where(
            ParticipantQuestion.participant_id == participant.id,
            ParticipantQuestion.status.in_(["answered", "expired"]),
            ParticipantQuestion.sent_at.is_not(None),
        ))
        result = {
            "participant_id": participant.id, "telegram_id": user.telegram_id,
            "status": participant.status, "total_score": participant.total_score,
            "closed_questions": closed, "questions_count": room.questions_count,
            "maximum_score": room.questions_count * room.max_points_per_question,
            "room_title": room.title,
        }
        if participant.status != "playing":
            return result
        if assignment is None:
            assignment = session.scalar(select(ParticipantQuestion).where(
                ParticipantQuestion.participant_id == participant.id,
                ParticipantQuestion.position == participant.current_question_number,
            ))
        question = session.get(Question, assignment.question_id)
        options = list(session.scalars(select(QuestionOption).where(
            QuestionOption.question_id == question.id,
        ).order_by(QuestionOption.sort_order)))
        result.update({
            "assignment_id": assignment.id, "position": assignment.position,
            "question_status": assignment.status, "text": question.text,
            "time_limit_seconds": question.time_limit_seconds or room.question_time_limit_seconds,
            "expires_at": iso(assignment.expires_at),
            "message_id": assignment.telegram_message_id,
            "max_points": room.max_points_per_question,
        })
        if assignment.status in ("pending", "active"):
            result["options"] = [{"id": o.id, "text": o.text} for o in options]
        else:
            answer = session.scalar(select(Answer).where(Answer.participant_question_id == assignment.id))
            result.update({
                "explanation": question.explanation,
                "correct_option": next(o.text for o in options if o.is_correct),
                "selected_option": next((o.text for o in options if answer and o.id == answer.selected_option_id), None),
                "is_correct": bool(answer and answer.is_correct),
                "points": answer.points_awarded if answer else 0,
            })
        return result

    def enroll(self, join_code, telegram_id, first_name, username=None, last_name=None):
        with self.sessions.begin() as session:
            # The room lock serializes two registrations before a participant exists.
            room = session.scalar(select(Room).where(Room.join_code == join_code).with_for_update())
            if not room:
                raise GameError("Комната не найдена. Откройте ссылку из QR-кода", 404)
            user = session.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
            now = self.clock()
            if user:
                user.username, user.first_name, user.last_name = username, first_name, last_name
                attempts = list(session.scalars(select(Participant).where(
                    Participant.room_id == room.id, Participant.user_id == user.id,
                ).order_by(Participant.joined_at.desc(), Participant.id.desc()).with_for_update()))
                current = next((attempt for attempt in attempts if attempt.status == "playing"), None)
                if current:
                    self._sync_deadlines(session, current, room, now)
                    return self._view(session, current)
            else:
                attempts = []
                if not room_is_open(room, now):
                    raise GameError("Комната ещё не началась" if room.status == "draft" else "Комната завершена")
            question_ids = list(session.scalars(select(Question.id).join(RoomQuestion).where(
                RoomQuestion.room_id == room.id, Question.is_active.is_(True),
            ).order_by(Question.id)))
            if len(question_ids) < room.questions_count:
                raise GameError("Не удалось подготовить вопросы; обратитесь к организатору")
            if not user:
                # Cross-room registrations of the same Telegram account may be concurrent.
                values = dict(telegram_id=telegram_id, first_name=first_name, username=username, last_name=last_name)
                if session.bind.dialect.name == "mysql":
                    stmt = mysql_insert(User).values(**values)
                    session.execute(stmt.on_duplicate_key_update(
                        first_name=first_name, username=username, last_name=last_name,
                    ))
                else:
                    stmt = sqlite_insert(User).values(**values)
                    session.execute(stmt.on_conflict_do_update(index_elements=["telegram_id"], set_=values))
                user = session.scalar(select(User).where(User.telegram_id == telegram_id).with_for_update())
                attempts = list(session.scalars(select(Participant).where(
                    Participant.room_id == room.id, Participant.user_id == user.id,
                ).order_by(Participant.joined_at.desc(), Participant.id.desc()).with_for_update()))
                current = next((attempt for attempt in attempts if attempt.status == "playing"), None)
                if current:
                    self._sync_deadlines(session, current, room, now)
                    return self._view(session, current)

            # Existing users need an unused administrator grant for every room after their first.
            # The user row is locked above, so two simultaneous enrollments cannot spend one grant twice.
            has_previous_participation = session.scalar(select(Participant.id).where(
                Participant.user_id == user.id,
            ).limit(1)) is not None
            grant = None
            if has_previous_participation and not attempts and room.status != "draft":
                grant = session.scalar(select(UserAccessGrant).where(
                    UserAccessGrant.user_id == user.id, UserAccessGrant.used_at.is_(None),
                ).order_by(UserAccessGrant.id).limit(1).with_for_update())
            if attempts:
                self._sync_deadlines(session, attempts[0], room, now)
                return self._view(session, attempts[0])
            if has_previous_participation and not grant:
                if not room_is_open(room, now):
                    raise GameError("Комната ещё не началась" if room.status == "draft" else "Комната завершена")
                raise GameError("Для участия в новой комнате организатор должен выдать повторный доступ")
            if not room_is_open(room, now) and not grant:
                raise GameError("Комната ещё не началась" if room.status == "draft" else "Комната завершена")
            participant = Participant(
                room_id=room.id, user_id=user.id, joined_at=now,
                deadline_at=now + timedelta(minutes=room.duration_minutes) if grant else None,
            )
            session.add(participant)
            session.flush()
            chosen = secrets.SystemRandom().sample(question_ids, room.questions_count)
            session.add_all([ParticipantQuestion(participant_id=participant.id, question_id=q, position=i)
                             for i, q in enumerate(chosen, 1)])
            if grant:
                grant.used_at, grant.participant_id = now, participant.id
            log.info("participant_enrolled participant=%s room=%s", participant.id, room.id)
            return self._view(session, participant)

    def resume(self, telegram_id, participant_id=None):
        with self.sessions.begin() as session:
            if participant_id is None:
                participant_id = session.scalar(select(Participant.id).join(User).where(
                    User.telegram_id == telegram_id,
                ).order_by(Participant.joined_at.desc(), Participant.id.desc()).limit(1))
            if participant_id is None:
                return None
            participant = self._participant(session, participant_id, telegram_id)
            self._sync_deadlines(session, participant, session.get(Room, participant.room_id), self.clock())
            return self._view(session, participant)

    def reserve_delivery(self, telegram_id, assignment_id):
        with self.sessions.begin() as session:
            participant, item = self._assignment(session, assignment_id, telegram_id)
            now = self.clock()
            self._sync_deadlines(session, participant, session.get(Room, participant.room_id), now)
            if participant.status != "playing" or item.position != participant.current_question_number:
                return None
            if item.status != "pending" or (item.delivery_lease_until and item.delivery_lease_until > now):
                return None
            item.delivery_token = secrets.token_hex(16)
            item.delivery_lease_until = now + timedelta(seconds=60)
            return item.delivery_token

    def confirm_delivery(self, telegram_id, assignment_id, token, message_id):
        with self.sessions.begin() as session:
            participant, item = self._assignment(session, assignment_id, telegram_id)
            now = self.clock()
            room = session.get(Room, participant.room_id)
            self._sync_deadlines(session, participant, room, now)
            if item.status != "pending" or item.delivery_token != token:
                return False
            question = session.get(Question, item.question_id)
            item.sent_at = now
            attempt_deadline = participant.deadline_at or room.ends_at
            item.expires_at = min(now + timedelta(seconds=question.time_limit_seconds or room.question_time_limit_seconds), attempt_deadline)
            item.telegram_message_id = message_id
            item.status = "active"
            item.delivery_token = None
            item.delivery_lease_until = None
            log.info("question_sent assignment=%s", item.id)
            return True

    def release_delivery(self, telegram_id, assignment_id, token):
        with self.sessions.begin() as session:
            _, item = self._assignment(session, assignment_id, telegram_id)
            if item.delivery_token == token:
                item.delivery_token = None
                item.delivery_lease_until = None

    def submit_answer(self, telegram_id, assignment_id, option_id):
        with self.sessions.begin() as session:
            participant, item = self._assignment(session, assignment_id, telegram_id)
            room = session.get(Room, participant.room_id)
            now = self.clock()
            self._sync_deadlines(session, participant, room, now)
            option = session.get(QuestionOption, option_id)
            if not option or option.question_id != item.question_id:
                raise GameError("Недопустимый вариант ответа", 400)
            if item.status in ("answered", "expired") or participant.status != "playing":
                return self._view(session, participant, item)
            if item.status != "active" or item.position != participant.current_question_number:
                raise GameError("Вопрос ещё не выдан. Повторите /start")
            elapsed = max(0, int((now - item.sent_at).total_seconds() * 1000))
            question = session.get(Question, item.question_id)
            points = calculate_points(
                correct=option.is_correct, elapsed_ms=elapsed,
                limit_seconds=question.time_limit_seconds or room.question_time_limit_seconds,
                maximum=room.max_points_per_question, minimum=room.min_correct_points,
            )
            session.add(Answer(
                participant_question_id=item.id, selected_option_id=option.id,
                is_correct=option.is_correct, response_time_ms=elapsed, points_awarded=points, answered_at=now,
            ))
            item.status = "answered"
            item.completed_at = now
            participant.total_score += points
            log.info("answer_recorded assignment=%s points=%s", item.id, points)
            return self._view(session, participant, item)

    def next_question(self, telegram_id, assignment_id):
        with self.sessions.begin() as session:
            participant, item = self._assignment(session, assignment_id, telegram_id)
            room = session.get(Room, participant.room_id)
            now = self.clock()
            self._sync_deadlines(session, participant, room, now)
            if participant.status != "playing":
                return self._view(session, participant)
            # A callback from an older result restores the current question without advancing.
            if item.position < participant.current_question_number:
                return self._view(session, participant)
            if item.position != participant.current_question_number or item.status not in ("answered", "expired"):
                raise GameError("Сначала ответьте на текущий вопрос")
            item.result_notified_at = now
            if item.position == room.questions_count:
                participant.status = "completed"
                participant.completed_at = now
            else:
                participant.current_question_number += 1
            return self._view(session, participant)

    def expire_due(self):
        with self.sessions() as session:
            now = self.clock()
            ids = list(session.scalars(select(Participant.id).join(Room).where(
                Participant.status == "playing", or_(
                    and_(Participant.deadline_at.is_not(None), Participant.deadline_at <= now),
                    and_(Participant.deadline_at.is_(None), or_(Room.status != "active", Room.ends_at <= now)),
                ),
            )))
        for participant_id in sorted(set(ids)):
            with self.sessions.begin() as session:
                participant = self._participant(session, participant_id)
                self._sync_deadlines(session, participant, session.get(Room, participant.room_id), self.clock())
        with self.sessions.begin() as session:
            rooms = list(session.scalars(select(Room).where(Room.status == "active", Room.ends_at <= self.clock()).with_for_update()))
            for room in rooms:
                room.status = "finished"
                log.info("room_finished room=%s", room.id)

    def pending_notifications(self):
        with self.sessions() as session:
            results = list(session.execute(select(ParticipantQuestion.id, User.telegram_id).join(
                Participant, Participant.id == ParticipantQuestion.participant_id,
            ).join(User).where(
                Participant.status == "playing",
                ParticipantQuestion.position == Participant.current_question_number,
                ParticipantQuestion.status.in_(["answered", "expired"]),
                ParticipantQuestion.result_notified_at.is_(None),
            )))
            finals = list(session.execute(select(Participant.id, User.telegram_id).join(User).where(
                Participant.status.in_(["expired", "completed"]), Participant.final_notified_at.is_(None),
            )))
            return {"results": results, "finals": finals}

    def mark_notified(self, telegram_id, *, assignment_id=None, participant_id=None):
        with self.sessions.begin() as session:
            if assignment_id:
                _, item = self._assignment(session, assignment_id, telegram_id)
                item.result_notified_at = self.clock()
            else:
                participant = self._participant(session, participant_id, telegram_id)
                participant.final_notified_at = self.clock()

    def question_state(self, telegram_id, assignment_id):
        with self.sessions.begin() as session:
            participant, item = self._assignment(session, assignment_id, telegram_id)
            self._sync_deadlines(session, participant, session.get(Room, participant.room_id), self.clock())
            return self._view(session, participant, item)
