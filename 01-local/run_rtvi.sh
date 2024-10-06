#!/bin/bash

# Exit script on any error
set -e

# Build Docker images
echo "Building Docker images..."
docker build -t rtvi-bot:latest -f bot/Dockerfile ./bot
docker build -t rtvi-runner:latest -f runner/Dockerfile ./runner

# Run Docker containers
echo "Running Docker containers..."
docker network create rtvi-network || true # Create a network if it doesn't already exist

docker run -d --name rtvi-bot --network rtvi-network rtvi-bot:latest
docker run -d --name rtvi-runner --network rtvi-network -p 7860:7860 rtvi-runner:latest

echo "RTVI services are running locally. Access the runner on http://localhost:7860"
