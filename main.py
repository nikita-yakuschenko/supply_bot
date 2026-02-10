import asyncio
import logging
import warnings
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import BotCommand, ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import ContextTypes, Application
from telegram.warnings import PTBUserWarning
from config import Config
from dotenv import load_dotenv
import os
from telegram.error import Forbidden

# Убираем предупреждения PTB про per_message (у нас смесь MessageHandler и CallbackQueryHandler — оставляем per_message=False)
warnings.filterwarnings("ignore", category=PTBUserWarning)

# Импорты из ваших модулей
from bot.commands import user, admin, utils
from bot.events import messages, errors
from bot.core import bot_core
from bot.events.callbacks import handle_admin_approval

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение токена бота
TOKEN = os.getenv('BOT_TOKEN')

# Клавиатура для главного меню
def get_reply_keyboard(user_id, is_registered=False):
    # Проверяем, является ли пользователь администратором
    is_admin = utils.is_admin(user_id)

    if is_registered:
        # Клавиатура для зарегистрированных пользователей
        keyboard = [
            [KeyboardButton("🚚 Доставка"), KeyboardButton("🏎️ Заезд")],
            [KeyboardButton("🔙 Возврат"), KeyboardButton("🎨 Покраска")],
            [KeyboardButton("ℹ️ Помощь")]
        ]
    else:
        # Клавиатура для незарегистрированных
        keyboard = [
            [KeyboardButton("📝 Регистрация"), KeyboardButton("ℹ️ Помощь")]
        ]
    
    # Добавляем админ-панель если пользователь админ
    if user_id in Config.ADMIN_IDS or is_admin:
        if is_registered:
            keyboard.append([KeyboardButton("⚙️ Админ-панель")])
        else:
            keyboard = [
                [KeyboardButton("🚚 Доставка"), KeyboardButton("🏎️ Заезд")],
                [KeyboardButton("🔙 Возврат"), KeyboardButton("🎨 Покраска")],
                [KeyboardButton("ℹ️ Помощь")],
                [KeyboardButton("⚙️ Админ-панель")]
            ]
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def check_user_registration(user_id):
    # Проверка регистрации пользователя
    return user.is_user_registered(user_id)

async def start(update, context):
    try:
        await update.message.reply_text("Привет! Я бот.")
    except Forbidden:
        print("Пользователь заблокировал бота.")
        # Можно записать в лог или пропустить ошибку

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

# Создаем фильтр для проверки состояния пользователя
class StateFilter(filters.MessageFilter):
    def __init__(self, state_name):
        self.state_name = state_name
        super().__init__()
        
    def filter(self, message):
        return message.get_bot().application.user_data.get(message.from_user.id, {}).get('state') == self.state_name

# Создаем фильтр для проверки статуса админа
class AdminFilter(filters.MessageFilter):
    def __init__(self):
        super().__init__()
        
    def filter(self, message):
        return admin.is_admin(message.from_user.id)

