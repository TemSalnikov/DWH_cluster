from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("airflow-telegram-bot")

BACKEND_URL = os.getenv("BACKEND_URL", "http://airflow-telegram-backend:8000").rstrip("/")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS = {
    int(chat_id.strip())
    for chat_id in os.getenv("TELEGRAM_CHAT_IDS", "").split(",")
    if chat_id.strip()
}
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
STATE_FILE = Path(os.getenv("STATE_FILE", "/data/notified_failures.json"))

BTN_SUCCESS_TODAY = "✅ Выполненные сегодня"
BTN_SKIPPED_TODAY = "⏭ Скипнутые сегодня"
BTN_FAILED_MONTH = "❌ Упавшие за месяц"
BTN_FAILED_PREV_MONTH = "📅 Упавшие за прошлый месяц"
BTN_MENU = "📋 Меню"


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_SUCCESS_TODAY), KeyboardButton(BTN_SKIPPED_TODAY)],
            [KeyboardButton(BTN_FAILED_MONTH), KeyboardButton(BTN_FAILED_PREV_MONTH)],
            [KeyboardButton(BTN_MENU)],
        ],
        resize_keyboard=True,
    )


def is_allowed(update: Update) -> bool:
    if not TELEGRAM_CHAT_IDS:
        return True
    chat = update.effective_chat
    user = update.effective_user
    chat_id = chat.id if chat else None
    user_id = user.id if user else None
    return chat_id in TELEGRAM_CHAT_IDS or user_id in TELEGRAM_CHAT_IDS


async def backend_get(path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.get(f"{BACKEND_URL}{path}")
        response.raise_for_status()
        return response.json()


def format_run_line(item: dict[str, Any]) -> str:
    dag_id = item.get("dag_id", "—")
    start = item.get("start_date", "—")
    state = item.get("state", "—")
    line = f"• {dag_id}\n  start: {start} | state: {state}"
    failed_tasks = item.get("failed_tasks") or []
    if failed_tasks:
        tasks = ", ".join(task.get("task_id", "?") for task in failed_tasks)
        line += f"\n  failed tasks: {tasks}"
    skipped_tasks = item.get("skipped_tasks") or []
    if skipped_tasks:
        tasks = ", ".join(task.get("task_id", "?") for task in skipped_tasks[:10])
        suffix = "" if len(skipped_tasks) <= 10 else f" (+{len(skipped_tasks) - 10})"
        line += f"\n  skipped tasks: {tasks}{suffix}"
    return line


def format_list(title: str, payload: dict[str, Any]) -> str:
    items = payload.get("items") or []
    count = payload.get("count", len(items))
    if not items:
        return f"{title}\n\nНичего не найдено."
    body = "\n\n".join(format_run_line(item) for item in items[:50])
    extra = ""
    if count > 50:
        extra = f"\n\n… и ещё {count - 50}"
    return f"{title}\nВсего: {count}\n\n{body}{extra}"


def format_failure_alert(item: dict[str, Any]) -> str:
    dag_id = item.get("dag_id", "—")
    dag_run_id = item.get("dag_run_id", "—")
    start = item.get("start_date", "—")
    end = item.get("end_date", "—")
    failed_tasks = item.get("failed_tasks") or []
    if failed_tasks:
        tasks_text = "\n".join(
            f"  • {task.get('task_id')} (try={task.get('try_number')}, end={task.get('end_date')})"
            for task in failed_tasks
        )
    else:
        tasks_text = "  • неизвестно"
    return (
        "🚨 Падение DAG\n"
        f"DAG: {dag_id}\n"
        f"Run: {dag_run_id}\n"
        f"Start: {start}\n"
        f"End: {end}\n"
        f"Упавшие таски:\n{tasks_text}"
    )


def load_notified() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("notified", []))
    except (OSError, json.JSONDecodeError):
        return set()


def save_notified(notified: set[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"notified": sorted(notified)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def failure_key(item: dict[str, Any]) -> str:
    return f"{item.get('dag_id')}::{item.get('dag_run_id')}"


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in text.split("\n\n"):
        addition = len(block) + (2 if current else 0)
        if current and current_len + addition > limit:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += addition
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def reply_long(update: Update, text: str) -> None:
    for chunk in chunk_text(text):
        await update.message.reply_text(chunk, reply_markup=menu_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Мониторинг Airflow DAG.\nВыберите пункт меню:",
        reply_markup=menu_keyboard(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not is_allowed(update):
        return

    text = (update.message.text or "").strip()
    mapping = {
        BTN_SUCCESS_TODAY: ("/runs/success/today", "✅ Выполненные сегодня"),
        BTN_SKIPPED_TODAY: ("/runs/skipped/today", "⏭ Скипнутые сегодня"),
        BTN_FAILED_MONTH: ("/runs/failed/current-month", "❌ Упавшие за текущий месяц"),
        BTN_FAILED_PREV_MONTH: ("/runs/failed/previous-month", "📅 Упавшие за прошлый месяц"),
    }

    if text in (BTN_MENU, "/menu"):
        await update.message.reply_text("Меню:", reply_markup=menu_keyboard())
        return

    if text not in mapping:
        await update.message.reply_text(
            "Используйте кнопки меню.",
            reply_markup=menu_keyboard(),
        )
        return

    path, title = mapping[text]
    try:
        payload = await backend_get(path)
        await reply_long(update, format_list(title, payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Backend request failed")
        await update.message.reply_text(
            f"Ошибка запроса к backend: {exc}",
            reply_markup=menu_keyboard(),
        )


async def poll_failures(app: Application) -> None:
    notified = load_notified()
    logger.info("Failure poller started, interval=%ss", POLL_INTERVAL_SECONDS)
    while True:
        try:
            payload = await backend_get("/runs/failed/today")
            items = payload.get("items") or []
            new_items = [item for item in items if failure_key(item) not in notified]
            for item in new_items:
                message = format_failure_alert(item)
                targets = TELEGRAM_CHAT_IDS or set()
                if not targets:
                    logger.warning("TELEGRAM_CHAT_IDS is empty, skip alert send")
                    continue
                for chat_id in targets:
                    await app.bot.send_message(chat_id=chat_id, text=message)
                notified.add(failure_key(item))
            if new_items:
                save_notified(notified)
        except Exception:  # noqa: BLE001
            logger.exception("Failure polling error")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def post_init(app: Application) -> None:
    app.create_task(poll_failures(app))


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
