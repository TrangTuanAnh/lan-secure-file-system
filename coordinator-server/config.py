"""Configuration loader for Coordinator Server."""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration."""
    host: str
    port: int
    name: str
    user: str
    password: str
    pool_size: int
    # mTLS to PostgreSQL
    sslmode: str = "disable"
    sslcert: Optional[str] = None
    sslkey: Optional[str] = None
    sslrootcert: Optional[str] = None


@dataclass
class RedisConfig:
    """Redis configuration."""
    host: str
    port: int
    password: Optional[str]
    pool_size: int
    # mTLS to Redis
    ssl_enabled: bool = False
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    ssl_ca: Optional[str] = None


@dataclass
class ServerConfig:
    """Server ports and timeouts configuration."""
    client_port: int
    storage_port: int
    notification_port: int
    session_ttl_seconds: int
    upload_ticket_ttl_seconds: int
    download_ticket_ttl_seconds: int
    upload_chunk_size: int
    storage_node_heartbeat_interval: int
    storage_node_timeout: int
    storage_node_secret: str
    client_max_workers: int
    storage_max_workers: int
    upload_slot_ttl_seconds: int
    storage_min_free_bytes: int
    # TLS for the client-facing plane (port 8080) only. The storage-node
    # control plane (8081) stays plaintext — it talks to the Java node over the
    # internal network.
    client_tls_enabled: bool
    client_tls_cert: str
    client_tls_key: str
    # mTLS for the storage-node control plane (8081): require + verify a client
    # cert from the storage node against the internal CA.
    storage_tls_enabled: bool
    storage_tls_cert: str
    storage_tls_key: str
    storage_tls_ca: str


@dataclass
class Config:
    """Main configuration container."""
    database: DatabaseConfig
    redis: RedisConfig
    server: ServerConfig


def load_config() -> Config:
    """Load configuration from environment variables with defaults."""
    
    # Database configuration
    database = DatabaseConfig(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        name=os.getenv('DB_NAME', 'coordinator'),
        user=os.getenv('DB_USER', 'coordinator_user'),
        password=os.getenv('DB_PASSWORD', 'secure_password'),
        pool_size=int(os.getenv('DB_POOL_SIZE', '20')),
        sslmode=os.getenv('DB_SSLMODE', 'disable'),
        sslcert=os.getenv('DB_SSLCERT', '/app/certs/internal/coordinator.crt'),
        sslkey=os.getenv('DB_SSLKEY', '/app/certs/internal/coordinator.key'),
        sslrootcert=os.getenv('DB_SSLROOTCERT', '/app/certs/internal/ca.crt'),
    )
    
    # Redis configuration
    redis = RedisConfig(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', '6379')),
        password=os.getenv('REDIS_PASSWORD', None),
        pool_size=int(os.getenv('REDIS_POOL_SIZE', '10')),
        ssl_enabled=os.getenv('REDIS_SSL', 'false').lower() in ('1', 'true', 'yes', 'on'),
        ssl_cert=os.getenv('REDIS_SSL_CERT', '/app/certs/internal/coordinator.crt'),
        ssl_key=os.getenv('REDIS_SSL_KEY', '/app/certs/internal/coordinator.key'),
        ssl_ca=os.getenv('REDIS_SSL_CA', '/app/certs/internal/ca.crt'),
    )
    
    # Server configuration
    server = ServerConfig(
        client_port=int(os.getenv('SERVER_CLIENT_PORT', '8080')),
        storage_port=int(os.getenv('SERVER_STORAGE_PORT', '8081')),
        notification_port=int(os.getenv('SERVER_NOTIFICATION_PORT', '8082')),
        session_ttl_seconds=int(os.getenv('SESSION_TTL_SECONDS', '86400')),
        upload_ticket_ttl_seconds=int(os.getenv('UPLOAD_TICKET_TTL_SECONDS', '1800')),
        download_ticket_ttl_seconds=int(os.getenv('DOWNLOAD_TICKET_TTL_SECONDS', '900')),
        upload_chunk_size=int(os.getenv('UPLOAD_CHUNK_SIZE', '524288')),
        storage_node_heartbeat_interval=int(os.getenv('STORAGE_NODE_HEARTBEAT_INTERVAL', '30')),
        storage_node_timeout=int(os.getenv('STORAGE_NODE_TIMEOUT', '90')),
        storage_node_secret=os.getenv('STORAGE_NODE_SECRET', 'change-this-secret-in-production'),
        client_max_workers=int(os.getenv('CLIENT_MAX_WORKERS', '8')),
        storage_max_workers=int(os.getenv('STORAGE_MAX_WORKERS', '4')),
        upload_slot_ttl_seconds=int(os.getenv('UPLOAD_SLOT_TTL_SECONDS', '60')),
        storage_min_free_bytes=int(os.getenv('STORAGE_MIN_FREE_BYTES', '0')),
        client_tls_enabled=os.getenv('CLIENT_TLS_ENABLED', 'false').lower() in ('1', 'true', 'yes', 'on'),
        client_tls_cert=os.getenv('CLIENT_TLS_CERT', '/app/certs/server.crt'),
        client_tls_key=os.getenv('CLIENT_TLS_KEY', '/app/certs/server.key'),
        storage_tls_enabled=os.getenv('STORAGE_TLS_ENABLED', 'false').lower() in ('1', 'true', 'yes', 'on'),
        storage_tls_cert=os.getenv('STORAGE_TLS_CERT', '/app/certs/internal/coordinator.crt'),
        storage_tls_key=os.getenv('STORAGE_TLS_KEY', '/app/certs/internal/coordinator.key'),
        storage_tls_ca=os.getenv('STORAGE_TLS_CA', '/app/certs/internal/ca.crt'),
    )
    
    return Config(database=database, redis=redis, server=server)