def setup_handlers(app):
    # Настройка обработчиков команд
    app.add_handler(CommandHandler("start", user.start))
    app.add_handler(CommandHandler("help", user.help))
    app.add_handler(CommandHandler("settings", user.settings))
    
    # ConversationHandler для регистрации
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📝 Регистрация$"), user.register)
        ],
        states={
            user.FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_fullname)],
            user.PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_phone)],
            user.POSITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_position)],
            user.DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_department)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel)
        ],
        allow_reentry=True,
        per_message=False
    )
    
    app.add_handler(conv_handler)
    
    # ConversationHandler для редактирования данных пользователя
    edit_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin.handle_edit_name, pattern="^edit_name_"),
            CallbackQueryHandler(admin.handle_edit_phone, pattern="^edit_phone_"),
            CallbackQueryHandler(admin.handle_edit_position, pattern="^edit_position_"),
            CallbackQueryHandler(admin.handle_edit_department, pattern="^edit_department_"),
        ],
        states={
            "EDITING_FIELD": [MessageHandler(filters.TEXT & ~filters.COMMAND, admin.handle_input_for_edit)],
        },
        fallbacks=[
            CallbackQueryHandler(
                lambda update, context: admin.handle_callback_query(update, context), 
                pattern="^cancel_edit_"
            ),
        ],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(edit_handler)
    
    # ConversationHandler для доставки
    delivery_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚚 Доставка$"), user.delivery)],
        states={
            user.FORM_CONTRACT: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_form_contract)
            ],
            user.FORM_TEXT: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_form_text)
            ],
            user.FORM_CONFIRM: [CallbackQueryHandler(user.form_callback)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(delivery_handler)
    
    # ConversationHandler для заезда
    checkin_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🏎️ Заезд$"), user.checkin)],
        states={
            user.CHECKIN_CONTRACT: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_checkin_contract)
            ],
            user.CHECKIN_DATE: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_checkin_date)
            ],
            user.CHECKIN_BRIG_NAME: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_checkin_brig_name)
            ],
            user.CHECKIN_BRIG_PHONE: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_checkin_brig_phone)
            ],
            user.CHECKIN_CARRYING: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_checkin_carrying)
            ],
            user.CHECKIN_CONFIRM: [CallbackQueryHandler(user.checkin_callback)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(checkin_handler)
    
    # ConversationHandler для возврата
    refund_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔙 Возврат$"), user.refund)],
        states={
            user.FORM_CONTRACT: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_form_contract)
            ],
            user.FORM_TEXT: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_form_text)
            ],
            user.FORM_CONFIRM: [CallbackQueryHandler(user.form_callback)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(refund_handler)
    
    # ConversationHandler для покраски
    painting_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎨 Покраска$"), user.painting)],
        states={
            user.FORM_CONTRACT: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_form_contract)
            ],
            user.FORM_TEXT: [
                MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel_form_process),
                MessageHandler(filters.TEXT & ~filters.COMMAND, user.get_form_text)
            ],
            user.FORM_CONFIRM: [CallbackQueryHandler(user.form_callback)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Отмена$"), user.cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(painting_handler)
    
    # Обработчики для кнопок помощи и других кнопок
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ Помощь$"), user.help))
    
    # Обработчик для настроек через команду меню
    app.add_handler(CommandHandler("settings", user.settings))
    app.add_handler(CallbackQueryHandler(user.handle_settings_callback, pattern=r'^(toggle_auto_numbering|back_to_main_menu)$'))
    
    # Обработчики для админ-панели
    app.add_handler(MessageHandler(filters.Regex("^👥 Управление пользователями$"), admin.handle_user_management))
    app.add_handler(MessageHandler(filters.Regex("^📋 Список заявок$"), admin.handle_applications_list))
    app.add_handler(MessageHandler(filters.Regex("^📥 Загрузить таблицу$"), admin.handle_upload_table_request))
    app.add_handler(MessageHandler(filters.Regex("^📈 Потребление$"), admin.handle_bot_usage_request))
    
    # Обработчики для скачивания таблицы в разных форматах
    app.add_handler(CallbackQueryHandler(admin.handle_download_xlsx, pattern='^download_xlsx$'))
    app.add_handler(CallbackQueryHandler(admin.handle_download_json, pattern='^download_json$'))
    app.add_handler(CallbackQueryHandler(admin.handle_download_csv, pattern='^download_csv$'))
    
    # Обработчик для кнопок подтверждения/отклонения регистрации
    app.add_handler(CallbackQueryHandler(handle_admin_approval, pattern=r'^(approve|reject)_\d+$'))
    app.add_handler(CommandHandler("update_kb", force_update_keyboard))
    
    # Обработчик для повторной отправки в Битрикс и отмены
    app.add_handler(CallbackQueryHandler(user.retry_bitrix_callback, pattern=r'^(retry|cancel)_(delivery|refund|painting|checkin)(?:_\d+)?$'))
    
    # Обработчик для админ-панели
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Админ-панель$"), admin.admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^🔙 На главную$"), admin.back_to_main))
    
    # Обработчики для управления пользователями
    app.add_handler(CallbackQueryHandler(
        lambda update, context: admin.handle_user_edit(update, context, int(update.callback_query.data.split('_')[2])),
        pattern="^edit_user_"
    ))
    app.add_handler(CallbackQueryHandler(
        lambda update, context: admin.handle_delete_user(update, context, int(update.callback_query.data.split('_')[2])),
        pattern="^delete_user_"
    ))
    app.add_handler(CallbackQueryHandler(
        lambda update, context: admin.handle_confirm_delete(update, context, int(update.callback_query.data.split('_')[2])),
        pattern="^confirm_delete_"
    ))
    app.add_handler(CallbackQueryHandler(
        lambda update, context: admin.handle_user_applications(update, context, int(update.callback_query.data.split('_')[2])),
        pattern="^user_applications_"
    ))
    app.add_handler(CallbackQueryHandler(
        lambda update, context: admin.handle_user_edit(update, context, int(update.callback_query.data.split('_')[3])),
        pattern="^back_to_edit_"
    ))
    
    # Обработчики для навигации по пользователям
    app.add_handler(MessageHandler(filters.Regex("^⬅️$"), admin.handle_prev_user))
    app.add_handler(MessageHandler(filters.Regex("^➡️$"), admin.handle_next_user))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Вернуться$"), admin.admin_panel))
    
    # Создаем экземпляр фильтра AdminFilter для использования во всех обработчиках
    admin_filter = AdminFilter()
    
    # Добавляем обработчик для всех текстовых сообщений от админа
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & admin_filter, admin.handle_message))
    
    # Обработчик для всех остальных текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages.handle_message))
    app.add_error_handler(errors.error_handler)
    
    # Добавляем общий обработчик callback-запросов (он будет обрабатывать все callback-запросы, не обработанные другими обработчиками)
    app.add_handler(CallbackQueryHandler(admin.handle_callback_query))
    
    # Убедимся, что обработчик регистрации работает (повторная регистрация)
    app.add_handler(conv_handler)
    
    # Создаем класс фильтра для ожидания ввода ID заявки
    class WaitingForAppIdFilter(filters.MessageFilter):
        def filter(self, message):
            return (message.text != "🔙 Вернуться" and 
                   "waiting_for_app_id" in message.from_user.id_data and 
                   message.from_user.id_data["waiting_for_app_id"])
    
    # Создаем класс фильтра для ожидания ввода значения поля заявки
    class WaitingForAppFieldValueFilter(filters.MessageFilter):
        def filter(self, message):
            return ("waiting_for_app_field_value" in message.from_user.id_data and 
                   message.from_user.id_data["waiting_for_app_field_value"])
    
    # Создаем класс фильтра для ожидания выбора типа заявки
    class WaitingForAppTypeFilter(filters.MessageFilter):
        def filter(self, message):
            return (message.text != "🔙 Вернуться" and 
                   "waiting_for_app_type" in message.from_user.id_data and 
                   message.from_user.id_data["waiting_for_app_type"])
    
    # Создаем класс фильтра для ожидания выбора типа заявки для просмотра
    class WaitingForAppListTypeFilter(filters.MessageFilter):
        def filter(self, message):
            return (message.text != "🔙 Вернуться" and 
                   "waiting_for_app_list_type" in message.from_user.id_data and 
                   message.from_user.id_data["waiting_for_app_list_type"])
    
    # Добавление обработчиков для работы с заявками
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & admin_filter & WaitingForAppTypeFilter(),
        admin.handle_app_type_selection
    ))
    
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & admin_filter & WaitingForAppListTypeFilter(),
        admin.handle_app_list_type_selection
    ))
    
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & admin_filter & WaitingForAppIdFilter(),
        admin.handle_app_id_input
    ))
    
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & admin_filter & WaitingForAppFieldValueFilter(),
        admin.handle_app_field_value_input
    ))
    
    # Добавление callback обработчиков для управления заявками
    app.add_handler(CallbackQueryHandler(admin.handle_edit_application, pattern=r'^edit_app_\d+$'))
    app.add_handler(CallbackQueryHandler(admin.handle_delete_application, pattern=r'^delete_app_\d+$'))
    app.add_handler(CallbackQueryHandler(admin.handle_edit_app_field, pattern=r'^edit_app_field_'))
    app.add_handler(CallbackQueryHandler(admin.handle_confirm_delete_app, pattern=r'^confirm_delete_app_'))
    app.add_handler(CallbackQueryHandler(admin.handle_cancel_delete_app, pattern=r'^cancel_delete_app_'))
    app.add_handler(CallbackQueryHandler(admin.handle_cancel_app_edit, pattern=r'^cancel_app_edit$'))
    app.add_handler(CallbackQueryHandler(admin.handle_back_to_admin, pattern=r'^back_to_admin$'))
    
    # Добавляем обработчики навигации по заявкам
    app.add_handler(MessageHandler(filters.Regex("^<$"), admin.handle_prev_application))
    app.add_handler(MessageHandler(filters.Regex("^>$"), admin.handle_next_application))

