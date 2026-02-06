from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.commands.user import save_user_to_json
import logging

# Удаляем импорт из main, чтобы избежать циклического импорта
# from main import get_main_keyboard

async def handle_admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, user_id = query.data.split('_')
    user_id = int(user_id)
    
    try:
        user_data = context.bot_data.get(f'pending_user_{user_id}')
        if not user_data:
            await query.edit_message_text("❌ Ошибка: данные пользователя не найдены")
            return

        if action == "approve":
            user_data['approved'] = True
            if save_user_to_json(user_data):
                # Импортируем функцию здесь, чтобы избежать циклического импорта
                from main import get_reply_keyboard
                
                # Отправляем новую клавиатуру пользователю
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Ваша регистрация подтверждена! Теперь вам доступны все функции.",
                    reply_markup=get_reply_keyboard(user_id, is_registered=True)
                )
                
                # Отправляем сообщение администратору о том, что регистрация подтверждена
                await query.edit_message_text(
                    f"✅ Регистрация пользователя {user_data['fullname']} успешно подтверждена!"
                )
            else:
                await query.edit_message_text("❌ Ошибка при сохранении данных")
                
        elif action == "reject":
            # Импортируем функцию здесь, чтобы избежать циклического импорта
            from main import get_reply_keyboard
            
            # Отправляем сообщение пользователю
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ваша регистрация отклонена. Пожалуйста, обратитесь к администратору.",
                reply_markup=get_reply_keyboard(user_id, is_registered=False)
            )
            
            # Отправляем сообщение администратору
            await query.edit_message_text(
                f"❌ Регистрация пользователя {user_data['fullname']} отклонена"
            )
            
        # Удаляем данные пользователя из временного хранилища
        del context.bot_data[f'pending_user_{user_id}']
        
    except Exception as e:
        logging.error(f"Error in handle_admin_approval: {e}")
        await query.edit_message_text("⚠️ Произошла ошибка при обработке запроса")
