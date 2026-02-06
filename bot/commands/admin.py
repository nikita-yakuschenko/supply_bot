from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters
from bot.commands.utils import (
    is_admin, get_reply_keyboard, check_user_registration,
    get_user_by_id, update_user_data, get_user_applications,
    format_user_info, format_application_info,
    get_user_management_keyboard, get_user_actions_keyboard
)
import logging
import json
import os
import csv
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import tempfile
import matplotlib as mpl
from matplotlib.font_manager import FontProperties
import asyncio
import time
from bot.services.supabase_storage import (
    delete_application,
    delete_user as delete_user_from_supabase,
    get_application_by_id,
    get_forms_grouped_for_export,
    get_usage_stats,
    list_applications_by_type,
    list_users,
    update_application_field,
)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором с помощью улучшенной функции
    is_user_admin = is_admin(user_id)
    
    if not is_user_admin:
        await update.message.reply_text("⛔ Доступ запрещён!")
        return
    
    # Клавиатура только для админов
    admin_keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("👥 Управление пользователями")],

            [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
            [KeyboardButton("🔙 На главную")]
        ],
        resize_keyboard=True
    )
    
    await update.message.reply_text(
        "⚙️ Админ-панель:",
        reply_markup=admin_keyboard
    )

async def handle_user_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки управления пользователями"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для управления пользователями")
        return
    
    try:
        users = list_users()
        
        if not users:
            await update.message.reply_text("Список пользователей пуст")
            return
        
        # Сохраняем список пользователей в контексте
        context.user_data['users'] = users
        # Если current_page не установлен или выходит за пределы списка, устанавливаем 0
        if 'current_page' not in context.user_data or context.user_data['current_page'] >= len(users):
            context.user_data['current_page'] = 0
        
        # Отправляем информацию о пользователе с навигационными кнопками
        # Эта функция создаст все необходимые клавиатуры и сообщения
        await send_user_list(update, context)
    except Exception as e:
        logging.error(f"Ошибка получения списка пользователей: {e}")
        await update.message.reply_text("Ошибка при получении списка пользователей")

async def send_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет информацию о текущем пользователе с правильными кнопками навигации"""
    users = context.user_data.get('users', [])
    current_page = context.user_data.get('current_page', 0)
    
    if not users:
        if update.message:
            await update.message.reply_text("Список пользователей пуст")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Список пользователей пуст"
            )
        return
    
    # Получаем текущего пользователя
    user = users[current_page]
    
    message = f"Пользователь {current_page + 1} из {len(users)}:\n\n"
    message += f"👤 Имя: {user.get('username', 'Без имени')}\n"
    message += f"🆔 ID: {user.get('user_id')}\n\n"
    message += f"📱 Телефон: {user.get('phone', 'Не указан')}\n"
    message += f"👨‍💼 ФИО: {user.get('fullname', 'Не указано')}\n"
    message += f"🏢 Должность: {user.get('position', 'Не указана')}\n"
    message += f"🏢 Отдел: {user.get('department', 'Не указан')}\n\n"
    message += f"👑 Админ: {'Да' if user.get('admin', False) else 'Нет'}\n"
    message += f"✅ Подтвержден: {'Да' if user.get('approved', False) else 'Нет'}\n"
    
    # Создаем клавиатуру с кнопками навигации
    nav_buttons = []
    
    # Если это не первый пользователь - добавляем кнопку "<"
    if current_page > 0:
        nav_buttons.append(KeyboardButton("<"))
    
    # Всегда добавляем кнопку "Вернуться"
    nav_buttons.append(KeyboardButton("🔙 Вернуться"))
    
    # Если это не последний пользователь - добавляем кнопку ">"
    if current_page < len(users) - 1:
        nav_buttons.append(KeyboardButton(">"))
    
    reply_markup = ReplyKeyboardMarkup([nav_buttons], resize_keyboard=True)
    
    # Дополнительно показываем инлайн-кнопки действий для пользователя
    inline_keyboard = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_user_{user.get('user_id')}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"delete_user_{user.get('user_id')}")],
        [InlineKeyboardButton("📋 Заявки пользователя", callback_data=f"user_applications_{user.get('user_id')}")]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)
    
    # В зависимости от типа апдейта (сообщение или callback) отправляем сообщения
    if update.message:
        # Отправляем сообщение с информацией о пользователе
        await update.message.reply_text(
        message,
            reply_markup=reply_markup
        )
        
        # Отправляем второе сообщение с инлайн-кнопками для действий
        await update.message.reply_text(
            "Действия с пользователем:",
            reply_markup=inline_markup
        )
    else:
        # Если это callback_query, используем context.bot.send_message
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message,
            reply_markup=reply_markup
        )
        
        # Отправляем второе сообщение с инлайн-кнопками для действий
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Действия с пользователем:",
            reply_markup=inline_markup
    )

async def handle_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отображения списка пользователей с пагинацией"""
    query = update.callback_query
    await query.answer()
    
    try:
        users = context.user_data.get('users', [])
        current_page = context.user_data.get('current_page', 0)
        
        if query.data.startswith("prev_page_"):
            current_page = int(query.data.split("_")[2]) - 1
        elif query.data.startswith("next_page_"):
            current_page = int(query.data.split("_")[2]) + 1
        
        context.user_data['current_page'] = current_page
        
        # Создаем клавиатуру для списка пользователей
        def get_user_list_keyboard(users, current_page):
            keyboard = []
            # Добавляем кнопки для пользователей
            for i, user in enumerate(users[current_page*5:(current_page+1)*5]):
                keyboard.append([InlineKeyboardButton(
                    f"{user.get('username', 'Пользователь')} ({user.get('user_id')})",
                    callback_data=f"edit_user_{user.get('user_id')}"
                )])
            
            # Добавляем кнопки навигации
            nav_buttons = []
            if current_page > 0:
                nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"prev_page_{current_page}"))
            if (current_page + 1) * 5 < len(users):
                nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"next_page_{current_page}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            return InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "Выберите пользователя для редактирования:",
            reply_markup=get_user_list_keyboard(users, current_page)
        )
    except Exception as e:
        logging.error(f"Ошибка при пагинации списка пользователей: {e}")
        await query.edit_message_text("Ошибка при отображении списка пользователей")

async def handle_user_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Обработчик редактирования данных пользователя"""
    query = update.callback_query
    await query.answer()
    
    user = get_user_by_id(user_id)
    if not user:
        await query.edit_message_text("Пользователь не найден")
        return
    
    # Убираем ReplyKeyboard
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Редактирование пользователя",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Отправляем сообщение с кнопками редактирования
    await query.edit_message_text(
        format_user_info(user),
        reply_markup=get_user_edit_keyboard(user_id, user.get('admin', False))
    )

async def handle_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Обработчик удаления пользователя"""
    query = update.callback_query
    await query.answer()
    
    user = get_user_by_id(user_id)
    if not user:
        await query.edit_message_text("Пользователь не найден")
        return
    
    # Создаем клавиатуру для подтверждения удаления
    def get_delete_confirmation_keyboard(user_id):
        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{user_id}")],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data=f"cancel_delete_{user_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Вы уверены, что хотите удалить пользователя {user.get('username', 'Без имени')}?",
        reply_markup=get_delete_confirmation_keyboard(user_id)
    )

