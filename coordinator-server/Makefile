.PHONY: help setup install migrate test run clean build up down logs logs-coordinator logs-db logs-redis db-shell redis-cli restart

help:
	@echo "Coordinator Server - Available Commands"
	@echo "========================================"
	@echo "Local Development:"
	@echo "  make setup           - Create virtual environment and install dependencies"
	@echo "  make install         - Install dependencies only"
	@echo "  make migrate         - Run database migrations"
	@echo "  make test            - Test database and Redis connections"
	@echo "  make run             - Start the coordinator server"
	@echo "  make clean           - Remove virtual environment and cache files"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make build           - Build the Coordinator Docker image"
	@echo "  make up              - Start all services with docker-compose"
	@echo "  make down            - Stop all services"
	@echo "  make logs            - Show logs from all services"
	@echo "  make logs-coordinator - Show only Coordinator logs"
	@echo "  make logs-db         - Show only PostgreSQL logs"
	@echo "  make logs-redis      - Show only Redis logs"
	@echo "  make db-shell        - Open PostgreSQL shell for debugging"
	@echo "  make redis-cli       - Open Redis CLI for debugging"
	@echo "  make restart         - Restart the Coordinator service"

setup:
	@echo "Setting up Coordinator Server..."
	@bash setup.sh

install:
	@echo "Installing dependencies..."
	@pip install -r requirements.txt

migrate:
	@echo "Running database migrations..."
	@alembic upgrade head

test:
	@echo "Testing setup..."
	@python test_setup.py

run:
	@echo "Starting Coordinator Server..."
	@python main.py

clean:
	@echo "Cleaning up..."
	@rm -rf venv __pycache__ *.pyc
	@find . -type d -name __pycache__ -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@docker-compose down -v 2>/dev/null || true
	@docker rmi coordinator-server_coordinator 2>/dev/null || true
	@echo "Cleanup complete"

# Docker targets
build:
	@echo "Building Coordinator Docker image..."
	@docker-compose build

up:
	@echo "Starting all services with docker-compose..."
	@docker-compose up -d
	@echo "Services started. Use 'make logs' to view logs."

down:
	@echo "Stopping all services..."
	@docker-compose down

logs:
	@echo "Showing logs from all services (Ctrl+C to exit)..."
	@docker-compose logs -f

logs-coordinator:
	@echo "Showing Coordinator logs (Ctrl+C to exit)..."
	@docker-compose logs -f coordinator

logs-db:
	@echo "Showing PostgreSQL logs (Ctrl+C to exit)..."
	@docker-compose logs -f postgres

logs-redis:
	@echo "Showing Redis logs (Ctrl+C to exit)..."
	@docker-compose logs -f redis

db-shell:
	@echo "Opening PostgreSQL shell..."
	@docker-compose exec postgres psql -U coordinator_user -d coordinator

redis-cli:
	@echo "Opening Redis CLI..."
	@docker-compose exec redis redis-cli

restart:
	@echo "Restarting Coordinator service..."
	@docker-compose restart coordinator
	@echo "Coordinator service restarted."
