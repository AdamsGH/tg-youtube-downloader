import logging
import os
import time
import asyncio
import yt_dlp
from yt_dlp.utils import download_range_func
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes
from .utils import progress_hook

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

def cleanup_temp_files(pattern="temp_video*"):
    """Clean temporary files matching the pattern."""
    try:
        for file in os.listdir(TEMP_DIR):
            if file.startswith(pattern.replace("*", "")):
                try:
                    os.remove(os.path.join(TEMP_DIR, file))
                    logger.info(f"Temp file removed: {file}")
                except Exception as e:
                    logger.error(f"Error deleting {file}: {e}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

async def upload_to_tempsh(file_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Upload file to temp.sh and return the download URL."""
    try:
        # Upload initiated.
        message = await update.message.reply_text('Upload started...')
        message_id = message.message_id

        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as file:
                data = aiohttp.FormData()
                data.add_field('file', file, filename='video.mp4')
                for attempt in range(3):
                    try:
                        async with session.post('https://temp.sh/upload', data=data) as response:
                            if response.status == 200:
                                upload_url = await response.text()
                                logger.info(f"Upload successful, URL: {upload_url}")
                                return upload_url
                            elif response.status == 502 and attempt < 2:
                                logger.warning(f"Upload failed with status {response.status}. Retrying...")
                                await asyncio.sleep(5)
                            else:
                                logger.error(f"Upload failed with status {response.status}")
                                return None
                    except Exception as e:
                        if attempt < 2:
                            logger.warning(f"Upload error: {e}. Retrying...")
                            await asyncio.sleep(5)
                        else:
                            raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return None

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE, video_link: str, start_time: str = None, duration_seconds: int = None) -> bool:
    """Download video using yt_dlp; if start_time and duration_seconds are provided, download segment."""
    try:
        message = await update.message.reply_text('Download started...')
        message_id = message.message_id

        temp_video_path = os.path.join(TEMP_DIR, 'temp_video.mp4')
        start_seconds = None

        if start_time is not None and duration_seconds is not None:
            try:
                from .utils import convert_to_seconds
                start_seconds = convert_to_seconds(start_time)
                if start_seconds < 0:
                    raise ValueError("Start time cannot be negative")
                if duration_seconds <= 0:
                    raise ValueError("Duration must be positive")
                logger.info(f"Download segment: start_seconds={start_seconds}, duration_seconds={duration_seconds}")
            except Exception as e:
                logger.error(f"Time format error: {e}")
                await update.message.reply_text("Invalid time format. Use HH:MM:SS, MM:SS, or SS")
                return False

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': temp_video_path,
            'force_keyframes_at_cuts': True,
            'progress_hooks': [lambda d: progress_hook(d, update, context, message_id)],
            'force_generic_extractor': False,
            'fragment_retries': 10,
            'ignoreerrors': False,
            'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
            'postprocessor_args': ['-avoid_negative_ts', 'make_zero']
        }
        if start_seconds is not None and duration_seconds is not None:
            ydl_opts['download_ranges'] = download_range_func([], [[start_seconds, start_seconds + duration_seconds]])

        logger.info(f"Downloading video: {video_link}")
        if start_time is not None and duration_seconds is not None:
            logger.info(f"Segment parameters: start={start_time}, duration={duration_seconds}s")
        logger.info(f"yt_dlp options: {ydl_opts}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_link])

        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=message_id,
            text='Download complete.'
        )
        return True
    except Exception as e:
        logger.error(f"Download error: {e}")
        await update.message.reply_text(f"Download error: {e}")
        return False

async def send_or_upload_video(file_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send video directly if small, otherwise upload to temp.sh and send link."""
    try:
        file_size = os.path.getsize(file_path)
        if file_size < 50 * 1024 * 1024:
            with open(file_path, 'rb') as video_file:
                await context.bot.send_video(chat_id=update.message.chat_id, video=video_file)
            logger.info(f"Video sent to chat {update.message.chat_id}")
        else:
            upload_url = await upload_to_tempsh(file_path, update, context)
            if upload_url:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"File too large. Download from: {upload_url}"
                )
                logger.info(f"Video uploaded for chat {update.message.chat_id}")
            else:
                await context.bot.send_message(chat_id=update.message.chat_id, text="Upload failed.")
                logger.error(f"Upload failed for chat {update.message.chat_id}")
    except Exception as e:
        logger.error(f"Send video error: {e}")
        await update.message.reply_text(f"Send video error: {e}")
    finally:
        cleanup_temp_files()
