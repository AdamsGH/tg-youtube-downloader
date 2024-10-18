import logging
import os
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from bot_commands import help, button, start, cut, download  # Импорт функций из bot_commands

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Главная функция
def main():
    logger.info("Starting the bot...")
    TOKEN = os.getenv('TOKEN')
    if not TOKEN:
        logger.error("TOKEN environment variable is not set!")
        return

    logger.info("Building application...")
    app = ApplicationBuilder().token(TOKEN).build()

    logger.info("Adding handlers...")
    app.add_handler(CommandHandler('help', help))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cut", cut))
    app.add_handler(CommandHandler("download", download))

    logger.info("Starting application...")
    app.run_polling()
    logger.info("Bot is now running!")

if __name__ == '__main__':
    logger.info("Script started. Calling main()...")
    main()
