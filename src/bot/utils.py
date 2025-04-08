"""
Progress tracking and time conversion utilities.

This module provides utilities for tracking download/upload progress,
converting time formats, and managing progress updates to Telegram messages.
"""
import time
import re
from typing import Dict, Any, Tuple, Optional, Union, Match
from dataclasses import dataclass
from queue import Queue, Full

from telegram import Update
from telegram.ext import Application
from tqdm import tqdm

from config.logging import configure_logger
from config.constants import PROGRESS_UPDATE_INTERVAL, PROGRESS_QUEUE_SIZE

logger = configure_logger(__name__)

@dataclass
class ProgressUpdate:
    """
    Progress update data structure.
    
    Stores information about a progress update to be sent to a Telegram chat.
    """
    chat_id: int
    message_id: int
    text: str
    timestamp: float

class ProgressManager:
    """
    Manages progress update queues for multiple downloads/uploads.
    
    This class handles rate-limited progress updates to avoid flooding
    the Telegram API with too many message edits.
    """
    def __init__(self, update_interval: float = PROGRESS_UPDATE_INTERVAL):
        """
        Initialize the progress manager.
        
        Args:
            update_interval: Minimum time between updates in seconds
        """
        self._queues: Dict[Tuple[int, int], Queue[ProgressUpdate]] = {}
        self._last_updates: Dict[Tuple[int, int], float] = {}
        self._update_interval = update_interval

    def get_queue(self, chat_id: int, message_id: int) -> Queue[ProgressUpdate]:
        """
        Get or create a progress queue for a specific chat message.
        
        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to update
            
        Returns:
            Queue for the specified chat and message
        """
        key = (chat_id, message_id)
        if key not in self._queues:
            self._queues[key] = Queue(maxsize=PROGRESS_QUEUE_SIZE)
        return self._queues[key]

    def put_update(self, update: ProgressUpdate) -> bool:
        """
        Add a rate-limited update to the queue.
        
        Updates are only added if sufficient time has passed since the last update
        for the same chat/message.
        
        Args:
            update: Progress update to add
            
        Returns:
            True if update was added, False if skipped due to rate limiting or queue full
        """
        key = (update.chat_id, update.message_id)
        last_update = self._last_updates.get(key, 0)
        
        if (update.timestamp - last_update) >= self._update_interval:
            queue = self.get_queue(update.chat_id, update.message_id)
            try:
                queue.put_nowait(update)
                self._last_updates[key] = update.timestamp
                return True
            except Full:
                logger.warning(f"Progress queue full for {key}, skipping update")
                return False
        return False

    def remove_queue(self, chat_id: int, message_id: int) -> None:
        """
        Remove a completed download queue.
        
        Args:
            chat_id: Telegram chat ID
            message_id: Message ID
        """
        key = (chat_id, message_id)
        self._queues.pop(key, None)
        self._last_updates.pop(key, None)

    def get_all_queues(self) -> Dict[Tuple[int, int], Queue[ProgressUpdate]]:
        """
        Get all active progress queues.
        
        Returns:
            Dictionary of all queues, keyed by (chat_id, message_id)
        """
        return dict(self._queues)

# Global progress manager instance
progress_manager = ProgressManager()

def extract_timestamp_from_url(url: str) -> int:
    """
    Extract timestamp from YouTube URL.
    
    Supports various YouTube timestamp formats:
    - t=XX or start=XX parameter (seconds)
    - t=XXmYYs format (minutes and seconds)
    - t=XXhYYmZZs format (hours, minutes, seconds)
    
    Args:
        url: YouTube URL to parse
        
    Returns:
        Timestamp in seconds, or 0 if no timestamp found
    """
    try:
        # Match t=XX or start=XX parameter (seconds)
        time_param = re.search(r'[?&](t|start)=(\d+)', url)
        if time_param:
            return int(time_param.group(2))
            
        # Match t=XXmYYs format (minutes and seconds)
        time_param = re.search(r'[?&]t=(\d+)m(\d+)s', url)
        if time_param:
            minutes = int(time_param.group(1))
            seconds = int(time_param.group(2))
            return minutes * 60 + seconds
            
        # Match t=XXhYYmZZs format (hours, minutes, seconds)
        time_param = re.search(r'[?&]t=(\d+)h(\d+)m(\d+)s', url)
        if time_param:
            hours = int(time_param.group(1))
            minutes = int(time_param.group(2))
            seconds = int(time_param.group(3))
            return hours * 3600 + minutes * 60 + seconds
            
        return 0
    except (ValueError, AttributeError) as e:
        logger.debug(f"Error extracting timestamp from URL: {e}")
        return 0

