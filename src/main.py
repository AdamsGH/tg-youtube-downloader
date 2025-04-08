#!/usr/bin/env python
"""
Telegram bot application for YouTube video processing.

This module contains the main application class that sets up and runs
the Telegram bot for downloading and cutting YouTube videos.
"""
import os
import signal
from typing import NoReturn, Optional

from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from config.logging import configure_logger
from bot.commands import Commands
from bot.utils import process_progress_updates

logger = configure_logger(__name__)

class BotApplication:
    """
    Bot application setup and lifecycle.
    
    This class handles the initialization, configuration, and execution
    of the Telegram bot application. It sets up command handlers,
    background jobs, and signal handlers for clean shutdown.
    """

    def __init__(self, token: str):
        """
        Initialize the bot application with the provided token.
        
        Args:
            token: Telegram bot API token
        """
        self.token = token
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
        self._setup_jobs()
        self._setup_signals()

    def _setup_handlers(self) -> None:
        """
        Register command and message handlers.
        
        Note: Methods prefixed with underscore are intended for internal use only.
        """
        # YouTube video link regex pattern
        youtube_link_pattern = r'https?://(?:www\.)?youtu(?:\.be|be\.com)'
        
        # Time format regex pattern (HH:MM:SS, MM:SS, or SS)
        time_format_pattern = r'^\d{1,2}:\d{2}:\d{2}$|^\d{1,2}:\d{2}$|^\d+$'
        
        handlers = [
            CommandHandler("start", Commands.start),
            CommandHandler("help", Commands.help_command),
            CommandHandler("cut", Commands.cut),
            CommandHandler("download", Commands.download),
            CallbackQueryHandler(Commands.button),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.Regex(youtube_link_pattern),
                Commands.handle_video_link
            ),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.Regex(time_format_pattern),
                Commands.handle_end_time
            )
        ]
        
        for handler in handlers:
            self.application.add_handler(handler)

    def _setup_jobs(self) -> None:
        """
        Setup background jobs for progress tracking.
        
        Note: Methods prefixed with underscore are intended for internal use only.
        """
        self.application.job_queue.run_repeating(
            self._progress_job,
            interval=1.0,
            first=1.0,
            name="progress_job"
        )

    def _setup_signals(self) -> None:
        """
        Handle shutdown signals for clean application termination.
        
        Note: Methods prefixed with underscore are intended for internal use only.
        """
        signal.signal(signal.SIGINT, self._shutdown_signal)
        signal.signal(signal.SIGTERM, self._shutdown_signal)

    async def _progress_job(self, context) -> None:
        """
        Process progress updates for active downloads/uploads.
        
        Args:
            context: Job context containing application instance
            
        Note: Methods prefixed with underscore are intended for internal use only.
        """
        try:
            await process_progress_updates(context.application)
        except Exception as e:
            logger.error(f"Progress update error: {e}")
            # Log the full exception for debugging
            logger.exception("Detailed progress job error:")

    def _shutdown_signal(self, signum: int, _) -> NoReturn:
        """
        Handle clean shutdown on system signals.
        
        Args:
            signum: Signal number received
            _: Frame object (unused)
            
        Note: Methods prefixed with underscore are intended for internal use only.
        """
        logger.info(f"Signal {signal.Signals(signum).name} received. Shutting down...")

    def run(self) -> None:
        """
        Start bot polling and handle updates.
        """
        logger.info("Bot started.")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

def main() -> None:
    """
    Application entry point.
    
    Retrieves the bot token from environment variables and starts the bot.
    """
    token = os.getenv("TOKEN")
    if not token:
        logger.error("Bot token not set. Please set the TOKEN environment variable.")
        return

    bot = BotApplication(token)
    bot.run()

if __name__ == '__main__':
    main()
