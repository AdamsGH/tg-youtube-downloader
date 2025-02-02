#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .utils import convert_to_seconds
from .video_handler import download_video, send_or_upload_video, cleanup_temp_files

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Список разрешённых user_id (не забудьте указать их в переменной окружения ALLOWED_USER_IDS)
ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS', '').split(',')


async def check_auth(update: Update) -> bool:
    """Проверяет авторизацию пользователя."""
    user_id = str(update.effective_user.id)
    if user_id not in ALLOWED_USER_IDS:
        # Использование effective_message гарантирует наличие нужного объекта при любых обновлениях.
        await update.effective_message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return False
    return True


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пользователю сообщение с описанием доступных команд."""
    if not await check_auth(update):
        return

    help_text = (
        "Доступные команды:\n"
        "/start - Начать взаимодействие с ботом\n"
        "/cut <video_link> <start_time> <duration> - Обрезать видео\n"
        "/download <video_link> - Скачать видео\n"
        "/help - Показать это сообщение"
    )
    await update.effective_message.reply_text(help_text)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки в меню."""
    query = update.callback_query
    await query.answer()

    if query.data == 'cut':
        await query.edit_message_text(text="Введите /cut <video_link> <start_time> <duration>")
    elif query.data == 'download':
        await query.edit_message_text(text="Введите /download <video_link>")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пользователю начальное сообщение с меню команд."""
    if not await check_auth(update):
        return

    keyboard = [
        [
            InlineKeyboardButton("Обрезать видео", callback_data='cut'),
            InlineKeyboardButton("Скачать видео", callback_data='download')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.effective_message.reply_text('Выберите команду:', reply_markup=reply_markup)


async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрезает видео по заданным параметрам."""
    if not await check_auth(update):
        return

    try:
        args = context.args
        if len(args) != 3:
            await update.effective_message.reply_text(
                'Недопустимое количество аргументов. Использование:\n'
                '/cut <video_link> <start_time> <duration>'
            )
            return

        video_link, start_time, end_time = args

        try:
            start_seconds = convert_to_seconds(start_time)
            end_seconds = convert_to_seconds(end_time)

            if start_seconds < 0:
                raise ValueError("Время начала не может быть отрицательным")
            if end_seconds <= start_seconds:
                raise ValueError("Конечное время должно быть больше начального")

            duration_seconds = end_seconds - start_seconds
            duration = f"{duration_seconds // 3600:02d}:{(duration_seconds % 3600) // 60:02d}:{duration_seconds % 60:02d}"

            await update.effective_message.reply_text(
                f"Будет вырезан фрагмент с {start_time} по {end_time} "
                f"(длительность: {duration})"
            )
        except ValueError as e:
            await update.effective_message.reply_text(
                f'Ошибка в формате времени: {e}\n'
                'Используйте формат ЧЧ:ММ:СС для указания времени.\n'
                'Пример: /cut <ссылка> 00:04:00 00:08:00'
            )
            return

        logger.info(f"Запрос на обрезку видео: {video_link}, время начала: {start_time}, длительность: {duration}")
        # Функция download_video должна быть асинхронной и корректно работать с передаваемыми параметрами.
        if not await download_video(update, context, video_link, start_time, duration_seconds):
            return

        temp_video_path = os.path.join("temp", "temp_video.mp4")
        await send_or_upload_video(temp_video_path, update, context)

    except Exception as e:
        logger.error(f"Ошибка при обрезке видео: {e}")
        await update.effective_message.reply_text(f"Произошла ошибка при обрезке видео: {e}")
    finally:
        cleanup_temp_files()


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загружает видео по ссылке."""
    if not await check_auth(update):
        return

    try:
        args = context.args
        if len(args) != 1:
            await update.effective_message.reply_text(
                'Недопустимое количество аргументов. Использование:\n'
                '/download <video_link>'
            )
            return

        video_link = args[0]
        if await download_video(update, context, video_link, None, None):
            temp_video_path = os.path.join("temp", "temp_video.mp4")
            await send_or_upload_video(temp_video_path, update, context)

    except Exception as e:
        logger.error(f"Ошибка при загрузке видео: {e}")
        await update.effective_message.reply_text(f"Произошла ошибка при загрузке видео: {e}")
    finally:
        cleanup_temp_files()

# Примечание: функции download_video, send_or_upload_video и cleanup_temp_files
# должны быть реализованы с учётом асинхронного характера библиотеки.
#
# Также не забудьте зарегистрировать команды в объекте Application:
#
#     application.add_handler(CommandHandler("start", start))
#     application.add_handler(CommandHandler("help", help_command))
#     application.add_handler(CommandHandler("cut", cut))
#     application.add_handler(CommandHandler("download", download))
#     application.add_handler(CallbackQueryHandler(button))
#
# и запустить фоновую задачу process_progress_updates(application)
#
# Для запуска фоновой задачи, например:
#     application.job_queue.run_repeating(lambda ctx: asyncio.create_task(process_progress_updates(application)), interval=1)
#
# Далее – стандартный запуск бота.