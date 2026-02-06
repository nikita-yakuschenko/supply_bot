from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from bot.commands.utils import get_reply_keyboard, get_cancel_keyboard, get_owner_fullname, is_admin, get_user_settings, update_user_settings
from config import Config
import logging
import os, asyncio
from datetime import datetime
from bot.services.supabase_storage import (
    get_admin_username,
    get_form_by_type_and_number,
    get_next_form_number,
    get_user_by_id as get_user_by_id_from_supabase,
    is_user_registered as is_user_registered_in_supabase,
    save_form_to_supabase,
    upsert_user,
)

# Состояния для ConversationHandler
FULLNAME, PHONE, POSITION, DEPARTMENT = range(4)

def save_user_to_json(user_data):
    try:
        return upsert_user(user_data)
    except Exception as e:
        logging.error(f"Failed to save user: {e}")
        return False

def is_user_registered(user_id):
    """Check user registration status."""
    try:
        return is_user_registered_in_supabase(user_id)
    except Exception as e:
        logging.error(f"Failed to check registration: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        is_registered = is_user_registered(user_id)
        is_user_admin = is_admin(user_id)

        if "last_bot_message_id" in context.user_data:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data["last_bot_message_id"]
                )
            except Exception as e:
                logging.warning(f"Couldn't delete previous message: {e}")

        new_msg = await update.message.reply_text(
            "Добро пожаловать!" if not is_registered else "С возвращением!",
            reply_markup=get_reply_keyboard(user_id, is_registered or is_user_admin)
        )

        if new_msg:
            context.user_data["last_bot_message_id"] = new_msg.message_id

    except Exception as e:
        logging.error(f"Error in start: {e}")
        await update.message.reply_text(
            "Ошибка при запуске. Попробуйте снова.",
            reply_markup=get_reply_keyboard(update.effective_user.id)
        )

async def help(update, context):
    user_id = update.effective_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    is_registered = is_user_registered(user_id)
    is_user_admin = is_admin(user_id)
    
    if is_registered or is_user_admin:
        # Получаем ID администратора из переменных окружения
        admin_ids = os.getenv('ADMIN_IDS', '').split(',')
        admin_ids = [int(x.strip()) for x in admin_ids if x.strip().isdigit()]
        admin_username = get_admin_username(admin_ids)
        contact_link = f"t.me/{admin_username}" if admin_username else "t.me/gdcoding"
        
        help_text = (
            "✨ ℹ️ РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ ℹ️ ✨\n\n"
            "1. 📝 Регистрация - подача официальной заявки на доступ к системе\n"
            "2. 🚚 Доставка - формирование заявки на доставку материалов в системе Битрикс24\n"
            "3. 🚗 Заезд - формирование заявки на заезд в системе Битрикс24\n"
            "4. 🔄 Возврат - оформление процедуры возврата материалов через Битрикс24\n"
            "5. 🎨 Покраска - создание заявки на услуги покраски в системе Битрикс24\n\n"
            f"❗ Для получения дополнительной помощи обратитесь к [специалисту]({contact_link}) ❗"
        )
    else:
        # Получаем ID администратора из переменных окружения
        admin_ids = os.getenv('ADMIN_IDS', '').split(',')
        admin_ids_int = [int(x.strip()) for x in admin_ids if x.strip().isdigit()]
        admin_id = str(admin_ids_int[0]) if admin_ids_int else None
        admin_username = get_admin_username(admin_ids_int)
        contact_link = f"t.me/{admin_username}" if admin_username else f"tg://user?id={admin_id}"
        
        help_text = (
            "ℹ️ РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ:\n\n"
            "1. 📝 Регистрация - подача официальной заявки на доступ к системе\n\n"
            f"❗ Для получения дополнительной помощи обратитесь к [специалисту]({contact_link}) ❗"
        )
    
    await update.message.reply_text(
        help_text,
        reply_markup=get_reply_keyboard(user_id, is_registered or is_user_admin), parse_mode='Markdown'
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса регистрации"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором
    if is_admin(user_id):
        await update.message.reply_text(
            "👑 Вы являетесь администратором бота и уже имеете полный доступ.",
            reply_markup=get_reply_keyboard(user_id, is_registered=True)
        )
        return ConversationHandler.END
    
    # Проверяем, зарегистрирован ли пользователь
    if is_user_registered(user_id):
        await update.message.reply_text(
            "✅ Вы уже зарегистрированы в системе!",
            reply_markup=get_reply_keyboard(user_id, is_registered=True)
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 Начинаем регистрацию!\n\n"
        "Пожалуйста, введите ваше ФИО полностью (Фамилия Имя Отчество):",
        reply_markup=get_cancel_keyboard()
    )
    return FULLNAME

async def get_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ФИО и запрос номера телефона"""
    # Проверяем, не нажата ли кнопка отмены
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
        
    fullname = update.message.text.strip()
    
    # Проверка корректности ФИО (должно содержать минимум 2 слова, только буквы)
    name_parts = fullname.split()
    if len(name_parts) < 2 or not all(part.isalpha() for part in name_parts):
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректное ФИО (Фамилия Имя Отчество).\n"
            "ФИО должно содержать только буквы и состоять минимум из двух слов.",
            reply_markup=get_cancel_keyboard()
        )
        return FULLNAME
    
    context.user_data['fullname'] = fullname
    
    await update.message.reply_text(
        f"Спасибо, {fullname}!\n\n"
        "Теперь введите ваш номер телефона в формате +7XXXXXXXXXX или 8XXXXXXXXXX:",
        reply_markup=get_cancel_keyboard()
    )
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение номера телефона и запрос должности"""
    # Проверяем, не нажата ли кнопка отмены
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
        
    phone = update.message.text.strip()
    
    # Проверка формата номера телефона (должен начинаться с +7 или 8 и содержать 11-12 цифр)
    import re
    if not re.match(r'^\+?7\d{10}$', phone.replace(' ', '')) and not re.match(r'^8\d{10}$', phone.replace(' ', '')):
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректный номер телефона в формате +7XXXXXXXXXX или 8XXXXXXXXXX.",
            reply_markup=get_cancel_keyboard()
        )
        return PHONE
    
    # Нормализация формата телефона
    phone = '+7' + re.sub (r'[^\d]', '', phone)[-10:]
    context.user_data['phone'] = phone
    
    await update.message.reply_text(
        "Отлично!\n\n"
        "Укажите вашу должность (не менее 3 символов):",
        reply_markup=get_cancel_keyboard()
    )
    return POSITION