async def error_handler(update, context):
    error = context.error
    if isinstance(error, Forbidden):
        print("Бот заблокирован пользователем.")
    else:
        print(f"Ошибка: {error}")

async def setup_commands(app):
    """Настройка команд меню бота"""
    commands = [
        BotCommand("start", "Запуск бота"),
        BotCommand("settings", "Настройки бота"),
        BotCommand("help", "Получить помощь"),
        BotCommand("update_kb", "Обновить клавиатуру")
    ]
    await app.bot.set_my_commands(commands)

def _shutdown_exception_handler(loop, context):
    """Смягчает вывод при остановке: без длинного traceback для Ctrl+C и отмены задач."""
    exc = context.get("exception")
    if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
        logger.info("Остановка бота (завершение фоновых задач)...")
        return
    loop.default_exception_handler(context)


async def main():
    """Запуск бота"""
    load_dotenv()
    token = os.getenv('BOT_TOKEN')
    
    if not token:
        logger.error("Не указан токен бота в .env файле!")
        return
    
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_shutdown_exception_handler)
    
    # Создаем экземпляр приложения бота
    app = Application.builder().token(token).build()
    
    # Настраиваем обработчики
    setup_handlers(app)
    
    # Настраиваем команды меню
    await setup_commands(app)
    
    # Запускаем бота
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот останавливается...")
    finally:
        await app.updater.stop()
        await asyncio.sleep(0.3)
        await app.stop()
        await app.shutdown()
        logger.info("Бот завершил работу")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}")
