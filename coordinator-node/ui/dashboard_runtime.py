"""Shared dashboard runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass

from config import APP_CONFIG
from network.backend_client_sdk import BackendConfig


@dataclass(frozen=True)
class DashboardRuntimeConfig:
    """Backend runtime settings shared across dashboard pages."""

    host: str = APP_CONFIG.backend_host
    port: int = APP_CONFIG.backend_port
    timeout: int = APP_CONFIG.backend_timeout
    socket_timeout: int = APP_CONFIG.backend_socket_timeout
    max_retries: int = APP_CONFIG.backend_max_retries
    retry_delay: int = APP_CONFIG.backend_retry_delay

    def to_backend_config(self) -> BackendConfig:
        return BackendConfig(
            host=self.host,
            port=self.port,
            timeout=self.timeout,
            socket_timeout=self.socket_timeout,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
        )


__all__ = ["DashboardRuntimeConfig"]
