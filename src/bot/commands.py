"""
Bot command handlers.

This module contains the implementation of all bot commands and message handlers,
including video processing operations and user interaction flows.
"""
from typing import List, Tuple, Optional, Callable, Awaitable, Dict, Any
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
    SELECT_COMMAND, TIME_ERROR, CUT_ERROR, DOWNLOAD_ERROR, CUTTING_VIDEO,
    ENTER_END_TIME, PROCESSING_VIDEO
)
from .utils import convert_to_seconds, extract_timestamp_from_url
from .video_handler import VideoProcessor, VideoProcessingResult

logger = configure_logger(__name__)

# Type aliases for better readability
VideoTaskCallback = Callable[[Update, ContextTypes.DEFAULT_TYPE, str, Optional[int], Optional[int]], Awaitable[VideoProcessingResult]]

class CommandHandler:
    """
    Command processing utilities.
    
    This class provides helper methods for command processing,
    including user authentication, error handling, and time formatting.
    """

    @staticmethod
    def get_allowed_users() -> List[str]:
        """
        Get list of allowed user IDs from environment variables.
        
        Returns:
            List of user IDs that are authorized to use the bot
        """
        return os.getenv('ALLOWED_USER_IDS', '').split(',')

    @classmethod
    async def check_auth(cls, update: Update) -> bool:
        """
        Check if the user is authorized to use the bot.
        
        Args:
            update: Telegram update object containing user information
            
        Returns:
            True if user is authorized, False otherwise
        """
        user_id = str(update.effective_user.id)
        if user_id not in cls.get_allowed_users():
            await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
            return False
        return True

    @staticmethod
    async def send_error_message(update: Update, error: Exception) -> None:
        """
        Send error message to user and log the error.
        
        Args:
            update: Telegram update object
            error: Exception that occurred
        """
        error_message = str(error)
        logger.error(error_message)
        await update.effective_message.reply_text(error_message)

    @staticmethod
    def format_duration(seconds: int) -> str:
        """
        Format seconds to HH:MM:SS format.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted time string in HH:MM:SS format
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    async def validate_cut_params(start_time: str, end_time: str) -> Tuple[int, int]:
        """
        Validate and convert video cut times.
        
        Args:
            start_time: Start time in HH:MM:SS, MM:SS, or SS format
            end_time: End time in HH:MM:SS, MM:SS, or SS format
            
        Returns:
            Tuple of (start_seconds, duration_seconds)
            
        Raises:
            ValueError: If times are invalid or end time is not after start time
        """
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
    """
    Bot command implementations.
    
    This class contains all the command handlers and message processors
    for the Telegram bot, implementing the core functionality.
    """

    @staticmethod
    async def help_command(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Send help message with available commands.
        
        Args:
            update: Telegram update object
            _: Context object (unused)
        """
        if not await CommandHandler.check_auth(update):
            return
        await update.effective_message.reply_text(HELP_TEXT)

    @staticmethod
    async def button(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle inline button clicks.
        
        Args:
            update: Telegram update object containing callback query
            _: Context object (unused)
        """
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
        """
        Send start menu with command options.
        
        Args:
            update: Telegram update object
            _: Context object (unused)
        """
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
    async def _create_video_processing_task(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        video_link: str,
        start_seconds: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        error_template: str = CUT_ERROR
    ) -> None:
        """
        Create and run an asynchronous video processing task.
        
        Args:
            update: Telegram update object
            context: Bot context
            video_link: URL of the video to process
            start_seconds: Start time in seconds (for cutting)
            duration_seconds: Duration in seconds (for cutting)
            error_template: Error message template to use
            
        Note: This is a private helper method used by multiple command handlers.
        """
        async def download_task():
            try:
                # Convert start_seconds to string if provided
                start_time_str = str(start_seconds) if start_seconds is not None else None
                
                result = await VideoProcessor.download_video(
                    update=update,
                    context=context,
                    video_link=video_link,
                    start_time=start_time_str,
                    duration_seconds=duration_seconds
                )
                
                if result.success:
                    await VideoProcessor.send_or_upload_video(result.file_path, update, context)
                else:
                    await CommandHandler.send_error_message(
                        update, error_template.format(result.error_message)
                    )
            except Exception as e:
                await CommandHandler.send_error_message(update, error_template.format(str(e)))

        # Create and start the task
        asyncio.create_task(download_task())

    @staticmethod
    async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Process video cutting command.
        
        Format: /cut <video_link> <start_time> <end_time>
        
        Args:
            update: Telegram update object
            context: Bot context with command arguments
        """
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
            
            await Commands._create_video_processing_task(
                update=update,
                context=context,
                video_link=video_link,
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
                error_template=CUT_ERROR
            )

        except Exception as e:
            await CommandHandler.send_error_message(update, CUT_ERROR.format(str(e)))

    @staticmethod
    async def handle_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Process video link sent as a message.
        
        This handler processes YouTube links sent directly as messages,
        extracting timestamps if present and handling different scenarios:
        1. Link with timestamp + end time in message: Cut video
        2. Link with timestamp only: Ask for end time
        3. Link without timestamp: Download full video
        
        Args:
            update: Telegram update object
            context: Bot context
        """
        try:
            if not await CommandHandler.check_auth(update):
                return

            message_parts = update.message.text.strip().split()
            video_link = message_parts[0]
            start_time = extract_timestamp_from_url(video_link)

            if start_time > 0:
                # Link contains timestamp
                if len(message_parts) > 1:
                    # End time provided in message
                    end_time = message_parts[1]
                    try:
                        start_seconds, duration_seconds = await CommandHandler.validate_cut_params(
                            str(start_time), end_time
                        )
                        
                        duration_formatted = CommandHandler.format_duration(duration_seconds)
                        await update.message.reply_text(
                            CUTTING_VIDEO.format(start_time, end_time, duration_formatted)
                        )

                        await Commands._create_video_processing_task(
                            update=update,
                            context=context,
                            video_link=video_link,
                            start_seconds=start_seconds,
                            duration_seconds=duration_seconds,
                            error_template=CUT_ERROR
                        )
                        return
                    except Exception as e:
                        await CommandHandler.send_error_message(update, CUT_ERROR.format(str(e)))
                        return

                # No end time, ask for it
                reply = await update.message.reply_text(ENTER_END_TIME)
                context.user_data['video_link'] = video_link
                context.user_data['start_time'] = start_time
                context.user_data['reply_message_id'] = reply.message_id
                return

            # No timestamp, just download
            await update.message.reply_text(PROCESSING_VIDEO)
            await Commands._create_video_processing_task(
                update=update,
                context=context,
                video_link=video_link,
                error_template=DOWNLOAD_ERROR
            )

        except Exception as e:
            await CommandHandler.send_error_message(update, DOWNLOAD_ERROR.format(str(e)))

    @staticmethod
    async def handle_end_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Process end time response for video cutting.
        
        This handler is triggered when a user sends a time format message
        after being prompted for an end time in the video cutting flow.
        
        Args:
            update: Telegram update object
            context: Bot context containing stored video link and start time
        """
        try:
            if not await CommandHandler.check_auth(update):
                return

            if 'video_link' not in context.user_data:
                return

            video_link = context.user_data['video_link']
            start_time = context.user_data['start_time']
            end_time = update.message.text.strip()

            # Clean up stored data
            context.user_data.clear()

            start_seconds, duration_seconds = await CommandHandler.validate_cut_params(
                str(start_time), end_time
            )
            
            duration_formatted = CommandHandler.format_duration(duration_seconds)
            await update.message.reply_text(
                CUTTING_VIDEO.format(start_time, end_time, duration_formatted)
            )

            await Commands._create_video_processing_task(
                update=update,
                context=context,
                video_link=video_link,
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
                error_template=CUT_ERROR
            )

        except Exception as e:
            await CommandHandler.send_error_message(update, CUT_ERROR.format(str(e)))

    @staticmethod
    async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Process video download command.
        
        Format: /download <video_link>
        
        Args:
            update: Telegram update object
            context: Bot context with command arguments
        """
        try:
            if not await CommandHandler.check_auth(update):
                return

            if not context.args or len(context.args) != 1:
                await update.effective_message.reply_text(DOWNLOAD_USAGE)
                return

            video_link = context.args[0]
            
            await Commands._create_video_processing_task(
                update=update,
                context=context,
                video_link=video_link,
                error_template=DOWNLOAD_ERROR
            )

        except Exception as e:
            await CommandHandler.send_error_message(update, DOWNLOAD_ERROR.format(str(e)))
