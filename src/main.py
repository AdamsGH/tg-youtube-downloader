#!/usr/bin/env python
import os
import logging
import signal
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from bot.commands import start, help_command, cut, download, button
from bot.utils import process_progress_updates

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# Suppress extra logs from third-party modules
logging.getLogger("httpx").setLevel(logging.ERROR)
aps_logger = logging.getLogger("apscheduler.scheduler")
aps_logger.setLevel(logging.ERROR)
class SuppressMaxInstancesFilter(logging.Filter):
    def filter(self, record):
        return "maximum number of running instances reached" not in record.getMessage()
aps_logger.addFilter(SuppressMaxInstancesFilter())

progress_job_running = False

async def progress_job(context):
    global progress_job_running
    if progress_job_running:
        context.application.logger.debug("Skipping progress job; previous task in progress")
        return
    progress_job_running = True
    try:
        await process_progress_updates(context.application)
    except Exception as e:
        context.application.logger.error(f"Progress update error: {e}")
    finally:
        progress_job_running = False

def shutdown_signal(signum, frame):
    logger.info(f"Signal {signal.Signals(signum).name} received. Shutting down...")

def main():
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("Bot token not set.")
        return
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cut", cut))
    application.add_handler(CommandHandler("download", download))
    application.add_handler(CallbackQueryHandler(button))

    application.job_queue.run_repeating(
        progress_job,
        interval=1.0,
        first=1.0,
        name="progress_job"
    )

    signal.signal(signal.SIGINT, shutdown_signal)
    signal.signal(signal.SIGTERM, shutdown_signal)

    logger.info("Bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()