import logging
import os
import time
import yt_dlp
import requests
from telegram import Update
from telegram.ext import CallbackContext
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from .utils import create_callback, progress_hook

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создание сессии requests
session = requests.Session()

# Путь к директории для временных файлов
TEMP_DIR = "temp"

# Создаем директорию для временных файлов, если она не существует
os.makedirs(TEMP_DIR, exist_ok=True)

def cleanup_temp_files(pattern="temp_video*"):
    """
    Очищает временные файлы по заданному паттерну.
    """
    try:
        for file in os.listdir(TEMP_DIR):
            if file.startswith(pattern.replace("*", "")):
                try:
                    os.remove(os.path.join(TEMP_DIR, file))
                    logger.info(f"Удален временный файл: {file}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении файла {file}: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {str(e)}")

def upload_to_tempsh(file_path, update: Update, context: CallbackContext):
    """
    Загружает файл на сервис temp.sh и возвращает URL для скачивания.
    """
    try:
        logger.info(f"Начало загрузки файла {file_path}")
        with open(file_path, 'rb') as file:
            encoder = MultipartEncoder(fields={'file': ('video.mp4', file)})
            message = update.message.reply_text('Загрузка началась...')
            message_id = message.message_id
            monitor = MultipartEncoderMonitor(
                encoder,
                create_callback(encoder, update, context, message_id)
            )

            for i in range(3):  # Попытка загрузки 3 раза
                response = session.post(
                    'https://temp.sh/upload',
                    data=monitor,
                    headers={'Content-Type': monitor.content_type}
                )
                if response.status_code == 200:
                    upload_url = response.text
                    logger.info(f"Загрузка успешна, URL: {upload_url}")
                    return upload_url
                elif response.status_code == 502 and i < 2:
                    logger.warning(f"Не удалось загрузить {file_path}, код ответа: {response.status_code}. Повторная попытка...")
                    time.sleep(5)
                else:
                    logger.error(f"Не удалось загрузить {file_path}, код ответа: {response.status_code}")
                    return None
    except Exception as e:
        logger.error(f"Не удалось загрузить {file_path}, ошибка: {str(e)}")
        return None

def download_video(update: Update, context: CallbackContext, video_link: str) -> bool:
    """
    Загружает видео с помощью yt_dlp и сохраняет его во временный файл.
    Возвращает True в случае успеха, False в случае ошибки.
    """
    try:
        message = update.message.reply_text('Загрузка началась...')
        message_id = message.message_id

        temp_video_path = os.path.join(TEMP_DIR, 'temp_video.mp4')
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': temp_video_path,
            'nooverwrites': False,
            'progress_hooks': [
                lambda d: progress_hook(d, update, context, message_id)
            ]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_link])

        context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=message_id,
            text='Загрузка завершена.'
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при загрузке видео: {str(e)}")
        update.message.reply_text(f"Произошла ошибка при загрузке видео: {str(e)}")
        return False

def send_or_upload_video(file_path: str, update: Update, context: CallbackContext):
    """
    Отправляет видео пользователю напрямую или через temp.sh в зависимости от размера.
    """
    try:
        file_size = os.path.getsize(file_path)
        if file_size < 50 * 1024 * 1024:  # 50MB
            with open(file_path, 'rb') as video_file:
                context.bot.send_video(
                    chat_id=update.message.chat_id,
                    video=video_file
                )
            logger.info(f"Видео отправлено напрямую в чат {update.message.chat_id}")
        else:
            upload_url = upload_to_tempsh(file_path, update, context)
            if upload_url:
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"Файл слишком большой для Telegram. Скачайте по ссылке: {upload_url}"
                )
                logger.info(f"Видео загружено на temp.sh для чата {update.message.chat_id}")
            else:
                context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="Не удалось загрузить файл."
                )
                logger.error(f"Ошибка загрузки видео для чата {update.message.chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке видео: {str(e)}")
        update.message.reply_text(f"Произошла ошибка при отправке видео: {str(e)}")
    finally:
        cleanup_temp_files()
