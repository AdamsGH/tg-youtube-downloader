"""Bot command handlers."""
from typing import List
import os
import asyncio

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import ContextTypes

from config.logging import configure_logger
from config.constants import (
    UNAUTHORIZED_MESSAGE, HELP_TEXT, CUT_USAGE, DOWNLOAD_USAGE,
    SELECT_COMMAND, TIME_ERROR, CUT_ERROR, DOWNLOAD_ERROR, CUTTING_VIDEO
)
from .utils import convert_to_seconds
from .video_handler import VideoProcessor

logger = configure_logger(__name__)

class CommandHandler:
    """Command processing utilities."""

    @staticmethod
    def get_allowed_users() -> List[str]:
        """Get allowed user IDs."""
        return os.getenv('ALLOWED_USER_IDS', '').split(',')

    @classmethod
    async def check_auth(cls, update: Update) -> bool:
        """Check if user is authorized."""
        user_id = str(update.effective_user.id)
        if user_id not in cls.get_allowed_users():
            await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
            return False
        return True

    @staticmethod
    async def send_error_message(update: Update, error: Exception) -> None:
        """Send error to user."""
        error_message = str(error)
        logger.error(error_message)
        await update.effective_message.reply_text(error_message)

    @staticmethod
    def format_duration(seconds: int) -> str:
        """Format seconds to HH:MM:SS."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    async def validate_cut_params(start_time: str, end_time: str) -> tuple[int, int]:
        """Validate and convert video cut times."""
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

class Commands:
    """Bot command implementations."""

    @staticmethod
    async def help_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """Send help message."""
        if not await CommandHandler.check_auth(update):
            return
        await update.effective_message.reply_text(HELP_TEXT)

    @staticmethod
    async def button(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button clicks."""
        query = update.callback_query
        await query.answer()
        
        usage_messages = {
            'cut': CUT_USAGE,
            'download': DOWNLOAD_USAGE
        }
        
        if query.data in usage_messages:
            await query.edit_message_text(text=usage_messages[query.data])

    @staticmethod
    async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """Send start menu."""
        if not await CommandHandler.check_auth(update):
            return
            
        keyboard = [
            [
                InlineKeyboardButton("Cut Video", callback_data='cut'),
                InlineKeyboardButton("Download Video", callback_data='download')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.effective_message.reply_text(SELECT_COMMAND, reply_markup=reply_markup)

    @staticmethod
    async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process video cutting."""
        try:
            if not await CommandHandler.check_auth(update):
                return

            if not context.args or len(context.args) != 3:
                await update.effective_message.reply_text(CUT_USAGE)
                return

            video_link, start_time, end_time = context.args
            start_seconds, duration_seconds = await CommandHandler.validate_cut_params(start_time, end_time)
            
            duration_formatted = CommandHandler.format_duration(duration_seconds)
            await update.effective_message.reply_text(
                CUTTING_VIDEO.format(start_time, end_time, duration_formatted)
            )

            logger.info(f"Cut: {video_link}, start: {start_time}, duration: {duration_seconds}s")
            
            async def download_task():
                try:
                    result = await VideoProcessor.download_video(
                        update=update,
                        context=context,
                        video_link=video_link,
                        start_time=str(start_seconds),
                        duration_seconds=duration_seconds
                    )
                    if result.success:
                        await VideoProcessor.send_or_upload_video(result.file_path, update, context)
                    else:
                        await CommandHandler.send_error_message(
                            update, CUT_ERROR.format(result.error_message)
                        )
                except Exception as e:
                    await CommandHandler.send_error_message(update, CUT_ERROR.format(str(e)))

            asyncio.create_task(download_task())

        except Exception as e:
            await CommandHandler.send_error_message(update, CUT_ERROR.format(str(e)))

    @staticmethod
    async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process video download."""
        try:
            if not await CommandHandler.check_auth(update):
                return

            if not context.args or len(context.args) != 1:
                await update.effective_message.reply_text(DOWNLOAD_USAGE)
                return

            video_link = context.args[0]
            
            async def download_task():
                try:
                    result = await VideoProcessor.download_video(update, context, video_link)
                    if result.success:
                        await VideoProcessor.send_or_upload_video(result.file_path, update, context)
                    else:
                        await CommandHandler.send_error_message(
                            update, DOWNLOAD_ERROR.format(result.error_message)
                        )
                except Exception as e:
                    await CommandHandler.send_error_message(update, DOWNLOAD_ERROR.format(str(e)))

            asyncio.create_task(download_task())

        except Exception as e:
            await CommandHandler.send_error_message(update, DOWNLOAD_ERROR.format(str(e)))
