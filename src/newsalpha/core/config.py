from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIGS_DIR = REPO_ROOT / "configs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: SecretStr = Field(default=SecretStr(""))

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: SecretStr | None = None
    langchain_project: str = "newsalpha"

    # Data APIs
    finnhub_api_key: SecretStr | None = None
    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    fred_api_key: SecretStr | None = None

    # Storage
    postgres_dsn: str = "postgresql+psycopg://newsalpha:newsalpha_dev@localhost:5432/newsalpha"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379/0"

    # Broker
    broker_mode: Literal["paper", "live"] = "paper"
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # LLM budget
    llm_daily_budget_usd: float = 20.0

    # App
    log_level: str = "INFO"
    environment: Literal["development", "production"] = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=8)
def load_yaml_config(name: str) -> dict:
    """Load a YAML file from configs/ by name (without extension)."""
    path = CONFIGS_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
