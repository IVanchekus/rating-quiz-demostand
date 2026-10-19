import hmac
import logging
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import SessionLocal
from app.schemas import CategoryInput, QuestionInput, RoomInput, RoomPatch, RoomQuestionsInput
from app.services.admin import AdminService
from app.services.game import GameError, GameService
from app.services.leaderboard import LeaderboardService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(sessions=SessionLocal, settings=None):
    settings = settings or get_settings()
    app = FastAPI(title="Питерский мостик IT Challenge", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in settings.cors_origins.split(",") if s.strip()],
                       allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type"])
    admin = AdminService(sessions, settings)
    public = LeaderboardService(sessions, settings)
    game = GameService(sessions)
    # Per-process, bounded local limiter. Deployment runs one API process; proxy adds a global cap.
    requests = defaultdict(deque)
    mutex = Lock()

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            key = (request.client.host if request.client else "unknown", request.url.path.startswith("/api/admin"))
            now = time.monotonic()
            with mutex:
                for old in list(requests):
                    if not requests[old] or requests[old][-1] < now - 60:
                        del requests[old]
                bucket = requests[key]
                while bucket and bucket[0] <= now - 60:
                    bucket.popleft()
                if len(bucket) >= (120 if key[1] else 300):
                    return JSONResponse({"detail": "Слишком много запросов. Попробуйте через минуту"}, status_code=429, headers={"Retry-After": "60"})
                bucket.append(now)
        return await call_next(request)

    @app.exception_handler(GameError)
    async def game_error(_, error):
        return JSONResponse({"detail": error.message}, status_code=error.status_code)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_, error):
        logging.getLogger(__name__).warning("database_constraint_conflict")
        return JSONResponse({"detail": "Конфликт данных: запись уже существует или используется"}, status_code=409)

    @app.get("/api/health")
    def health():
        with sessions() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/api/rooms/active")
    def active_rooms():
        return public.rooms(active_only=True)

    @app.get("/api/rooms")
    def public_rooms():
        return public.rooms()

    @app.get("/api/rooms/{identifier}")
    def room(identifier: str):
        return public.room(identifier)

    @app.get("/api/rooms/{identifier}/leaderboard")
    def leaderboard(identifier: str):
        return public.leaderboard(identifier)

    @app.get("/api/rooms/{identifier}/stats")
    def stats(identifier: str):
        return public.stats(identifier)

    def authenticate(authorization: str = Header(default="")):
        if len(settings.admin_secret) < 32 or settings.admin_secret.startswith("replace"):
            raise HTTPException(503, "Задайте ADMIN_SECRET: минимум 32 случайных символа")
        expected = f"Bearer {settings.admin_secret}"
        if not hmac.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(401, "Неверный ключ администратора", headers={"WWW-Authenticate": "Bearer"})

    router = APIRouter(prefix="/api/admin", dependencies=[Depends(authenticate)])

    @router.get("/rooms")
    def admin_rooms():
        return public.rooms(admin=True)

    @router.get("/rooms/{room_id}")
    def admin_room(room_id: int):
        return public.room(room_id, admin=True)

    @router.post("/rooms", status_code=201)
    def create_room(data: RoomInput):
        return public.room(admin.create_room(data), admin=True)

    @router.patch("/rooms/{room_id}")
    def update_room(room_id: int, data: RoomPatch):
        admin.update_room(room_id, data)
        return public.room(room_id, admin=True)

    @router.post("/rooms/{room_id}/start")
    def start_room(room_id: int):
        admin.start_room(room_id)
        return public.room(room_id, admin=True)

    @router.post("/rooms/{room_id}/finish")
    def finish_room(room_id: int):
        admin.finish_room(room_id)
        game.expire_due()
        return public.room(room_id, admin=True)

    @router.post("/rooms/{room_id}/questions")
    def assign_questions(room_id: int, data: RoomQuestionsInput):
        return {"assigned": admin.assign_questions(room_id, data)}

    @router.get("/categories")
    def categories():
        return admin.categories()

    @router.post("/categories", status_code=201)
    def create_category(data: CategoryInput):
        return {"id": admin.create_category(data)}

    @router.get("/questions")
    def questions(search: str | None = None):
        return admin.questions(search)

    @router.post("/questions", status_code=201)
    def create_question(data: QuestionInput):
        return {"id": admin.save_question(data)}

    @router.patch("/questions/{question_id}")
    def update_question(question_id: int, data: QuestionInput):
        return {"id": admin.save_question(data, question_id)}

    app.include_router(router)
    return app


app = create_app()
