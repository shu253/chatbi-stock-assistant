"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_project_path(value: str, default: str) -> Path:
    raw = Path(value or default).expanduser()
    return raw.resolve() if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()


def _get_tavily_key() -> str:
    """Read Tavily key from the process, then Windows user environment like the prototype."""
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if key or sys.platform != "win32":
        return key
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry_key:
            value, _ = winreg.QueryValueEx(registry_key, "TAVILY_API_KEY")
            return str(value).strip()
    except OSError:
        return ""


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings with secure local-development defaults."""

    dashscope_api_key: str
    tushare_token: str
    tavily_api_key: str
    enable_web_search: bool
    model: str
    db_path: Path
    runtime_dir: Path
    log_level: str
    max_query_rows: int = 2_000
    max_sql_length: int = 10_000
    query_timeout_seconds: float = 5.0
    image_retention_hours: int = 24
    image_retention_count: int = 100


def get_settings() -> Settings:
    return Settings(
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
        tushare_token=os.getenv("TUSHARE_TOKEN", "").strip(),
        tavily_api_key=_get_tavily_key(),
        enable_web_search=_as_bool(os.getenv("CHATBI_ENABLE_WEB_SEARCH"), default=True),
        model=os.getenv("CHATBI_MODEL", "qwen-turbo").strip() or "qwen-turbo",
        db_path=_resolve_project_path(os.getenv("CHATBI_DB_PATH", ""), "data/stock.db"),
        runtime_dir=_resolve_project_path(os.getenv("CHATBI_RUNTIME_DIR", ""), "runtime/images"),
        log_level=os.getenv("CHATBI_LOG_LEVEL", "INFO").upper(),
    )
