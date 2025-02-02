#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .utils import convert_to_seconds
from .video_handler import download_video, send_or_upload_video, cleanup_temp_files

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS', '').split(',')

async def check_auth(update: Update) -> bool:
    """Check user authentication."""
    user_id = str(update.effective_user.id)
    if user_id not in ALLOWED_USER_IDS:
        await update.effective_message.reply_text('Unauthorized.')
        return False
    return True

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    if not await check_auth(update):
        return
    help_text = (
        "Commands:\n"
        "/start - Start bot\n"
        "/cut <video_link> <start_time> <duration> - Cut video\n"
        "/download <video_link> - Download video\n"
        "/help - Show this message"
    )
    await update.effective_message.reply_text(help_text)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()
    if query.data == 'cut':
        await query.edit_message_text(text="Usage: /cut <video_link> <start_time> <duration>")
    elif query.data == 'download':
        await query.edit_message_text(text="Usage: /download <video_link>")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send start menu."""
    if not await check_auth(update):
        return
    keyboard = [
        [InlineKeyboardButton("Cut Video", callback_data='cut'),
         InlineKeyboardButton("Download Video", callback_data='download')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.effective_message.reply_text('Select command:', reply_markup=reply_markup)

async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process video cutting."""
    if not await check_auth(update):
        return
    try:
        args = context.args
        if len(args) != 3:
            await update.effective_message.reply_text('Usage: /cut <video_link> <start_time> <duration>')
            return
        video_link, start_time, end_time = args
        try:
            start_seconds = convert_to_seconds(start_time)
            end_seconds = convert_to_seconds(end_time)
            if start_seconds < 0:
                raise ValueError("Negative start time")
            if end_seconds <= start_seconds:
                raise ValueError("End time must exceed start")
            duration_seconds = end_seconds - start_seconds
            duration_formatted = f"{duration_seconds // 3600:02d}:{(duration_seconds % 3600) // 60:02d}:{duration_seconds % 60:02d}"
            await update.effective_message.reply_text(
                f"Cutting video from {start_time} to {end_time} (Duration: {duration_formatted})"
            )
        except ValueError as e:
            await update.effective_message.reply_text(f"Time error: {e}. Use HH:MM:SS.")
            return
        logger.info(f"Cut: {video_link}, start: {start_time}, duration: {duration_seconds}s")
        if not await download_video(update, context, video_link, start_time, duration_seconds):
            return
        temp_video_path = os.path.join("temp", "temp_video.mp4")
        await send_or_upload_video(temp_video_path, update, context)
    except Exception as e:
        logger.error(f"Cut error: {e}")
        await update.effective_message.reply_text(f"Cut error: {e}")
    finally:
        cleanup_temp_files()

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process video download."""
    if not await check_auth(update):
        return
    try:
        args = context.args
        if len(args) != 1:
            await update.effective_message.reply_text('Usage: /download <video_link>')
            return
        video_link = args[0]
        if await download_video(update, context, video_link):
            temp_video_path = os.path.join("temp", "temp_video.mp4")
            await send_or_upload_video(temp_video_path, update, context)
    except Exception as e:
        logger.error(f"Download error: {e}")
        await update.effective_message.reply_text(f"Download error: {e}")
    finally:
        cleanup_temp_files()