from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException

from core.config import get_settings
from db.session import init_db
from services.repository import Repository

app = FastAPI(title="Ibu Tracker API", version="0.1.0")
repo = Repository()


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/recent/{telegram_user_id}")
def recent(telegram_user_id: int, _: None = Depends(require_api_key)) -> dict[str, list[str]]:
    return repo.recent_summary(telegram_user_id, limit=10)
