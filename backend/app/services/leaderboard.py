from sqlalchemy import case, func, select

from app.models import Answer, Participant, ParticipantQuestion, Room, RoomQuestion, User, utcnow
from app.services.game import GameError, iso


class LeaderboardService:
    def __init__(self, sessions, settings, clock=utcnow):
        self.sessions, self.settings, self.clock = sessions, settings, clock

    def _room(self, session, identifier):
        # Codes contain URL-safe random text. Numeric identifiers address internal room IDs.
        room = session.scalar(select(Room).where(
            Room.id == int(identifier) if str(identifier).isdigit() else Room.join_code == str(identifier)
        ))
        if not room:
            raise GameError("Комната не найдена", 404)
        return room

    def _metadata(self, session, room):
        now = self.clock()
        return dict(
            id=room.id, public_code=room.join_code, title=room.title,
            status="finished" if room.status == "active" and now >= room.ends_at else room.status,
            starts_at=iso(room.starts_at), ends_at=iso(room.ends_at), server_time=iso(now),
            participants_count=session.scalar(select(func.count()).select_from(Participant).where(Participant.room_id == room.id)),
            questions_count=room.questions_count, max_points_per_question=room.max_points_per_question,
            join_url=f"https://t.me/{self.settings.telegram_bot_username}?start=room_{room.join_code}",
            public_url=f"{self.settings.public_base_url.rstrip('/')}/rooms/{room.join_code}",
        )

    def rooms(self, active_only=False, admin=False):
        with self.sessions() as session:
            statement = select(Room).order_by(Room.created_at.desc(), Room.id.desc())
            if active_only:
                statement = statement.where(Room.status == "active", Room.ends_at > self.clock())
            elif not admin:
                statement = statement.where(Room.status.in_(["active", "finished"]))
            return [self._metadata(session, room) for room in session.scalars(statement)]

    def room(self, identifier, admin=False):
        with self.sessions() as session:
            room = self._room(session, identifier)
            result = self._metadata(session, room)
            if admin:
                result.update(
                    duration_minutes=room.duration_minutes,
                    question_time_limit_seconds=room.question_time_limit_seconds,
                    min_correct_points=room.min_correct_points,
                    question_ids=list(session.scalars(select(RoomQuestion.question_id).where(RoomQuestion.room_id == room.id))),
                )
            return result

    def leaderboard(self, identifier):
        with self.sessions() as session:
            room = self._room(session, identifier)
            closed = select(
                ParticipantQuestion.participant_id.label("pid"),
                func.sum(case((
                    ParticipantQuestion.status.in_(["answered", "expired"]) & ParticipantQuestion.sent_at.is_not(None), 1,
                ), else_=0)).label("closed"),
            ).group_by(ParticipantQuestion.participant_id).subquery()
            speed = select(
                ParticipantQuestion.participant_id.label("pid"),
                func.sum(case((Answer.is_correct.is_(True), Answer.response_time_ms), else_=0)).label("time"),
            ).join(Answer).group_by(ParticipantQuestion.participant_id).subquery()
            completed = Participant.status == "completed"
            rows = session.execute(select(
                Participant, User, func.coalesce(closed.c.closed, 0),
            ).join(User).outerjoin(closed, closed.c.pid == Participant.id).outerjoin(speed, speed.c.pid == Participant.id).where(
                Participant.room_id == room.id,
            ).order_by(
                case((completed, 0), else_=1),
                case((completed, Participant.total_score), else_=0).desc(),
                case((completed, func.coalesce(speed.c.time, 0)), else_=0),
                Participant.joined_at, Participant.id,
            ))
            result = self._metadata(session, room)
            result["room_id"] = room.id
            result["leaderboard"] = [dict(
                place=place if p.status == "completed" else None, participant_id=p.id,
                display_name=f"@{u.username}" if u.username else (u.first_name.strip() or f"Участник {p.id}"),
                total_score=p.total_score if p.status == "completed" else None,
                closed_questions=int(count), completed=p.status == "completed",
                status="expired" if p.status == "playing" and (
                    (p.deadline_at is not None and p.deadline_at <= self.clock())
                    or (p.deadline_at is None and result["status"] in ("finished", "cancelled"))
                ) else p.status,
            ) for place, (p, u, count) in enumerate(rows, 1)]
            return result

    def stats(self, identifier):
        with self.sessions() as session:
            room = self._room(session, identifier)
            count, completed, average, maximum = session.execute(select(
                func.count(), func.sum(case((Participant.status == "completed", 1), else_=0)),
                func.avg(case((Participant.status == "completed", Participant.total_score), else_=None)),
                func.max(case((Participant.status == "completed", Participant.total_score), else_=None)),
            ).where(Participant.room_id == room.id)).one()
            return dict(participants_count=count, completed_count=int(completed or 0),
                        average_score=round(float(average or 0), 1), highest_score=maximum or 0)
