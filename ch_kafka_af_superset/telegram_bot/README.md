# Airflow Telegram Bot

Сервисы:
- `airflow-telegram-backend` — FastAPI, читает статусы DAG через Airflow REST API
- `airflow-telegram-bot` — Telegram-бот (Telethon + MTProto proxy) с меню и алертами

## Настройка

1. Скопируйте `telegram_bot/.env.example` в `telegram_bot/.env` (если файла ещё нет).
2. Укажите:
   - `TELEGRAM_BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
   - `TELEGRAM_CHAT_IDS` — chat/user id через запятую (куда слать алерты и кому доступно меню)
   - `TELEGRAM_PROXY_HOST` / `TELEGRAM_PROXY_PORT` / `TELEGRAM_PROXY_SECRET` — MTProto proxy

### Где взять `TELEGRAM_CHAT_IDS`

Это числовой id пользователя или чата. Не username (`@name`), а именно число.

**Личный чат (ваш user id):**

1. Напишите боту [@userinfobot](https://t.me/userinfobot) или [@getmyid_bot](https://t.me/getmyid_bot).
2. Бот ответит числом вида `123456789` — это ваш id.
3. Вставьте его в `.env`:
   ```env
   TELEGRAM_CHAT_IDS=123456789
   ```

**Группа / канал:**

1. Добавьте вашего бота в группу (для канала — как администратора).
2. Напишите в группе любое сообщение (или перешлите пост канала боту [@getmyid_bot](https://t.me/getmyid_bot) / [@userinfobot](https://t.me/userinfobot)).
3. Id группы обычно отрицательный, например `-1001234567890`.
4. В `.env`:
   ```env
   TELEGRAM_CHAT_IDS=-1001234567890
   ```

**Несколько получателей** — через запятую:

```env
TELEGRAM_CHAT_IDS=123456789,-1001234567890
```

Алерты о падениях DAG уходят только в эти id. Меню бота тоже доступно только им (если список задан).

После изменения `TELEGRAM_CHAT_IDS` перезапустите бота:

```bash
docker compose -f docker-compose_af.yml up -d --force-recreate airflow-telegram-bot
```

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
