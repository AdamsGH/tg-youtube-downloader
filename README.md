# YT Cut Bot

A Telegram bot for downloading and cutting YouTube videos.

## Features

### Core Functionality
- Download videos from YouTube
- Cut videos by timestamps (HH:MM:SS, MM:SS, or SS format)
- Send videos directly via Telegram (if size < 50MB)
- Auto-upload to temp.sh for larger files
- Real-time download and upload progress tracking
- Smart link processing:
  - Auto-download when sending YouTube links
  - Auto-detect timestamps from YouTube URLs
  - Optional end time in the same message for quick cutting

### Security
- User authorization support
- Automatic temp file cleanup
- Graceful shutdown support

### Logging
- Download, cut, and upload operation logs
- Filtered technical messages from ffmpeg and yt-dlp
- Full error stack traces

## Requirements

- Telegram Bot Token
- List of allowed user IDs in .env file

## Commands

- `/start` - Start the bot
- `/help` - Show help message
- `/download <url>` - Download full video
- `/cut <url> <start_time> <end_time>` - Cut video segment

## Examples

```
# Using commands
/download https://youtu.be/example
/cut https://youtu.be/example 00:01:30 00:02:45
/cut https://youtu.be/example 1:30 2:45
/cut https://youtu.be/example 90 165

# Direct link processing
https://youtu.be/example                    # Downloads full video
https://youtu.be/example?t=90               # Asks for end time to cut
https://youtu.be/example?t=90 02:45         # Cuts from 1:30 to 2:45
https://youtu.be/example?start=90 165       # Cuts from 90s to 165s
```

## Project Structure

```
src/
├── bot/
│   ├── commands.py    # Command handlers
│   ├── utils.py       # Utility functions
│   └── video_handler.py # Video processing
├── config/
│   ├── constants.py   # Constants
│   ├── logging.py     # Logging setup
│   └── video.py       # Video config
└── main.py           # Entry point
```

## License

MIT
