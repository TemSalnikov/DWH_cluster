#!/usr/bin/env python3
"""Minimal Airflow REST API mock for backend smoke tests."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn

app = FastAPI()
security = HTTPBasic()

NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    if credentials.username != "airflow" or credentials.password != "airflow":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/api/v1/dags/~/dagRuns")
def dag_runs(
    state: str | None = None,
    end_date_gte: str | None = None,
    end_date_lte: str | None = None,
    limit: int = 100,
    offset: int = 0,
    order_by: str | None = None,
    _: None = Depends(auth),
):
    runs = [
        {
            "dag_id": "demo_success",
            "dag_run_id": "manual__success",
            "state": "success",
            "execution_date": NOW,
            "start_date": NOW,
            "end_date": NOW,
        },
        {
            "dag_id": "demo_failed",
            "dag_run_id": "manual__failed",
            "state": "failed",
            "execution_date": NOW,
            "start_date": NOW,
            "end_date": NOW,
        },
    ]
    if state:
        runs = [r for r in runs if r["state"] == state]
    page = runs[offset : offset + limit]
    return {"dag_runs": page, "total_entries": len(runs)}


@app.get("/api/v1/dags/~/dagRuns/~/taskInstances")
def task_instances_range(
    state: str | None = None,
    start_date_gte: str | None = None,
    start_date_lte: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _: None = Depends(auth),
):
    tasks = [
        {
            "dag_id": "demo_skipped",
            "dag_run_id": "manual__skipped",
            "task_id": "branch_skip",
            "state": "skipped",
            "start_date": NOW,
            "end_date": NOW,
        }
    ]
    if state:
        tasks = [t for t in tasks if t["state"] == state]
    page = tasks[offset : offset + limit]
    return {"task_instances": page, "total_entries": len(tasks)}


@app.get("/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
def task_instances(dag_id: str, dag_run_id: str, state: str | None = None, _: None = Depends(auth)):
    tasks = [
        {
            "dag_id": dag_id,
            "dag_run_id": dag_run_id,
            "task_id": "extract",
            "state": "failed" if "failed" in dag_run_id else "success",
            "try_number": 1,
            "start_date": NOW,
            "end_date": NOW,
            "duration": 1.5,
        }
    ]
    if state:
        tasks = [t for t in tasks if t["state"] == state]
    return {"task_instances": tasks, "total_entries": len(tasks)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18080)
