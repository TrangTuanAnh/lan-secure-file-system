#!/bin/bash
# Setup script for Coordinator Server

set -e

echo "=== Coordinator Server Setup ==="

# Check Python version
echo "Checking Python version..."
python3 --version

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit .env with your database and Redis credentials"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env with your database and Redis credentials"
echo "2. Make sure PostgreSQL and Redis are running"
echo "3. Run database migrations: alembic upgrade head"
echo "4. Start the server: python main.py"
echo ""
