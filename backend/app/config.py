from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "bridge_quiz"
    mysql_user: str = "bridge_quiz"
    mysql_password: str = "replace_me"
    telegram_bot_token: str = ""
    telegram_bot_username: str = "YourQuizBot"
    admin_secret: str = ""
    public_base_url: str = "http://localhost:8080"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    room_duration_minutes: int = Field(default=60, ge=1, le=1440)
    questions_per_game: int = Field(default=10, ge=1, le=100)
    question_time_limit_seconds: int = Field(default=30, ge=1, le=3600)
    max_points_per_question: int = Field(default=100, ge=1, le=10000)
    min_correct_points: int = Field(default=0, ge=0)
    question_expiration_check_seconds: float = Field(default=5, ge=0.2)

    @model_validator(mode="after")
    def validate_points(self):
        if self.min_correct_points > self.max_points_per_question:
            raise ValueError("MIN_CORRECT_POINTS exceeds MAX_POINTS_PER_QUESTION")
        return self

    @property
    def sqlalchemy_url(self):
        return self.database_url or URL.create(
            "mysql+pymysql", username=self.mysql_user, password=self.mysql_password,
            host=self.mysql_host, port=self.mysql_port, database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings():
    return Settings()
