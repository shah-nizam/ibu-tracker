from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base
from core.config import get_settings


def _normalize_database_url(db_url: str) -> str:
    # Railway and some providers expose postgres://, while SQLAlchemy expects postgresql://.
    if db_url.startswith("postgres://"):
        db_url = "postgresql://" + db_url[len("postgres://") :]

    # Ensure SQLAlchemy uses psycopg v3; plain postgresql:// defaults to psycopg2.
    if db_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + db_url[len("postgresql://") :]

    return db_url


def _build_engine():
    settings = get_settings()
    db_url = _normalize_database_url(settings.database_url)

    if db_url.startswith("sqlite:///"):
        db_file = db_url.replace("sqlite:///", "", 1)
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(db_url, connect_args={"check_same_thread": False})

    return create_engine(db_url, pool_pre_ping=True)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()
