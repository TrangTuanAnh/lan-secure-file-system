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
from typing import FrozenSet


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
        if not ENV_FILE.exists():
            return

        # Fallback parser so the desktop client still honors coordinator-node/.env
        # even when python-dotenv is not installed in the local Python runtime.
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _get_str(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _get_str_alias(primary_key: str, alias_keys: tuple[str, ...], default: str) -> str:
    for key in (primary_key, *alias_keys):
        raw_value = os.getenv(key)
        if raw_value is not None and raw_value.strip():
            return raw_value.strip()
    return default


def _get_int_alias(primary_key: str, alias_keys: tuple[str, ...], default: int) -> int:
    for key in (primary_key, *alias_keys):
        raw_value = os.getenv(key)
        if raw_value is None or raw_value.strip() == "":
            continue
        try:
            return int(raw_value)
        except ValueError:
            print(f"[Config] Invalid int for {key}={raw_value!r}. Using default {default}.")
            return default
    return default


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


def _get_csv_set(key: str, default: set[str]) -> FrozenSet[str]:
    raw_value = os.getenv(key)
    if raw_value is None or raw_value.strip() == "":
        return frozenset(value.strip().lower() for value in default if value.strip())
    return frozenset(
        value.strip().lower()
        for value in raw_value.split(",")
        if value.strip()
    )


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

    # TLS to the coordinator (port 8080)
    backend_tls: bool
    backend_tls_cacert: str
    backend_tls_insecure: bool
    backend_tls_server_name: str

    notification_host: str
    notification_port: int

    storage_host: str
    storage_port: int
    admin_usernames: FrozenSet[str]

    def backend_kwargs(self) -> dict[str, int | str]:
        """Common backend connection settings for UI pages/workers."""
        return {
            "host": self.backend_host,
            "port": self.backend_port,
            "timeout": self.backend_timeout,
            "socket_timeout": self.backend_socket_timeout,
            "max_retries": self.backend_max_retries,
            "retry_delay": self.backend_retry_delay,
            "tls": self.backend_tls,
            "tls_cacert": self.backend_tls_cacert or None,
            "tls_insecure": self.backend_tls_insecure,
            "tls_server_name": self.backend_tls_server_name or None,
        }

    def is_admin_username(self, username: str) -> bool:
        return username.strip().lower() in self.admin_usernames

    def resolve_global_role(self, username: str, backend_role: str = "") -> str:
        normalized_backend_role = backend_role.strip().upper()
        if normalized_backend_role in {"ADMIN", "USER"}:
            return normalized_backend_role
        if self.is_admin_username(username):
            return "ADMIN"
        return "USER"

    @classmethod
    def load(cls) -> "AppConfig":
        _load_dotenv_if_available()

        return cls(
            app_env=_get_str("APP_ENV", "development"),
            app_debug=_get_bool("APP_DEBUG", True),

            backend_host=_get_str_alias("BACKEND_HOST", ("COORDINATOR_HOST",), "localhost"),
            backend_port=_get_int_alias("BACKEND_PORT", ("COORDINATOR_PORT",), 8080),
            backend_timeout=_get_int("BACKEND_TIMEOUT", 15),
            backend_socket_timeout=_get_int("BACKEND_SOCKET_TIMEOUT", 5),
            backend_max_retries=_get_int("BACKEND_MAX_RETRIES", 2),
            backend_retry_delay=_get_int("BACKEND_RETRY_DELAY", 1),

            backend_tls=_get_bool("BACKEND_TLS", False),
            backend_tls_cacert=_get_str(
                "BACKEND_TLS_CACERT", str(PROJECT_ROOT / "certs" / "server.crt")
            ),
            backend_tls_insecure=_get_bool("BACKEND_TLS_INSECURE", False),
            backend_tls_server_name=_get_str("BACKEND_TLS_SERVER_NAME", ""),

            notification_host=_get_str("NOTIFICATION_HOST", "localhost"),
            notification_port=_get_int("NOTIFICATION_PORT", 8082),

            storage_host=_get_str("STORAGE_HOST", "localhost"),
            storage_port=_get_int("STORAGE_PORT", 9001),
            admin_usernames=_get_csv_set("ADMIN_USERNAMES", {"admin"}),
        )


APP_CONFIG = AppConfig.load()
