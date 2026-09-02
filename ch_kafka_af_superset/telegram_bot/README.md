# Airflow Telegram Bot

Сервисы:
- `airflow-telegram-backend` — FastAPI, читает статусы DAG через Airflow REST API
- `airflow-telegram-bot` — Telegram-бот с меню и алертами о падениях

## Настройка

1. Скопируйте `telegram_bot/.env.example` в `telegram_bot/.env` (уже есть шаблон).
2. Укажите:
   - `TELEGRAM_BOT_TOKEN` — токен от @BotFather
   - `TELEGRAM_CHAT_IDS` — chat/user id через запятую (куда слать алерты и кому доступно меню)

## Запуск

```bash
docker compose -f docker-compose.yml build airflow-telegram-backend airflow-telegram-bot
docker compose -f docker-compose.yml up -d airflow-telegram-backend airflow-telegram-bot
```

или для `docker-compose_af.yml` аналогично.

## Меню бота

- Выполненные сегодня
- Скипнутые сегодня (DAG runs с skipped-тасками)
- Упавшие за текущий месяц
- Упавшие за прошлый месяц

Бот каждые `POLL_INTERVAL_SECONDS` (по умолчанию 60) проверяет падения за текущий день и присылает DAG + упавшие таски.
