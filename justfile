# Default task: run if no argument is provided.
default: run

# Build Docker images using docker-compose.
build:
	@echo "Building Docker containers..."
	docker compose build

# Run Docker containers in detached mode.
run:
	@echo "Starting Docker containers in detached mode..."
	docker compose up -d

# Stop and remove Docker containers.
stop:
	@echo "Stopping and removing Docker containers..."
	docker compose down

# Remove the specified Docker image.
rm:
	@echo "Removing Docker image: youtube-downloader-telegram..."
	docker rmi youtube-downloader-telegram

# Rebuild: stop containers, remove image, build images, then run containers.
rebuild: stop rm build run