# Инструкция: GitHub + Dokploy (Dockerfile)

## 0. Что уже учтено
- Секреты не коммитятся (`.env`, `.env.*` в `.gitignore`).
- Локальные миграционные артефакты не коммитятся (`migration_exports/` в `.gitignore`).
- Runtime-данные в `data/*.json` игнорируются.

## 1. Авторизация в GitHub

### Вариант A (рекомендуется): GitHub CLI
```bash
gh auth login
```
Далее:
1. `GitHub.com`
2. `HTTPS`
3. `Login with a web browser`
4. Подтвердить код в браузере.

Проверка:
```bash
gh auth status
```

### Вариант B: без `gh`
1. Войти на `https://github.com` в браузере.
2. Все действия по созданию репозитория сделать через веб-интерфейс.
3. Для `git push` использовать HTTPS + PAT (Personal Access Token) вместо пароля.

## 2. Создать репозиторий

### Через CLI
```bash
gh repo create <owner>/<repo-name> --private --source . --remote origin --push
```

### Через веб
1. `New repository` на GitHub.
2. Выбрать `Private`.
3. Не добавлять `README/.gitignore/license` (репозиторий должен быть пустым).

## 3. Залить код (если делаете вручную)

В корне проекта:
```bash
git init
git add .
git commit -m "Initial production-ready bot version (Supabase + Bitrix)"
git branch -M main
git remote add origin https://github.com/<owner>/<repo-name>.git
git push -u origin main
```

Если репозиторий уже инициализирован, пропустить `git init` и `remote add`.

## 4. Подготовить Dokploy
1. Убедиться, что локально бот не запущен (чтобы не было `409 Conflict` по Telegram long polling).
2. Убедиться, что в Dokploy есть доступ к вашему GitHub-репозиторию.

## 5. Создать приложение в Dokploy через GitHub + Dockerfile
1. В Dokploy нажать `New Application`.
2. Тип: `Dockerfile`.
3. Source: `GitHub Repository`.
4. Выбрать репозиторий и ветку `main`.
5. `Dockerfile Path`: `Dockerfile`.
6. `Build Context`: `.` (корень репозитория).
7. Command override не нужен (используется `CMD ["python", "main.py"]` из Dockerfile).

## 6. Переменные окружения в Dokploy
Добавить значения из вашего локального `.env` (без коммита файла в GitHub):

- `BOT_TOKEN`
- `ADMIN_IDS`
- `FULLNAME`
- `BITRIX_WEBHOOK_URL` (или legacy `URL_BITRIX_API`)
- `USER_AGENT`
- `CONTENT_TYPE`
- `DATABASE_URL`

Или альтернативный набор подключения к БД:
- `SUPABASE_HOST`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POOLER_PROXY_PORT_TRANSACTION`
- `POOLER_TENANT_ID`

## 7. Persistent storage (рекомендуется)
Если нужно сохранять локальные тех.данные (`resource_peaks.json`) между деплоями:
1. Добавить volume.
2. Смонтировать в `/app/data`.

## 8. Деплой
1. Нажать `Deploy`.
2. Дождаться успешного build и запуска контейнера.

## 9. Проверка после деплоя
1. В логах должно быть `Application started`.
2. Бот должен отвечать на `/start`.
3. Тестовая заявка должна:
   - создаться в Bitrix24;
   - записаться в Supabase (`bot.forms`).
4. Убедиться, что активен только один инстанс бота.

## 10. Обновления в будущем
1. Коммит в `main`.
2. `git push`.
3. В Dokploy: `Redeploy` (или авто-деплой, если настроен).