async def handle_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Обработчик подтверждения удаления пользователя"""
    query = update.callback_query
    await query.answer()
    
    try:
        deleted = delete_user_from_supabase(user_id)
        if not deleted:
            await query.edit_message_text("❌ Пользователь не найден")
            return

        users = list_users()
        
        # Обновляем список пользователей в контексте
        context.user_data['users'] = users
        
        # Если удалили последнего пользователя на странице, переходим на предыдущую страницу
        current_page = context.user_data.get('current_page', 0)
        if current_page >= len(users):
            context.user_data['current_page'] = max(0, len(users) - 1)
        
        # Показываем сообщение об успешном удалении
        await query.edit_message_text("✅ Пользователь успешно удален")
        
        # Если есть еще пользователи, показываем следующего
        if users:
            # Создаем новое сообщение с информацией о следующем пользователе
            user = users[context.user_data['current_page']]
            message = f"Режим редактирования данных:\n\n"
            message += f"Пользователь {context.user_data['current_page'] + 1} из {len(users)}:\n\n"
            message += f"👤 Имя: {user.get('username', 'Без имени')}\n"
            message += f"🆔 ID: {user.get('user_id')}\n"
            message += f"📱 Телефон: {user.get('phone', 'Не указан')}\n"
            message += f"📧 Email: {user.get('email', 'Не указан')}\n"
            message += f"👑 Админ: {'Да' if user.get('admin', False) else 'Нет'}\n"
            message += f"✅ Подтвержден: {'Да' if user.get('approved', False) else 'Нет'}\n"
            
            await update.effective_message.reply_text(
                message,
                reply_markup=get_user_actions_keyboard(user.get('user_id'))
            )
        else:
            # Если пользователей не осталось, возвращаемся в админ-панель
            await admin_panel(update, context)
    except Exception as e:
        logging.error(f"Ошибка при удалении пользователя: {e}")
        await query.edit_message_text("❌ Ошибка при удалении пользователя")

async def handle_user_applications(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Обработчик отображения заявок пользователя"""
    query = update.callback_query
    await query.answer()
    
    applications = get_user_applications(user_id)
    if not applications:
        await query.edit_message_text("У пользователя нет заявок")
        return
    
    # Формируем текстовый файл со списком заявок
    user = get_user_by_id(user_id)
    username = user.get('username', 'Неизвестный пользователь')
    
    file_content = f"Список заявок пользователя {username} (ID: {user_id}):\n\n"
    
    for i, app in enumerate(applications):
        file_content += f"--- Заявка #{i+1} ---\n"
        file_content += f"Тип: {app.get('form_type', 'Неизвестный тип')}\n"
        file_content += f"Дата: {app.get('date', 'Без даты')}\n"
        
        # Добавляем все доступные поля заявки
        for key, value in app.items():
            if key not in ['user_id', 'form_type', 'date', 'id']:
                file_content += f"{key}: {value}\n"
        
        file_content += "\n"
    
    # Создаем временный файл
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False, mode='w', encoding='utf-8') as temp_file:
        temp_file.write(file_content)
        temp_file_path = temp_file.name
    
    # Отправляем файл
    with open(temp_file_path, 'rb') as file:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=file,
            filename=f"applications_user_{user_id}.txt",
            caption=f"Список заявок пользователя {username}"
        )
    
    # Удаляем временный файл
    os.unlink(temp_file_path)
    
    # Добавляем кнопку возврата
    keyboard = [[InlineKeyboardButton(
            "🔙 Назад к пользователю", 
            callback_data=f"back_to_edit_{user_id}"
    )]]
    
    await query.edit_message_text(
        f"Файл со списком заявок пользователя {username} отправлен.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_upload_table_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик запроса на загрузку таблицы в разных форматах"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для загрузки таблицы")
        return
    
    # Создаем кнопки для выбора формата файла
    keyboard = [
        [InlineKeyboardButton("📊 XLSX", callback_data='download_xlsx')],
        [InlineKeyboardButton("🔄 JSON", callback_data='download_json')],
        [InlineKeyboardButton("📝 CSV", callback_data='download_csv')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите формат для скачивания таблицы:",
        reply_markup=reply_markup
    )


FORM_TYPE_LABELS = {
    "delivery": "доставка",
    "refund": "возврат",
    "painting": "покраска",
    "checkin": "заезд",
}


def _get_forms_export_data():
    grouped = get_forms_grouped_for_export()
    # Keep deterministic order for exports.
    return {
        "delivery": grouped.get("delivery", []),
        "refund": grouped.get("refund", []),
        "painting": grouped.get("painting", []),
        "checkin": grouped.get("checkin", []),
    }


def _build_flat_export_rows(grouped_data: dict) -> list[dict]:
    rows = []
    for form_type in ("delivery", "refund", "painting", "checkin"):
        for row in grouped_data.get(form_type, []):
            rows.append({"type": form_type, **row})
    return rows


async def handle_upload_table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выгрузки таблицы заявок в формате CSV"""
    query = update.callback_query
    await query.answer()
    
    try:
        grouped = _get_forms_export_data()
        rows = _build_flat_export_rows(grouped)

        filename = "supabase_forms_export.csv"
        if not rows:
            with open(filename, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["type", "created_at", "creator_fullname", "form_number", "contract_number", "form_text", "checkin_date", "brig_name", "brig_phone", "carring"])
        else:
            fieldnames = list(rows[0].keys())
            with open(filename, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        
        with open(filename, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=filename,
                caption="✅ Таблица успешно экспортирована из Supabase в формате CSV"
            )
        
        os.remove(filename)
        
    except Exception as e:
        logging.error(f"Ошибка загрузки таблицы: {e}")
        await query.edit_message_text(f"❌ Ошибка при загрузке таблицы: {str(e)}")

async def handle_download_xlsx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик скачивания таблицы в формате XLSX"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем кнопки и показываем сообщение об ожидании
    await query.edit_message_text("⏳ Пожалуйста, подождите. Создаю XLSX файл...")
    
    try:
        grouped = _get_forms_export_data()

        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as temp_file:
            excel_file_path = temp_file.name
        
        with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
            has_rows = False
            for form_type in ("delivery", "refund", "painting", "checkin"):
                rows = grouped.get(form_type, [])
                if not rows:
                    continue
                has_rows = True
                df = pd.DataFrame(rows)
                sheet_name = FORM_TYPE_LABELS.get(form_type, form_type)[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)

            if not has_rows:
                pd.DataFrame([{"info": "Нет данных в Supabase"}]).to_excel(
                    writer, sheet_name="export", index=False
                )
        
        with open(excel_file_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename="supabase_export.xlsx",
                caption="✅ Таблица успешно экспортирована из Supabase в формате XLSX"
            )
        
        os.remove(excel_file_path)
        
    except ImportError:
        await query.edit_message_text("❌ Ошибка: библиотека pandas не установлена. Используйте 'pip install pandas openpyxl' для установки.")
    except Exception as e:
        logging.error(f"Ошибка при создании XLSX: {e}")
        await query.edit_message_text(f"❌ Ошибка при скачивании таблицы: {str(e)}")

async def handle_download_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик скачивания таблицы в формате JSON"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем кнопки и показываем сообщение об ожидании
    await query.edit_message_text("⏳ Пожалуйста, подождите. Создаю JSON файл...")
    
    try:
        grouped = _get_forms_export_data()
        export_payload = {
            FORM_TYPE_LABELS.get(form_type, form_type): rows
            for form_type, rows in grouped.items()
        }

        filename = "supabase_export.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_payload, f, ensure_ascii=False, indent=4)
        
        with open(filename, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=filename,
                caption="✅ Таблица успешно экспортирована из Supabase в формате JSON"
            )
        
        os.remove(filename)
        
    except Exception as e:
        logging.error(f"Ошибка при создании JSON: {e}")
        await query.edit_message_text(f"❌ Ошибка при скачивании таблицы: {str(e)}")

async def handle_download_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик скачивания таблицы в формате CSV"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем кнопки и показываем сообщение об ожидании
    await query.edit_message_text("⏳ Пожалуйста, подождите. Создаю CSV файл...")
    
    try:
        grouped = _get_forms_export_data()

        import zipfile
        zip_filename = "supabase_export_all_sheets.zip"
        
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            empty = True
            for form_type in ("delivery", "refund", "painting", "checkin"):
                rows = grouped.get(form_type, [])
                if not rows:
                    continue
                empty = False
                csv_filename = f"{FORM_TYPE_LABELS.get(form_type, form_type)}.csv"
                fieldnames = list(rows[0].keys())
                with open(csv_filename, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                zipf.write(csv_filename)
                os.remove(csv_filename)

            if empty:
                csv_filename = "export.csv"
                with open(csv_filename, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["info"])
                    writer.writerow(["Нет данных в Supabase"])
                zipf.write(csv_filename)
                os.remove(csv_filename)

        with open(zip_filename, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=zip_filename,
                caption="✅ Таблица успешно экспортирована из Supabase в формате CSV (все листы)"
            )
        
        os.remove(zip_filename)
        
    except Exception as e:
        logging.error(f"Ошибка при создании CSV: {e}")
        await query.edit_message_text(f"❌ Ошибка при скачивании таблицы: {str(e)}")

# Регистрация обработчиков
download_xlsx_handler = CallbackQueryHandler(handle_download_xlsx, pattern='^download_xlsx$')
download_json_handler = CallbackQueryHandler(handle_download_json, pattern='^download_json$')
download_csv_handler = CallbackQueryHandler(handle_download_csv, pattern='^download_csv$')

async def handle_bot_usage_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик запроса на просмотр статистики использования бота и системных ресурсов"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав для просмотра статистики")
        return
    
    # Проверяем, нет ли уже активного запроса статистики для этого пользователя
    # Используем отдельный ключ в bot_data для отслеживания блокировки кнопки "Потребление"
    if 'consumption_locks' not in context.bot_data:
        context.bot_data['consumption_locks'] = {}
    
    if user_id in context.bot_data['consumption_locks'] and context.bot_data['consumption_locks'][user_id]:
        await update.message.reply_text("⏳ Сбор статистики уже выполняется, пожалуйста подождите...")
        return
    
    # Блокируем кнопку "Потребление" для этого пользователя
    context.bot_data['consumption_locks'][user_id] = True
    
    # Показываем сообщение о загрузке
    loading_message = await update.message.reply_text("⏳ Загрузка данных о потреблении ресурсов...")
    
    try:
        # Импортируем необходимые библиотеки для мониторинга системных ресурсов
        import psutil
        import datetime
        import time
        
        # Начинаем собирать данные 
        resource_data = await collect_resource_data()
        
        # Получаем данные об использовании бота из Supabase.
        try:
            usage_data = get_usage_stats()
        except Exception as e:
            logging.error(f"Ошибка при получении статистики из Supabase: {e}")
            usage_data = {
                'total_users': 0,
                'total_applications': 0,
                'today_applications': 0,
                'messages_sent': 0
            }
        
        # Удаляем сообщение о загрузке
        await loading_message.delete()
        
        # Формируем сообщение со статистикой
        message = create_stats_message(usage_data, resource_data)
        
        # Отправляем итоговое сообщение со статистикой
        await update.message.reply_text(
            message,
            parse_mode='HTML'
        )
        
    except ImportError:
        if loading_message:
            await loading_message.delete()
        await update.message.reply_text(
            "❌ Для мониторинга системных ресурсов необходима библиотека psutil.\n"
            "Установите её командой: pip install psutil"
        )
    except Exception as e:
        logging.error(f"Ошибка при сборе статистики: {e}")
        if loading_message:
            await loading_message.delete()
        await update.message.reply_text(f"❌ Ошибка при получении статистики: {str(e)}")
    finally:
        # Снимаем блокировку кнопки "Потребление" для этого пользователя
        if 'consumption_locks' in context.bot_data and user_id in context.bot_data['consumption_locks']:
            context.bot_data['consumption_locks'][user_id] = False

async def collect_resource_data():
    """Собирает данные о системных ресурсах"""
    import psutil
    import datetime
    import os
    
    # Получаем ID текущего процесса
    current_process = psutil.Process(os.getpid())
    
    # Форматирование размера в читаемый вид
    def format_bytes(bytes):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024
        return f"{bytes:.1f} PB"
    
    # Получаем данные о потреблении CPU для текущего процесса
    # Измеряем CPU для текущего процесса и его потомков
    import time
    
    # Получаем список всех потомков текущего процесса
    children = current_process.children(recursive=True)
    all_processes = [current_process] + children
    
    # Измеряем CPU несколько раз для более точного результата
    cpu_percent = 0.0
    
    # Первое измерение для инициализации
    process_cpu_times = {}
    for proc in all_processes:
        try:
            process_cpu_times[proc.pid] = proc.cpu_percent(interval=None)
            proc.cpu_percent(interval=None)  # Сбрасываем счетчик для первого измерения
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    # Делаем паузу для накопления данных
    time.sleep(0.5)
    
    # Второе измерение для получения реальных значений
    for proc in all_processes:
        try:
            current_cpu = proc.cpu_percent(interval=None)
            cpu_percent += current_cpu
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    # Если нет данных от процессов, используем системное измерение
    if cpu_percent <= 0:
        cpu_percent = psutil.cpu_percent(interval=0.5)
    
    # Округляем до 2 знаков после запятой
    cpu_percent = round(cpu_percent, 2)
    
    # Получаем данные о памяти для текущего процесса
    memory_info = current_process.memory_info()
    memory_used = format_bytes(memory_info.rss)  # Resident Set Size - физическая память, используемая процессом
    
    # Получаем общие данные о памяти системы для сравнения
    system_memory = psutil.virtual_memory()
    memory_total = format_bytes(system_memory.total)
    memory_percent = round((memory_info.rss / system_memory.total) * 100, 2)
    
    # Получаем данные о потреблении диска текущим процессом
    try:
        disk_usage = 0
        bot_folder = os.getcwd()
        for root, dirs, files in os.walk(bot_folder):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    disk_usage += os.path.getsize(file_path)
                except (FileNotFoundError, PermissionError):
                    pass
        disk_used = format_bytes(disk_usage)
    except Exception as e:
        logging.error(f"Ошибка при подсчете размера папки бота: {e}")
        disk_used = "N/A"
    
    # Общие данные о диске системы
    disk = psutil.disk_usage('/')
    disk_total = format_bytes(disk.total)
    disk_percent = round((disk_usage / disk.total) * 100, 2) if disk_used != "N/A" else 0
    
    # Получаем время работы процесса
    process_create_time = datetime.datetime.fromtimestamp(current_process.create_time())
    uptime = datetime.datetime.now() - process_create_time
    days, seconds = uptime.days, uptime.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    uptime_str = f"{days}д {hours}ч {minutes}м"
    
    # Получаем текущее время
    current_time = datetime.datetime.now().strftime("%H:%M:%S %d.%m.%Y")
    
    # Загружаем историю пиковых значений, если есть
    try:
        with open('data/resource_peaks.json', 'r') as f:
            peaks = json.load(f)
            bot_cpu_peak = peaks.get('bot_cpu_peak', 0)
            bot_memory_peak = peaks.get('bot_memory_peak', 0)
    except (FileNotFoundError, json.JSONDecodeError):
        bot_cpu_peak = 0
        bot_memory_peak = 0
    
    # Обновляем пиковые значения, если текущие больше
    if cpu_percent > bot_cpu_peak:
        bot_cpu_peak = cpu_percent
    if memory_percent > bot_memory_peak:
        bot_memory_peak = memory_percent
    
    # Собираем данные о потоках и дескрипторах
    threads_count = current_process.num_threads()
    try:
        open_files = len(current_process.open_files())
    except:
        open_files = "N/A"
    
    # Сохраняем обновленные пиковые значения
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/resource_peaks.json', 'w') as f:
            json.dump({
                'bot_cpu_peak': bot_cpu_peak,
                'bot_memory_peak': bot_memory_peak
            }, f)
    except Exception as e:
        logging.error(f"Ошибка при сохранении пиковых значений: {e}")
    
    return {
        'cpu_percent': cpu_percent,
        'memory_total': memory_total,
        'memory_used': memory_used,
        'memory_percent': memory_percent,
        'disk_total': disk_total,
        'disk_used': disk_used,
        'disk_percent': disk_percent,
        'uptime': uptime_str,
        'last_update': current_time,
        'bot_cpu_peak': bot_cpu_peak,
        'bot_memory_peak': bot_memory_peak,
        'threads_count': threads_count,
        'open_files': open_files
    }

def create_stats_message(usage_data, resource_data):
    """Создает сообщение со статистикой использования и ресурсов"""
    message = "📊 <b>Статистика использования бота:</b>\n\n"
    message += f"👥 Всего пользователей: <b>{usage_data.get('total_users', 0)}</b>\n"
    message += f"📝 Всего заявок: <b>{usage_data.get('total_applications', 0)}</b>\n"
    message += f"📅 Заявок за сегодня: <b>{usage_data.get('today_applications', 0)}</b>\n"
    message += f"📨 Отправлено сообщений: <b>{usage_data.get('messages_sent', 0)}</b>\n\n"
    
    # Добавляем информацию о потреблении ресурсов процессом бота
    message += "💻 <b>Потребление ресурсов ботом:</b>\n\n"
    message += f"🔄 <b>CPU:</b> {resource_data['cpu_percent']}%\n"
    message += f"🧠 <b>Оперативная память:</b> {resource_data['memory_used']} ({resource_data['memory_percent']}% от системной)\n"
    message += f"💾 <b>Размер бота на диске:</b> {resource_data['disk_used']}\n"
    message += f"🧵 <b>Активных потоков:</b> {resource_data['threads_count']}\n"
    message += f"📂 <b>Открытых файлов:</b> {resource_data['open_files']}\n"
    message += f"🔝 <b>Пиковая нагрузка CPU бота:</b> {resource_data['bot_cpu_peak']}%\n"
    message += f"🔝 <b>Пиковая нагрузка RAM бота:</b> {resource_data['bot_memory_peak']}%\n\n"
    message += f"⏱️ <b>Время работы бота:</b> {resource_data['uptime']}\n"
    message += f"⏱️ <b>Последнее обновление:</b> {resource_data['last_update']}"
    
    return message

EDIT_FULLNAME, EDIT_PHONE, EDIT_POSITION, EDIT_DEPARTMENT = range(4)

async def handle_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изменения ФИО пользователя"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID пользователя из callback_data
    user_id = int(query.data.split("_")[2])
    
    # Сохраняем информацию о текущем действии
    context.user_data['edit_action'] = 'fullname'
    context.user_data['edit_user_id'] = user_id
    
    await query.edit_message_text(
        "Введите новое ФИО пользователя (Фамилия Имя Отчество):",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data=f"cancel_edit_{user_id}")
        ]])
    )
    
    # Устанавливаем состояние ожидания ввода
    context.user_data['waiting_for_input'] = True

    return "EDITING_FIELD"

async def handle_edit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изменения телефона пользователя"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID пользователя из callback_data
    user_id = int(query.data.split("_")[2])
    
    # Сохраняем информацию о текущем действии
    context.user_data['edit_action'] = 'phone'
    context.user_data['edit_user_id'] = user_id
    
    await query.edit_message_text(
        "Введите новый номер телефона пользователя в формате +7XXXXXXXXXXили 8XXXXXXXXXX:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data=f"cancel_edit_{user_id}")
        ]])
    )
    
    # Устанавливаем состояние ожидания ввода
    context.user_data['waiting_for_input'] = True

    return "EDITING_FIELD"

async def handle_edit_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изменения должности пользователя"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID пользователя из callback_data
    user_id = int(query.data.split("_")[2])
    
    # Сохраняем информацию о текущем действии
    context.user_data['edit_action'] = 'position'
    context.user_data['edit_user_id'] = user_id
    
    await query.edit_message_text(
        "Введите новую должность пользователя:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data=f"cancel_edit_{user_id}")
        ]])
    )
    
    # Устанавливаем состояние ожидания ввода
    context.user_data['waiting_for_input'] = True

    return "EDITING_FIELD"

async def handle_edit_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изменения отдела пользователя"""
    query = update.callback_query
    await query.answer()
    
    # Получаем ID пользователя из callback_data
    user_id = int(query.data.split("_")[2])
    
    # Сохраняем информацию о текущем действии
    context.user_data['edit_action'] = 'department'
    context.user_data['edit_user_id'] = user_id
    
    await query.edit_message_text(
        "Введите новый отдел пользователя:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data=f"cancel_edit_{user_id}")
        ]])
    )
    
    # Устанавливаем состояние ожидания ввода
    context.user_data['waiting_for_input'] = True

    return "EDITING_FIELD"

