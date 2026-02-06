from telegram import Update
from telegram.ext import ContextTypes
from bot.commands import user, admin
from bot.commands.utils import get_reply_keyboard, check_user_registration, is_admin
import logging

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        logging.warning("Update doesn't contain message")
        return

    try:
        text = update.message.text
        user_id = update.effective_user.id
        
        # Используем функцию из user.py вместо check_user_registration
        is_registered = user.is_user_registered(user_id)
        # Проверяем, является ли пользователь администратором
        is_user_admin = is_admin(user_id)
        
        logging.info(f"Пользователь {user_id}, статус регистрации: {is_registered}, админ: {is_user_admin}")

        if text == "ℹ️ Помощь":
            await user.help(update, context)
        elif text == "📝 Регистрация" and not is_registered:
            await user.register(update, context)
        elif text == "🔙 На главную":
            # Возвращаем администратора в главное меню
            await admin.back_to_main(update, context)
        elif is_registered or is_user_admin:
            # Обработка для подтвержденных пользователей или администраторов
            if text == "🚚 Доставка":
                await user.delivery(update, context)
            elif text == "🏎️ Заезд":
                await user.checkin(update, context)
            elif text == "🔙 Возврат":
                await user.refund(update, context)
            elif text == "🎨 Покраска":
                await user.painting(update, context)
            elif text == "⚙️ Админ-панель":
                await admin.admin_panel(update, context)
        else:
            # Если пользователь не подтвержден и не админ
            await update.message.reply_text(
                "⏳ Ваша регистрация еще не подтверждена администратором",
                reply_markup=get_reply_keyboard(user_id, False)
            )

    except Exception as e:
        logging.error(f"Error in handle_message: {e}")
        await update.message.reply_text(
            "Произошла ошибка. Пожалуйста, попробуйте снова.",
            reply_markup=get_reply_keyboard(user_id, is_registered)
        )
