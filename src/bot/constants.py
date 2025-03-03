from typing import Final

# Command messages
UNAUTHORIZED_MESSAGE: Final = 'Unauthorized.'
HELP_TEXT: Final = (
    "Commands:\n"
    "/start - Start bot\n"
    "/cut <video_link> <start_time> <end_time> - Cut video (time format: HH:MM:SS, MM:SS, or SS)\n"
    "/download <video_link> - Download video\n"
    "/help - Show this message"
)

# Usage messages
CUT_USAGE: Final = 'Usage: /cut <video_link> <start_time> <end_time>'
DOWNLOAD_USAGE: Final = 'Usage: /download <video_link>'
SELECT_COMMAND: Final = 'Select command:'

# Error messages
TIME_ERROR: Final = "Time error: {}. Use HH:MM:SS, MM:SS, or SS format."
CUT_ERROR: Final = "Cut error: {}"
DOWNLOAD_ERROR: Final = "Download error: {}"

# Progress messages
CUTTING_VIDEO: Final = "Cutting video from {} to {} (Duration: {})"