async def handle_input_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода данных для редактирования"""
    if not context.user_data.get('waiting_for_input'):
        return
    
    user_id = context.user_data.get('edit_user_id')
    action = context.user_data.get('edit_action')
    new_value = update.message.text
    
    if not user_id or not action:
        await update.message.reply_text("Ошибка: не найдены данные для редактирования")
        # Очищаем контекст в случае ошибки
        context.user_data.pop('waiting_for_input', None)
        context.user_data.pop('edit_action', None)
        context.user_data.pop('edit_user_id', None)
        return ConversationHandler.END
    
    # Проверка введенных данных в зависимости от поля
    if action == 'fullname':
        name_parts = new_value.split()
        if len(name_parts) < 2 or not all(part.isalpha() for part in name_parts):
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректное ФИО.\n"
                "ФИО должно содержать только буквы и состоять минимум из двух слов."
            )
            return "EDITING_FIELD"
    elif action == 'phone':
        import re
        if not re.match(r'^\+?7\d{10}$', new_value.replace(' ', '')) and not re.match(r'^8\d{10}$', new_value.replace(' ', '')):
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректный номер телефона в формате +7XXXXXXXXXX или 8XXXXXXXXXX."
            )
            return "EDITING_FIELD"
        # Нормализация формата телефона
        new_value = '+7' + re.sub(r'[^\d]', '', new_value)[-10:]
    elif action == 'position':
        if len(new_value) < 3:
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректную должность (не менее 3 символов)."
            )
            return "EDITING_FIELD"
    elif action == 'department':
        if len(new_value) < 2:
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректное название подразделения (не менее 2 символов)."
            )
            return "EDITING_FIELD"
    
    try:
        updated = update_user_data(user_id, {action: new_value})
        if not updated:
            await update.message.reply_text("❌ Пользователь не найден")
            # Очищаем контекст в случае ошибки
            context.user_data.pop('waiting_for_input', None)
            context.user_data.pop('edit_action', None)
            context.user_data.pop('edit_user_id', None)
            return ConversationHandler.END

        if 'users' in context.user_data:
            context.user_data['users'] = list_users()
        
        # Отправляем сообщение об успешном обновлении
        field_names = {
            'fullname': 'ФИО',
            'phone': 'телефон',
            'position': 'должность',
            'department': 'отдел'
        }
        
        # Отправляем сообщение с информацией об успешном обновлении
        success_msg = await update.message.reply_text(
            f"✅ {field_names.get(action, action)} пользователя успешно обновлен"
        )
        
        # Убираем клавиатуру ReplyKeyboard
        await update.message.reply_text(
            "Возвращаемся к просмотру пользователя",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Отправляем сообщение с информацией о пользователе и кнопками редактирования
        user = get_user_by_id(user_id)
        if user:
            await update.message.reply_text(
                format_user_info(user),
                reply_markup=get_user_edit_keyboard(user_id, user.get('admin', False))
        )
    except Exception as e:
        logging.error(f"Ошибка при обновлении данных пользователя: {e}")
        await update.message.reply_text("❌ Ошибка при обновлении данных пользователя")
    
    # Обязательно очищаем все параметры состояния
    context.user_data.pop('waiting_for_input', None)
    context.user_data.pop('edit_action', None)
    context.user_data.pop('edit_user_id', None)
    
    return ConversationHandler.END

async def handle_prev_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик перехода к предыдущему пользователю"""
    users = context.user_data.get('users', [])
    current_page = context.user_data.get('current_page', 0)
    
    if current_page > 0:
        context.user_data['current_page'] = current_page - 1
        await send_user_list(update, context)

