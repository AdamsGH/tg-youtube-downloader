import logging
import os
import re
import asyncio
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from video_processing import download_video, send_or_upload_video, process_video  # Импорт функции обработки видео

# Настройка логирования
logger = logging.getLogger(__name__)

ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS').split(',')

def convert_to_seconds(time_str):
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    else:
        raise ValueError("Invalid time format. Use HH:MM:SS, MM:SS, or SS.")

async def help(update: Update, context: CallbackContext):
    help_text = (
        "Доступные команды:\n"
        "/start - Начать взаимодействие с ботом\n"
        "/cut - Обрезать видео\n"
        "/download - Скачать видео\n"
        "Выберите команду из меню ниже:"
    )
    keyboard = [[
        InlineKeyboardButton("Обрезать видео", callback_data='cut'),
        InlineKeyboardButton("Скачать видео", callback_data='download'),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(help_text, reply_markup=reply_markup)

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'cut':
        await query.edit_message_text(text="Введите /cut <video_link> <start_time> <duration>")
    elif query.data == 'download':
        await query.edit_message_text(text="Введите /download <video_link>")
    else:
        await query.edit_message_text(text="Неизвестная команда. Пожалуйста, выберите команду из меню.")

async def check_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        await update.message.reply_text('Извините, но вы не авторизованы для использования этого бота.')
        return False
    return True

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        await update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return
    await help(update, context)

async def cut(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        await update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text('Недопустимое количество аргументов. Использование:\n/cut <video_link> <start_time> <duration>')
        return

    video_link = args[0]
    start_time = args[1]
    duration = args[2]

    try:
        start_time_seconds = convert_to_seconds(start_time)
        duration_seconds = convert_to_seconds(duration)
    except ValueError as e:
        await update.message.reply_text(f'Ошибка в формате времени: {str(e)}')
        return

    # Рассчитываем продолжительность, если duration передан как конечное время
    if ':' in duration:
        end_time_seconds = convert_to_seconds(duration)
        duration_seconds = end_time_seconds - start_time_seconds

    await update.message.reply_text('Начинаю загрузку...')
    success = await download_video(update, context, video_link)

    if success:
        await process_video(update, context, str(start_time_seconds), duration_seconds)
    else:
        await update.message.reply_text('Ошибка: не удалось загрузить видео.')

async def download(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        await update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return
    args = context.args
    if len(args) != 1:
        await update.message.reply_text('Недопустимое количество аргументов. Использование: /download <video_link>')
        return

    video_link = args[0]
    await update.message.reply_text('Начинаю загрузку...')
    success = await download_video(update, context, video_link)

    if not success:
        await update.message.reply_text('Ошибка: не удалось загрузить видео.')
