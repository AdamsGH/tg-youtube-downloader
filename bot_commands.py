import logging
import os
import re
import asyncio
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from video_processing import download_video, send_or_upload_video, cut_video, clean_url
from database import Database
import psycopg2

# Настройка логирования
logger = logging.getLogger(__name__)

ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS', '').split(',')
db = Database()  # Инициализация базы данных


def convert_to_seconds(time_str):
    """Конвертирует строку времени в секунды."""
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    else:
        raise ValueError("Invalid time format. Use HH:MM:SS, MM:SS, or SS.")


async def help_command(update: Update, context: CallbackContext):
    """Отправляет справочную информацию по командам."""
    help_text = (
        "Доступные команды:\n"
        "/start - Начать взаимодействие с ботом\n"
        "/cut - Обрезать видео\n"
        "/download - Скачать видео\n"
        "Выберите команду из меню ниже:"
    )
    keyboard = [
        [
            InlineKeyboardButton("Обрезать видео", callback_data='cut'),
            InlineKeyboardButton("Скачать видео", callback_data='download'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup)


async def button_handler(update: Update, context: CallbackContext):
    """Обрабатывает нажатия на кнопки инлайн-клавиатуры."""
    query = update.callback_query
    await query.answer()

    if query.data == 'cut':
        await query.edit_message_text(text="Введите команду в формате:\n/cut <video_link> <start_time> <duration>")
    elif query.data == 'download':
        await query.edit_message_text(text="Введите команду в формате:\n/download <video_link>")
    elif query.data in ['save_yes', 'save_no']:
        await handle_save_video(update, context)
    else:
        await query.edit_message_text(text="Неизвестная команда. Пожалуйста, выберите команду.")


async def check_user(update: Update, context: CallbackContext) -> bool:
    """Проверяет, авторизован ли пользователь."""
    user_id = None
    if update.message and update.message.from_user:
        user_id = update.message.from_user.id
    elif update.callback_query and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id

    if user_id is None:
        await update.effective_message.reply_text('Не удалось определить пользователя.')
        return False

    if str(user_id) not in ALLOWED_USER_IDS:
        await update.effective_message.reply_text('Извините, но вы не авторизованы для использования этого бота.')
        return False
    return True


async def ask_save_video(update: Update, context: CallbackContext):
    """Запрашивает у пользователя подтверждение на сохранение видео."""
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data='save_yes'),
            InlineKeyboardButton("Нет", callback_data='save_no')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        # Проверяем, является ли это вызовом из команды /cut или /download
        if context.user_data.get('is_cut'):
            await update.message.reply_text('Хотите сохранить эту обрезанную версию видео в базе данных?', reply_markup=reply_markup)
        else:
            await update.message.reply_text('Хотите сохранить это видео в базе данных?', reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text('Хотите сохранить это видео в базе данных?', reply_markup=reply_markup)


async def start(update: Update, context: CallbackContext):
    """Обрабатывает команду /start."""
    if not await check_user(update, context):
        return
    await help_command(update, context)


async def cut(update: Update, context: CallbackContext):
    """Обрабатывает команду /cut для обрезки видео."""
    if not await check_user(update, context):
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            'Недопустимое количество аргументов.\nИспользование:\n/cut <video_link> <start_time> <duration>'
        )
        return

    video_link, start_time, duration = args
    logger.info(f"Запрос на обрезку видео: {video_link}, время начала: {start_time}, продолжительность: {duration}")

    # Очистка URL
    cleaned_video_link = clean_url(video_link)

    try:
        start_time_seconds = convert_to_seconds(start_time)
        duration_seconds = convert_to_seconds(duration)
    except ValueError as e:
        await update.message.reply_text(f'Ошибка в формате времени: {str(e)}')
        return

    # Генерируем уникальный ключ для обрезанного видео
    cut_key = f"{cleaned_video_link}_cut_{start_time_seconds}_{duration_seconds}"

    # Проверка наличия обрезанного видео в базе данных
    existing_cut = db.get_video_by_url(cut_key)
    if existing_cut and existing_cut.get('media_id'):
        await update.message.reply_text('Обрезанная версия видео уже существует в базе данных. Отправляю её...')
        await send_or_upload_video(existing_cut['media_id'], context, update)
        return

    # Проверка наличия исходного видео
    existing_video = db.get_video_by_url(cleaned_video_link)
    if not existing_video:
        await update.message.reply_text('Исходное видео не найдено в базе данных. Скачиваю...')
        success = await download_video(update, context, cleaned_video_link)
        if not success:
            await update.message.reply_text('Ошибка: не удалось загрузить исходное видео.')
            return
    elif not existing_video.get('media_id'):  # Изменено
        await update.message.reply_text('Исходное видео уже загружено, но file_id отсутствует. Повторная загрузка...')
        success = await download_video(update, context, cleaned_video_link)
        if not success:
            await update.message.reply_text('Ошибка: не удалось получить file_id исходного видео.')
            return

    # Путь к исходному видео
    video_path = 'temp/temp_video.mp4'
    if not os.path.exists(video_path):
        await update.message.reply_text('Ошибка: загруженное видео не найдено.')
        return

    output_path = await cut_video(video_path, start_time_seconds, duration_seconds)

    if output_path and os.path.exists(output_path):
        await send_or_upload_video(output_path, context, update)
        # Сохраняем обрезанное видео в базе данных, но пока без file_id
        db.add_video(media_id=None, url=cut_key, keywords=[], original_url=cleaned_video_link)
        # Удаляем обрезанное и исходное видео
        os.remove(output_path)
        os.remove(video_path)
        await ask_save_video(update, context)
    else:
        await update.message.reply_text('Ошибка: обрезка видео не удалась.')


async def download(update: Update, context: CallbackContext):
    """Обрабатывает команду /download для скачивания видео."""
    if not await check_user(update, context):
        return

    args = context.args
    if len(args) != 1:
        await update.message.reply_text('Недопустимое количество аргументов. Использование: /download <video_link>')
        return

    video_link = args[0]
    cleaned_video_link = clean_url(video_link)
    logger.info(f"Запрос на загрузку видео: {cleaned_video_link}")

    # Проверка наличия видео в базе данных
    existing_video = db.get_video_by_url(cleaned_video_link)
    if existing_video and existing_video.get('media_id'):
        await update.message.reply_text('Видео уже существует в базе данных. Отправляю его...')
        await send_or_upload_video(existing_video['media_id'], context, update)
        return

    await update.message.reply_text('Начинаю загрузку...')
    success = await download_video(update, context, cleaned_video_link)

    if success:
        context.user_data['video_link'] = cleaned_video_link
        await send_or_upload_video('temp/temp_video.mp4', context, update)
        await ask_save_video(update, context)
    else:
        await update.message.reply_text('Ошибка: не удалось загрузить видео.')


async def handle_save_video(update: Update, context: CallbackContext):
    """Обрабатывает ответ пользователя на сохранение видео."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()

        if query.data == 'save_yes':
            video_link = context.user_data.get('video_link')
            if video_link:
                # Проверяем, существует ли уже запись с этим URL
                existing_video = db.get_video_by_url(video_link)
                if existing_video:
                    await query.message.reply_text("Видео уже сохранено в базе данных.")
                else:
                    await query.message.reply_text("Введите ключевые слова для поиска, разделенные запятыми:")
                    context.user_data['waiting_for_keywords'] = True
            else:
                await query.message.reply_text('Ошибка: не найдена ссылка на видео.')
        elif query.data == 'save_no':
            await query.message.reply_text('Видео не сохранено.')
        else:
            await query.message.reply_text("Неизвестная команда. Пожалуйста, выберите опцию сохранения.")
    else:
        # Обработка текстового сообщения с ключевыми словами
        if context.user_data.get('waiting_for_keywords'):
            keywords = [keyword.strip() for keyword in update.message.text.split(',')]
            video_link = context.user_data.get('video_link')
            file_id = context.user_data.get('file_id')  # Убедитесь, что file_id сохранен

            if video_link and file_id:
                # Проверяем, является ли это обрезанным видео
                if '_cut_' in video_link:
                    original_url = video_link.split('_cut_')[0]
                else:
                    original_url = None

                # Проверка на существование перед добавлением
                existing_video = db.get_video_by_url(video_link)
                if existing_video:
                    await update.message.reply_text('Видео уже существует в базе данных.')
                else:
                    try:
                        db.add_video(media_id=file_id, url=video_link, keywords=keywords, original_url=original_url)
                        await update.message.reply_text('Видео успешно сохранено в базе данных.')
                    except psycopg2.errors.UniqueViolation:
                        await update.message.reply_text('Видео уже сохранено в базе данных.')
                        db.connection.rollback()
                    except Exception as e:
                        logger.error(f"Ошибка при сохранении видео: {e}")
                        await update.message.reply_text('Произошла ошибка при сохранении видео.')
                context.user_data['waiting_for_keywords'] = False
            else:
                await update.message.reply_text('Ошибка: не найдены необходимые данные для сохранения.')
        else:
            await update.message.reply_text('Пожалуйста, сначала выберите опцию сохранения видео.')
