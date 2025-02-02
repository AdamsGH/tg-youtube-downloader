#!/usr/bin/env python
import os
import logging
import signal
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# Импорт функций-обработчиков – замените на свои реализации
from bot.commands import start, help_command, cut, download, button
from bot.utils import process_progress_updates  # Ваша функция для обработки очереди прогресса

# Настройка базового логирования
logging.basicConfig(
    format='%(asctime)s — %(name)s — %(levelname)s — %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Снижаем уровень логирования для apscheduler, чтобы убрать спам

logging.getLogger("apscheduler.scheduler").setLevel(logging.ERROR)

# Глобальный флаг, сигнализирующий о том, что progress_job уже запущена
progress_job_running = False

async def progress_job(context):
    global progress_job_running
    if progress_job_running:
        context.application.logger.info("Пропуск progress_job – предыдущая задача всё ещё выполняется")
        return

    progress_job_running = True
    try:
        await process_progress_updates(context.application)
    except Exception as e:
        context.application.logger.error(f"Ошибка при обработке очереди прогресса: {e}")
    finally:
        progress_job_running = False

def shutdown_signal(signum, frame):
    logger.info(f"Получен сигнал {signal.Signals(signum).name}. Завершаем работу...")

def main():
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("Не установлен токен бота в переменных окружения")
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

    logger.info("Бот запущен и готов к работе.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()