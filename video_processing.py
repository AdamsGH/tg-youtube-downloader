import logging
import os
import subprocess
import re
import yt_dlp
import urllib.parse
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import CallbackContext
from database import Database
from functools import partial
from telegram.error import BadRequest

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database()


def clean_url(url: str) -> str:
    """Очистка URL от лишних параметров и приведение к стандартному виду."""
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    video_id = query_params.get('v', [None])[0]
    if not video_id:
        # Обработка коротких ссылок типа youtu.be
        if parsed_url.netloc in ['youtu.be']:
            video_id = parsed_url.path.lstrip('/')
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    else:
        return url  # Вернуть исходный URL, если не удалось очистить


def progress_hook(d, update: Update, context: CallbackContext, message_id: int):
    """Хук для отображения прогресса загрузки."""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0.0%')
        percent = re.sub(r'\x1b\[.*?m', '', percent).strip()
        last_percent = context.user_data.get('last_percent', None)
        if percent != last_percent:
            context.user_data['last_percent'] = percent
            # Используем asyncio.create_task для безопасного вызова из синхронного контекста
            try:
                asyncio.create_task(
                    context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=message_id,
                        text=f'Загрузка: {percent}'
                    )
                )
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    logger.error(f"Ошибка при обновлении сообщения: {e}")
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения: {e}")

async def send_or_upload_video(file, context: CallbackContext, update: Update):
    """Отправляет или загружает видео пользователю.
    
    file может быть либо file_id, либо путем к файлу.
    """
    try:
        if isinstance(file, str) and os.path.exists(file):
            # Это путь к файлу
            file_size = os.path.getsize(file)
            if file_size < 50 * 1024 * 1024:  # Если размер видео меньше 50 МБ
                with open(file, 'rb') as video_file:
                    message = await context.bot.send_video(chat_id=update.effective_chat.id, video=video_file)
                    # Сохраняем file_id в user_data для последующего сохранения в базу
                    context.user_data['file_id'] = message.video.file_id
                os.remove(file)
            else:
                upload_url = await upload_to_tempsh(file, update, context)
                if upload_url:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Файл слишком большой для отправки через Telegram. Вы можете скачать его по этой ссылке: {upload_url}"
                    )
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text="Не удалось загрузить файл.")
        else:
            # Предполагаем, что это file_id
            await context.bot.send_video(chat_id=update.effective_chat.id, video=file)
            # Нет необходимости обновлять базу данных, так как file_id уже сохранен
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass  # Игнорируем ошибку, если сообщение не изменилось
        else:
            logger.error(f"Ошибка при отправке видео: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Произошла ошибка при отправке видео.")
    except Exception as e:
        logger.error(f"Ошибка при отправке видео: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Произошла ошибка при отправке видео.")

async def download_video(update: Update, context: CallbackContext, video_link: str) -> bool:
    """Загружает видео с помощью yt_dlp и отправляет его пользователю."""
    # Очистка URL
    cleaned_video_link = clean_url(video_link)

    # Отправляем сообщение о начале загрузки и сохраняем message_id
    message = await update.message.reply_text('Загрузка началась...')
    message_id = message.message_id
    # Добавляем message_id в context.user_data для доступа в progress_hook
    context.user_data['download_message_id'] = message_id

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': 'temp/temp_video.%(ext)s',
        'nooverwrites': True,
        'progress_hooks': [partial(progress_hook, update=update, context=context, message_id=message_id)]
    }

    try:
        # Проверка существования видео в базе данных
        logger.info(f"Проверка существования видео: {cleaned_video_link}")
        existing_video = db.get_video_by_url(cleaned_video_link)
        if existing_video and existing_video.get('media_id'):
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=message_id,
                text='Видео уже загружено.'
            )
            context.user_data['video_link'] = cleaned_video_link
            return True  # Возвращаем True, так как видео уже загружено и существует
        else:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([cleaned_video_link])
            except Exception as e:
                logger.error(f"Ошибка при загрузке видео: {e}")
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id,
                    text='Ошибка при загрузке видео.'
                )
                return False

            # Найдём файл в директории temp
            temp_dir = 'temp'
            files = os.listdir(temp_dir)
            video_files = [f for f in files if f.startswith('temp_video.') and (f.endswith('.mp4') or f.endswith('.m4a'))]

            if not video_files:
                logger.error("Файл видео не найден после загрузки.")
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id,
                    text='Ошибка: файл видео не найден после загрузки.'
                )
                return False

            video_path = os.path.join(temp_dir, 'temp_video.mp4')
            if not os.path.exists(video_path):
                logger.error(f"Файл видео не найден: {video_path}")
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message_id,
                    text='Ошибка: файл видео не найден после загрузки.'
                )
                return False

            logger.info(f"Видео сохранено по пути: {video_path}")

            # Отправляем видео пользователю
            await send_or_upload_video(video_path, context, update)

            # После отправки, получаем file_id и сохраняем в базу данных
            file_id = context.user_data.get('file_id')
            if file_id:
                db.add_video(media_id=file_id, url=cleaned_video_link, keywords=[], original_url=None)
                logger.info(f"Добавлено видео: url={cleaned_video_link}")
            else:
                logger.error("file_id не получен после отправки видео.")

            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=message_id,
                text='Загрузка завершена.'
            )
            context.user_data['video_link'] = cleaned_video_link
            return True

    finally:
        # Очистка message_id из context.user_data
        context.user_data.pop('download_message_id', None)

async def cut_video(video_path: str, start_time: int, duration: int) -> str:
    """Обрезает видео с помощью ffmpeg."""
    output_path = f'temp/cut_video_{start_time}_{duration}.mp4'
    logger.info(f"Начало обрезки видео: {video_path}, start_time: {start_time}, duration: {duration}")
    command = [
        'ffmpeg', '-i', video_path,
        '-ss', str(start_time), '-t', str(duration),
        '-c', 'copy', output_path
    ]
    logger.info(f"Запуск команды: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при обрезке видео: {e.stderr.decode()}")
        return None

    if not os.path.exists(output_path):
        logger.error(f"Файл не был создан: {output_path}")
        return None

    return output_path


async def upload_to_tempsh(file_path: str, update: Update, context: CallbackContext) -> str:
    """Загружает файл на file.io и возвращает URL."""
    upload_url = "https://file.io/"
    try:
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as f:
                data = {'file': f}
                async with session.post(upload_url, data=data) as resp:
                    if resp.status == 200:
                        json_response = await resp.json()
                        return json_response.get('link') or json_response.get('url')  # В зависимости от API
                    else:
                        logger.error(f"Ошибка загрузки на file.io: статус {resp.status}")
                        return None
    except Exception as e:
        logger.error(f"Ошибка при загрузке на file.io: {e}")
        return None