async def handle_next_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик перехода к следующему пользователю"""
    users = context.user_data.get('users', [])
    current_page = context.user_data.get('current_page', 0)
    
    if current_page < len(users) - 1:
        context.user_data['current_page'] = current_page + 1
        await send_user_list(update, context)

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия кнопки 'На главную' в админ-панели"""
    user_id = update.effective_user.id
    is_registered = check_user_registration(user_id)
    
    await update.message.reply_text(
        "🏠 Вы вернулись на главную",
        reply_markup=get_reply_keyboard(user_id, is_registered=is_registered)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений от админа"""
    # Если есть ожидание ввода, обрабатываем его
    if context.user_data.get('waiting_for_input'):
        return await handle_input_for_edit(update, context)
    
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    text = update.message.text
    
    if text == "<":
        await handle_prev_user(update, context)
    elif text == ">":
        await handle_next_user(update, context)
    elif text == "🔙 Вернуться":
        # Возвращаем ReplyKeyboard администратора
        admin_keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("👥 Управление пользователями")],
                [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
                [KeyboardButton("🔙 На главную")]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "Возврат в админ-панель",
            reply_markup=admin_keyboard
        )
    elif text == "👥 Управление пользователями":
        await handle_user_management(update, context)
    elif text == "📥 Загрузить таблицу":
        await handle_upload_table_request(update, context)
    elif text == "📈 Потребление":
        # Проверяем, заблокирована ли кнопка "Потребление" для этого пользователя
        if 'consumption_locks' in context.bot_data and user_id in context.bot_data['consumption_locks'] and context.bot_data['consumption_locks'][user_id]:
            await update.message.reply_text("⏳ Сбор статистики уже выполняется, пожалуйста подождите...")
        else:
            await handle_bot_usage_request(update, context)
    elif text == "🔙 На главную":
        await back_to_main(update, context)

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена редактирования и возврат к списку пользователей"""
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data.split("_")[2])
    user = get_user_by_id(user_id)
    
    if user:
        # Возвращаем ReplyKeyboard администратора
        admin_keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("👥 Управление пользователями")],
                [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
                [KeyboardButton("🔙 На главную")]
            ],
            resize_keyboard=True
        )
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Редактирование отменено",
            reply_markup=admin_keyboard
        )
        
        # Отправляем сообщение с информацией о пользователе
        await query.edit_message_text(
            format_user_info(user),
            reply_markup=get_user_edit_keyboard(user_id, user.get('admin', False))
        )
    
    return ConversationHandler.END

