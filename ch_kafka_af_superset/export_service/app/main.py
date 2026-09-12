from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .clickhouse import ClickHouseExporter
from .config import settings
from .filters import FilterCompileError, build_export_sql
from .jobs import ExportService
from .models import ExportRequest, JobStatus
from .registry import ManifestRegistry

registry = ManifestRegistry(settings.manifests_path)
exporter = ExportService(registry)
ch = ClickHouseExporter()

app = FastAPI(title="Superset Export Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "dry_run": str(settings.dry_run).lower()}


@app.get("/dashboards")
def list_dashboards() -> dict:
    items = [
        {
            "id": m.id,
            "title": m.title,
            "superset_dashboard_id": m.superset.dashboard_id,
            "table": m.source.table,
            "exports": [{"id": e.id, "label": e.label, "mode": e.mode} for e in m.exports],
        }
        for m in registry.all()
    ]
    return {"count": len(items), "items": items}


@app.get("/dashboards/{dashboard_id}")
def get_dashboard(dashboard_id: str) -> dict:
    try:
        m = registry.get(dashboard_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return m.model_dump()


@app.get("/dashboards/{dashboard_id}/filters")
def get_filters(dashboard_id: str) -> dict:
    try:
        m = registry.get(dashboard_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = []
    for f in m.filters:
        item = f.model_dump()
        if f.values_from and f.type == "multi_select":
            try:
                item["values"] = ch.distinct_values(
                    table=m.source.table,
                    column=f.values_from.distinct,
                    where=f.values_from.where,
                    limit=f.values_from.limit,
                )
            except Exception as exc:  # noqa: BLE001
                item["values"] = []
                item["values_error"] = str(exc)
        result.append(item)
    return {"dashboard_id": dashboard_id, "filters": result}


@app.post("/exports", response_model=JobStatus)
def create_export(req: ExportRequest) -> JobStatus:
    try:
        return exporter.create_job(req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FilterCompileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/exports/{job_id}", response_model=JobStatus)
def get_export(job_id: str) -> JobStatus:
    try:
        return exporter.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"job '{job_id}' not found") from exc


@app.get("/exports/{job_id}/download")
def download_export(job_id: str):
    try:
        job = exporter.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job.status != "done" or not job.file_name:
        raise HTTPException(status_code=409, detail=f"job status={job.status}")
    path = exporter.file_path(job)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(path, filename=job.file_name)


@app.post("/exports/preview-sql")
def preview_sql(req: ExportRequest) -> dict:
    try:
        m = registry.get(req.dashboard_id)
        export = m.export_by_id(req.export_id)
        if export.mode == "bundle":
            parts = []
            for child_id in export.include or []:
                child = m.export_by_id(child_id)
                if child.mode == "bundle":
                    continue
                parts.append({"export_id": child_id, "sql": build_export_sql(m, child, req.filters)})
            return {"dashboard_id": req.dashboard_id, "export_id": req.export_id, "parts": parts}
        sql = build_export_sql(m, export, req.filters)
        return {"dashboard_id": req.dashboard_id, "export_id": req.export_id, "sql": sql}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FilterCompileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
