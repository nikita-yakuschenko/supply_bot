from telegram import Update
from telegram.ext import ContextTypes

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Ошибка: {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")