"""Application configuration loaded from .env.

This file centralizes runtime config so the app can switch between:
- local development: localhost
- LAN demo: server machine LAN IP

Usage:
    from config import AppConfig

    config = AppConfig.load()
    print(config.backend_host)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"


def _load_dotenv_if_available() -> None:
    """Load .env if python-dotenv is installed.

    The app still works without python-dotenv because os.environ/defaults
    are used as fallback.
    """
    try:
        from dotenv import load_dotenv

        if ENV_FILE.exists():
            load_dotenv(ENV_FILE)
    except ImportError:
        # python-dotenv is optional.
        # Install with: pip install python-dotenv
        pass


def _get_str(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _get_int(key: str, default: int) -> int:
    raw_value = os.getenv(key)

    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        return int(raw_value)
    except ValueError:
        print(f"[Config] Invalid int for {key}={raw_value!r}. Using default {default}.")
        return default


def _get_bool(key: str, default: bool) -> bool:
    raw_value = os.getenv(key)

    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the frontend app."""

    app_env: str
    app_debug: bool

    backend_host: str
    backend_port: int
    backend_timeout: int
    backend_socket_timeout: int
    backend_max_retries: int
    backend_retry_delay: int

    notification_host: str
    notification_port: int

    storage_host: str
    storage_port: int

    def backend_kwargs(self) -> dict[str, int | str]:
        """Common backend connection settings for UI pages/workers."""
        return {
            "host": self.backend_host,
            "port": self.backend_port,
            "timeout": self.backend_timeout,
            "socket_timeout": self.backend_socket_timeout,
            "max_retries": self.backend_max_retries,
            "retry_delay": self.backend_retry_delay,
        }

    @classmethod
    def load(cls) -> "AppConfig":
        _load_dotenv_if_available()

        return cls(
            app_env=_get_str("APP_ENV", "development"),
            app_debug=_get_bool("APP_DEBUG", True),

            backend_host=_get_str("BACKEND_HOST", "localhost"),
            backend_port=_get_int("BACKEND_PORT", 8080),
            backend_timeout=_get_int("BACKEND_TIMEOUT", 15),
            backend_socket_timeout=_get_int("BACKEND_SOCKET_TIMEOUT", 5),
            backend_max_retries=_get_int("BACKEND_MAX_RETRIES", 2),
            backend_retry_delay=_get_int("BACKEND_RETRY_DELAY", 1),

            notification_host=_get_str("NOTIFICATION_HOST", "localhost"),
            notification_port=_get_int("NOTIFICATION_PORT", 8082),

            storage_host=_get_str("STORAGE_HOST", "localhost"),
            storage_port=_get_int("STORAGE_PORT", 9001),
        )


APP_CONFIG = AppConfig.load()
