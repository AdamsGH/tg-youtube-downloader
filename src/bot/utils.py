import logging
import time
import re
import asyncio
from telegram import Update
from telegram.ext import ContextTypes, Application
from tqdm import tqdm

# Глобальная очередь для обновлений прогресса
progress_queue = asyncio.Queue()

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

async def create_callback(encoder, update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """
    Создает callback функцию для отслеживания прогресса загрузки файла.
    """
    bar = tqdm(total=encoder.len, unit='B', unit_scale=True)
    last_update_time = 0
    upload_complete = False

    async def callback(monitor):
        nonlocal last_update_time
        nonlocal upload_complete
        bar.update(monitor.bytes_read - bar.n)
        current_time = time.time()
        if current_time - last_update_time >= 5:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.message.chat_id,
                    message_id=message_id,
                    text=f'Загрузка: {bar.n / bar.total * 100:.2f}%'
                )
                last_update_time = current_time
            except Exception as e:
                logging.error(f"Ошибка при обновлении прогресса: {str(e)}")

        if bar.n == bar.total and not upload_complete:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.message.chat_id,
                    message_id=message_id,
                    text='Загрузка завершена.'
                )
                upload_complete = True
            except Exception as e:
                logging.error(f"Ошибка при обновлении статуса завершения: {str(e)}")

    return callback

def progress_hook(d: dict, update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """
    Отслеживает прогресс загрузки видео и обновляет сообщение с прогрессом.
    Эта функция должна быть синхронной, так как она вызывается из yt-dlp.
    """
    if d['status'] == 'downloading':
        current_time = time.time()
        if current_time - getattr(progress_hook, 'last_update_time', 0) >= 10:
            try:
                percent = d['_percent_str']
                # Удаление ANSI цветовых кодов
                percent = re.sub(r'\x1b\[.*?m', '', percent)
                
                # Добавляем информацию об обновлении в очередь
                update_info = {
                    'chat_id': update.message.chat_id,
                    'message_id': message_id,
                    'text': f'Загрузка: {percent}'
                }
                
                # Используем sync_q.put_nowait() для добавления в очередь без блокировки
                try:
                    progress_queue.put_nowait(update_info)
                except asyncio.QueueFull:
                    logging.warning("Очередь обновлений прогресса переполнена")
                
                progress_hook.last_update_time = current_time
            except Exception as e:
                logging.error(f"Ошибка при обновлении прогресса загрузки: {str(e)}")

# Инициализация атрибута для хранения времени последнего обновления
progress_hook.last_update_time = 0

async def process_progress_updates(application):
    """
    Фоновая задача, извлекающая обновления из очереди и обновляющая сообщение с прогрессом.
    Рекомендуется запускать эту функцию как фоновую задачу.
    """
    while True:
        try:
            update_info = await progress_queue.get()
            try:
                await application.bot.edit_message_text(
                    chat_id=update_info['chat_id'],
                    message_id=update_info['message_id'],
                    text=update_info['text']
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке обновления прогресса: {e}")
            finally:
                progress_queue.task_done()
        except Exception as e:
            logging.error(f"Ошибка при обработке очереди прогресса: {e}")
        # Небольшая задержка, чтобы не грузить цикл событий
        await asyncio.sleep(0.5)