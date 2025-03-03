import os
import asyncio
import yt_dlp
import aiohttp
from typing import Optional
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

from telegram import Update
from telegram.ext import ContextTypes

from .utils import progress_hook, convert_to_seconds, progress_manager
from .logger_config import setup_logger
from .video_config import (
    get_ydl_opts, TEMP_DIR, MAX_DIRECT_UPLOAD_SIZE, 
    UPLOAD_CONFIG
)

logger = setup_logger(__name__)

class VideoProcessingError(Exception):
    """Base exception for video processing errors."""
    pass

class DownloadError(VideoProcessingError):
    """Raised when video download fails."""
    pass

class UploadError(VideoProcessingError):
    """Raised when video upload fails."""
    pass

def ensure_temp_dir():
    """Ensure temporary directory exists."""
    Path(TEMP_DIR).mkdir(exist_ok=True)

def generate_temp_filename(user_id: int) -> str:
    """Generate unique temporary filename based on user ID and timestamp."""
    timestamp = int(asyncio.get_event_loop().time() * 1000)
    return f"temp_video_{user_id}_{timestamp}.mp4"

def get_temp_path(filename: str) -> str:
    """Get full path for temporary file."""
    return str(Path(TEMP_DIR) / filename)

def cleanup_temp_file(filepath: str) -> None:
    """Clean specific temporary file."""
    try:
        file = Path(filepath)
        if file.exists():
            file.unlink()
            logger.info(f"Removed temp file: {file}")
    except Exception as e:
        logger.error(f"Error deleting {filepath}: {e}")

async def upload_to_tempsh(file_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Upload file to temp.sh and return the download URL."""
    message = await update.message.reply_text('Upload started...')
    
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as file:
            data = aiohttp.FormData()
            data.add_field('file', file, filename='video.mp4')
            
            for attempt in range(UPLOAD_CONFIG['max_retries']):
                try:
                    async with session.post(UPLOAD_CONFIG['upload_url'], data=data) as response:
                        if response.status == 200:
                            upload_url = await response.text()
                            logger.info(f"Upload successful: {upload_url}")
                            return upload_url
                        elif response.status == 502 and attempt < UPLOAD_CONFIG['max_retries'] - 1:
                            logger.warning(f"Upload failed (attempt {attempt + 1})")
                            await asyncio.sleep(UPLOAD_CONFIG['retry_delay'])
                        else:
                            raise UploadError(f"Upload failed with status {response.status}")
                except Exception as e:
                    if attempt < UPLOAD_CONFIG['max_retries'] - 1:
                        logger.warning(f"Upload error (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(UPLOAD_CONFIG['retry_delay'])
                    else:
                        raise UploadError(f"Upload failed after {UPLOAD_CONFIG['max_retries']} attempts: {e}")
    
    raise UploadError("Upload failed: maximum retries exceeded")

async def download_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_link: str,
    start_time: Optional[str] = None,
    duration_seconds: Optional[int] = None
) -> tuple[bool, str]:
    """Download video using yt-dlp with optional time range."""
    ensure_temp_dir()
    message = await update.message.reply_text('Download started...')
    message_id = message.message_id

    try:
        temp_filename = generate_temp_filename(update.effective_user.id)
        temp_video_path = get_temp_path(temp_filename)
        start_seconds = None

        if start_time and duration_seconds:
            try:
                start_seconds = convert_to_seconds(start_time)
                if start_seconds < 0:
                    raise ValueError("Start time cannot be negative")
                if duration_seconds <= 0:
                    raise ValueError("Duration must be positive")
                logger.info(f"Download segment: start={start_seconds}s, duration={duration_seconds}s")
            except ValueError as e:
                raise DownloadError(f"Invalid time format: {e}")

        ydl_opts = get_ydl_opts(
            temp_video_path,
            lambda d: progress_hook(d, update, context, message_id),
            start_seconds,
            duration_seconds
        )

        logger.info(f"Downloading: {video_link}")
        
        # Запускаем yt-dlp в отдельном потоке
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,  # использовать ThreadPoolExecutor по умолчанию
            lambda: yt_dlp.YoutubeDL(ydl_opts).download([video_link])
        )

        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=message_id,
            text='Download complete.'
        )
        progress_manager.remove_queue(update.message.chat_id, message_id)
        return True, temp_video_path

    except Exception as e:
        progress_manager.remove_queue(update.message.chat_id, message_id)
        raise DownloadError(f"Download failed: {e}")

async def send_or_upload_video(
    file_path: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Send video directly if small, otherwise upload to temp.sh and send link."""
    try:
        file_size = os.path.getsize(file_path)
        
        if file_size < MAX_DIRECT_UPLOAD_SIZE:
            # Отправляем видео напрямую
            with open(file_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.message.chat_id,
                    video=video_file
                )
            logger.info(f"Video sent directly to chat {update.message.chat_id}")
        else:
            # Загружаем на temp.sh в отдельном потоке
            loop = asyncio.get_event_loop()
            upload_task = asyncio.create_task(upload_to_tempsh(file_path, update, context))
            upload_url = await upload_task
            
            if upload_url:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"File too large for direct upload. Download from: {upload_url}"
                )
                logger.info(f"Video link sent to chat {update.message.chat_id}")
            else:
                raise UploadError("Failed to get upload URL")
                
    except Exception as e:
        raise VideoProcessingError(f"Failed to send video: {e}")
    finally:
        cleanup_temp_file(file_path)
