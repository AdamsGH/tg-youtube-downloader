import logging
import time
import yt_dlp
import subprocess
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
import re
from tqdm import tqdm
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS').split(',')
last_update_time = 0
message_id = None

# Создание меню с кнопками для команд
def help(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("/cut", callback_data='1'),
         InlineKeyboardButton("/download", callback_data='2')],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Выберите команду:', reply_markup=reply_markup)

# Функция для обработки нажатий на кнопки
def button(update: Update, context: CallbackContext):
    query = update.callback_query

    query.answer()

    if query.data == 'cut':
        query.edit_message_text(text="Введите /cut <video_link> <start_time> <duration>")
    elif query.data == 'download':
        query.edit_message_text(text="Введите /download <video_link>")


def check_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USERS:
        update.message.reply_text('Извините, но вы не авторизованы для использования этого бота.')
        return False
    return True

# Создание callback функции для отслеживания прогресса загрузки
def create_callback(encoder, update, context, message_id):
    bar = tqdm(total=encoder.len, unit='B', unit_scale=True)
    last_update_time = 0
    upload_complete = False

    def callback(monitor):
        nonlocal last_update_time
        nonlocal upload_complete
        bar.update(monitor.bytes_read - bar.n)
        current_time = time.time()
        if current_time - last_update_time >= 5:  # Обновление сообщения о прогрессе каждые 5 секунд
            context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message_id, text=f'Загрузка: {bar.n / bar.total * 100:.2f}%')
            last_update_time = current_time
        if bar.n == bar.total and not upload_complete:  # Если загрузка завершена и сообщение не было обновлено
            context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message_id, text='Загрузка завершена.')
            upload_complete = True

    return callback


# Загрузка файла на transfer.sh
def upload_to_transfersh(file_path, update: Update, context: CallbackContext):
    encoder = MultipartEncoder(
        fields={
            'file': ('video.mp4', open(file_path, 'rb')),
        }
    )
    message = update.message.reply_text('Загрузка началась...')
    message_id = message.message_id
    monitor = MultipartEncoderMonitor(encoder, create_callback(encoder, update, context, message_id))
    headers = {"Max-Downloads": "5", "Max-Days": "5", 'Content-Type': monitor.content_type}
    response = requests.post('https://transfer.sh/', data=monitor, headers=headers)
    if response.status_code == 200:
        delete_link = response.headers.get('X-Url-Delete')
        return response.text, delete_link
    else:
        return None, None


# Загрузка видео с помощью yt_dlp
def download_video(update: Update, context: CallbackContext, video_link):
    global message_id
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': 'temp_video.mp4',
        'nooverwrites': False,
        'progress_hooks': [lambda d: progress_hook(d, update, context)]
    }

    # Отправка начального сообщения о загрузке и сохранение его message_id для последующего редактирования
    message = update.message.reply_text('Загрузка началась...')
    message_id = message.message_id

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_link])

    context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message_id, text='Загрузка завершена.')

# Отслеживание прогресса загрузки
def progress_hook(d, update: Update, context: CallbackContext):
    global last_update_time
    global message_id
    if d['status'] == 'downloading':
        current_time = time.time()
        if current_time - last_update_time >= 10:
            percent = d['_percent_str']
            # Удаление ANSI цветовых кодов
            percent = re.sub(r'\x1b\[.*?m', '', percent)
            context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message_id, text=f'Загрузка: {percent}')
            last_update_time = current_time

# Начальное сообщение при взаимодействии с ботом
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return
    keyboard = [[
        InlineKeyboardButton("Обрезать видео", callback_data='cut'),
        InlineKeyboardButton("Скачать видео", callback_data='download'),
    ]]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Выберите команду:', reply_markup=reply_markup)


# Отправка или загрузка видео
def send_or_upload_video(update: Update, context: CallbackContext, file_path):
    file_size = os.path.getsize(file_path)
    if file_size > 200 * 1024 * 1024:  # Если размер файла больше 200MB
        message = update.message.reply_text('Файл слишком большой для отправки через Telegram. Загружаю на transfer.sh...')
        url, delete_link = upload_to_transfersh(file_path, update, context)
        if url is not None:
            delete_token = delete_link.split('/')[-1]  # Берем последнюю часть ссылки для удаления
            context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message.message_id, text='Загрузка завершена.')
            update.message.reply_text(f'Видео загружено на transfer.sh: {url}\nТокен для удаления: `{delete_token}`', parse_mode='Markdown')
            logger.info(f'Uploaded video to transfer.sh: {url}\nDelete token: {delete_token}')
        else:
            context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=message.message_id, text='Не удалось загрузить видео на transfer.sh.')
            logger.error('Failed to upload video to transfer.sh.')
    else:
        with open(file_path, 'rb') as video:
            context.bot.send_video(chat_id=update.message.chat_id, video=video)

# Обрезка видео
def cut(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return
    args = context.args
    if len(args) != 3:
        update.message.reply_text('Недопустимое количество аргументов. Использование:\n/cut <video_link> <start_time> <duration>\nor /download <video_link>')
        return

    video_link = args[0]
    start_time = args[1]
    duration = args[2]

    update.message.reply_text('Начинаю загрузку...')
    download_video(update, context, video_link)

    # Обрезка видео
    cut_command = f'ffmpeg -ss {start_time} -i temp_video.mp4 -t {duration} -c:v copy -c:a copy output_video.mp4'
    subprocess.run(cut_command, shell=True)

    # Загрузка обрезанного видео
    send_or_upload_video(update, context, 'output_video.mp4')

    # Очистка временных файлов
    os.remove('output_video.mp4')

# Загрузка видео
def download(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return
    args = context.args
    if len(args) != 1:
        update.message.reply_text('Invalid number of arguments. Usage: /download <video_link>')
        return

    video_link = args[0]

    update.message.reply_text('Начало загрузки...')
    download_video(update, context, video_link)

    # Отправка загруженного видео
    send_or_upload_video(update, context, 'temp_video.mp4')

    # Очистка временного файла
    os.remove('temp_video.mp4')

# Главная функция
def main():
    TOKEN = os.getenv('TOKEN')  # Замените на свой токен бота
    updater = Updater(TOKEN, use_context=True)

    dp = updater.dispatcher
    # Добавление обработчиков для команды /help и кнопок
    dp.add_handler(CommandHandler('help', help))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("cut", cut))
    dp.add_handler(CommandHandler("download", download))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

