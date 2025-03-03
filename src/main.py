#!/usr/bin/env python
"""Telegram bot application."""
import os
import signal
import asyncio
from contextlib import asynccontextmanager

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config.logging import configure_logger
from bot.commands import Commands
from bot.utils import process_progress_updates

logger = configure_logger(__name__)

class BotApplication:
    """Bot application setup and lifecycle."""

    def __init__(self, token: str):
        """Initialize with bot token."""
        self.token = token
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
        self._setup_jobs()
        self._setup_signals()

    def _setup_handlers(self) -> None:
        """Register command handlers."""
        handlers = [
            CommandHandler("start", Commands.start),
            CommandHandler("help", Commands.help_command),
            CommandHandler("cut", Commands.cut),
            CommandHandler("download", Commands.download),
            CallbackQueryHandler(Commands.button)
        ]
        for handler in handlers:
            self.application.add_handler(handler)

    def _setup_jobs(self) -> None:
        """Setup progress tracking."""
        self.application.job_queue.run_repeating(
            self._progress_job,
            interval=1.0,
            first=1.0,
            name="progress_job"
        )

    def _setup_signals(self) -> None:
        """Handle shutdown signals."""
        signal.signal(signal.SIGINT, self._shutdown_signal)
        signal.signal(signal.SIGTERM, self._shutdown_signal)

    async def _progress_job(self, context) -> None:
        """Process progress updates."""
        try:
            await process_progress_updates(context.application)
        except Exception as e:
            context.application.logger.error(f"Progress update error: {e}")

    def _shutdown_signal(self, signum: int, frame) -> None:
        """Clean shutdown on system signals."""
        logger.info(f"Signal {signal.Signals(signum).name} received. Shutting down...")

    def run(self) -> None:
        """Start bot polling."""
        logger.info("Bot started.")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

def main() -> None:
    """Start bot application."""
    token = os.getenv("TOKEN")
    if not token:
        logger.error("Bot token not set.")
        return

    bot = BotApplication(token)
    bot.run()

if __name__ == '__main__':
    main()
