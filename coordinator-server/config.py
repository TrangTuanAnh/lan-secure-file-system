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


@dataclass
class RedisConfig:
    """Redis configuration."""
    host: str
    port: int
    password: Optional[str]
    pool_size: int


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
        pool_size=int(os.getenv('DB_POOL_SIZE', '20'))
    )
    
    # Redis configuration
    redis = RedisConfig(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', '6379')),
        password=os.getenv('REDIS_PASSWORD', None),
        pool_size=int(os.getenv('REDIS_POOL_SIZE', '10'))
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
        storage_node_secret=os.getenv('STORAGE_NODE_SECRET', 'change-this-secret-in-production')
    )
    
    return Config(database=database, redis=redis, server=server)