def get_user_edit_keyboard(user_id, is_admin=False):
    """Клавиатура для редактирования пользователя"""
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить ФИО", callback_data=f"edit_name_{user_id}")],
        [InlineKeyboardButton("📱 Изменить телефон", callback_data=f"edit_phone_{user_id}")],
        [InlineKeyboardButton("👨‍💼 Изменить должность", callback_data=f"edit_position_{user_id}")],
        [InlineKeyboardButton("🏢 Изменить отдел", callback_data=f"edit_department_{user_id}")],
    ]
    
    # Добавляем кнопку в зависимости от статуса админа
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Снять админа", callback_data=f"remove_admin_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton("👑 Назначить админа", callback_data=f"make_admin_{user_id}")])
    
    # Всегда добавляем кнопку возврата к списку пользователей
    keyboard.append([InlineKeyboardButton("🔙 Назад к списку", callback_data="back_to_user_list")])
    
    return InlineKeyboardMarkup(keyboard)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback-запросов"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    
    if data == "back_to_user_list":
        # Возвращаемся к списку пользователей
        try:
            await query.delete_message()  # Удаляем сообщение с кнопками редактирования
        except Exception as e:
            logging.error(f"Ошибка при удалении сообщения: {e}")
        
        # Просто вызываем функцию отображения списка пользователей
        # она сама восстановит всю необходимую клавиатуру
        await handle_user_management(update, context)
    elif data.startswith("edit_user_"):
        user_id = int(data.split("_")[2])
        await handle_user_edit(update, context, user_id)
    elif data.startswith("delete_user_"):
        user_id = int(data.split("_")[2])
        await handle_delete_user(update, context, user_id)
    elif data.startswith("confirm_delete_"):
        user_id = int(data.split("_")[2])
        await handle_confirm_delete(update, context, user_id)
    elif data.startswith("cancel_delete_"):
        user_id = int(data.split("_")[2])
        await handle_user_edit(update, context, user_id)
    elif data.startswith("user_applications_"):
        user_id = int(data.split("_")[2])
        await handle_user_applications(update, context, user_id)
    elif data == "upload_table":
        await handle_upload_table(update, context)
    elif data == "bot_usage":
        # Проверяем, заблокирована ли кнопка "Потребление" для этого пользователя
        if 'consumption_locks' in context.bot_data and user_id in context.bot_data['consumption_locks'] and context.bot_data['consumption_locks'][user_id]:
            await query.edit_message_text("⏳ Сбор статистики уже выполняется, пожалуйста подождите...")
        else:
            await handle_bot_usage_request(update, context)
    elif data.startswith("back_to_edit_"):
        user_id = int(data.split("_")[3])
        await handle_user_edit(update, context, user_id)
    elif data.startswith("edit_name_"):
        user_id = int(data.split("_")[2])
        await handle_edit_name(update, context)
    elif data.startswith("edit_phone_"):
        user_id = int(data.split("_")[2])
        await handle_edit_phone(update, context)
    elif data.startswith("edit_position_"):
        user_id = int(data.split("_")[2])
        await handle_edit_position(update, context)
    elif data.startswith("edit_department_"):
        user_id = int(data.split("_")[2])
        await handle_edit_department(update, context)
    elif data.startswith("make_admin_"):
        user_id = int(data.split("_")[2])
        await handle_toggle_admin(update, context, user_id, True)
    elif data.startswith("remove_admin_"):
        user_id = int(data.split("_")[2])
        await handle_toggle_admin(update, context, user_id, False)
    elif data.startswith("cancel_edit_"):
        user_id = int(data.split("_")[2])
        # Сбрасываем состояние ожидания ввода и возвращаемся к редактированию пользователя
        context.user_data['waiting_for_input'] = False
        context.user_data.pop('edit_action', None)
        context.user_data.pop('edit_user_id', None)
        
        user = get_user_by_id(user_id)
        if user:
            await query.edit_message_text(
                format_user_info(user),
                reply_markup=get_user_edit_keyboard(user_id, user.get('admin', False))
            )

