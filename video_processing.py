import logging
import os
import time
import yt_dlp
import subprocess
import re
from telegram import Update
from telegram.ext import CallbackContext
from database import Database
import asyncio

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация соединения с базой данных
db = Database()
last_update_time = 0

# Загрузка видео с помощью yt_dlp
async def download_video(update: Update, context: CallbackContext, video_link):
    global message_id
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': 'temp/temp_video.mp4',
        'nooverwrites': False,
        'progress_hooks': [lambda d: progress_hook(d, update, context)]
    }

    message = await update.message.reply_text('Загрузка началась...')
    message_id = message.message_id

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_link])
    except Exception as e:
        logger.error(f"Ошибка при загрузке видео: {str(e)}")
        await context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message_id, text='Ошибка при загрузке видео.')
        return False

    await context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message_id, text='Загрузка завершена.')
    return True  # Успешная загрузка

async def cut_video(video_path, start_time, duration):
    output_path = 'temp/cut_video.mp4'
    logger.info(f"Начало обрезки видео: {video_path}, start_time: {start_time}, duration: {duration}")
    command = ['ffmpeg', '-i', video_path, '-ss', start_time, '-t', str(duration), '-c', 'copy', output_path]
    logger.info(f"Запуск команды: {' '.join(command)}")
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        logger.error("Ошибка при обрезке видео.")
        return None
    if not os.path.exists(output_path):
        logger.error(f"Файл не был создан: {output_path}")
    return output_path

async def process_video(update: Update, context: CallbackContext, start_time, duration):
    video_path = 'temp/temp_video.mp4'
    if not os.path.exists(video_path):
        await update.message.reply_text('Ошибка: загруженное видео не найдено.')
        return

    output_path = await cut_video(video_path, start_time, duration)
    
    if output_path and os.path.exists(output_path):
        await send_or_upload_video(output_path, update, context)
        if os.path.exists(output_path):  # Проверяем, существует ли файл перед удалением
            os.remove(output_path)
            os.remove(video_path)
    else:
        await update.message.reply_text('Ошибка: обрезка видео не удалась.')

def progress_hook(d, update: Update, context: CallbackContext):
    global last_update_time
    global message_id
    if d['status'] == 'downloading':
        current_time = time.time()
        if current_time - last_update_time >= 10:
            percent = d['_percent_str']
            percent = re.sub(r'\x1b\[.*?m', '', percent)
            try:
                asyncio.create_task(context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message_id, text=f'Загрузка: {percent}'))
            except Exception as e:
                logging.error(f"Ошибка при обновлении сообщения: {str(e)}")
            last_update_time = current_time

async def send_or_upload_video(file_path, update: Update, context: CallbackContext):
    file_size = os.path.getsize(file_path)
    if file_size <  50 * 1024 * 1024:
        with open(file_path, 'rb') as video_file:
            message = await context.bot.send_video(chat_id=update.message.chat_id, video=video_file)
            db.add_video(telegram_id=message.video.file_id, keywords='your_keywords_here')  # Убрано await
        os.remove(file_path)
    else:
        upload_url = await upload_to_tempsh(file_path, update, context)
        if upload_url is not None:
            await context.bot.send_message(chat_id=update.message.chat_id, text=f"Файл слишком большой для отправки через Telegram. Вы можете скачать его по этой ссылке: {upload_url}")
        else:
            await context.bot.send_message(chat_id=update.message.chat_id, text="Не удалось загрузить файл.")
