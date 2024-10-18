import logging
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)
from bot_commands import help_command, button_handler, start, cut, download, handle_save_video

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Глобальный обработчик ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    # Можно отправить сообщение пользователю о том, что произошла ошибка
    if isinstance(update, Update):
        try:
            await update.effective_message.reply_text('Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.')
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения об ошибке пользователю: {e}")

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
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cut", cut))
    app.add_handler(CommandHandler("download", download))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_save_video))

    # Регистрация глобального обработчика ошибок
    app.add_error_handler(error_handler)

    logger.info("Starting application...")
    app.run_polling()
    logger.info("Bot is now running!")

if __name__ == '__main__':
    logger.info("Script started. Calling main()...")
    main()