async def handle_toggle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, make_admin: bool):
    """Обработчик изменения статуса администратора пользователя"""
    query = update.callback_query
    await query.answer()
    
    try:
        updated = update_user_data(user_id, {'admin': make_admin})
        if not updated:
            await query.edit_message_text("❌ Пользователь не найден")
            return

        if 'users' in context.user_data:
            context.user_data['users'] = list_users()
        
        status_text = "активирован" if make_admin else "деактивирован"
        
        # Отображаем сообщение с кнопками редактирования
        user = get_user_by_id(user_id)
        if user:
            await query.edit_message_text(
                f"✅ Статус администратора успешно {status_text}\n\n{format_user_info(user)}",
                reply_markup=get_user_edit_keyboard(user_id, user.get('admin', False))
            )
        else:
            await query.edit_message_text(
                f"✅ Статус администратора успешно {status_text}, но не удалось получить информацию о пользователе"
            )
    except Exception as e:
        logging.error(f"Ошибка при изменении статуса администратора: {e}")
        await query.edit_message_text("❌ Ошибка при изменении статуса администратора")

# Добавляем новые функции для работы с заявками
async def handle_applications_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик списка всех заявок по типам"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для просмотра заявок")
        return
    
    # Предлагаем выбрать тип заявки для просмотра
    keyboard = [
        [KeyboardButton("🚚 Доставка"), KeyboardButton("🏎️ Заезд")],
        [KeyboardButton("🔙 Возврат"), KeyboardButton("🎨 Покраска")],
        [KeyboardButton("🔙 Вернуться")]
    ]
    
    await update.message.reply_text(
        "Выберите тип заявок для просмотра:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    context.user_data['waiting_for_app_list_type'] = True

async def handle_app_list_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора типа заявок для просмотра"""
    if not context.user_data.get('waiting_for_app_list_type'):
        return
    
    type_map = {
        "🚚 Доставка": "delivery",
        "🏎️ Заезд": "checkin",
        "🔙 Возврат": "refund",
        "🎨 Покраска": "painting"
    }
    
    selected_type = update.message.text
    if selected_type not in type_map:
        await update.message.reply_text("❌ Выберите один из предложенных типов заявок")
        return
    
    context.user_data['waiting_for_app_list_type'] = False
    
    try:
        filtered_apps = list_applications_by_type(type_map[selected_type])
        
        if not filtered_apps:
            await update.message.reply_text(f"Заявок типа '{selected_type}' не найдено")
            
            # Возвращаем админское меню
            admin_keyboard = ReplyKeyboardMarkup(
                [
                    [KeyboardButton("👥 Управление пользователями")],
                    [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
                    [KeyboardButton("🔙 На главную")]
                ],
                resize_keyboard=True
            )
            await update.message.reply_text("Возврат в админ-панель", reply_markup=admin_keyboard)
            return
        
        # Сохраняем отфильтрованные заявки в контексте
        context.user_data['applications'] = filtered_apps
        # Устанавливаем текущую страницу
        context.user_data['app_current_page'] = 0
        
        # Отправляем информацию о первой заявке
        await send_application_info(update, context)
        
    except Exception as e:
        logging.error(f"Ошибка при получении списка заявок: {e}")
        await update.message.reply_text("❌ Ошибка при получении списка заявок")
        
        # Возвращаем админское меню в случае ошибки
        admin_keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("👥 Управление пользователями")],
                [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
                [KeyboardButton("🔙 На главную")]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Возврат в админ-панель", reply_markup=admin_keyboard)

async def send_application_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет информацию о текущей заявке"""
    applications = context.user_data.get('applications', [])
    current_page = context.user_data.get('app_current_page', 0)
    
    if not applications:
        if update.message:
            await update.message.reply_text("Список заявок пуст")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Список заявок пуст"
            )
        return
    
    # Получаем текущую заявку
    app = applications[current_page]
    
    # Форматируем информацию о заявке
    message = f"Заявка {current_page + 1} из {len(applications)}:\n\n"
    message += f"🆔 ID: {app.get('id', 'Нет ID')}\n"
    message += f"📝 Тип: {app.get('form_type', 'Неизвестный тип')}\n"
    message += f"📅 Дата: {app.get('date', 'Без даты')}\n"
    
    user_id = app.get('user_id')
    if user_id:
        user = get_user_by_id(user_id)
        if user:
            message += f"👤 Пользователь: {user.get('fullname', user.get('username', 'Неизвестный'))}\n\n"
        else:
            message += f"👤 ID пользователя: {user_id}\n\n"
    
    # Добавляем содержимое заявки
    message += "📄 Содержимое заявки:\n"
    for key, value in app.items():
        if key not in ['id', 'user_id', 'form_type', 'date']:
            message += f"- {key}: {value}\n"
    
    # Создаем клавиатуру с кнопками навигации
    nav_buttons = []
    
    # Если это не первая заявка - добавляем кнопку "<"
    if current_page > 0:
        nav_buttons.append(KeyboardButton("<"))
    
    # Всегда добавляем кнопку "Вернуться"
    nav_buttons.append(KeyboardButton("🔙 Вернуться"))
    
    # Если это не последняя заявка - добавляем кнопку ">"
    if current_page < len(applications) - 1:
        nav_buttons.append(KeyboardButton(">"))
    
    reply_markup = ReplyKeyboardMarkup([nav_buttons], resize_keyboard=True)
    
    # Создаем инлайн-кнопки для действий с заявкой
    app_id = app.get('id')
    inline_keyboard = [
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_app_{app_id}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"delete_app_{app_id}")]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)
    
    # Отправляем сообщения
    if update.message:
        await update.message.reply_text(
            message,
            reply_markup=reply_markup
        )
        
        await update.message.reply_text(
            "Действия с заявкой:",
            reply_markup=inline_markup
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message,
            reply_markup=reply_markup
        )
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Действия с заявкой:",
            reply_markup=inline_markup
        )

async def handle_prev_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик перехода к предыдущей заявке"""
    applications = context.user_data.get('applications', [])
    current_page = context.user_data.get('app_current_page', 0)
    
    if current_page > 0:
        context.user_data['app_current_page'] = current_page - 1
        await send_application_info(update, context)

async def handle_next_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик перехода к следующей заявке"""
    applications = context.user_data.get('applications', [])
    current_page = context.user_data.get('app_current_page', 0)
    
    if current_page < len(applications) - 1:
        context.user_data['app_current_page'] = current_page + 1
        await send_application_info(update, context)

