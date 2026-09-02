from __future__ import annotations

from fastapi import FastAPI, HTTPException
from httpx import HTTPError

from . import services

app = FastAPI(title="Airflow Telegram Backend", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/runs/success/today")
async def success_today() -> dict:
    try:
        items = await services.get_success_today()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Airflow API error: {exc}") from exc
    return {"count": len(items), "items": items}


@app.get("/runs/skipped/today")
async def skipped_today() -> dict:
    try:
        items = await services.get_skipped_today()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Airflow API error: {exc}") from exc
    return {"count": len(items), "items": items}


@app.get("/runs/failed/current-month")
async def failed_current_month() -> dict:
    try:
        items = await services.get_failed_current_month()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Airflow API error: {exc}") from exc
    return {"count": len(items), "items": items}


@app.get("/runs/failed/previous-month")
async def failed_previous_month() -> dict:
    try:
        items = await services.get_failed_previous_month()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Airflow API error: {exc}") from exc
    return {"count": len(items), "items": items}


@app.get("/runs/failed/today")
async def failed_today() -> dict:
    try:
        items = await services.get_failed_today_with_tasks()
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Airflow API error: {exc}") from exc
    return {"count": len(items), "items": items}
