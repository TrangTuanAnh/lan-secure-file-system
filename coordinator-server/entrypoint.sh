#!/bin/bash
set -e

# Prepare PostgreSQL client TLS material. libpq requires the private key to be
# mode 0600 and owned by the running user; bind-mounted keys keep their host
# owner, so copy them into a process-owned location.
if [ "${DB_SSLMODE:-disable}" != "disable" ]; then
  cp "$DB_SSLCERT"     /tmp/pg-client.crt
  cp "$DB_SSLKEY"      /tmp/pg-client.key
  cp "$DB_SSLROOTCERT" /tmp/pg-ca.crt
  chmod 600 /tmp/pg-client.key
  export DB_SSLCERT=/tmp/pg-client.crt DB_SSLKEY=/tmp/pg-client.key DB_SSLROOTCERT=/tmp/pg-ca.crt
  export PGSSLMODE="$DB_SSLMODE" PGSSLCERT=/tmp/pg-client.crt PGSSLKEY=/tmp/pg-client.key PGSSLROOTCERT=/tmp/pg-ca.crt
  echo "PostgreSQL client mTLS prepared (sslmode=$DB_SSLMODE)"
fi

echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is ready!"

echo "Waiting for Redis to be ready..."
until python -c "
import redis, sys, os
kw = dict(host=os.environ['REDIS_HOST'], port=int(os.environ['REDIS_PORT']), socket_connect_timeout=2)
if os.environ.get('REDIS_SSL', 'false').lower() in ('1', 'true', 'yes', 'on'):
    kw.update(ssl=True, ssl_certfile=os.environ['REDIS_SSL_CERT'],
              ssl_keyfile=os.environ['REDIS_SSL_KEY'], ssl_ca_certs=os.environ['REDIS_SSL_CA'],
              ssl_cert_reqs='required')
sys.exit(0 if redis.Redis(**kw).ping() else 1)
" 2>/dev/null; do
  echo "Redis is unavailable - sleeping"
  sleep 2
done

echo "Redis is ready!"

echo "Running database migrations..."
alembic upgrade head

echo "Starting Coordinator Server..."
exec python main.py
