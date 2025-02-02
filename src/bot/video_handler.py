import logging
import os
import time
import asyncio
import yt_dlp
from yt_dlp.utils import download_range_func
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes
from .utils import progress_hook

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

async def upload_to_tempsh(file_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Загружает файл на сервис temp.sh и возвращает URL для скачивания.
    """
    try:
        logger.info(f"Начало загрузки файла {file_path}")
        message = await update.message.reply_text('Загрузка началась...')
        message_id = message.message_id

        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as file:
                data = aiohttp.FormData()
                data.add_field('file', file, filename='video.mp4')

                last_update_time = time.time()

                for i in range(3):  # Попытка загрузки 3 раза
                    try:
                        async with session.post('https://temp.sh/upload', data=data) as response:
                            if response.status == 200:
                                upload_url = await response.text()
                                logger.info(f"Загрузка успешна, URL: {upload_url}")
                                return upload_url
                            elif response.status == 502 and i < 2:
                                logger.warning(f"Не удалось загрузить {file_path}, код ответа: {response.status}. Повторная попытка...")
                                await asyncio.sleep(5)
                            else:
                                logger.error(f"Не удалось загрузить {file_path}, код ответа: {response.status}")
                                return None
                    except Exception as e:
                        if i < 2:
                            logger.warning(f"Ошибка при загрузке: {str(e)}. Повторная попытка...")
                            await asyncio.sleep(5)
                        else:
                            raise

    except Exception as e:
        logger.error(f"Не удалось загрузить {file_path}, ошибка: {str(e)}")
        return None

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE, video_link: str, start_time: str = None, duration_seconds: int = None) -> bool:
    """
    Загружает видео с помощью yt_dlp и сохраняет его во временный файл.
    При указании start_time и duration_seconds загружает только указанный фрагмент.
    Возвращает True в случае успеха, False в случае ошибки.
    """
    try:
        message = await update.message.reply_text('Загрузка началась...')
        message_id = message.message_id

        temp_video_path = os.path.join(TEMP_DIR, 'temp_video.mp4')
        
        # Инициализация переменных
        start_seconds = None

        # Если указаны параметры времени
        if start_time is not None and duration_seconds is not None:
            try:
                # Вычисляем время начала
                start_parts = [int(x) for x in start_time.split(':')]
                start_seconds = start_parts[0] * 3600 + start_parts[1] * 60 + start_parts[2]

                # Проверка на отрицательные значения
                if start_seconds < 0:
                    raise ValueError("Время начала не может быть отрицательным")
                if duration_seconds <= 0:
                    raise ValueError("Длительность должна быть положительной")

                logger.info(f"Вычисленное время: start_seconds={start_seconds}, duration_seconds={duration_seconds}")
            except Exception as e:
                logger.error(f"Ошибка при обработке времени: {str(e)}")
                await update.message.reply_text("Ошибка в формате времени. Используйте формат ЧЧ:ММ:СС")
                return False

        # Базовые параметры
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': temp_video_path,
            'force_keyframes_at_cuts': True,
            'progress_hooks': [
                lambda d: progress_hook(d, update, context, message_id)
            ],
            'force_generic_extractor': False,
            'fragment_retries': 10,
            'ignoreerrors': False,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls']
                }
            },
            'postprocessor_args': ['-avoid_negative_ts', 'make_zero']
        }

        # Добавляем параметры обрезки только если указаны временные параметры
        if start_seconds is not None and duration_seconds is not None:
            ydl_opts['download_ranges'] = download_range_func([], [[start_seconds, start_seconds + duration_seconds]])

        logger.info(f"Загрузка видео {video_link}")
        if start_time is not None and duration_seconds is not None:
            logger.info(f"Параметры обрезки: start={start_time}, duration={duration_seconds} seconds")
        logger.info(f"Параметры yt-dlp: {ydl_opts}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_link])

        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=message_id,
            text='Загрузка завершена.'
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при загрузке видео: {str(e)}")
        await update.message.reply_text(f"Произошла ошибка при загрузке видео: {str(e)}")
        return False

async def send_or_upload_video(file_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет видео пользователю напрямую или через temp.sh в зависимости от размера.
    """
    try:
        file_size = os.path.getsize(file_path)
        if file_size < 50 * 1024 * 1024:  # 50MB
            with open(file_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.message.chat_id,
                    video=video_file
                )
            logger.info(f"Видео отправлено напрямую в чат {update.message.chat_id}")
        else:
            upload_url = await upload_to_tempsh(file_path, update, context)
            if upload_url:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"Файл слишком большой для Telegram. Скачайте по ссылке: {upload_url}"
                )
                logger.info(f"Видео загружено на temp.sh для чата {update.message.chat_id}")
            else:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="Не удалось загрузить файл."
                )
                logger.error(f"Ошибка загрузки видео для чата {update.message.chat_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке видео: {str(e)}")
        await update.message.reply_text(f"Произошла ошибка при отправке видео: {str(e)}")
    finally:
        cleanup_temp_files()
