# YT Cut Bot

## Description

YT Cut Bot is a Telegram bot that allows you to download videos from YouTube, trim them, and then either send them back on Telegram or upload them to temp.sh if the file size exceeds 200 MB.

## Dependencies

This bot uses the following libraries:

- `logging` for logging
- `time` for time-related operations
- `yt_dlp` for downloading videos from YouTube
- `subprocess` for executing shell commands
- `os` for file system operations
- `requests` for sending HTTP requests
- `telegram` for interacting with the Telegram API
- `re` for working with regular expressions
- `tqdm` for displaying download progress
- `requests_toolbelt` for handling multipart forms

## Installation

1. Clone this repository
```bash
git clone https://github.com/AdamsGH/tg-youtube-downloader
```
2. Provide .env vars 
3. Run docker compose