"""
Video download and processing operations.

This module handles YouTube video downloading, processing, and uploading
to Telegram or external services when files are too large for direct upload.
"""
import os
import asyncio
import yt_dlp
import aiohttp
from typing import Optional, Dict, Any, Tuple, Union
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
    """
    Operation result with status and details.
    
    Stores the result of a video processing operation, including success status,
    file path (if successful), and error message (if failed).
    """
    success: bool
    file_path: str = ""
    error_message: str = ""

class VideoProcessingError(Exception):
    """
    Base video processing error.
    
    Parent class for all video processing related exceptions.
    """
    pass

class DownloadError(VideoProcessingError):
    """
    Video download error.
    
    Raised when a video download operation fails.
    """
    pass

class UploadError(VideoProcessingError):
    """
    Video upload error.
    
    Raised when a video upload operation fails.
    """
    pass

class VideoProcessor:
    """
    Video processing operations.
    
    This class provides methods for downloading, processing, and uploading videos,
    with support for progress tracking and error handling.
    """
    
    @staticmethod
    def ensure_temp_dir() -> Path:
        """
        Create temp directory if it doesn't exist.
        
        Returns:
            Path object for the temp directory
        """
        temp_dir = Path(TEMP_DIR)
        temp_dir.mkdir(exist_ok=True)
        return temp_dir

    @staticmethod
    def generate_temp_filename(user_id: int) -> str:
        """
        Generate unique filename for video.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Unique filename with timestamp
        """
        timestamp = int(asyncio.get_event_loop().time() * 1000)
        return f"temp_video_{user_id}_{timestamp}.mp4"

    @staticmethod
    def get_temp_path(filename: str) -> str:
        """
        Get full temp file path.
        
        Args:
            filename: Base filename
            
        Returns:
            Full path to file in temp directory
        """
        return str(Path(TEMP_DIR) / filename)

    @staticmethod
    def cleanup_temp_file(filepath: str) -> bool:
        """
        Remove temporary file.
        
        Args:
            filepath: Path to file to delete
            
        Returns:
            True if file was deleted successfully, False otherwise
        """
        try:
            file = Path(filepath)
            if file.exists():
                file.unlink()
                logger.info(f"Removed temp file: {file}")
                return True
            else:
                logger.debug(f"File not found for cleanup: {filepath}")
                return False
        except Exception as e:
            logger.error(f"Error deleting {filepath}: {e}")
            return False

    @staticmethod
    async def _handle_upload_attempt(
        session: aiohttp.ClientSession,
        data: aiohttp.FormData,
        attempt: int,
        max_retries: int,
        retry_delay: int
    ) -> str:
        """
        Handle a single upload attempt with retry logic.
        
        Args:
            session: aiohttp session
            data: Form data with file
            attempt: Current attempt number (0-based)
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
            
        Returns:
            Upload URL if successful
            
        Raises:
            UploadError: If upload fails
        """
        try:
            async with session.post(UPLOAD_CONFIG['upload_url'], data=data) as response:
                if response.status == 200:
                    upload_url = await response.text()
                    logger.info(f"Upload successful: {upload_url}")
                    return upload_url
                elif response.status == 502 and attempt < max_retries - 1:
                    logger.warning(f"Upload failed with 502 error (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    raise UploadError("Temporary server error, retrying")
                else:
                    raise UploadError(f"Upload failed with status {response.status}")
        except aiohttp.ClientError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Upload network error (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)
                raise UploadError(f"Network error: {e}")
            else:
                raise UploadError(f"Upload failed after {max_retries} attempts: {e}")
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Upload error (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)
                raise UploadError(f"Error: {e}")
            else:
                raise UploadError(f"Upload failed after {max_retries} attempts: {e}")

    @staticmethod
    async def upload_to_tempsh(
        file_path: str,
        update: Update
    ) -> str:
        """
        Upload file to temp.sh and return download URL.
        
        Args:
            file_path: Path to video file
            update: Telegram update object
            
        Returns:
            Download URL for the uploaded file
            
        Raises:
            UploadError: If upload fails after all retries
        """
        await update.message.reply_text('Upload started...')
        
        max_retries = UPLOAD_CONFIG['max_retries']
        retry_delay = UPLOAD_CONFIG['retry_delay']
        
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as file:
                data = aiohttp.FormData()
                data.add_field('file', file, filename='video.mp4')
                
                for attempt in range(max_retries):
                    try:
                        return await VideoProcessor._handle_upload_attempt(
                            session, data, attempt, max_retries, retry_delay
                        )
                    except UploadError as e:
                        if attempt == max_retries - 1:
                            raise
                        # Otherwise continue to next attempt
        
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
        """
        Download video using yt-dlp.
        
        Args:
            update: Telegram update object
            context: Bot context
            video_link: URL of video to download
            start_time: Start time for video cutting (in seconds or time format)
            duration_seconds: Duration for video cutting (in seconds)
            
        Returns:
            VideoProcessingResult with download status and details
        """
        cls.ensure_temp_dir()
        status_message = await update.message.reply_text('Download started...')
        message_id = status_message.message_id

        try:
            temp_filename = cls.generate_temp_filename(update.effective_user.id)
            temp_video_path = cls.get_temp_path(temp_filename)

            # Convert start_time to seconds if provided
            start_seconds = None
            if start_time is not None:
                try:
                    # Handle both integer strings and time format strings
                    start_seconds = int(start_time) if start_time.isdigit() else convert_to_seconds(start_time)
                except ValueError as e:
                    logger.error(f"Invalid start time format: {e}")
                    raise DownloadError(f"Invalid start time format: {e}")

            ydl_opts = get_download_options(
                output_path=temp_video_path,
                progress_hook=lambda d: progress_hook(d, update, message_id),
                start_seconds=start_seconds,
                duration_seconds=duration_seconds
            )

            logger.info(f"Downloading: {video_link} (start: {start_seconds}s, duration: {duration_seconds}s)")
            
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None,
                    lambda: yt_dlp.YoutubeDL(ydl_opts).download([video_link])
                )
            except yt_dlp.utils.DownloadError as e:
                raise DownloadError(f"YouTube download error: {e}")
            except Exception as e:
                raise DownloadError(f"Download error: {e}")

            # Verify the file exists and has content
            if not os.path.exists(temp_video_path) or os.path.getsize(temp_video_path) == 0:
                raise DownloadError("Download completed but file is missing or empty")

            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=message_id,
                text='Download complete.'
            )
            progress_manager.remove_queue(update.message.chat_id, message_id)
            
            return VideoProcessingResult(success=True, file_path=temp_video_path)

        except VideoProcessingError as e:
            progress_manager.remove_queue(update.message.chat_id, message_id)
            return VideoProcessingResult(success=False, error_message=str(e))
        except Exception as e:
            progress_manager.remove_queue(update.message.chat_id, message_id)
            logger.exception("Unexpected download error:")
            error_msg = f"Download failed: {str(e)}"
            return VideoProcessingResult(success=False, error_message=error_msg)

    @classmethod
    async def send_or_upload_video(
        cls,
        file_path: str,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Send video directly or upload to temp.sh if too large.
        
        Args:
            file_path: Path to video file
            update: Telegram update object
            context: Bot context
            
        Raises:
            VideoProcessingError: If sending/uploading fails
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                raise VideoProcessingError(f"Video file not found: {file_path}")
                
            file_size = os.path.getsize(file_path)
            logger.info(f"Video file size: {file_size / (1024 * 1024):.2f} MB")
            
            if file_size < MAX_DIRECT_UPLOAD_SIZE:
                # Send directly via Telegram
                try:
                    with open(file_path, 'rb') as video_file:
                        await context.bot.send_video(
                            chat_id=update.message.chat_id,
                            video=video_file,
                            supports_streaming=True
                        )
                    logger.info(f"Video sent directly to chat {update.message.chat_id}")
                except Exception as e:
                    raise VideoProcessingError(f"Failed to send video via Telegram: {e}")
            else:
                # Upload to external service
                try:
                    upload_task = asyncio.create_task(cls.upload_to_tempsh(file_path, update))
                    upload_url = await upload_task
                    
                    if upload_url:
                        file_size_mb = file_size / (1024 * 1024)
                        await context.bot.send_message(
                            chat_id=update.message.chat_id,
                            text=f"File too large for direct upload ({file_size_mb:.1f} MB). Download from: {upload_url}"
                        )
                        logger.info(f"Video link sent to chat {update.message.chat_id}")
                    else:
                        raise UploadError("Failed to get upload URL")
                except Exception as e:
                    raise VideoProcessingError(f"Failed to upload video: {e}")
                    
        except VideoProcessingError:
            # Re-raise VideoProcessingError without wrapping
            raise
        except Exception as e:
            raise VideoProcessingError(f"Failed to send video: {e}")
        finally:
            # Always clean up the temp file
            cleanup_success = cls.cleanup_temp_file(file_path)
            if not cleanup_success:
                logger.warning(f"Failed to clean up temporary file: {file_path}")
