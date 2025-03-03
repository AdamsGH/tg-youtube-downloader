#!/usr/bin/env python
import os
import signal
import asyncio
from contextlib import asynccontextmanager

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.commands import start, help_command, cut, download, button
from bot.utils import process_progress_updates
from bot.logger_config import setup_logger

logger = setup_logger(__name__)

class ProgressState:
    """Class to manage progress job state."""
    def __init__(self):
        self.running = False

    @asynccontextmanager
    async def lock(self):
        """Context manager for progress job execution."""
        if self.running:
            logger.debug("Skipping progress job; previous task in progress")
            yield False
            return
        self.running = True
        try:
            yield True
        finally:
            self.running = False

# Create global state manager
progress_state = ProgressState()

async def progress_job(context):
    """Handle progress updates."""
    async with progress_state.lock() as acquired:
        if not acquired:
            return
        try:
            await process_progress_updates(context.application)
        except Exception as e:
            context.application.logger.error(f"Progress update error: {e}")

def shutdown_signal(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Signal {signal.Signals(signum).name} received. Shutting down...")

def main():
    """Initialize and run the bot."""
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("Bot token not set.")
        return

    application = Application.builder().token(TOKEN).build()

    # Register command handlers
    handlers = [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        CommandHandler("cut", cut),
        CommandHandler("download", download),
        CallbackQueryHandler(button)
    ]
    for handler in handlers:
        application.add_handler(handler)

    # Schedule progress updates
    application.job_queue.run_repeating(
        progress_job,
        interval=1.0,
        first=1.0,
        name="progress_job"
    )

    # Setup signal handlers
    signal.signal(signal.SIGINT, shutdown_signal)
    signal.signal(signal.SIGTERM, shutdown_signal)

    logger.info("Bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
