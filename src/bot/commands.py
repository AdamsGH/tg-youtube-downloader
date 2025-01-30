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

        video_link, start_time, duration = args

        try:
            start_time_seconds = convert_to_seconds(start_time)
            duration_seconds = convert_to_seconds(duration)
        except ValueError as e:
            update.message.reply_text(f'Ошибка в формате времени: {str(e)}')
            return

        logger.info(
            f"Запрос на обрезку видео: {video_link}, "
            f"время начала: {start_time}, продолжительность: {duration}"
        )

        if not download_video(update, context, video_link):
            return

        # Обрезка видео
        input_path = os.path.join("temp", "temp_video.mp4")
        output_path = os.path.join("temp", "output_video.mp4")
        
        cut_command = (
            f'ffmpeg -ss {start_time_seconds} -i {input_path} '
            f'-t {duration_seconds} -c:v copy -c:a copy {output_path}'
        )
        subprocess.run(cut_command, shell=True)

        # Отправка обрезанного видео
        send_or_upload_video(output_path, update, context)

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
        if download_video(update, context, video_link):
            temp_video_path = os.path.join("temp", "temp_video.mp4")
            send_or_upload_video(temp_video_path, update, context)

    except Exception as e:
        logger.error(f"Ошибка при загрузке видео: {str(e)}")
        update.message.reply_text(f"Произошла ошибка при загрузке видео: {str(e)}")
    finally:
        cleanup_temp_files()
