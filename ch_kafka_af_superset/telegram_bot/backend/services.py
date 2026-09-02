from __future__ import annotations

from collections import defaultdict
from typing import Any

from .airflow_client import airflow_client


def _unique_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for run in runs:
        key = (run.get("dag_id", ""), run.get("dag_run_id", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(run)
    return result


def serialize_run(run: dict[str, Any], failed_tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    item = {
        "dag_id": run.get("dag_id"),
        "dag_run_id": run.get("dag_run_id"),
        "state": run.get("state"),
        "execution_date": airflow_client.format_local(run.get("execution_date")),
        "start_date": airflow_client.format_local(run.get("start_date")),
        "end_date": airflow_client.format_local(run.get("end_date")),
    }
    if failed_tasks is not None:
        item["failed_tasks"] = [
            {
                "task_id": task.get("task_id"),
                "state": task.get("state"),
                "try_number": task.get("try_number"),
                "start_date": airflow_client.format_local(task.get("start_date")),
                "end_date": airflow_client.format_local(task.get("end_date")),
                "duration": task.get("duration"),
            }
            for task in failed_tasks
        ]
    return item


async def get_success_today() -> list[dict[str, Any]]:
    day = airflow_client.today()
    start, end = airflow_client._day_bounds_utc(day)
    runs = await airflow_client.list_dag_runs(state="success", end_gte=start, end_lte=end)
    return [serialize_run(run) for run in _unique_runs(runs)]


async def get_skipped_today() -> list[dict[str, Any]]:
    day = airflow_client.today()
    start, end = airflow_client._day_bounds_utc(day)
    tasks = await airflow_client.list_task_instances_range(
        state="skipped",
        start_gte=start,
        start_lte=end,
    )
    by_run: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        key = (task.get("dag_id", ""), task.get("dag_run_id", ""))
        by_run[key].append(task)

    result: list[dict[str, Any]] = []
    for (dag_id, dag_run_id), skipped_tasks in sorted(by_run.items()):
        result.append(
            {
                "dag_id": dag_id,
                "dag_run_id": dag_run_id,
                "state": "skipped",
                "skipped_tasks": [
                    {
                        "task_id": task.get("task_id"),
                        "start_date": airflow_client.format_local(task.get("start_date")),
                        "end_date": airflow_client.format_local(task.get("end_date")),
                    }
                    for task in skipped_tasks
                ],
            }
        )
    return result


async def get_failed_for_month(year: int, month: int) -> list[dict[str, Any]]:
    start, end = airflow_client._month_bounds_utc(year, month)
    runs = await airflow_client.list_dag_runs(state="failed", end_gte=start, end_lte=end)
    result: list[dict[str, Any]] = []
    for run in _unique_runs(runs):
        failed_tasks = await airflow_client.list_task_instances(
            run["dag_id"],
            run["dag_run_id"],
            state="failed",
        )
        result.append(serialize_run(run, failed_tasks))
    return result


async def get_failed_current_month() -> list[dict[str, Any]]:
    year, month = airflow_client.current_month()
    return await get_failed_for_month(year, month)


async def get_failed_previous_month() -> list[dict[str, Any]]:
    year, month = airflow_client.previous_month()
    return await get_failed_for_month(year, month)


async def get_failed_today_with_tasks() -> list[dict[str, Any]]:
    day = airflow_client.today()
    start, end = airflow_client._day_bounds_utc(day)
    runs = await airflow_client.list_dag_runs(state="failed", end_gte=start, end_lte=end)
    result: list[dict[str, Any]] = []
    for run in _unique_runs(runs):
        failed_tasks = await airflow_client.list_task_instances(
            run["dag_id"],
            run["dag_run_id"],
            state="failed",
        )
        result.append(serialize_run(run, failed_tasks))
    return result