async def handle_edit_application_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик запроса на редактирование заявки"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав для редактирования заявок")
        return
    
    # Предлагаем выбрать тип заявки
    keyboard = [
        [KeyboardButton("🚚 Доставка"), KeyboardButton("🏎️ Заезд")],
        [KeyboardButton("🔙 Возврат"), KeyboardButton("🎨 Покраска")],
        [KeyboardButton("🔙 Вернуться")]
    ]
    
    await update.message.reply_text(
        "Выберите тип заявки для редактирования:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    context.user_data['waiting_for_app_type'] = True

async def handle_app_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора типа заявки для редактирования"""
    if not context.user_data.get('waiting_for_app_type'):
        return
    
    type_map = {
        "🚚 Доставка": "delivery",
        "🏎️ Заезд": "checkin",
        "🔙 Возврат": "refund",
        "🎨 Покраска": "painting"
    }
    
    selected_type = update.message.text
    if selected_type not in type_map:
        await update.message.reply_text("❌ Выберите один из предложенных типов заявок")
        return
    
    # Сохраняем выбранный тип заявки
    context.user_data['selected_app_type'] = type_map[selected_type]
    context.user_data['waiting_for_app_type'] = False
    
    # Просим ввести ID заявки
    await update.message.reply_text(
        f"Введите ID заявки типа '{selected_type}', которую хотите отредактировать:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("🔙 Вернуться")]
        ], resize_keyboard=True)
    )
    
    context.user_data['waiting_for_app_id'] = True

async def handle_app_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода ID заявки для редактирования"""
    if not context.user_data.get('waiting_for_app_id'):
        return
    
    app_id = update.message.text.strip()
    app_type = context.user_data.get('selected_app_type')
    
    if not app_type:
        await update.message.reply_text("❌ Ошибка: тип заявки не выбран")
        return
    
    try:
        app = get_application_by_id(app_id)
        if app and app.get('form_type') != app_type:
            app = None
        
        if not app:
            await update.message.reply_text(f"❌ Заявка с ID {app_id} типа '{app_type}' не найдена")
            return
        
        # Сохраняем текущую заявку для редактирования
        context.user_data['current_app'] = app
        
        # Показываем данные заявки и варианты полей для редактирования
        editable_fields = [k for k in app.keys() if k not in ['id', 'user_id', 'form_type', 'date']]
        
        message = f"📝 Данные заявки ({app_type}):\n\n"
        message += f"🆔 ID: {app.get('id', 'Нет ID')}\n"
        message += f"📅 Дата: {app.get('date', 'Без даты')}\n\n"
        
        user_id = app.get('user_id')
        if user_id:
            user = get_user_by_id(user_id)
            if user:
                message += f"👤 Пользователь: {user.get('fullname', user.get('username', 'Неизвестный'))}\n\n"
        
        message += "Выберите поле для редактирования:"
        
        keyboard = []
        for field in editable_fields:
            # Форматируем имена полей для лучшей читабельности
            field_name = field
            if field == "contract":
                field_name = "Договор"
            elif field == "text":
                field_name = "Текст заявки"
            elif field == "date_checkin":
                field_name = "Дата заезда"
            elif field == "brigadier_name":
                field_name = "Имя бригадира"
            elif field == "brigadier_phone":
                field_name = "Телефон бригадира"
            elif field == "carrying":
                field_name = "Грузоподъемность"
            
            field_value = app.get(field, "")
            # Ограничиваем длину отображаемого значения
            if len(str(field_value)) > 30:
                field_value = str(field_value)[:27] + "..."
            
            keyboard.append([InlineKeyboardButton(
                f"{field_name}: {field_value}",
                callback_data=f"edit_app_field_{field}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data="cancel_app_edit")])
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logging.error(f"Ошибка при поиске заявки: {e}")
        await update.message.reply_text("❌ Ошибка при поиске заявки")
    
    # Сбрасываем флаг ожидания ID заявки
    context.user_data['waiting_for_app_id'] = False

async def handle_edit_app_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора поля заявки для редактирования"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith("edit_app_field_"):
        return
    
    field = query.data.split("_")[3]
    app = context.user_data.get('current_app')
    
    if not app:
        await query.edit_message_text("❌ Ошибка: данные заявки не найдены")
        return
    
    app_type = app.get('form_type', '')
    
    # Сохраняем поле для редактирования
    context.user_data['edit_app_field'] = field
    current_value = app.get(field, "")
    
    # Получаем человекочитаемое название поля
    field_name = field
    if field == "contract":
        field_name = "Договор"
    elif field == "text":
        field_name = "Текст заявки"
    elif field == "date_checkin":
        field_name = "Дата заезда"
    elif field == "brigadier_name":
        field_name = "Имя бригадира"
    elif field == "brigadier_phone":
        field_name = "Телефон бригадира"
    elif field == "carrying":
        field_name = "Грузоподъемность"
    
    # Отображаем текущее значение и просим ввести новое
    form_type_str = {
        "delivery": "🚚 Доставка",
        "checkin": "🏎️ Заезд",
        "refund": "🔙 Возврат",
        "painting": "🎨 Покраска"
    }.get(app_type, app_type)
    
    await query.edit_message_text(
        f"Заявка типа: {form_type_str}\n\n"
        f"Текущее значение поля '{field_name}': \n{current_value}\n\n"
        f"Введите новое значение:",
                reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data="cancel_app_edit")
        ]])
    )
    
    # Устанавливаем состояние ожидания ввода нового значения
    context.user_data['waiting_for_app_field_value'] = True

