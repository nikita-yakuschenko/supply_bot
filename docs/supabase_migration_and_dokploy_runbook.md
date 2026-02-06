# Runbook: Supabase + Dokploy (актуальный)

## Scope
Этот документ описывает только актуальный контур:
- хранение данных в Supabase (Postgres),
- запуск бота через Dokploy,
- эксплуатационные проверки.

## Компоненты
- Схема БД: `database/supabase/001_schema.sql`
- Импорт локальных исторических JSON: `scripts/import_local_json_to_supabase.py`
- Docker Compose для Dokploy: `docker-compose.dokploy.yml`
- Шаблон переменных окружения: `.env.example`

## Подготовка
1. Установить зависимости:
```bash
pip install -r requirements.txt
```
2. Настроить `.env`.
3. Проверить соединение с Postgres/Supabase.

## Проверки БД
```sql
select count(*) from bot.users;
select count(*) from bot.user_settings;
select application_type, count(*) from bot.forms group by 1 order by 1;
```

## Деплой в Dokploy
1. Создать Compose-приложение из репозитория.
2. Указать `docker-compose.dokploy.yml`.
3. Передать env-переменные.
4. Выполнить deploy/redeploy.

## Post-deploy checks
1. Бот отвечает на `/start`.
2. Новая заявка пишется в `bot.forms`.
3. Задача успешно создается в Bitrix24.
4. Админ-выгрузки работают.

## Security notes
- Секреты хранятся только в `.env`/секретах Dokploy.
- В репозитории не должно быть рабочих токенов и паролей.
- Детальные payload/response-логи внешних API должны быть отключены в проде.
