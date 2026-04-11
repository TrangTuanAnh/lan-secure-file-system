.PHONY: help setup install migrate test run clean

help:
	@echo "Coordinator Server - Available Commands"
	@echo "========================================"
	@echo "make setup      - Create virtual environment and install dependencies"
	@echo "make install    - Install dependencies only"
	@echo "make migrate    - Run database migrations"
	@echo "make test       - Test database and Redis connections"
	@echo "make run        - Start the coordinator server"
	@echo "make clean      - Remove virtual environment and cache files"

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
	@echo "Cleanup complete"
