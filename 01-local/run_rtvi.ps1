# Exit on any error
$ErrorActionPreference = "Stop"

# Build Docker image
Write-Host "Building Docker image..."
docker build -t rtvi-unified:latest -f Dockerfile .

# Run Docker container
Write-Host "Running Docker container..."

# Create a Docker network if it doesn't already exist
try {
    docker network create rtvi-network
} catch {
    Write-Host "Network 'rtvi-network' already exists, continuing..."
}

# Run the unified container
docker run -d --name rtvi-unified --network rtvi-network -p 7860:7860 rtvi-unified:latest

Write-Host "RTVI services are running locally. Access the runner on http://localhost:7860"
