import os
import logging
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from src.bot.commands import start, help, cut, download, button

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """
    Основная функция запуска бота.
    Инициализирует и запускает бота с настроенными обработчиками команд.
    """
    # Получение токена из переменных окружения
    TOKEN = os.getenv('TOKEN')
    if not TOKEN:
        logger.error("Не установлен токен бота в переменных окружения")
        return

    try:
        # Инициализация бота
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher

        # Регистрация обработчиков команд
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help))
        dp.add_handler(CommandHandler("cut", cut))
        dp.add_handler(CommandHandler("download", download))
        dp.add_handler(CallbackQueryHandler(button))

        # Запуск бота
        logger.info("Бот запущен и готов к работе")
        updater.start_polling()
        updater.idle()

    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {str(e)}")

if __name__ == '__main__':
    main()
