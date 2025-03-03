#!/usr/bin/env python3
from typing import List, Optional
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .utils import convert_to_seconds
from .video_handler import download_video, send_or_upload_video, cleanup_temp_files
from .logger_config import setup_logger
from .constants import (
    UNAUTHORIZED_MESSAGE, HELP_TEXT, CUT_USAGE, DOWNLOAD_USAGE,
    SELECT_COMMAND, TIME_ERROR, CUT_ERROR, DOWNLOAD_ERROR, CUTTING_VIDEO
)

logger = setup_logger(__name__)

class AuthError(Exception):
    """Raised when user authentication fails."""
    pass

def get_allowed_users() -> List[str]:
    """Get list of allowed user IDs from environment."""
    return os.getenv('ALLOWED_USER_IDS', '').split(',')

async def check_auth(update: Update) -> bool:
    """Check user authentication."""
    user_id = str(update.effective_user.id)
    if user_id not in get_allowed_users():
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return False
    return True

async def send_error_message(update: Update, error: Exception) -> None:
    """Send error message to user."""
    error_message = str(error)
    logger.error(error_message)
    await update.effective_message.reply_text(error_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message."""
    if not await check_auth(update):
        return
    await update.effective_message.reply_text(HELP_TEXT)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()
    
    usage_messages = {
        'cut': CUT_USAGE,
        'download': DOWNLOAD_USAGE
    }
    
    if query.data in usage_messages:
        await query.edit_message_text(text=usage_messages[query.data])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send start menu."""
    if not await check_auth(update):
        return
        
    keyboard = [
        [
            InlineKeyboardButton("Cut Video", callback_data='cut'),
            InlineKeyboardButton("Download Video", callback_data='download')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.effective_message.reply_text(SELECT_COMMAND, reply_markup=reply_markup)

def format_duration(seconds: int) -> str:
    """Format duration in seconds to HH:MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

async def validate_cut_params(start_time: str, end_time: str) -> tuple[int, int]:
    """Validate and convert cut parameters."""
    try:
        start_seconds = convert_to_seconds(start_time)
        end_seconds = convert_to_seconds(end_time)
        
        if start_seconds < 0:
            raise ValueError("Start time cannot be negative")
        if end_seconds <= start_seconds:
            raise ValueError("End time must be greater than start time")
            
        duration_seconds = end_seconds - start_seconds
        return start_seconds, duration_seconds
    except ValueError as e:
        raise ValueError(TIME_ERROR.format(str(e)))

async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process video cutting."""
    try:
        if not await check_auth(update):
            return

        if not context.args or len(context.args) != 3:
            await update.effective_message.reply_text(CUT_USAGE)
            return

        video_link, start_time, end_time = context.args
        start_seconds, duration_seconds = await validate_cut_params(start_time, end_time)
        
        duration_formatted = format_duration(duration_seconds)
        await update.effective_message.reply_text(
            CUTTING_VIDEO.format(start_time, end_time, duration_formatted)
        )

        logger.info(f"Cut: {video_link}, start: {start_time}, duration: {duration_seconds}s")
        
        if await download_video(update, context, video_link, start_time, duration_seconds):
            temp_video_path = os.path.join("temp", "temp_video.mp4")
            await send_or_upload_video(temp_video_path, update, context)

    except Exception as e:
        await send_error_message(update, CUT_ERROR.format(str(e)))
    finally:
        cleanup_temp_files()

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process video download."""
    try:
        if not await check_auth(update):
            return

        if not context.args or len(context.args) != 1:
            await update.effective_message.reply_text(DOWNLOAD_USAGE)
            return

        video_link = context.args[0]
        if await download_video(update, context, video_link):
            temp_video_path = os.path.join("temp", "temp_video.mp4")
            await send_or_upload_video(temp_video_path, update, context)

    except Exception as e:
        await send_error_message(update, DOWNLOAD_ERROR.format(str(e)))
    finally:
        cleanup_temp_files()
