from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from telethon import Button, TelegramClient, events
from telethon.network.connection.tcpmtproxy import ConnectionTcpMTProxyRandomizedIntermediate

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
SESSION_PATH = os.getenv("TELEGRAM_SESSION_PATH", "/data/bot_session")

# Official Telegram Desktop client credentials (public).
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "2040"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "b18441a1ff607e10a989891a5462e627")

TELEGRAM_PROXY_HOST = os.getenv("TELEGRAM_PROXY_HOST", "").strip()
TELEGRAM_PROXY_PORT = int(os.getenv("TELEGRAM_PROXY_PORT", "0") or "0")
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "").strip()

BTN_SUCCESS_TODAY = "✅ Выполненные сегодня"
BTN_SKIPPED_TODAY = "⏭ Скипнутые сегодня"
BTN_FAILED_MONTH = "❌ Упавшие за месяц"
BTN_FAILED_PREV_MONTH = "📅 Упавшие за прошлый месяц"
BTN_MENU = "📋 Меню"

MENU_BUTTONS = [
    [Button.text(BTN_SUCCESS_TODAY), Button.text(BTN_SKIPPED_TODAY)],
    [Button.text(BTN_FAILED_MONTH), Button.text(BTN_FAILED_PREV_MONTH)],
    [Button.text(BTN_MENU)],
]


def is_allowed(event: events.NewMessage.Event) -> bool:
    if not TELEGRAM_CHAT_IDS:
        return True
    return event.chat_id in TELEGRAM_CHAT_IDS or event.sender_id in TELEGRAM_CHAT_IDS


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


def build_client() -> TelegramClient:
    kwargs: dict[str, Any] = {
        "session": SESSION_PATH,
        "api_id": TELEGRAM_API_ID,
        "api_hash": TELEGRAM_API_HASH,
    }
    if TELEGRAM_PROXY_HOST and TELEGRAM_PROXY_PORT and TELEGRAM_PROXY_SECRET:
        logger.info(
            "Using MTProto proxy %s:%s",
            TELEGRAM_PROXY_HOST,
            TELEGRAM_PROXY_PORT,
        )
        kwargs["connection"] = ConnectionTcpMTProxyRandomizedIntermediate
        kwargs["proxy"] = (TELEGRAM_PROXY_HOST, TELEGRAM_PROXY_PORT, TELEGRAM_PROXY_SECRET)
    else:
        logger.warning("MTProto proxy is not configured")
    return TelegramClient(**kwargs)


async def poll_failures(client: TelegramClient) -> None:
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
                    await client.send_message(chat_id, message)
                notified.add(failure_key(item))
            if new_items:
                save_notified(notified)
        except Exception:  # noqa: BLE001
            logger.exception("Failure polling error")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    Path(SESSION_PATH).parent.mkdir(parents=True, exist_ok=True)
    client = build_client()

    @client.on(events.NewMessage(pattern=r"^/(start|menu)$"))
    async def start_handler(event: events.NewMessage.Event) -> None:
        if not is_allowed(event):
            return
        await event.respond(
            "Мониторинг Airflow DAG.\nВыберите пункт меню:",
            buttons=MENU_BUTTONS,
        )

    @client.on(events.NewMessage)
    async def text_handler(event: events.NewMessage.Event) -> None:
        if not event.message.message or not is_allowed(event):
            return
        text = event.message.message.strip()
        if text.startswith("/"):
            return

        mapping = {
            BTN_SUCCESS_TODAY: ("/runs/success/today", "✅ Выполненные сегодня"),
            BTN_SKIPPED_TODAY: ("/runs/skipped/today", "⏭ Скипнутые сегодня"),
            BTN_FAILED_MONTH: ("/runs/failed/current-month", "❌ Упавшие за текущий месяц"),
            BTN_FAILED_PREV_MONTH: ("/runs/failed/previous-month", "📅 Упавшие за прошлый месяц"),
        }

        if text == BTN_MENU:
            await event.respond("Меню:", buttons=MENU_BUTTONS)
            return

        if text not in mapping:
            await event.respond("Используйте кнопки меню.", buttons=MENU_BUTTONS)
            return

        path, title = mapping[text]
        try:
            payload = await backend_get(path)
            for chunk in chunk_text(format_list(title, payload)):
                await event.respond(chunk, buttons=MENU_BUTTONS)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Backend request failed")
            await event.respond(
                f"Ошибка запроса к backend: {exc}",
                buttons=MENU_BUTTONS,
            )

    await client.start(bot_token=TELEGRAM_BOT_TOKEN)
    logger.info("Telegram bot started")
    asyncio.create_task(poll_failures(client))
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
