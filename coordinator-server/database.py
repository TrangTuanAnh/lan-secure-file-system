"""PostgreSQL database connection and utilities."""
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from typing import Optional, Any, Dict, List
from contextlib import contextmanager
from config import DatabaseConfig
from logging_config import get_logger

logger = get_logger(__name__)


class Database:
    """PostgreSQL database connection pool manager."""
    
    def __init__(self, config: DatabaseConfig):
        """
        Initialize database connection pool.
        
        Args:
            config: Database configuration
        """
        self.config = config
        self._pool: Optional[pool.SimpleConnectionPool] = None
        
    def connect(self) -> None:
        """Create connection pool."""
        try:
            conn_kwargs = dict(
                minconn=1,
                maxconn=self.config.pool_size,
                host=self.config.host,
                port=self.config.port,
                database=self.config.name,
                user=self.config.user,
                password=self.config.password,
            )
            sslmode = getattr(self.config, 'sslmode', 'disable')
            if sslmode and sslmode != 'disable':
                # mTLS: present the coordinator client cert + verify the server
                # cert against the internal CA.
                conn_kwargs.update(
                    sslmode=sslmode,
                    sslcert=self.config.sslcert,
                    sslkey=self.config.sslkey,
                    sslrootcert=self.config.sslrootcert,
                )
            self._pool = psycopg2.pool.SimpleConnectionPool(**conn_kwargs)
            tls = f" (sslmode={sslmode})" if sslmode != 'disable' else ""
            logger.info(f"Database connection pool created (max={self.config.pool_size}){tls}")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise
    
    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            logger.info("Database connection pool closed")
    
    @contextmanager
    def get_connection(self):
        """
        Get a connection from the pool.
        
        Yields:
            Database connection with RealDictCursor
        """
        if not self._pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self):
        """
        Get a cursor from a pooled connection.
        
        Yields:
            Database cursor (RealDictCursor for dict-like results)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query string
            params: Query parameters
        
        Returns:
            List of result rows as dictionaries
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query.
        
        Args:
            query: SQL query string
            params: Query parameters
        
        Returns:
            Number of affected rows
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    
    def execute_insert_returning(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """
        Execute an INSERT query with RETURNING clause.
        
        Args:
            query: SQL query string with RETURNING clause
            params: Query parameters
        
        Returns:
            Inserted row as dictionary
        """
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()
