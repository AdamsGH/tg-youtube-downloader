import logging
import time
import re
import asyncio
from telegram import Update
from telegram.ext import ContextTypes, Application
from tqdm import tqdm

# Global queue for progress updates
progress_queue = asyncio.Queue()

def convert_to_seconds(time_str):
    """Convert a time string (HH:MM:SS, MM:SS, or SS) to seconds."""
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    else:
        raise ValueError("Invalid time format. Use HH:MM:SS, MM:SS, or SS.")

async def create_callback(encoder, update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Create an upload progress callback using tqdm."""
    bar = tqdm(total=encoder.len, unit='B', unit_scale=True)
    last_update_time = 0
    upload_complete = False

    async def callback(monitor):
        nonlocal last_update_time, upload_complete
        bar.update(monitor.bytes_read - bar.n)
        current_time = time.time()
        if current_time - last_update_time >= 5:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.message.chat_id,
                    message_id=message_id,
                    text=f'Upload: {bar.n / bar.total * 100:.2f}%'
                )
                last_update_time = current_time
            except Exception as e:
                logging.error(f"Progress update error: {e}")
        if bar.n == bar.total and not upload_complete:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.message.chat_id,
                    message_id=message_id,
                    text='Upload complete.'
                )
                upload_complete = True
            except Exception as e:
                logging.error(f"Completion update error: {e}")
    return callback

def progress_hook(d: dict, update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Track download progress and update message."""
    if d['status'] == 'downloading':
        current_time = time.time()
        if current_time - getattr(progress_hook, 'last_update_time', 0) >= 10:
            try:
                percent = d.get('_percent_str', '').strip()
                percent = re.sub(r'\x1b\[.*?m', '', percent)
                update_info = {
                    'chat_id': update.message.chat_id,
                    'message_id': message_id,
                    'text': f'Upload: {percent}'
                }
                try:
                    progress_queue.put_nowait(update_info)
                except asyncio.QueueFull:
                    logging.warning("Progress queue full")
                progress_hook.last_update_time = current_time
            except Exception as e:
                logging.error(f"Progress hook error: {e}")

progress_hook.last_update_time = 0

async def process_progress_updates(application):
    """Background task to update progress messages."""
    while True:
        try:
            update_info = await progress_queue.get()
            try:
                await application.bot.edit_message_text(
                    chat_id=update_info['chat_id'],
                    message_id=update_info['message_id'],
                    text=update_info['text']
                )
            except Exception as e:
                logging.error(f"Update send error: {e}")
            finally:
                progress_queue.task_done()
        except Exception as e:
            logging.error(f"Queue processing error: {e}")
        await asyncio.sleep(0.5)