def convert_to_seconds(time_str: str) -> int:
    """
    Parse time string to seconds.
    
    Supports formats:
    - HH:MM:SS (hours:minutes:seconds)
    - MM:SS (minutes:seconds)
    - SS (seconds)
    
    Args:
        time_str: Time string to convert
        
    Returns:
        Time in seconds
        
    Raises:
        ValueError: If the time format is invalid
    """
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
    """
    Progress bar with Telegram updates.
    
    Tracks progress of uploads/downloads and sends updates to Telegram.
    """
    def __init__(self, total: int, update: Update, message_id: int):
        """
        Initialize progress tracking.
        
        Args:
            total: Total size in bytes
            update: Telegram update object
            message_id: Message ID to update with progress
        """
        self.bar = tqdm(total=total, unit='B', unit_scale=True)
        self.update = update
        self.message_id = message_id
        self.last_percentage: Optional[int] = None

    def update_progress(self, current: int) -> None:
        """
        Update progress and notify Telegram.
        
        Updates the progress bar and sends a rate-limited update to Telegram.
        
        Args:
            current: Current progress in bytes
        """
        self.bar.update(current - self.bar.n)
        
        # Calculate percentage for progress reporting
        percentage = int(current / self.bar.total * 100) if self.bar.total > 0 else 0
        
        # Only send updates when percentage changes or complete
        is_complete = current >= self.bar.total
        percentage_changed = self.last_percentage != percentage
        
        if is_complete or percentage_changed:
            self.last_percentage = percentage
            
            text = 'Upload complete.' if is_complete else f'Upload: {percentage}%'
            progress_manager.put_update(ProgressUpdate(
                chat_id=self.update.message.chat_id,
                message_id=self.message_id,
                text=text,
                timestamp=time.time()
            ))

    def close(self) -> None:
        """
        Close progress bar and clean up resources.
        """
        self.bar.close()

async def create_callback(encoder: Any, update: Update, message_id: int):
    """
    Create upload progress callback for aiohttp.
    
    Args:
        encoder: Encoder object with length information
        update: Telegram update object
        message_id: Message ID to update with progress
        
    Returns:
        Async callback function for monitoring upload progress
    """
    progress = ProgressBar(encoder.len, update, message_id)
    
    async def callback(monitor):
        progress.update_progress(monitor.bytes_read)
    
    return callback

def progress_hook(d: Dict[str, Any], update: Update, message_id: int) -> None:
    """
    Track and report download progress for yt-dlp.
    
    Args:
        d: Progress dictionary from yt-dlp
        update: Telegram update object
        message_id: Message ID to update with progress
    """
    if d['status'] == 'downloading':
        try:
            # Try to get percentage from yt-dlp progress info
            percent = d.get('_percent_str', '').strip()
            if percent:
                # Remove ANSI escape codes
                percent = re.sub(r'\x1b\[.*?m', '', percent)
                
                # Try to get downloaded bytes and total bytes for more precise tracking
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                
                # Create progress text
                if total > 0:
                    percentage = downloaded / total * 100
                    text = f'Download: {percentage:.1f}%'
                else:
                    text = f'Download: {percent}'
                
                progress_manager.put_update(ProgressUpdate(
                    chat_id=update.message.chat_id,
                    message_id=message_id,
                    text=text,
                    timestamp=time.time()
                ))
        except Exception as e:
            logger.error(f"Progress hook error: {e}")
            logger.debug(f"Progress data: {d}")

async def process_progress_updates(application: Application) -> None:
    """
    Send queued progress updates to Telegram.
    
    This function is called periodically to process all pending progress
    updates across all active downloads/uploads.
    
    Args:
        application: Telegram application instance
    """
    try:
        for (chat_id, message_id), q in progress_manager.get_all_queues().items():
            try:
                # Process all updates in the queue
                updates_processed = 0
                while not q.empty():
                    update = q.get_nowait()
                    try:
                        await application.bot.edit_message_text(
                            chat_id=update.chat_id,
                            message_id=update.message_id,
                            text=update.text
                        )
                        updates_processed += 1
                    except Exception as e:
                        logger.error(f"Failed to send progress update: {e}")
                
                if updates_processed > 0:
                    logger.debug(f"Processed {updates_processed} updates for chat {chat_id}, message {message_id}")
                    
            except Exception as e:
                logger.error(f"Error processing queue for {chat_id}, {message_id}: {e}")
    except Exception as e:
        logger.error(f"Progress update processing error: {e}")
        logger.exception("Detailed progress processing error:")
