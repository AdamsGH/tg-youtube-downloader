# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Insttall ffmpeg
RUN apt-get update && apt-get install -y ffmpeg --no-install-recommends

# Set work directory
WORKDIR /bot

# Install dependencies
COPY requirements.txt /bot/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /bot
COPY . /bot/

# Run the command to start your bot
CMD ["python", "main.py"]
