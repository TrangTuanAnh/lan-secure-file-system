#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is ready!"

echo "Waiting for Redis to be ready..."
until python -c "import redis,sys,os; r=redis.Redis(host=os.environ['REDIS_HOST'], port=int(os.environ['REDIS_PORT']), socket_connect_timeout=2); sys.exit(0 if r.ping() else 1)" 2>/dev/null; do
  echo "Redis is unavailable - sleeping"
  sleep 2
done

echo "Redis is ready!"

echo "Running database migrations..."
alembic upgrade head

echo "Starting Coordinator Server..."
exec python main.py
