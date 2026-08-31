from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    allowed_user_ids: str = ""
    timezone: str = "Asia/Singapore"
    database_url: str = "sqlite:///./data/ibu_tracker.db"
    api_key: Optional[str] = None

    glucose_low_mmol: float = 4.0
    glucose_high_mmol: float = 10.0
    bp_high_sys: int = 140
    bp_high_dia: int = 90
    bp_urgent_sys: int = 180
    bp_urgent_dia: int = 120

    @property
    def allowlist(self) -> set[int]:
        if not self.allowed_user_ids.strip():
            return set()
        output: set[int] = set()
        for item in self.allowed_user_ids.split(","):
            item = item.strip()
            if item:
                output.add(int(item))
        return output


@lru_cache
def get_settings() -> Settings:
    return Settings()
