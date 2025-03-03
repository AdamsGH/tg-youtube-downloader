"""Video download and processing operations."""
import os
import asyncio
import yt_dlp
import aiohttp
from typing import Optional
from pathlib import Path
from dataclasses import dataclass

from telegram import Update
from telegram.ext import ContextTypes

from config.logging import configure_logger
from config.constants import TEMP_DIR, MAX_DIRECT_UPLOAD_SIZE, UPLOAD_CONFIG
from config.video import get_download_options
from .utils import progress_hook, progress_manager, convert_to_seconds

logger = configure_logger(__name__)

@dataclass
class VideoProcessingResult:
    """Operation result with status and details."""
    success: bool
    file_path: str = ""
    error_message: str = ""

class VideoProcessingError(Exception):
    """Base video processing error."""
    pass

class DownloadError(VideoProcessingError):
    """Video download error."""
    pass

class UploadError(VideoProcessingError):
    """Video upload error."""
    pass

class VideoProcessor:
    """Video processing operations."""
    
    @staticmethod
    def ensure_temp_dir() -> None:
        """Create temp directory if not exists."""
        Path(TEMP_DIR).mkdir(exist_ok=True)

    @staticmethod
    def generate_temp_filename(user_id: int) -> str:
        """Generate unique filename for video."""
        timestamp = int(asyncio.get_event_loop().time() * 1000)
        return f"temp_video_{user_id}_{timestamp}.mp4"

    @staticmethod
    def get_temp_path(filename: str) -> str:
        """Get full temp file path."""
        return str(Path(TEMP_DIR) / filename)

    @staticmethod
    def cleanup_temp_file(filepath: str) -> None:
        """Remove temporary file."""
        try:
            file = Path(filepath)
            if file.exists():
                file.unlink()
                logger.info(f"Removed temp file: {file}")
        except Exception as e:
            logger.error(f"Error deleting {filepath}: {e}")

    @staticmethod
    async def upload_to_tempsh(
        file_path: str,
        update: Update
    ) -> str:
        """Upload file to temp.sh and return download URL."""
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

    @classmethod
    async def download_video(
        cls,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        video_link: str,
        start_time: Optional[str] = None,
        duration_seconds: Optional[int] = None
    ) -> VideoProcessingResult:
        """Download video using yt-dlp.
        
        Args:
            update: Telegram update object
            context: Bot context
            video_link: URL of video to download
            start_time: Start time for video cutting
            duration_seconds: Duration for video cutting
            
        Returns:
            VideoProcessingResult with download status and details
        """
        cls.ensure_temp_dir()
        message = await update.message.reply_text('Download started...')
        message_id = message.message_id

        try:
            temp_filename = cls.generate_temp_filename(update.effective_user.id)
            temp_video_path = cls.get_temp_path(temp_filename)

            # Convert start_time to seconds if provided
            start_seconds = None
            if start_time is not None:
                start_seconds = convert_to_seconds(start_time)

            ydl_opts = get_download_options(
                output_path=temp_video_path,
                progress_hook=lambda d: progress_hook(d, update, message_id),
                start_seconds=start_seconds,
                duration_seconds=duration_seconds
            )

            logger.info(f"Downloading: {video_link}")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(ydl_opts).download([video_link])
            )

            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=message_id,
                text='Download complete.'
            )
            progress_manager.remove_queue(update.message.chat_id, message_id)
            
            return VideoProcessingResult(success=True, file_path=temp_video_path)

        except Exception as e:
            progress_manager.remove_queue(update.message.chat_id, message_id)
            error_msg = f"Download failed: {str(e)}"
            return VideoProcessingResult(success=False, error_message=error_msg)

    @classmethod
    async def send_or_upload_video(
        cls,
        file_path: str,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send video directly or upload to temp.sh.
        
        Args:
            file_path: Path to video file
            update: Telegram update object
            context: Bot context
            
        Raises:
            VideoProcessingError: If sending/uploading fails
        """
        try:
            file_size = os.path.getsize(file_path)
            
            if file_size < MAX_DIRECT_UPLOAD_SIZE:
                with open(file_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=update.message.chat_id,
                        video=video_file
                    )
                logger.info(f"Video sent directly to chat {update.message.chat_id}")
            else:
                loop = asyncio.get_event_loop()
                upload_task = asyncio.create_task(cls.upload_to_tempsh(file_path, update))
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
            cls.cleanup_temp_file(file_path)
