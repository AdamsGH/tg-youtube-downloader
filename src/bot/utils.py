import logging
import time
from telegram import Update
from telegram.ext import CallbackContext
from tqdm import tqdm
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
import re

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

def create_callback(encoder, update, context, message_id):
    """
    Создает callback функцию для отслеживания прогресса загрузки файла.
    """
    bar = tqdm(total=encoder.len, unit='B', unit_scale=True)
    last_update_time = 0
    upload_complete = False

    def callback(monitor):
        nonlocal last_update_time
        nonlocal upload_complete
        bar.update(monitor.bytes_read - bar.n)
        current_time = time.time()
        if current_time - last_update_time >= 5:
            context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=message_id,
                text=f'Загрузка: {bar.n / bar.total * 100:.2f}%'
            )
            last_update_time = current_time
        if bar.n == bar.total and not upload_complete:
            context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=message_id,
                text='Загрузка завершена.'
            )
            upload_complete = True

    return callback

def progress_hook(d, update: Update, context: CallbackContext, message_id: int):
    """
    Отслеживает прогресс загрузки видео и обновляет сообщение с прогрессом.
    """
    if d['status'] == 'downloading':
        current_time = time.time()
        if current_time - getattr(progress_hook, 'last_update_time', 0) >= 10:
            percent = d['_percent_str']
            # Удаление ANSI цветовых кодов
            percent = re.sub(r'\x1b\[.*?m', '', percent)
            context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=message_id,
                text=f'Загрузка: {percent}'
            )
            progress_hook.last_update_time = current_time

# Инициализация атрибута для хранения времени последнего обновления
progress_hook.last_update_time = 0
