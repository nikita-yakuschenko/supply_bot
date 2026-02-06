from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import Config
import os
import logging
from bot.services.supabase_storage import (
    get_user_by_id as get_user_by_id_from_supabase,
    get_user_settings_from_supabase,
    is_user_admin as is_user_admin_in_supabase,
    is_user_registered as is_user_registered_in_supabase,
    list_applications_by_user,
    update_user_fields as update_user_fields_in_supabase,
    update_user_settings_in_supabase,
    upsert_user,
)

def is_admin(user_id):
    """Check whether user is bot admin."""
    try:
        admin_ids = os.getenv('ADMIN_IDS', '').split(',')
        admin_ids = [int(id.strip()) for id in admin_ids if id.strip().isdigit()]
        if user_id in admin_ids:
            return True
        return is_user_admin_in_supabase(user_id)
    except Exception as e:
        logging.error(f"Admin check failed: {e}")
        return False

def is_user_registered(user_id):
    """Check user registration status."""
    return is_user_registered_in_supabase(user_id)

async def cancel_operation(update, context, operation_name):
    """Отмена операции"""
    await update.message.reply_text(f"❌ {operation_name} отменена", reply_markup=get_reply_keyboard(update.effective_user.id, True))
    return ConversationHandler.END

def check_user_registration(user_id: int) -> bool:
    """Check user approved status."""
    return is_user_registered_in_supabase(user_id)

def get_reply_keyboard(user_id: int, is_registered: bool = False) -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру в зависимости от статуса регистрации"""
    if is_registered:
        keyboard = [
            [KeyboardButton("🚚 Доставка"), KeyboardButton("🏎️ Заезд")],
            [KeyboardButton("🔙 Возврат"), KeyboardButton("🎨 Покраска")],
            #[KeyboardButton("⚙️ Настройки")], 
            [KeyboardButton("ℹ️ Помощь")]
        ]
    else:
        # Клавиатура для незарегистрированных
        keyboard = [
            [KeyboardButton("📝 Регистрация"), KeyboardButton("ℹ️ Помощь")]
        ]
        
    # Добавляем админ-панель если пользователь админ
    if is_admin(user_id):
        if is_registered:
            keyboard.append([KeyboardButton("⚙️ Админ-панель")])
        else:
            keyboard = [
                [KeyboardButton("🚚 Доставка"), KeyboardButton("🏎️ Заезд")],
                [KeyboardButton("🔙 Возврат"), KeyboardButton("🎨 Покраска")],
                #[KeyboardButton("⚙️ Настройки")], 
                [KeyboardButton("ℹ️ Помощь")],
                [KeyboardButton("⚙️ Админ-панель")]
            ]
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой 'Отмена'"""
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True)

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для админ-панели"""
    keyboard = [
        [KeyboardButton("👥 Управление пользователями")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
        [KeyboardButton("🔙 На главную")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def save_user_to_json(user_data: dict) -> bool:
    try:
        return upsert_user(user_data)
    except Exception as e:
        logging.error(f"Failed to save user: {e}")
        return False
    
def check_user_registration(user_id: int) -> bool:
    """Check user approved status."""
    return is_user_registered_in_supabase(user_id)
    
async def force_update_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительное обновление клавиатуры"""
    user_id = update.effective_user.id
    is_registered = check_user_registration(user_id)
    
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
    except:
        pass
    
    await update.message.reply_text(
        "Клавиатура обновлена",
        reply_markup=get_reply_keyboard(user_id, is_registered)
    )

def get_user_by_id(user_id: int) -> dict:
    """Get user data by ID."""
    try:
        return get_user_by_id_from_supabase(user_id)
    except Exception as e:
        logging.error(f"Failed to read user data: {e}")
        return None

def update_user_data(user_id: int, new_data: dict) -> bool:
    """Update user data."""
    try:
        return update_user_fields_in_supabase(user_id, new_data)
    except Exception as e:
        logging.error(f"Failed to update user data: {e}")
        return False

def get_user_applications(user_id: int) -> list:
    """Get list of user applications."""
    try:
        return list_applications_by_user(user_id)
    except Exception as e:
        logging.error(f"Failed to read user applications: {e}")
        return []

def format_user_info(user: dict) -> str:
    """Форматирует информацию о пользователе для отображения"""
    return (
        f"👤 Имя: {user.get('username', 'Без имени')}\n"
        f"🆔 ID: {user.get('user_id')}\n\n"
        f"📱 Телефон: {user.get('phone', 'Не указан')}\n"
        f"👨‍💼 ФИО: {user.get('fullname', 'Не указано')}\n"
        f"🏢 Должность: {user.get('position', 'Не указана')}\n"
        f"🏢 Отдел: {user.get('department', 'Не указан')}\n\n"
        f"👑 Админ: {'Да' if user.get('admin', False) else 'Нет'}\n"
        f"✅ Подтвержден: {'Да' if user.get('approved', False) else 'Нет'}\n"
    )

def format_application_info(app: dict) -> str:
    """Форматирует информацию о заявке для отображения"""
    return (
        f"📋 Заявка #{app.get('id')}\n"
        f"📅 Дата: {app.get('date')}\n"
        f"📝 Тип: {app.get('type')}\n"
        f"📄 Описание: {app.get('description', 'Нет описания')}\n"
        f"📸 Фото: {'Есть' if app.get('photo') else 'Нет'}"
    )

def get_user_management_keyboard(current_page: int = 0, total_users: int = 0) -> ReplyKeyboardMarkup:
    """Создает клавиатуру для управления пользователями с учетом позиции в списке"""
    keyboard = []
    
    # Если это первый пользователь
    if current_page == 0:
        keyboard.append([
            KeyboardButton("🔙 Вернуться"),
            KeyboardButton("➡️")
        ])
    # Если это последний пользователь
    elif current_page == total_users - 1:
        keyboard.append([
            KeyboardButton("⬅️"),
            KeyboardButton("🔙 Вернуться")
        ])
    # Если пользователь в середине списка
    else:
        keyboard.append([
            KeyboardButton("⬅️"),
            KeyboardButton("🔙 Вернуться"),
            KeyboardButton("➡️")
        ])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_actions_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура действий с пользователем"""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Изменить данные", callback_data=f"edit_user_{user_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_user_{user_id}")
        ],
        [InlineKeyboardButton("📋 Список заявок", callback_data=f"user_applications_{user_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_owner_fullname():
    """Получает ФИО владельца бота из переменной окружения"""
    return os.getenv('FULLNAME', 'Администратор системы')

def get_user_settings(user_id: int) -> dict:
    """Get user settings."""
    try:
        return get_user_settings_from_supabase(user_id)
    except Exception as e:
        logging.error(f"Failed to read user settings: {e}")
        return {'auto_numbering': False}

def update_user_settings(user_id: int, new_settings: dict) -> bool:
    """Update user settings."""
    try:
        return update_user_settings_in_supabase(user_id, new_settings)
    except Exception as e:
        logging.error(f"Failed to update user settings: {e}")
        return False
