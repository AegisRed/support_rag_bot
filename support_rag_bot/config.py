from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")

    gemini_generation_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-2"

    db_path: str = "data/support_rag.sqlite3"
    kb_source_sites: str = "https://help.northstar.test,https://billing.northstar.test,https://status.northstar.test"

    top_k: int = 4
    min_similarity_score: float = 0.72
    min_self_confidence: float = 0.78
    max_ticket_chars: int = 3500
    max_context_chars: int = 6000
    max_clarification_rounds: int = 2
    show_decision_details: bool = False
    log_level: str = "INFO"
    admin_user_ids: str = ""

    @property
    def db_path_obj(self) -> Path:
        return Path(self.db_path)

    @property
    def source_sites(self) -> list[str]:
        raw = [item.strip().rstrip("/") for item in self.kb_source_sites.split(",")]
        return [item for item in raw if item]

    @property
    def admin_ids(self) -> set[int]:
        items = [item.strip() for item in self.admin_user_ids.split(",") if item.strip()]
        return {int(item) for item in items}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    return settings
