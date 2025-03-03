import logging
import time
import re
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from collections import deque

from telegram import Update
from telegram.ext import ContextTypes
from tqdm import tqdm

from .logger_config import setup_logger

logger = setup_logger(__name__)

@dataclass
class ProgressUpdate:
    """Structure for progress update information."""
    chat_id: int
    message_id: int
    text: str
    timestamp: float

class ProgressQueue:
    """Thread-safe queue for progress updates with rate limiting."""
    def __init__(self, maxsize: int = 100):
        self._queue = asyncio.Queue(maxsize=maxsize)
        self._last_updates: Dict[int, ProgressUpdate] = {}
        self._update_interval = 5.0  # seconds

    async def put(self, update: ProgressUpdate) -> None:
        """Add update to queue with rate limiting."""
        message_key = (update.chat_id, update.message_id)
        last_update = self._last_updates.get(message_key)
        
        if not last_update or (update.timestamp - last_update.timestamp) >= self._update_interval:
            try:
                await self._queue.put(update)
                self._last_updates[message_key] = update
            except asyncio.QueueFull:
                logger.warning("Progress queue full, skipping update")

    async def get(self) -> Optional[ProgressUpdate]:
        """Get next update from queue."""
        try:
            return await self._queue.get()
        except Exception as e:
            logger.error(f"Error getting from queue: {e}")
            return None

    def task_done(self) -> None:
        """Mark task as done."""
        self._queue.task_done()

# Global progress queue instance
progress_queue = ProgressQueue()

def convert_to_seconds(time_str: str) -> int:
    """Convert time string (HH:MM:SS, MM:SS, or SS) to seconds."""
    try:
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 1:
            return parts[0]
        else:
            raise ValueError("Invalid time format")
    except (ValueError, TypeError) as e:
        raise ValueError("Invalid time format. Use HH:MM:SS, MM:SS, or SS.") from e

class ProgressBar:
    """Wrapper for tqdm progress bar with Telegram updates."""
    def __init__(self, total: int, update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
        self.bar = tqdm(total=total, unit='B', unit_scale=True)
        self.update = update
        self.context = context
        self.message_id = message_id
        self.upload_complete = False

    async def update_progress(self, current: int) -> None:
        """Update progress bar and send updates to Telegram."""
        self.bar.update(current - self.bar.n)
        
        if current == self.bar.total and not self.upload_complete:
            await self._send_progress_update('Upload complete.')
            self.upload_complete = True
        else:
            await self._send_progress_update(f'Upload: {current / self.bar.total * 100:.2f}%')

    async def _send_progress_update(self, text: str) -> None:
        """Send progress update to queue."""
        try:
            await progress_queue.put(ProgressUpdate(
                chat_id=self.update.message.chat_id,
                message_id=self.message_id,
                text=text,
                timestamp=time.time()
            ))
        except Exception as e:
            logger.error(f"Error sending progress update: {e}")

    def close(self) -> None:
        """Close progress bar."""
        self.bar.close()

async def create_callback(encoder: Any, update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Create upload progress callback using ProgressBar."""
    progress = ProgressBar(encoder.len, update, context, message_id)
    
    async def callback(monitor):
        await progress.update_progress(monitor.bytes_read)
    
    return callback

def progress_hook(d: Dict[str, Any], update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    """Track download progress and queue updates."""
    if d['status'] == 'downloading':
        try:
            percent = d.get('_percent_str', '').strip()
            if percent:
                # Remove ANSI escape codes
                percent = re.sub(r'\x1b\[.*?m', '', percent)
                asyncio.create_task(progress_queue.put(ProgressUpdate(
                    chat_id=update.message.chat_id,
                    message_id=message_id,
                    text=f'Download: {percent}',
                    timestamp=time.time()
                )))
        except Exception as e:
            logger.error(f"Progress hook error: {e}")

async def process_progress_updates(application) -> None:
    """Process queued progress updates."""
    while True:
        try:
            update = await progress_queue.get()
            if update:
                try:
                    await application.bot.edit_message_text(
                        chat_id=update.chat_id,
                        message_id=update.message_id,
                        text=update.text
                    )
                except Exception as e:
                    logger.error(f"Failed to send progress update: {e}")
                finally:
                    progress_queue.task_done()
        except Exception as e:
            logger.error(f"Progress update processing error: {e}")
        await asyncio.sleep(0.1)
