# YT Cut Bot

A Telegram bot for downloading and cutting YouTube videos.

## Features

### Core Functionality
- Download videos from YouTube
- Cut videos by timestamps (HH:MM:SS, MM:SS, or SS format)
- Send videos directly via Telegram (if size < 50MB)
- Auto-upload to temp.sh for larger files
- Real-time download and upload progress tracking

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
/download https://youtu.be/example
/cut https://youtu.be/example 00:01:30 00:02:45
/cut https://youtu.be/example 1:30 2:45
/cut https://youtu.be/example 90 165
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