async def handle_app_field_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода нового значения для поля заявки"""
    if not context.user_data.get('waiting_for_app_field_value'):
        return
    
    # Получаем данные из контекста
    new_value = update.message.text
    field = context.user_data.get('edit_app_field')
    app = context.user_data.get('current_app')
    
    if not app or not field:
        await update.message.reply_text("❌ Ошибка: данные для редактирования не найдены")
        context.user_data.pop('waiting_for_app_field_value', None)
        context.user_data.pop('edit_app_field', None)
        context.user_data.pop('current_app', None)
        return
    
    app_type = app.get('form_type', '')
    app_id = app.get('id')
    
    try:
        app_updated = update_application_field(app_id, field, new_value)
        if not app_updated:
            await update.message.reply_text("❌ Заявка не найдена в системе")
            return

        refreshed_app = get_application_by_id(app_id)
        if refreshed_app:
            context.user_data['current_app'] = refreshed_app
            if 'applications' in context.user_data:
                context.user_data['applications'] = [
                    refreshed_app if str(a.get('id')) == str(app_id) else a
                    for a in context.user_data.get('applications', [])
                ]
        
        # Получаем человекочитаемое название поля
        field_name = field
        if field == "contract":
            field_name = "Договор"
        elif field == "text":
            field_name = "Текст заявки"
        elif field == "date_checkin":
            field_name = "Дата заезда"
        elif field == "brigadier_name":
            field_name = "Имя бригадира"
        elif field == "brigadier_phone":
            field_name = "Телефон бригадира"
        elif field == "carrying":
            field_name = "Грузоподъемность"
        
        # Сообщаем об успешном обновлении
        await update.message.reply_text(f"✅ Поле '{field_name}' успешно обновлено")
        
        # Создаем сообщение с выбором полей для редактирования
        await send_edit_fields_menu(update, context)
    
    except Exception as e:
        logging.error(f"Ошибка при обновлении заявки: {e}")
        await update.message.reply_text(f"❌ Ошибка при обновлении заявки: {str(e)}")
    
    # Важно! Сбрасываем флаг ожидания ввода значения
    context.user_data.pop('waiting_for_app_field_value', None)

async def send_edit_fields_menu(update, context):
    """Отправляет меню с полями для редактирования заявки"""
    app = context.user_data.get('current_app')
    if not app:
        await update.message.reply_text("❌ Ошибка: данные заявки не найдены")
        return
    
    app_type = app.get('form_type', '')
    
    # Формируем список полей для редактирования
    editable_fields = [k for k in app.keys() if k not in ['id', 'user_id', 'form_type', 'date']]
    
    # Получаем читаемое название типа заявки
    form_type_str = {
        "delivery": "🚚 Доставка",
        "checkin": "🏎️ Заезд",
        "refund": "🔙 Возврат",
        "painting": "🎨 Покраска"
    }.get(app_type, app_type)
    
    # Формируем сообщение
    message = f"📝 Данные заявки ({form_type_str}):\n\n"
    message += f"🆔 ID: {app.get('id', 'Нет ID')}\n"
    message += f"📅 Дата: {app.get('date', 'Без даты')}\n\n"
    
    user_id = app.get('user_id')
    if user_id:
            user = get_user_by_id(user_id)
    if user:
        message += f"👤 Пользователь: {user.get('fullname', user.get('username', 'Неизвестный'))}\n\n"
    
    message += "Выберите поле для редактирования:"
    
    # Формируем клавиатуру с кнопками для каждого поля
    keyboard = []
    for f in editable_fields:
        # Получаем человекочитаемое название поля
        f_name = f
        if f == "contract":
            f_name = "Договор"
        elif f == "text":
            f_name = "Текст заявки"
        elif f == "date_checkin":
            f_name = "Дата заезда"
        elif f == "brigadier_name":
            f_name = "Имя бригадира"
        elif f == "brigadier_phone":
            f_name = "Телефон бригадира"
        elif f == "carrying":
            f_name = "Грузоподъемность"
        
        f_value = app.get(f, "")
        # Ограничиваем длину отображаемого значения
        if len(str(f_value)) > 30:
            f_value = str(f_value)[:27] + "..."
        
        keyboard.append([InlineKeyboardButton(
            f"{f_name}: {f_value}",
            callback_data=f"edit_app_field_{f}"
        )])
    
    # Добавляем кнопки действий
    keyboard.append([
        InlineKeyboardButton("🔙 Отмена", callback_data="cancel_app_edit"),
        InlineKeyboardButton("✅ Готово", callback_data="back_to_admin")
    ])
    
    # Отправляем меню
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_edit_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки редактирования заявки"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith("edit_app_"):
        return
    
    app_id = query.data.split("_")[2]
    app = context.user_data.get('current_app')
    
    if not app or str(app.get('id')) != app_id:
        try:
            app = get_application_by_id(app_id)
            if not app:
                await query.edit_message_text("❌ Заявка не найдена")
                return
            context.user_data['current_app'] = app
        except Exception as e:
            logging.error(f"Ошибка при получении заявки: {e}")
            await query.edit_message_text("❌ Ошибка при получении заявки")
            return
    
    # Отправляем сообщение с выбором полей для редактирования через сообщение в чате,
    # а не через редактирование текущего сообщения с инлайн-клавиатурой
    # Это позволит пользователю видеть все предыдущие действия в истории чата
    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Загрузка данных заявки..."
    )
    
    # Обновляем контекст, чтобы send_edit_fields_menu мог использовать message
    update.message = message
    
    # Отправляем меню с полями для редактирования
    await send_edit_fields_menu(update, context)

async def handle_delete_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик удаления заявки"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith("delete_app_"):
        return
    
    app_id = query.data.split("_")[2]
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_app_{app_id}")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data=f"cancel_delete_app_{app_id}")]
    ]
    
    await query.edit_message_text(
        f"❓ Вы действительно хотите удалить заявку с ID {app_id}?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_confirm_delete_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения удаления заявки"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith("confirm_delete_app_"):
        return
    
    app_id = query.data.split("_")[3]
    
    try:
        deleted = delete_application(app_id)
        if not deleted:
            await query.edit_message_text("❌ Заявка не найдена")
            return
        applications = context.user_data.get('applications', [])
        applications = [a for a in applications if str(a.get('id')) != str(app_id)]
        
        # Обновляем список заявок в контексте, если он есть
        if 'applications' in context.user_data:
            context.user_data['applications'] = applications
            # Корректируем индекс текущей страницы при необходимости
            if context.user_data.get('app_current_page', 0) >= len(applications):
                context.user_data['app_current_page'] = max(0, len(applications) - 1)
        
        await query.edit_message_text("✅ Заявка успешно удалена")
        
        # Отправляем обновленный список заявок, если он не пустой
        if applications:
            await send_application_info(update, context)
        else:
            admin_keyboard = ReplyKeyboardMarkup(
                [
                    [KeyboardButton("👥 Управление пользователями")],
                    [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
                    [KeyboardButton("🔙 На главную")]
                ],
                resize_keyboard=True
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Список заявок пуст. Возврат в админ-панель.",
                reply_markup=admin_keyboard
            )
    
    except Exception as e:
        logging.error(f"Ошибка при удалении заявки: {e}")
        await query.edit_message_text(f"❌ Ошибка при удалении заявки: {str(e)}")

async def handle_cancel_delete_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отмены удаления заявки"""
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith("cancel_delete_app_"):
        return
    
    app_id = query.data.split("_")[3]
    
    # Возвращаемся к отображению информации о заявке
    try:
        app = get_application_by_id(app_id)
        
        if app:
            message = "📝 Данные заявки:\n\n"
            message += f"🆔 ID: {app.get('id', 'Нет ID')}\n"
            message += f"📝 Тип: {app.get('form_type', 'Неизвестный тип')}\n"
            message += f"📅 Дата: {app.get('date', 'Без даты')}\n\n"
            
            message += "Содержимое заявки:\n"
            for key, value in app.items():
                if key not in ['id', 'user_id', 'form_type', 'date']:
                    message += f"- {key}: {value}\n"
            
            inline_keyboard = [
                [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_app_{app_id}")],
                [InlineKeyboardButton("❌ Удалить", callback_data=f"delete_app_{app_id}")]
            ]
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(inline_keyboard)
            )
        else:
            await query.edit_message_text("❌ Заявка не найдена")
    
    except Exception as e:
        logging.error(f"Ошибка при отмене удаления заявки: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")

async def handle_cancel_app_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик отмены редактирования заявки"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем данные о редактировании заявки
    context.user_data.pop('current_app', None)
    context.user_data.pop('edit_app_field', None)
    context.user_data.pop('waiting_for_app_field_value', None)
    
    # Возвращаемся к админ-панели
    admin_keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("👥 Управление пользователями")],
            [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
            [KeyboardButton("🔙 На главную")]
        ],
        resize_keyboard=True
    )
    
    await query.edit_message_text("✅ Редактирование заявки отменено")
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Возврат в админ-панель",
        reply_markup=admin_keyboard
    )

async def handle_back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик возврата к админ-панели"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем данные о редактировании заявки
    context.user_data.pop('current_app', None)
    context.user_data.pop('edit_app_field', None)
    
    # Возвращаемся к админ-панели
    admin_keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("👥 Управление пользователями")],
            [KeyboardButton("📥 Загрузить таблицу"), KeyboardButton("📈 Потребление")],
            [KeyboardButton("🔙 На главную")]
        ],
        resize_keyboard=True
    )
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Возврат в админ-панель",
        reply_markup=admin_keyboard
    )
