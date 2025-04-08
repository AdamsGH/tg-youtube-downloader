"""
Constants configuration module.

This module defines all constant values used throughout the application,
organized by category for better maintainability.
"""
from typing import Final, Dict, Any, Literal
from pathlib import Path

# ===== Authentication =====
UNAUTHORIZED_MESSAGE: Final[str] = 'Unauthorized.'

# ===== Command Messages =====
HELP_TEXT: Final[str] = (
    "Commands:\n"
    "/start - Start bot\n"
    "/cut <video_link> <start_time> <end_time> - Cut video (time format: HH:MM:SS, MM:SS, or SS)\n"
    "/download <video_link> - Download video\n"
    "/help - Show this message"
)

# ===== Usage Messages =====
CUT_USAGE: Final[str] = 'Usage: /cut <video_link> <start_time> <end_time>'
DOWNLOAD_USAGE: Final[str] = 'Usage: /download <video_link>'
SELECT_COMMAND: Final[str] = 'Select command:'

# ===== Error Messages =====
TIME_ERROR: Final[str] = "Time error: {}. Use HH:MM:SS, MM:SS, or SS format."
CUT_ERROR: Final[str] = "Cut error: {}"
DOWNLOAD_ERROR: Final[str] = "Download error: {}"

# ===== Progress Messages =====
CUTTING_VIDEO: Final[str] = "Cutting video from {} to {} (Duration: {})"
ENTER_END_TIME: Final[str] = "Enter end time (format: HH:MM:SS, MM:SS or SS):"
PROCESSING_VIDEO: Final[str] = "Processing video..."

# ===== File Handling =====
# Directory for temporary files
TEMP_DIR: Final[Path] = Path("temp")

# Maximum size for direct upload to Telegram (50MB)
MAX_DIRECT_UPLOAD_SIZE: Final[int] = 50 * 1024 * 1024  

# ===== Upload Configuration =====
UPLOAD_CONFIG: Final[Dict[str, Any]] = {
    'max_retries': 3,      # Number of retry attempts
    'retry_delay': 5,      # Seconds between retries
    'upload_url': 'https://temp.sh/upload'  # External upload service URL
}

# ===== Progress Update Configuration =====
# Minimum time between progress updates (seconds)
PROGRESS_UPDATE_INTERVAL: Final[float] = 5.0  

# Maximum number of queued progress updates per message
PROGRESS_QUEUE_SIZE: Final[int] = 100
