from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings


def make_engine(url):
    options = {"pool_pre_ping": True}
    if str(url).startswith("mysql"):
        options["isolation_level"] = "READ COMMITTED"
        options["connect_args"] = {"init_command": "SET time_zone = '+00:00'"}
    elif str(url).startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


engine = make_engine(get_settings().sqlalchemy_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
