#!/bin/bash
set -e

echo "Pulling latest changes from Git..."
git pull

echo "Building Docker image..."
docker compose build --no-cache

echo "Starting Docker container..."
docker compose up -d

echo "Update and deployment complete!"