async def get_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение должности и запрос подразделения"""
    # Проверяем, не нажата ли кнопка отмены
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
        
    position = update.message.text.strip()
    
    # Проверка корректности должности (минимум 3 символа)
    if len(position) < 3:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректную должность (не менее 3 символов).",
            reply_markup=get_cancel_keyboard()
        )
        return POSITION
    
    context.user_data['position'] = position
    
    await update.message.reply_text(
        "Почти готово!\n\n"
        "Укажите ваше подразделение (не менее 2 символов):",
        reply_markup=get_cancel_keyboard()
    )
    return DEPARTMENT

async def get_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение регистрации"""
    # Проверяем, не нажата ли кнопка отмены
    if update.message.text == "❌ Отмена":
        return await cancel(update, context)
        
    department = update.message.text.strip()
    
    # Проверка корректности подразделения (минимум 2 символа)
    if len(department) < 2:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректное название подразделения (не менее 2 символов).",
            reply_markup=get_cancel_keyboard()
        )
        return DEPARTMENT
    
    context.user_data['department'] = department
    
    user_id = update.effective_user.id
    username = update.effective_user.username or "Нет username"
    user_data = {
        'user_id': user_id,
        'username': username,
        'fullname': context.user_data.get('fullname', ''),
        'phone': context.user_data.get('phone', ''),
        'position': context.user_data.get('position', ''),
        'department': department,
        'approved': False,
        'admin': False
    }
    
    # Сохраняем данные
    if save_user_to_json(user_data):
        # Сохраняем данные пользователя в контексте бота для доступа при одобрении/отклонении
        context.bot_data[f'pending_user_{user_id}'] = user_data
        
        # Отправляем сообщение о завершении регистрации пользователю
        await update.message.reply_text(
            "✅ Регистрация завершена! Ваша заявка отправлена на рассмотрение администратору. "
            "Вы получите уведомление, когда ваша регистрация будет одобрена.",
            reply_markup=get_reply_keyboard(user_id, is_registered=False)
        )
        
        # Отправляем уведомление администраторам
        for admin_id in Config.ADMIN_IDS:
            try:
                # Создаем клавиатуру с кнопками для одобрения/отклонения
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}")
                    ]
                ])
                
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📝 Новая заявка на регистрацию:\n\n"
                         f"👤 Пользователь: {user_data['fullname']}\n"
                         f"🆔 ID: {user_id}\n"
                         f"👤 Username: @{username}\n"
                         f"📱 Телефон: {user_data['phone']}\n"
                         f"💼 Должность: {user_data['position']}\n"
                         f"🏢 Подразделение: {user_data['department']}\n\n"
                         f"Пожалуйста, одобрите или отклоните заявку:",
                    reply_markup=keyboard
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")
    else:
        await update.message.reply_text(
            "❌ Ошибка сохранения данных",
            reply_markup=get_reply_keyboard(user_id)
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена регистрации"""
    user_id = update.effective_user.id
    await update.message.reply_text(
        "❌ Регистрация отменена.",
        reply_markup=get_reply_keyboard(user_id)
    )
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Обязательно отвечаем на callback
    
    data = query.data
    user_id = int(data.split('_')[1])  # Извлекаем ID пользователя
    
    if data.startswith('approve_'):
        # Одобрение регистрации
        user_data = context.bot_data.get(f'pending_user_{user_id}')
        if user_data:
            user_data['approved'] = True
            if save_user_to_json(user_data):
                # Уведомляем пользователя
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Ваша регистрация одобрена! Теперь вы можете пользоваться ботом."
                )
                # Уведомляем администратора
                await query.edit_message_text(
                    text=f"✅ Регистрация пользователя {user_data['fullname']} одобрена.",
                    reply_markup=None
                )
            else:
                await query.edit_message_text(
                    text="❌ Ошибка при сохранении данных пользователя.",
                    reply_markup=None
                )
    
    elif data.startswith('reject_'):
        # Отклонение регистрации
        user_data = context.bot_data.pop(f'pending_user_{user_id}', None)
        if user_data:
            # Уведомляем пользователя
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Ваша регистрация отклонена администратором."
            )
            # Уведомляем администратора
            await query.edit_message_text(
                text=f"❌ Регистрация пользователя {user_data['fullname']} отклонена.",
                reply_markup=None
            )

# ДОСТАВКА
FORM_CONTRACT, FORM_TEXT, FORM_CONFIRM = range(3, 6)
CHECKIN_CONTRACT, CHECKIN_DATE, CHECKIN_BRIG_NAME, CHECKIN_BRIG_PHONE, CHECKIN_CARRYING, CHECKIN_CONFIRM = range(6, 12)

async def form_process(update: Update, context: ContextTypes.DEFAULT_TYPE, form_type: str, form_emoji: str):
    user_id = update.effective_user.id
    context.user_data['form_type'] = form_type
    context.user_data['form_emoji'] = form_emoji
    context.user_data['form_state'] = 'contract_number'
    await update.message.reply_text(
        f"{form_emoji} Пожалуйста, введите номер договора:",
        reply_markup=get_cancel_keyboard())
    return FORM_CONTRACT

async def delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await form_process(update, context, "delivery", "🚚")

async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['form_type'] = "checkin"
    context.user_data['form_emoji'] = "🏎️"
    await update.message.reply_text(
        "🏎️ Пожалуйста, введите номер договора:",
        reply_markup=get_cancel_keyboard())
    return CHECKIN_CONTRACT

async def refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await form_process(update, context, "refund", "🔙")

async def painting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await form_process(update, context, "painting", "🎨")

async def cancel_form_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    form_type = context.user_data.get('form_type', 'заявки')
    form_emoji = context.user_data.get('form_emoji', '')
    
    # Определяем название типа заявки на русском
    form_type_ru = "заявки"
    if form_type == "delivery":
        form_type_ru = "доставку"
    elif form_type == "refund":
        form_type_ru = "возврат"
    elif form_type == "painting":
        form_type_ru = "покраску"
    elif form_type == "checkin":
        form_type_ru = "заезд"
    
    # Очистка всех данных формы
    keys_to_delete = ['contract_number', 'form_text', 'form_state', 'form_type', 'form_emoji', 
                      'num_contract', 'date', 'name_brig', 'phone_brig', 'carring']
    
    for key in keys_to_delete:
        if key in context.user_data:
            del context.user_data[key]
    
    await update.message.reply_text(
        f"❌ Создание заявки на {form_type_ru} отменено.",
        reply_markup=get_reply_keyboard(user_id, is_registered=True))
    return ConversationHandler.END

async def get_form_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    user_id = update.effective_user.id
    
    # Проверка на отмену
    if update.message.text == "❌ Отмена":
        return await cancel_form_process(update, context)
    
    contract_number = update.message.text
    context.user_data['contract_number'] = contract_number
    form_type = context.user_data.get('form_type', 'заявки')
    form_emoji = context.user_data.get('form_emoji', '')
    
    # Определяем название типа заявки на русском
    form_type_ru = "заявки"
    if form_type == "delivery":
        form_type_ru = "доставку"
    elif form_type == "refund":
        form_type_ru = "возврат"
    elif form_type == "painting":
        form_type_ru = "покраску"
    
    if context.user_data.get('form_state') == 'edit_contract':
        keyboard = [
            [
                InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{form_type}"),
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{form_type}"),
            ],
            [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{form_type}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{form_emoji} Ваша заявка на {form_type_ru} (обновлено):\n\n"
            f"📄 Номер договора: {context.user_data['contract_number']}\n"
            f"📝 Текст заявки: {context.user_data['form_text']}\n\n"
            f"Пожалуйста, проверьте данные и выберите действие:",
            reply_markup=reply_markup)
        context.user_data['form_state'] = 'confirm'
        return FORM_CONFIRM
    else:
        context.user_data['form_state'] = 'form_text'
        await update.message.reply_text(
            f"{form_emoji} Теперь введите текст заявки:",
            reply_markup=get_cancel_keyboard())
        return FORM_TEXT

async def get_form_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текста заявки на доставку/возврат/покраску"""
    # Проверяем, не нажата ли кнопка отмены
    if update.message.text == "❌ Отмена":
        return await cancel_form_process(update, context)
    
    # Получаем тип формы из контекста
    form_type = context.user_data.get('form_type', '')
    form_text = update.message.text.strip()
    
    # Проверка входных данных (не пустые)
    if not form_text:
        await update.message.reply_text(
            "❌ Текст заявки не может быть пустым. Пожалуйста, введите информацию:",
            reply_markup=get_cancel_keyboard()
        )
        return context.user_data.get('current_state')
    
    # Если это доставка, проверяем настройку автонумерации
    if form_type == "delivery":
        # Получаем настройки пользователя
        user_settings = get_user_settings(update.effective_user.id)
        
        # Если включена автонумерация и текст не содержит нумерацию
        if user_settings.get('auto_numbering', False):
            # Проверяем, нет ли уже нумерации в тексте
            lines = form_text.strip().split('\n')
            has_numbering = any(line.strip() and line.strip()[0].isdigit() and line.strip()[1:3] in ['. ', ') '] for line in lines if line.strip())
            
            # Если нумерация отсутствует, добавляем её
            if not has_numbering:
                numbered_lines = []
                for i, line in enumerate(lines):
                    if line.strip():  # Пропускаем пустые строки
                        numbered_lines.append(f"{i+1}. {line}")
                    else:
                        numbered_lines.append(line)  # Сохраняем пустые строки как есть
                
                form_text = '\n'.join(numbered_lines)
    
    # Сохраняем текст заявки в контексте
    context.user_data['form_text'] = form_text
    
    # Формируем информацию о заявке для подтверждения
    contract_number = context.user_data.get('contract_number', '')
    
    # Определяем тип заявки
    if form_type == "delivery":
        form_name = "доставку"
    elif form_type == "refund":
        form_name = "возврат"
    elif form_type == "painting":
        form_name = "покраску"
    else:
        form_name = form_type
    
    # Создаем клавиатуру для подтверждения/отмены
    keyboard = keyboard = [
            [
                InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{form_type}"),
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{form_type}"),
            ],
            [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{form_type}")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с информацией о заявке и запрашиваем подтверждение
    await update.message.reply_text(
        f"📋 <b>Информация о заявке на {form_name}:</b>\n\n"
        f"Договор: <b>{contract_number}</b>\n\n"
        f"Текст заявки:\n<pre>{form_text}</pre>\n\n"
        f"Пожалуйста, проверьте информацию и подтвердите заявку:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # Возвращаем состояние ожидания подтверждения
    return FORM_CONFIRM

async def get_checkin_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, редактируем ли мы существующую заявку
    is_editing = context.user_data.get('is_editing_checkin', False)
    
    # Сохраняем номер договора
    context.user_data['num_contract'] = update.message.text
    
    if is_editing:
        # Если редактирование, возвращаемся к меню редактирования
        keyboard = [
            [InlineKeyboardButton("📄 Номер договора", callback_data="edit_checkin_contract")],
            [InlineKeyboardButton("📅 Дата заезда", callback_data="edit_checkin_date")],
            [InlineKeyboardButton("👤 ФИО бригадира", callback_data="edit_checkin_brig_name")],
            [InlineKeyboardButton("📱 Номер бригадира", callback_data="edit_checkin_brig_phone")],
            [InlineKeyboardButton("⚖️ Грузоподъёмность", callback_data="edit_checkin_carrying")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_checkin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🏎️ Данные заявки (обновлено):\n\n"
            f"📄 Номер договора: {context.user_data['num_contract']} ✅\n"
            f"📅 Дата заезда: {context.user_data.get('date', 'Не указано')}\n"
            f"👤 ФИО бригадира: {context.user_data.get('name_brig', 'Не указано')}\n"
            f"📱 Номер бригадира: {context.user_data.get('phone_brig', 'Не указано')}\n"
            f"⚖️ Грузоподъёмность: {context.user_data.get('carring', 'Не указано')}\n\n"
            f"✏️ Выберите поле для редактирования:",
            reply_markup=reply_markup
        )
        return CHECKIN_CONFIRM
    else:
        # Если первичное заполнение, переходим к следующему шагу
        await update.message.reply_text(
            "📅 Введите дату заезда (например, 01.01.2023):",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return CHECKIN_DATE

async def get_checkin_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, редактируем ли мы существующую заявку
    is_editing = context.user_data.get('is_editing_checkin', False)
    
    # Сохраняем дату заезда
    context.user_data['date'] = update.message.text
    
    if is_editing:
        # Если редактирование, возвращаемся к меню редактирования
        keyboard = [
            [InlineKeyboardButton("📄 Номер договора", callback_data="edit_checkin_contract")],
            [InlineKeyboardButton("📅 Дата заезда", callback_data="edit_checkin_date")],
            [InlineKeyboardButton("👤 ФИО бригадира", callback_data="edit_checkin_brig_name")],
            [InlineKeyboardButton("📱 Номер бригадира", callback_data="edit_checkin_brig_phone")],
            [InlineKeyboardButton("⚖️ Грузоподъёмность", callback_data="edit_checkin_carrying")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_checkin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🏎️ Данные заявки (обновлено):\n\n"
            f"📄 Номер договора: {context.user_data.get('num_contract', 'Не указано')}\n"
            f"📅 Дата заезда: {context.user_data['date']} ✅\n"
            f"👤 ФИО бригадира: {context.user_data.get('name_brig', 'Не указано')}\n"
            f"📱 Номер бригадира: {context.user_data.get('phone_brig', 'Не указано')}\n"
            f"⚖️ Грузоподъёмность: {context.user_data.get('carring', 'Не указано')}\n\n"
            f"✏️ Выберите поле для редактирования:",
            reply_markup=reply_markup
        )
        return CHECKIN_CONFIRM
    else:
        # Если первичное заполнение, переходим к следующему шагу
        await update.message.reply_text(
            "👤 Введите ФИО бригадира:",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return CHECKIN_BRIG_NAME

async def get_checkin_brig_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, редактируем ли мы существующую заявку
    is_editing = context.user_data.get('is_editing_checkin', False)
    
    # Сохраняем ФИО бригадира
    context.user_data['name_brig'] = update.message.text
    
    if is_editing:
        # Если редактирование, возвращаемся к меню редактирования
        keyboard = [
            [InlineKeyboardButton("📄 Номер договора", callback_data="edit_checkin_contract")],
            [InlineKeyboardButton("📅 Дата заезда", callback_data="edit_checkin_date")],
            [InlineKeyboardButton("👤 ФИО бригадира", callback_data="edit_checkin_brig_name")],
            [InlineKeyboardButton("📱 Номер бригадира", callback_data="edit_checkin_brig_phone")],
            [InlineKeyboardButton("⚖️ Грузоподъёмность", callback_data="edit_checkin_carrying")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_checkin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🏎️ Данные заявки (обновлено):\n\n"
            f"📄 Номер договора: {context.user_data.get('num_contract', 'Не указано')}\n"
            f"📅 Дата заезда: {context.user_data.get('date', 'Не указано')}\n"
            f"👤 ФИО бригадира: {context.user_data['name_brig']} ✅\n"
            f"📱 Номер бригадира: {context.user_data.get('phone_brig', 'Не указано')}\n"
            f"⚖️ Грузоподъёмность: {context.user_data.get('carring', 'Не указано')}\n\n"
            f"✏️ Выберите поле для редактирования:",
            reply_markup=reply_markup
        )
        return CHECKIN_CONFIRM
    else:
        # Если первичное заполнение, переходим к следующему шагу
        await update.message.reply_text(
            "📱 Введите номер телефона бригадира:",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return CHECKIN_BRIG_PHONE

async def get_checkin_brig_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, редактируем ли мы существующую заявку
    is_editing = context.user_data.get('is_editing_checkin', False)
    
    # Сохраняем номер телефона бригадира
    context.user_data['phone_brig'] = update.message.text
    
    if is_editing:
        # Если редактирование, возвращаемся к меню редактирования
        keyboard = [
            [InlineKeyboardButton("📄 Номер договора", callback_data="edit_checkin_contract")],
            [InlineKeyboardButton("📅 Дата заезда", callback_data="edit_checkin_date")],
            [InlineKeyboardButton("👤 ФИО бригадира", callback_data="edit_checkin_brig_name")],
            [InlineKeyboardButton("📱 Номер бригадира", callback_data="edit_checkin_brig_phone")],
            [InlineKeyboardButton("⚖️ Грузоподъёмность", callback_data="edit_checkin_carrying")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_checkin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🏎️ Данные заявки (обновлено):\n\n"
            f"📄 Номер договора: {context.user_data.get('num_contract', 'Не указано')}\n"
            f"📅 Дата заезда: {context.user_data.get('date', 'Не указано')}\n"
            f"👤 ФИО бригадира: {context.user_data.get('name_brig', 'Не указано')}\n"
            f"📱 Номер бригадира: {context.user_data['phone_brig']} ✅\n"
            f"⚖️ Грузоподъёмность: {context.user_data.get('carring', 'Не указано')}\n\n"
            f"✏️ Выберите поле для редактирования:",
            reply_markup=reply_markup
        )
        return CHECKIN_CONFIRM
    else:
        # Если первичное заполнение, переходим к следующему шагу
        await update.message.reply_text(
            "⚖️ Введите грузоподъемность:",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return CHECKIN_CARRYING

async def get_checkin_carrying(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, редактируем ли мы существующую заявку
    is_editing = context.user_data.get('is_editing_checkin', False)
    
    # Сохраняем грузоподъемность
    context.user_data['carring'] = update.message.text
    
    if is_editing:
        # Если редактирование, возвращаемся к меню редактирования
        keyboard = [
            [InlineKeyboardButton("📄 Номер договора", callback_data="edit_checkin_contract")],
            [InlineKeyboardButton("📅 Дата заезда", callback_data="edit_checkin_date")],
            [InlineKeyboardButton("👤 ФИО бригадира", callback_data="edit_checkin_brig_name")],
            [InlineKeyboardButton("📱 Номер бригадира", callback_data="edit_checkin_brig_phone")],
            [InlineKeyboardButton("⚖️ Грузоподъёмность", callback_data="edit_checkin_carrying")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_checkin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🏎️ Данные заявки (обновлено):\n\n"
            f"📄 Номер договора: {context.user_data.get('num_contract', 'Не указано')}\n"
            f"📅 Дата заезда: {context.user_data.get('date', 'Не указано')}\n"
            f"👤 ФИО бригадира: {context.user_data.get('name_brig', 'Не указано')}\n"
            f"📱 Номер бригадира: {context.user_data.get('phone_brig', 'Не указано')}\n"
            f"⚖️ Грузоподъёмность: {context.user_data['carring']} ✅\n\n"
            f"✏️ Выберите поле для редактирования:",
            reply_markup=reply_markup
        )
        return CHECKIN_CONFIRM
    else:
        # Переходим к подтверждению заявки
        keyboard = [
            [
                InlineKeyboardButton("✏️ Изменить", callback_data="edit_checkin"),
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_checkin"),
            ],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_checkin")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🏎️ Ваша заявка на заезд:\n\n"
            f"📄 Номер договора: {context.user_data['num_contract']}\n"
            f"📅 Дата заезда: {context.user_data['date']}\n"
            f"👤 ФИО бригадира: {context.user_data['name_brig']}\n"
            f"📱 Номер бригадира: {context.user_data['phone_brig']}\n"
            f"⚖️ Грузоподъёмность: {context.user_data['carring']}\n\n"
            f"Пожалуйста, проверьте данные и выберите действие:",
            reply_markup=reply_markup
        )
        return CHECKIN_CONFIRM

async def checkin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    import os
    import datetime
    import logging
    import asyncio
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    if data == "edit_checkin":
        keyboard = [
            [InlineKeyboardButton("📄 Номер договора", callback_data="edit_checkin_contract")],
            [InlineKeyboardButton("📅 Дата заезда", callback_data="edit_checkin_date")],
            [InlineKeyboardButton("👤 ФИО бригадира", callback_data="edit_checkin_brig_name")],
            [InlineKeyboardButton("📱 Номер бригадира", callback_data="edit_checkin_brig_phone")],
            [InlineKeyboardButton("⚖️ Грузоподъёмность", callback_data="edit_checkin_carrying")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_checkin")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                "✏️ Выберите, что хотите изменить:",
                reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text="✏️ Выберите, что хотите изменить:",
                reply_markup=reply_markup)
    
    elif data == "edit_checkin_contract":
        # Устанавливаем флаг редактирования
        context.user_data['is_editing_checkin'] = True
        await query.edit_message_text("📄 Введите новый номер договора:")
        return CHECKIN_CONTRACT
    elif data == "edit_checkin_date":
        # Устанавливаем флаг редактирования
        context.user_data['is_editing_checkin'] = True
        await query.edit_message_text("📅 Введите новую дату заезда:")
        return CHECKIN_DATE
    elif data == "edit_checkin_brig_name":
        # Устанавливаем флаг редактирования
        context.user_data['is_editing_checkin'] = True
        await query.edit_message_text("👤 Введите новое ФИО бригадира:")
        return CHECKIN_BRIG_NAME
    elif data == "edit_checkin_brig_phone":
        # Устанавливаем флаг редактирования
        context.user_data['is_editing_checkin'] = True
        await query.edit_message_text("📱 Введите новый номер телефона бригадира:")
        return CHECKIN_BRIG_PHONE
    elif data == "edit_checkin_carrying":
        # Устанавливаем флаг редактирования
        context.user_data['is_editing_checkin'] = True
        await query.edit_message_text("⚖️ Введите новую информацию о грузоподъёмности:")
        return CHECKIN_CARRYING
    elif data == "back_to_checkin":
        # Сбрасываем флаг редактирования при возврате к сводке заявки
        if 'is_editing_checkin' in context.user_data:
            del context.user_data['is_editing_checkin']
            
        # Возвращаемся к сводке заявки
        keyboard = [
            [
                InlineKeyboardButton("✏️ Изменить", callback_data="edit_checkin"),
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_checkin"),
            ],
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_checkin")]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        message_text = (
            f"🏎️ Ваша заявка на заезд:\n\n"
            f"📄 Номер договора: {context.user_data['num_contract']}\n"
            f"📅 Дата заезда: {context.user_data['date']}\n"
            f"👤 ФИО бригадира: {context.user_data['name_brig']}\n"
            f"📱 Номер бригадира: {context.user_data['phone_brig']}\n"
            f"⚖️ Грузоподъёмность: {context.user_data['carring']}\n\n"
            f"Пожалуйста, проверьте данные и выберите действие:")
        
        try:
            await query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=reply_markup)
    
    elif data == "confirm_checkin":
        # Сбрасываем флаг редактирования при подтверждении заявки
        if 'is_editing_checkin' in context.user_data:
            del context.user_data['is_editing_checkin']
        
        # Отправляем анимированный стикер с сообщением о загрузке только один раз
        try:
            # Отправляем сообщение о загрузке
            loading_message = await context.bot.send_message(
                chat_id=user_id,
                text="⏳ Загрузка..."
            )
            # Анимация загрузки
            loading_symbols = ["⏳", "⌛", "⏳", "⌛"]
            for i in range(3):  # Повторяем анимацию 3 раза
                for symbol in loading_symbols:
                    await asyncio.sleep(0.5)  # Пауза между кадрами анимации
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=loading_message.message_id,
                        text=f"{symbol} Загрузка..."
                    )
            
            # Удаляем сообщение с анимацией перед отправкой стикера
            await context.bot.delete_message(
                chat_id=user_id,
                message_id=loading_message.message_id
            )
            
            # Отправляем только стикер без дополнительного сообщения
            await context.bot.send_sticker(
                chat_id=user_id,
                sticker="CAACAgIAAxkBAAELCmBlwZXHRnhh-Wd-AAGQFWnYV2Dt9QACGgADr8ZRGkXCNYYgQJAyMAQ"  # ID стикера с загрузкой
            )
        except Exception as e:
            # Отправляем только одно сообщение в случае ошибки
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏳ Обработка заявки..."
                )
            except:
                pass
        
        try:
            form_number = get_next_form_number("checkin")
        except Exception as e:
            logging.error(f"Failed to generate form number: {e}")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Произошла ошибка при сохранении заявки. Пожалуйста, попробуйте позже."
                )
            except Exception:
                pass
            return ConversationHandler.END

        form_data = {
            "user_id": user_id,
            "type": "checkin",
            "form_number": form_number,
            "num_contract": context.user_data.get('num_contract', ''),
            "date": context.user_data.get('date', ''),
            "name_brig": context.user_data.get('name_brig', ''),
            "phone_brig": context.user_data.get('phone_brig', ''),
            "carring": context.user_data.get('carring', ''),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        user_fullname = ""
        try:
            user_record = get_user_by_id_from_supabase(user_id)
            if user_record:
                user_fullname = user_record.get("fullname", "")
        except Exception as e:
            logging.error(f"Failed to load user data: {e}")
        form_data["creator_fullname"] = user_fullname

        # Отправка задачи в Битрикс
        await send_task_to_bitrix(user_id, user_fullname, "checkin", form_data)

        try:
            save_form_to_supabase(form_data)
        except Exception as e:
            logging.error(f"Ошибка при сохранении в Supabase: {e}")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Ваша заявка на заезд №{form_number} успешно создана!")
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения: {e}")
        
        await context.bot.send_message(
            chat_id=user_id,
            text="Вы вернулись в главное меню",
            reply_markup=get_reply_keyboard(user_id, is_registered=True))
        
        for key in ['num_contract', 'date', 'name_brig', 'phone_brig', 'carring', 'form_type', 'form_emoji']:
            if key in context.user_data:
                del context.user_data[key]
        return ConversationHandler.END
    
    elif data == "cancel_checkin":
        try:
            await query.edit_message_text(
                "❌ Создание заявки на заезд отменено.",
                reply_markup=None)
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Создание заявки на заезд отменено.")

        await context.bot.send_message(
            chat_id=user_id,
            text="Вы вернулись в главное меню",
            reply_markup=get_reply_keyboard(user_id, is_registered=True))
        
        for key in ['num_contract', 'date', 'name_brig', 'phone_brig', 'carring', 'form_type', 'form_emoji']:
            if key in context.user_data:
                del context.user_data[key]
        return ConversationHandler.END

async def form_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    import os
    import datetime
    import logging
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    form_type = context.user_data.get('form_type', 'заявки')
    form_emoji = context.user_data.get('form_emoji', '')
    if data.startswith('edit_') and data != 'edit_contract' and data != 'edit_text':
        keyboard = [
            [InlineKeyboardButton("📄 Номер договора", callback_data="edit_contract")],
            [InlineKeyboardButton("📝 Текст заявки", callback_data="edit_text")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_form")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                "✏️ Выберите, что хотите изменить:",
                reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text="✏️ Выберите, что хотите изменить:",
                reply_markup=reply_markup)
    elif data == 'edit_contract':
        context.user_data['form_state'] = 'edit_contract'
        try:
            await query.edit_message_text("📄 Введите новый номер договора:")
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text="📄 Введите новый номер договора:")
        return FORM_CONTRACT
    elif data == 'edit_text':
        context.user_data['form_state'] = 'edit_text'
        try:
            await query.edit_message_text("📝 Введите новый текст заявки:")
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text="📝 Введите новый текст заявки:")
        return FORM_TEXT
    elif data == 'back_to_form':
        keyboard = [
            [
                InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{form_type}"),
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{form_type}"),
            ],
            [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{form_type}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message_text = (
            f"{form_emoji} Ваша заявка на {form_type}:\n\n"
            f"📄 Номер договора: {context.user_data['contract_number']}\n"
            f"📝 Текст заявки: {context.user_data['form_text']}\n\n"
            f"Пожалуйста, проверьте данные и выберите действие:")
        try:
            await query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=reply_markup)
    
    elif data.startswith('confirm_'):
        # Отправляем анимированный стикер с сообщением о загрузке только один раз
        try:
            # Отправляем сообщение о загрузке
            loading_message = await context.bot.send_message(
                chat_id=user_id,
                text="⏳ Загрузка..."
            )
            # Анимация загрузки
            loading_symbols = ["⏳", "⌛", "⏳", "⌛"]
            for i in range(3):  # Повторяем анимацию 3 раза
                for symbol in loading_symbols:
                    await asyncio.sleep(0.5)  # Пауза между кадрами анимации
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=loading_message.message_id,
                        text=f"{symbol} Загрузка..."
                    )
            
            # Удаляем сообщение с анимацией перед отправкой стикера
            await context.bot.delete_message(
                chat_id=user_id,
                message_id=loading_message.message_id
            )
            
            # Отправляем только стикер без дополнительного сообщения
            await context.bot.send_sticker(
                chat_id=user_id,
                sticker="CAACAgIAAxkBAAELCmBlwZXHRnhh-Wd-AAGQFWnYV2Dt9QACGgADr8ZRGkXCNYYgQJAyMAQ"  # ID стикера с загрузкой
            )
        except Exception as e:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏳ Обработка заявки..."
                )
            except:
                pass
        
        try:
            form_number = get_next_form_number(form_type)
        except Exception as e:
            logging.error(f"Failed to generate form number: {e}")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Произошла ошибка при сохранении заявки. Пожалуйста, попробуйте позже."
                )
            except Exception:
                pass
            return ConversationHandler.END

        form_data = {
            "user_id": user_id,
            "type": form_type,
            "form_number": form_number,
            "contract_number": context.user_data.get('contract_number', ''),
            "form_text": context.user_data.get('form_text', ''),
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

        user_fullname = ""
        try:
            user_record = get_user_by_id_from_supabase(user_id)
            if user_record:
                user_fullname = user_record.get("fullname", "")
        except Exception as e:
            logging.error(f"Failed to load user data: {e}")
        form_data["creator_fullname"] = user_fullname

        # Отправка задачи в Битрикс
        bitrix_result, error_message = await send_task_to_bitrix(user_id, user_fullname, form_type, form_data)
        
        if not bitrix_result:
            # Если ошибка при отправке в Битрикс, отправляем сообщение с кнопкой повтора и текстом ошибки
            keyboard = [
                [InlineKeyboardButton("🔄 Отправить повторно", callback_data=f"retry_{form_type}_{form_number}")],
                [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{form_type}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Произошла ошибка при отправке заявки в Битрикс24.\n\n"
                     f"Номер заявки: #{form_number}\n"
                     f"Тип заявки: {form_type}\n"
                     f"Ошибка: {error_message}\n\n"
                     f"Пожалуйста, попробуйте отправить заявку повторно или отмените её.",
                reply_markup=reply_markup
            )
            return ConversationHandler.END

        # Если отправка в Битрикс успешна, сохраняем в Supabase
        text_name = ""
        if form_type == "delivery":
            text_name = "доставку"
        elif form_type == "refund":
            text_name = "возврат"
        elif form_type == "painting":
            text_name = "покраску"

        try:
            save_form_to_supabase(form_data)
        except Exception as e:
            logging.error(f"Ошибка при сохранении в Supabase: {e}")
            
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Ваша заявка на {text_name} №{form_number} успешно создана!")
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения: {e}")
            
        await context.bot.send_message(
            chat_id=user_id,
            text="Вы вернулись в главное меню",
            reply_markup=get_reply_keyboard(user_id, is_registered=True))
        
        # Очищаем данные формы
        for key in ['contract_number', 'form_text', 'form_state', 'form_type', 'form_emoji']:
            if key in context.user_data:
                del context.user_data[key]
        return ConversationHandler.END
    elif data.startswith('cancel_'):
        try:
            # Определяем название типа заявки на русском
            text_name = "заявку"
            if form_type == "delivery":
                text_name = "доставку"
            elif form_type == "refund":
                text_name = "возврат"
            elif form_type == "painting":
                text_name = "покраску"
            elif form_type == "checkin":
                text_name = "заезд"
            
            await query.edit_message_text(
                f"❌ Создание заявки на {text_name} отменено.",
                reply_markup=None)
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Создание заявки отменено.")
        await context.bot.send_message(
            chat_id=user_id,
            text="Вы вернулись в главное меню",
            reply_markup=get_reply_keyboard(user_id, is_registered=True))
        if 'contract_number' in context.user_data:
            del context.user_data['contract_number']
        if 'form_text' in context.user_data:
            del context.user_data['form_text']
        if 'form_state' in context.user_data:
            del context.user_data['form_state']
        if 'form_type' in context.user_data:
            del context.user_data['form_type']
        if 'form_emoji' in context.user_data:
            del context.user_data['form_emoji']
        return ConversationHandler.END

async def send_task_to_bitrix(user_id, user_fullname, form_type, form_data):
    import requests
    import logging
    import os
    import datetime
    from bot.commands.utils import get_owner_fullname
    
    try:
        # Проверяем, является ли пользователь владельцем бота
        # Если да, используем ФИО из переменной FULLNAME
        admin_ids = os.getenv('ADMIN_IDS', '').split(',')
        admin_ids = [int(id.strip()) for id in admin_ids if id.strip().isdigit()]
        
        if user_id in admin_ids:
            user_fullname = get_owner_fullname()
            logging.info(f"Используем ФИО владельца бота: {user_fullname}")
        
        # Получаем данные пользователя из Битрикс по ФИО
        from bitrix_addon import get_bitrix_user_by_fullname, create_bitrix_task_as_user
        
        bitrix_user = get_bitrix_user_by_fullname(user_fullname)
        if not bitrix_user:
            error_message = f"Пользователь с ФИО '{user_fullname}' не найден в Битрикс24"
            logging.warning(error_message)
            return False, error_message
            
        bitrix_user_id = bitrix_user.get('ID')
        if not bitrix_user_id:
            error_message = "Не удалось получить ID пользователя из Битрикс24"
            logging.warning(error_message)
            return False, error_message
        
        # Получаем текущую дату для заявки
        current_date = datetime.datetime.now().strftime("%d.%m.%Y")
        form_number = form_data.get('form_number', '')
            
        # Формируем заголовок и описание задачи
        if form_type == "delivery":
            task_title = f"Доставка Договор: {form_data.get('contract_number', '')}"
            
            # Получаем текст заявки как есть, без дополнительной обработки
            form_text = form_data.get('form_text', '')
            
            # Добавляем информацию о заявке
            task_description = form_text + f"\n\nЗаявка #{form_number} от {current_date}\n{user_fullname}"
            
            # Получаем ID ответственного и аудиторов из .env для доставки
            responsible_id = os.getenv('DELIVERY_RESPONSIBLE_ID')
            auditors_str = os.getenv('DELIVERY_AUDITORS', '[]')
            try:
                # Используем более надежный метод преобразования строки в список
                import ast
                try:
                    auditors = ast.literal_eval(auditors_str)
                except (ValueError, SyntaxError):
                    # Если метод не сработал, используем базовый разбор строки с фильтрацией невалидных значений
                    auditors = [x.strip() for x in auditors_str.strip('[]').replace("'", "").replace('"', '').split(',') if x.strip()]
                
                logging.info(f"Аудиторы для доставки: {auditors}")
            except Exception as e:
                logging.error(f"Ошибка при обработке аудиторов для доставки: {str(e)}")
                auditors = []
            
        elif form_type == "refund":
            task_title = f"Возврат материалов Договор: {form_data.get('contract_number', '')}"
            task_description = f"{form_data.get('form_text', '')}\n\nЗаявка #{form_number} от {current_date}\n{user_fullname}"
            
            # Получаем ID ответственного и аудиторов из .env для возврата
            responsible_id = os.getenv('RETURN_MATERIALS_RESPONSIBLE_ID')
            auditors_str = os.getenv('RETURN_MATERIALS_AUDITORS', '[]')
            try:
                # Используем более надежный метод преобразования строки в список
                import ast
                try:
                    auditors = ast.literal_eval(auditors_str)
                except (ValueError, SyntaxError):
                    # Если метод не сработал, используем базовый разбор строки с фильтрацией невалидных значений
                    auditors = [x.strip() for x in auditors_str.strip('[]').replace("'", "").replace('"', '').split(',') if x.strip()]
                
                logging.info(f"Аудиторы для возврата: {auditors}")
            except Exception as e:
                logging.error(f"Ошибка при обработке аудиторов для возврата: {str(e)}")
                auditors = []
            
        elif form_type == "painting":
            task_title = f"Покраска Договор: {form_data.get('contract_number', '')}"
            task_description = f"{form_data.get('form_text', '')}\n\nЗаявка #{form_number} от {current_date}\n{user_fullname}"
            
            # Получаем ID ответственного и аудиторов из .env для покраски
            responsible_id = os.getenv('PAINTING_RESPONSIBLE_ID')
            auditors_str = os.getenv('PAINTING_AUDITORS', '[]')
            try:
                # Используем более надежный метод преобразования строки в список
                import ast
                try:
                    auditors = ast.literal_eval(auditors_str)
                except (ValueError, SyntaxError):
                    # Если метод не сработал, используем базовый разбор строки с фильтрацией невалидных значений
                    auditors = [x.strip() for x in auditors_str.strip('[]').replace("'", "").replace('"', '').split(',') if x.strip()]
                
                logging.info(f"Аудиторы для покраски: {auditors}")
            except Exception as e:
                logging.error(f"Ошибка при обработке аудиторов для покраски: {str(e)}")
                auditors = []
            
        elif form_type == "checkin":
            task_title = f"Заезд Договор: {form_data.get('num_contract', '')}"
            task_description = (
                f"Договор: {form_data.get('num_contract', '')}\n"
                f"Дата Заезда: {form_data.get('date', '')}\n"
                f"ФИО Бригадира: {form_data.get('name_brig', '')}\n"
                f"Номер бригадира: {form_data.get('phone_brig', '')}\n"
                f"Грузоподъёмность: {form_data.get('carring', '')}\n\n"
                f"Заявка #{form_number} от {current_date}\n{user_fullname}"
            )
            
            # Получаем ID ответственного и аудиторов из .env для заезда
            responsible_id = os.getenv('CHECKIN_RESPONSIBLE_ID')
            auditors_str = os.getenv('CHECKIN_AUDITORS', '[]')
            try:
                # Используем более надежный метод преобразования строки в список
                import ast
                try:
                    auditors = ast.literal_eval(auditors_str)
                except (ValueError, SyntaxError):
                    # Если метод не сработал, используем базовый разбор строки с фильтрацией невалидных значений
                    auditors = [x.strip() for x in auditors_str.strip('[]').replace("'", "").replace('"', '').split(',') if x.strip()]
                
                logging.info(f"Аудиторы для заезда: {auditors}")
            except Exception as e:
                logging.error(f"Ошибка при обработке аудиторов для заезда: {str(e)}")
                auditors = []
        else:
            # Для неизвестных типов задач используем пустые значения
            responsible_id = None
            auditors = []
        
        # Создаем задачу в Битрикс от имени пользователя
        # с передачей ответственного и аудиторов
        from bitrix_addon import create_bitrix_task_with_responsible
        
        result = create_bitrix_task_with_responsible(
            creator_id=bitrix_user_id,
            title=task_title,
            description=task_description,
            responsible_id=responsible_id,
            auditors=auditors
        )
        
        if result:
            logging.info(f"Задача успешно создана в Битрикс24 для пользователя {user_fullname}")
            return True, ""
        else:
            error_message = "Ошибка при создании задачи в Битрикс24"
            logging.error(error_message)
            return False, error_message
            
    except Exception as e:
        error_message = f"Ошибка при отправке задачи в Битрикс24: {str(e)}"
        logging.error(error_message)
        return False, error_message

async def retry_bitrix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    # Проверяем, является ли это отменой
    if data.startswith('cancel_'):
        form_type = data.split('_')[1]
        await query.edit_message_text(
            f"❌ Создание заявки на {form_type} отменено.",
            reply_markup=None
        )
        await context.bot.send_message(
            chat_id=user_id,
            text="Вы вернулись в главное меню",
            reply_markup=get_reply_keyboard(user_id, is_registered=True)
        )
        return ConversationHandler.END
    
    # Извлекаем тип заявки и номер из callback_data
    _, form_type, form_number = data.split('_')
    form_number = int(form_number)
    
    # Получаем данные заявки из Supabase
    form_data = None
    try:
        form_data = get_form_by_type_and_number(form_type, form_number)
    except Exception as e:
        logging.error(f"Ошибка при чтении данных заявки: {e}")
    
    if not form_data:
        await query.edit_message_text(
            "❌ Не удалось найти данные заявки. Пожалуйста, создайте новую заявку.",
            reply_markup=None
        )
        return ConversationHandler.END
    
    # Получаем ФИО пользователя
    user_fullname = form_data.get('creator_fullname', '')
    
    # Пытаемся отправить заявку в Битрикс повторно
    bitrix_result, error_message = await send_task_to_bitrix(user_id, user_fullname, form_type, form_data)
    
    if not bitrix_result:
        # Если снова ошибка, показываем кнопки повтора и отмены с текстом ошибки
        keyboard = [
            [InlineKeyboardButton("🔄 Отправить повторно", callback_data=f"retry_{form_type}_{form_number}")],
            [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{form_type}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"❌ Снова произошла ошибка при отправке заявки в Битрикс24.\n\n"
            f"Номер заявки: #{form_number}\n"
            f"Тип заявки: {form_type}\n"
            f"Ошибка: {error_message}\n\n"
            f"Пожалуйста, попробуйте отправить заявку повторно или отмените её.",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    # Если отправка успешна, сохраняем в Supabase
    text_name = ""
    if form_type == "delivery":
        text_name = "доставку"
    elif form_type == "refund":
        text_name = "возврат"
    elif form_type == "painting":
        text_name = "покраску"

    try:
        save_form_to_supabase(form_data)
    except Exception as e:
        logging.error(f"Ошибка при сохранении в Supabase: {e}")
    
    # Отправляем сообщение об успешной отправке
    await query.edit_message_text(
        f"✅ Ваша заявка на {text_name} №{form_number} успешно отправлена!"
    )
    
    # Возвращаем в главное меню
    await context.bot.send_message(
        chat_id=user_id,
        text="Вы вернулись в главное меню",
        reply_markup=get_reply_keyboard(user_id, is_registered=True)
    )
    
    return ConversationHandler.END

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для настроек пользователя"""
    user_id = update.effective_user.id
    
    # Получаем текущие настройки пользователя
    user_settings = get_user_settings(user_id)
    
    # Создаем клавиатуру для настроек
    auto_numbering_status = "✅ Включен" if user_settings.get('auto_numbering', False) else "❌ Выключен"
    
    keyboard = [
        [InlineKeyboardButton(f"Автонумерация в Доставке: {auto_numbering_status}", callback_data="toggle_auto_numbering")],
        [InlineKeyboardButton("🔙 Вернуться в главное меню", callback_data="back_to_main_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ <b>Настройки</b>\n\n"
        "Здесь вы можете настроить работу бота под свои предпочтения.\n\n"
        "<b>Автонумерация в Доставке</b> - автоматически добавляет номера к каждой строке в списке товаров "
        "при создании заявки на доставку. Вам не нужно вручную нумеровать каждую позицию.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback запросов из меню настроек"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if query.data == "toggle_auto_numbering":
        # Получаем текущие настройки
        user_settings = get_user_settings(user_id)
        
        # Инвертируем значение auto_numbering
        new_value = not user_settings.get('auto_numbering', False)
        
        # Обновляем настройки
        update_user_settings(user_id, {'auto_numbering': new_value})
        
        # Обновляем сообщение с новым статусом
        auto_numbering_status = "✅ Включен" if new_value else "❌ Выключен"
        
        keyboard = [
            [InlineKeyboardButton(f"Автонумерация в Доставке: {auto_numbering_status}", callback_data="toggle_auto_numbering")],
            [InlineKeyboardButton("🔙 Вернуться в главное меню", callback_data="back_to_main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚙️ <b>Настройки</b>\n\n"
            "Здесь вы можете настроить работу бота под свои предпочтения.\n\n"
            "<b>Автонумерация в Доставке</b> - автоматически добавляет номера к каждой строке в списке товаров "
            "при создании заявки на доставку. Вам не нужно вручную нумеровать каждую позицию.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    elif query.data == "back_to_main_menu":
        # Возвращаемся в главное меню
        is_registered = is_user_registered(user_id)
        
        await query.message.reply_text(
            "Вы вернулись в главное меню",
            reply_markup=get_reply_keyboard(user_id, is_registered=is_registered)
        )
        
        # Удаляем сообщение с кнопками настроек
        try:
            await query.delete_message()
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщения: {e}")





