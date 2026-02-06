import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

class Config:
    TOKEN = os.getenv('BOT_TOKEN')
    ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS').split(',')] if os.getenv('ADMIN_IDS') else []

# Проверка обязательных переменных
if not Config.TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env файле")