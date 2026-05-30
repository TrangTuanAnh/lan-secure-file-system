#!/bin/bash

echo "Stopping local PostgreSQL service..."
sudo service postgresql stop

echo "Stopping old Docker containers..."
docker-compose down

echo "Starting LAN Secure File System..."
docker-compose up --build