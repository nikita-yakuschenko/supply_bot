# Telegram-бот заявок (Supabase + Bitrix24)

## Описание
Бот принимает заявки пользователей в Telegram, сохраняет данные в Supabase (Postgres) и создает задачи в Bitrix24.

## Текущий стек
- Python 3.12 (рекомендуется для локального запуска)
- `python-telegram-bot`
- Supabase/Postgres
- Bitrix24 REST webhook

## Быстрый старт (локально)
1. Создайте виртуальное окружение:
```bash
py -3.12 -m venv .venv312
```
2. Активируйте его:
```bash
.\.venv312\Scripts\Activate.ps1
```
3. Установите зависимости:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```
4. Настройте `.env` по образцу `.env.example`.
5. Запустите бота:
```bash
python main.py
```

## Ключевые переменные окружения
- `BOT_TOKEN`
- `ADMIN_IDS`
- `FULLNAME`
- `BITRIX_WEBHOOK_URL` (предпочтительно) или `URL_BITRIX_API` (legacy)
- `DATABASE_URL`  
  или набор: `SUPABASE_HOST`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_USER`, `POOLER_PROXY_PORT_TRANSACTION`, `POOLER_TENANT_ID`

## Деплой в Dokploy
1. Используйте `docker-compose.dokploy.yml`.
2. Передайте все env-переменные из `.env`.
3. Выполните redeploy.

## Важно по данным
- Источник истины для бизнес-данных: Supabase.
- Локальные JSON с заявками и пользователями в рантайме не используются.
- `data/resource_peaks.json` используется для технической статистики ресурсов.
