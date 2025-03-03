import logging
import time
import re
import asyncio
import queue
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

class ProgressManager:
    """Manager for multiple progress queues."""
    def __init__(self):
        self._queues: Dict[tuple[int, int], queue.Queue] = {}
        self._last_updates: Dict[tuple[int, int], float] = {}
        self._update_interval = 5.0  # seconds

    def get_queue(self, chat_id: int, message_id: int) -> queue.Queue:
        """Get or create queue for specific chat and message."""
        key = (chat_id, message_id)
        if key not in self._queues:
            self._queues[key] = queue.Queue(maxsize=100)
        return self._queues[key]

    def put_update(self, update: ProgressUpdate) -> None:
        """Add update to appropriate queue with rate limiting."""
        key = (update.chat_id, update.message_id)
        last_update = self._last_updates.get(key, 0)
        
        if (update.timestamp - last_update) >= self._update_interval:
            queue = self.get_queue(update.chat_id, update.message_id)
            try:
                queue.put_nowait(update)
                self._last_updates[key] = update.timestamp
            except queue.Full:
                logger.warning(f"Progress queue full for {key}, skipping update")

    def remove_queue(self, chat_id: int, message_id: int) -> None:
        """Remove queue for completed download."""
        key = (chat_id, message_id)
        self._queues.pop(key, None)
        self._last_updates.pop(key, None)

    def get_all_queues(self) -> Dict[tuple[int, int], queue.Queue]:
        """Get all active queues."""
        return dict(self._queues)

# Global progress manager instance
progress_manager = ProgressManager()

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

    def update_progress(self, current: int) -> None:
        """Update progress bar and send updates to Telegram."""
        self.bar.update(current - self.bar.n)
        
        text = 'Upload complete.' if current == self.bar.total else f'Upload: {current / self.bar.total * 100:.2f}%'
        progress_manager.put_update(ProgressUpdate(
            chat_id=self.update.message.chat_id,
            message_id=self.message_id,
            text=text,
            timestamp=time.time()
        ))

    def close(self) -> None:
        """Close progress bar."""
        self.bar.close()

async def create_callback(encoder: Any, update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Create upload progress callback using ProgressBar."""
    progress = ProgressBar(encoder.len, update, context, message_id)
    
    async def callback(monitor):
        progress.update_progress(monitor.bytes_read)
    
    return callback

def progress_hook(d: Dict[str, Any], update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    """Track download progress and queue updates."""
    if d['status'] == 'downloading':
        try:
            percent = d.get('_percent_str', '').strip()
            if percent:
                # Remove ANSI escape codes
                percent = re.sub(r'\x1b\[.*?m', '', percent)
                progress_manager.put_update(ProgressUpdate(
                    chat_id=update.message.chat_id,
                    message_id=message_id,
                    text=f'Download: {percent}',
                    timestamp=time.time()
                ))
        except Exception as e:
            logger.error(f"Progress hook error: {e}")

async def process_progress_updates(application) -> None:
    """Process queued progress updates for all active downloads."""
    try:
        # Обработка всех активных очередей
        for (chat_id, message_id), q in progress_manager.get_all_queues().items():
            try:
                # Получаем все доступные обновления из очереди
                while not q.empty():
                    update = q.get_nowait()
                    try:
                        await application.bot.edit_message_text(
                            chat_id=update.chat_id,
                            message_id=update.message_id,
                            text=update.text
                        )
                    except Exception as e:
                        logger.error(f"Failed to send progress update: {e}")
            except Exception as e:
                logger.error(f"Error processing queue for {chat_id}, {message_id}: {e}")
    except Exception as e:
        logger.error(f"Progress update processing error: {e}")
