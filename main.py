import logging
import time
import yt_dlp
import subprocess
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler
import re
from tqdm import tqdm
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
import requests

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS').split(',')
last_update_time = 0
message_id = None

# Создание сессии requests
session = requests.Session()

# Создание меню с кнопками для команд
def help(update: Update, context: CallbackContext):
    """
    Отправляет пользователю сообщение с описанием доступных команд.

    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    """
    help_text = (
        "Доступные команды:\n"
        "/start - Начать взаимодействие с ботом\n"
        "/cut <video_link> <start_time> <duration> - Обрезать видео\n"
        "/download <video_link> - Скачать видео\n"
        "/help - Показать это сообщение"
    )
    update.message.reply_text(help_text)

# Функция для обработки нажатий на кнопки
def button(update: Update, context: CallbackContext):
    """
    Обрабатывает нажатия на кнопки в меню.

    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    """
    query = update.callback_query

    query.answer()

    if query.data == 'cut':
        query.edit_message_text(text="Введите /cut <video_link> <start_time> <duration>")
    elif query.data == 'download':
        query.edit_message_text(text="Введите /download <video_link>")


def check_user(update: Update, context: CallbackContext):
    """
    Проверяет, авторизован ли пользователь для использования бота.

    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    :return: True, если пользователь авторизован, иначе False.
    """
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USERS:
        update.message.reply_text('Извините, но вы не авторизованы для использования этого бота.')
        return False
    return True

# Создание callback функции для отслеживания прогресса загрузки
def create_callback(encoder, update, context, message_id):
    """
    Создает callback функцию для отслеживания прогресса загрузки файла.

    :param encoder: Объект MultipartEncoder, используемый для загрузки файла.
    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    :param message_id: ID сообщения, которое будет обновляться с прогрессом загрузки.
    :return: Callback функция для отслеживания прогресса загрузки.
    """
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


# Загрузка файла на temp.sh
def upload_to_tempsh(file_path, update: Update, context: CallbackContext):
    """
    Загружает файл на сервис temp.sh и возвращает URL для скачивания.

    :param file_path: Путь к файлу, который нужно загрузить.
    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    :return: URL для скачивания файла или None, если загрузка не удалась.
    """
    try:
        logging.info(f"Начало загрузки файла {file_path}")
        with open(file_path, 'rb') as file:
            encoder = MultipartEncoder(fields={'file': ('video.mp4', file)})
            message = update.message.reply_text('Загрузка началась...')
            message_id = message.message_id
            monitor = MultipartEncoderMonitor(encoder, create_callback(encoder, update, context, message_id))

            for i in range(3):  # Попытка загрузки 3 раза
                response = session.post('https://temp.sh/upload', data=monitor, headers={'Content-Type': monitor.content_type})
                if response.status_code == 200:
                    upload_url = response.text
                    logging.info(f"Загрузка успешна, URL: {upload_url}")
                    return upload_url
                elif response.status_code == 502 and i < 2:  # Если сервер возвращает ошибку 502 и это не последняя попытка
                    logging.warning(f"Не удалось загрузить {file_path}, код ответа сервера: {response.status_code}. Повторная попытка...")
                    time.sleep(5)  # Пауза перед повторной попыткой
                else:
                    logging.error(f"Не удалось загрузить {file_path}, код ответа сервера: {response.status_code}")
                    return None
    except Exception as e:
        logging.error(f"Не удалось загрузить {file_path}, ошибка: {str(e)}")
        return None

# Загрузка видео с помощью yt_dlp
def download_video(update: Update, context: CallbackContext, video_link):
    """
    Загружает видео с помощью yt_dlp и сохраняет его во временный файл.

    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    :param video_link: Ссылка на видео, которое нужно загрузить.
    """
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
    """
    Отслеживает прогресс загрузки видео и обновляет сообщение с прогрессом.

    :param d: Словарь с информацией о прогрессе загрузки.
    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    """
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
    """
    Отправляет пользователю начальное сообщение с меню команд.

    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    """
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
def send_or_upload_video(file_path, update: Update, context: CallbackContext):
    """
    Отправляет видео пользователю напрямую, если его размер меньше 50MB, иначе загружает его на temp.sh и отправляет ссылку.

    :param file_path: Путь к файлу видео.
    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    """
    file_size = os.path.getsize(file_path)
    if file_size <  50 * 1024 * 1024:  # 50MB
        with open(file_path, 'rb') as video_file:
            context.bot.send_video(chat_id=update.message.chat_id, video=video_file)
        logging.info(f"Video sent directly in chat {update.message.chat_id}")
    else:
        upload_url = upload_to_tempsh(file_path, update, context)
        if upload_url is not None:
            context.bot.send_message(chat_id=update.message.chat_id, text=f"Файл слишком большой для отправки через Telegram. Вы можете скачать его по этой ссылке: {upload_url}")
            logging.info(f"Video uploaded to temp.sh and link sent in chat {update.message.chat_id}")
        else:
            context.bot.send_message(chat_id=update.message.chat_id, text="Не удалось загрузить файл.")
            logging.error(f"Failed to upload video from chat {update.message.chat_id}")

# Обрезка видео
def cut(update: Update, context: CallbackContext):
    """
    Обрезает видео по заданным параметрам и отправляет результат пользователю.

    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    """
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
    send_or_upload_video('output_video.mp4', update, context)

    # Очистка временных файлов
    os.remove('output_video.mp4')
    os.remove('temp_video.mp4')

# Загрузка видео
def download(update: Update, context: CallbackContext):
    """
    Загружает видео по ссылке и отправляет его пользователю.

    :param update: Объект Update, содержащий информацию о сообщении.
    :param context: Объект CallbackContext, содержащий контекст выполнения команды.
    """
    user_id = update.effective_user.id
    if str(user_id) not in ALLOWED_USER_IDS:
        update.message.reply_text('Вы не авторизованы для выполнения этой команды.')
        return
    args = context.args
    if len(args) != 1:
        update.message.reply_text('Invalid number of arguments. Usage: /download <video_link>')
        return

    video_link = args[0]

    # update.message.reply_text('Начало загрузки...')
    download_video(update, context, video_link)

    # Отправка загруженного видео
    send_or_upload_video('temp_video.mp4', update, context)

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

