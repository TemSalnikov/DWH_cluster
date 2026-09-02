from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import settings


class AirflowClient:
    def __init__(self) -> None:
        self.base_url = settings.airflow_api_url.rstrip("/")
        self.auth = (settings.airflow_username, settings.airflow_password)
        self.tz = ZoneInfo(settings.timezone)
        self.page_limit = settings.page_limit

    def _day_bounds_utc(self, day: date) -> tuple[str, str]:
        start_local = datetime.combine(day, time.min, tzinfo=self.tz)
        end_local = datetime.combine(day, time.max, tzinfo=self.tz)
        return (
            start_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            end_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def _month_bounds_utc(self, year: int, month: int) -> tuple[str, str]:
        start = date(year, month, 1)
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)
        start_local = datetime.combine(start, time.min, tzinfo=self.tz)
        end_local = datetime.combine(last_day, time.max, tzinfo=self.tz)
        return (
            start_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            end_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0, auth=self.auth) as client:
            response = await client.get(f"{self.base_url}{path}", params=params or {})
            response.raise_for_status()
            return response.json()

    async def _paginate(self, path: str, params: dict[str, Any], list_key: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page_params = {
                **params,
                "limit": self.page_limit,
                "offset": offset,
            }
            payload = await self._get(path, page_params)
            batch = payload.get(list_key) or []
            items.extend(batch)
            total = payload.get("total_entries", len(items))
            offset += self.page_limit
            if offset >= total or not batch:
                break
        return items

    async def list_dag_runs(
        self,
        *,
        state: str | None = None,
        start_gte: str | None = None,
        start_lte: str | None = None,
        end_gte: str | None = None,
        end_lte: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "order_by": "-end_date",
        }
        if state:
            params["state"] = state
        if start_gte:
            params["start_date_gte"] = start_gte
        if start_lte:
            params["start_date_lte"] = start_lte
        if end_gte:
            params["end_date_gte"] = end_gte
        if end_lte:
            params["end_date_lte"] = end_lte
        return await self._paginate("/dags/~/dagRuns", params, "dag_runs")

    async def list_task_instances(
        self,
        dag_id: str,
        dag_run_id: str,
        *,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if state:
            params["state"] = state
        return await self._paginate(
            f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
            params,
            "task_instances",
        )

    async def list_task_instances_range(
        self,
        *,
        state: str | None = None,
        start_gte: str | None = None,
        start_lte: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if state:
            params["state"] = state
        if start_gte:
            params["start_date_gte"] = start_gte
        if start_lte:
            params["start_date_lte"] = start_lte
        return await self._paginate("/dags/~/dagRuns/~/taskInstances", params, "task_instances")

    def today(self) -> date:
        return datetime.now(self.tz).date()

    def current_month(self) -> tuple[int, int]:
        now = datetime.now(self.tz)
        return now.year, now.month

    def previous_month(self) -> tuple[int, int]:
        now = datetime.now(self.tz)
        if now.month == 1:
            return now.year - 1, 12
        return now.year, now.month - 1

    def format_local(self, value: str | None) -> str:
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(self.tz).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value


airflow_client = AirflowClient()
