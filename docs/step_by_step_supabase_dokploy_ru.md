# Пошагово: прод-режим на Supabase + Dokploy

## 1. Установить зависимости
```bash
pip install -r requirements.txt
```

## 2. Проверить `.env`
Минимально нужно:

```env
BOT_TOKEN=...
ADMIN_IDS=...
FULLNAME=...
BITRIX_WEBHOOK_URL=https://.../rest/<user>/<token>
DATABASE_URL=postgresql://postgres.<tenant>:<password>@<host>:6543/postgres
```

Если `DATABASE_URL` не задан, используются отдельные переменные подключения к Postgres/Supabase.

## 3. Проверить подключение к БД
```bash
python - << 'PY'
import os, psycopg
from dotenv import load_dotenv
load_dotenv()
with psycopg.connect(os.getenv("DATABASE_URL"), prepare_threshold=None) as c:
    with c.cursor() as cur:
        cur.execute("select now(), current_database(), current_user")
        print(cur.fetchone())
PY
```

## 4. Запустить бота локально
```bash
python main.py
```

## 5. Смоук-проверка
1. Создать тестовую заявку в Telegram.
2. Проверить появление записи в `bot.forms`.
3. Проверить создание задачи в Bitrix24.
4. Проверить админ-выгрузки (`XLSX/JSON/CSV`) из Supabase.

## 6. Деплой в Dokploy
1. Подключить репозиторий.
2. Использовать `docker-compose.dokploy.yml`.
3. Заполнить переменные окружения.
4. Нажать redeploy.

## 7. После деплоя
1. Убедиться, что работает только один инстанс бота.
2. Проверить `/start`, создание заявки, админ-выгрузки.
3. Проверить логи контейнера на ошибки подключения к БД и Bitrix24.
