import os
import subprocess
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from .utils import convert_to_seconds
from .video_handler import download_video, send_or_upload_video, cleanup_temp_files

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS', '').split(',')

def check_auth(update: Update) -> bool:
    """Проверяет авторизацию пользователя."""
    user_id = str(update.effective_user.id)
    if user_id not in ALLOWED_USER_IDS:
        update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return False
    return True

def help(update: Update, context: CallbackContext):
    """Отправляет пользователю сообщение с описанием доступных команд."""
    if not check_auth(update):
        return
        
    help_text = (
        "Доступные команды:\n"
        "/start - Начать взаимодействие с ботом\n"
        "/cut <video_link> <start_time> <duration> - Обрезать видео\n"
        "/download <video_link> - Скачать видео\n"
        "/help - Показать это сообщение"
    )
    update.message.reply_text(help_text)

def button(update: Update, context: CallbackContext):
    """Обрабатывает нажатия на кнопки в меню."""
    query = update.callback_query
    query.answer()

    if query.data == 'cut':
        query.edit_message_text(text="Введите /cut <video_link> <start_time> <duration>")
    elif query.data == 'download':
        query.edit_message_text(text="Введите /download <video_link>")

def start(update: Update, context: CallbackContext):
    """Отправляет пользователю начальное сообщение с меню команд."""
    if not check_auth(update):
        return

    keyboard = [[
        InlineKeyboardButton("Обрезать видео", callback_data='cut'),
        InlineKeyboardButton("Скачать видео", callback_data='download'),
    ]]

    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Выберите команду:', reply_markup=reply_markup)

def cut(update: Update, context: CallbackContext):
    """Обрезает видео по заданным параметрам."""
    if not check_auth(update):
        return

    try:
        args = context.args
        if len(args) != 3:
            update.message.reply_text(
                'Недопустимое количество аргументов. Использование:\n'
                '/cut <video_link> <start_time> <duration>'
            )
            return

        video_link, start_time, end_time = args

        # Проверяем формат времени и логику временных отрезков
        try:
            start_seconds = convert_to_seconds(start_time)
            end_seconds = convert_to_seconds(end_time)
            
            if start_seconds < 0:
                raise ValueError("Время начала не может быть отрицательным")
            if end_seconds <= start_seconds:
                raise ValueError("Конечное время должно быть больше начального")
            
            duration_seconds = end_seconds - start_seconds
            duration = f"{duration_seconds//3600:02d}:{(duration_seconds%3600)//60:02d}:{duration_seconds%60:02d}"
                
            # Добавляем понятное сообщение для пользователя
            update.message.reply_text(
                f"Будет вырезан фрагмент с {start_time} по {end_time} "
                f"(длительность: {duration})"
            )
        except ValueError as e:
            update.message.reply_text(
                f'Ошибка в формате времени: {str(e)}\n'
                'Используйте формат ЧЧ:ММ:СС для указания времени.\n'
                'Пример: /cut <ссылка> 00:04:00 00:08:00 - вырежет фрагмент с 4-й по 8-ю минуту'
            )
            return

        logger.info(
            f"Запрос на обрезку видео: {video_link}, "
            f"время начала: {start_time}, продолжительность: {duration}"
        )

        # Загружаем и обрезаем видео одним действием
        if not download_video(update, context, video_link, start_time, duration_seconds):
            return

        # Отправляем видео
        temp_video_path = os.path.join("temp", "temp_video.mp4")
        send_or_upload_video(temp_video_path, update, context)

    except Exception as e:
        logger.error(f"Ошибка при обрезке видео: {str(e)}")
        update.message.reply_text(f"Произошла ошибка при обрезке видео: {str(e)}")
    finally:
        cleanup_temp_files()

def download(update: Update, context: CallbackContext):
    """Загружает видео по ссылке."""
    if not check_auth(update):
        return

    try:
        args = context.args
        if len(args) != 1:
            update.message.reply_text(
                'Недопустимое количество аргументов. Использование:\n'
                '/download <video_link>'
            )
            return

        video_link = args[0]
        if download_video(update, context, video_link, None, None):
            temp_video_path = os.path.join("temp", "temp_video.mp4")
            send_or_upload_video(temp_video_path, update, context)

    except Exception as e:
        logger.error(f"Ошибка при загрузке видео: {str(e)}")
        update.message.reply_text(f"Произошла ошибка при загрузке видео: {str(e)}")
    finally:
        cleanup_temp_files()
