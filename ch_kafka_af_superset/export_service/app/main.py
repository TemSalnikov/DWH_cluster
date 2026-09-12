from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .clickhouse import ClickHouseExporter
from .config import settings
from .filters import FilterCompileError, build_export_sql
from .jobs import ExportService
from .models import ConnectDashboardRequest, ExportRequest, JobStatus, PreviewRequest
from .registry import ManifestRegistry
from .sync import sync_dashboard

registry = ManifestRegistry(settings.manifests_path)
exporter = ExportService(registry)
ch = ClickHouseExporter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Выгрузка отчётов", version="0.2.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "dry_run": str(settings.dry_run).lower()}


@app.get("/api/dashboards")
@app.get("/dashboards")
def list_dashboards() -> dict:
    items = []
    for m in registry.all():
        exports = []
        for e in m.exports:
            exports.append(
                {
                    "id": e.id,
                    "label": e.label,
                    "mode": e.mode,
                    "description": _export_hint(e.mode),
                }
            )
        items.append(
            {
                "id": m.id,
                "title": m.title,
                "superset_dashboard_id": m.superset.dashboard_id,
                "table": m.source.table,
                "exports": exports,
                "filter_count": len(m.filters),
            }
        )
    return {"count": len(items), "items": items}


def _export_hint(mode: str) -> str:
    if mode == "raw":
        return "Все строки таблицы с учётом фильтров"
    if mode == "aggregate":
        return "Сводка как на графике/таблице отчёта"
    if mode == "bundle":
        return "Несколько файлов одним архивом ZIP"
    return ""


@app.get("/api/dashboards/{dashboard_id}")
@app.get("/dashboards/{dashboard_id}")
def get_dashboard(dashboard_id: str) -> dict:
    try:
        m = registry.get(dashboard_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return m.model_dump()


@app.get("/api/dashboards/{dashboard_id}/filters")
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
            if f.values_from.lazy:
                item["values"] = []
                item["lazy"] = True
            else:
                try:
                    item["values"] = ch.distinct_values(
                        table=m.source.table,
                        column=f.values_from.distinct,
                        where=f.values_from.where,
                        limit=min(f.values_from.limit, 3000),
                    )
                    item["lazy"] = False
                except Exception as exc:  # noqa: BLE001
                    item["values"] = []
                    item["values_error"] = str(exc)
                    item["lazy"] = False
        result.append(item)
    return {"dashboard_id": dashboard_id, "filters": result}


@app.get("/api/dashboards/{dashboard_id}/filters/{filter_id}/values")
@app.get("/dashboards/{dashboard_id}/filters/{filter_id}/values")
def search_filter_values(
    dashboard_id: str,
    filter_id: str,
    q: str = "",
    limit: int = 80,
) -> dict:
    """Search dimension values (used by lazy multi-select filters)."""
    try:
        m = registry.get(dashboard_id)
        fdef = m.filter_by_id(filter_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if fdef.type != "multi_select" or not fdef.values_from:
        raise HTTPException(status_code=400, detail="Фильтр не поддерживает поиск значений")
    q = (q or "").strip()
    if fdef.values_from.lazy and len(q) < 2:
        return {
            "filter_id": filter_id,
            "q": q,
            "values": [],
            "hint": "Введите минимум 2 символа для поиска",
        }
    try:
        values = ch.distinct_values(
            table=m.source.table,
            column=fdef.values_from.distinct,
            where=fdef.values_from.where,
            limit=min(max(limit, 1), 200),
            search=q or None,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось загрузить значения: {exc}",
        ) from exc
    return {"filter_id": filter_id, "q": q, "values": values, "count": len(values)}


@app.post("/api/manifests/connect")
@app.post("/manifests/connect")
def connect_dashboard(req: ConnectDashboardRequest) -> dict:
    """Create/update a YAML manifest from a Superset dashboard."""
    import re

    dash_id = req.superset_dashboard_id
    if dash_id is None and req.superset_url:
        m = re.search(r"/dashboard/(?:list/)?(\d+)", req.superset_url)
        if not m:
            m = re.search(r"(?:^|[^\d])(\d{1,5})(?:[^\d]|$)", req.superset_url.strip())
        if not m:
            raise HTTPException(
                status_code=400,
                detail="Не удалось найти номер дашборда в ссылке. "
                "Вставьте URL вида …/dashboard/20/ или укажите числовой id.",
            )
        dash_id = int(m.group(1))
    if dash_id is None:
        raise HTTPException(status_code=400, detail="Укажите id дашборда или ссылку из Superset")

    # Resolve output path (preview id first without write if conflict)
    try:
        draft = sync_dashboard(
            dash_id,
            out_path=None,
            manifest_id=req.manifest_id,
            title_override=req.title,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    manifest_id = draft["id"]
    out_path = settings.manifests_path / f"{manifest_id}.yaml"
    if out_path.exists() and not req.overwrite:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Отчёт «{manifest_id}» уже подключён. "
                "Включите «Заменить существующий», чтобы обновить.",
                "manifest_id": manifest_id,
                "title": draft.get("title"),
                "exists": True,
            },
        )

    try:
        saved = sync_dashboard(
            dash_id,
            out_path=out_path,
            manifest_id=manifest_id,
            title_override=req.title or draft.get("title"),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    meta = saved.pop("_meta", {})
    return {
        "ok": True,
        "file": str(out_path.name),
        "manifest_id": saved["id"],
        "title": saved["title"],
        "table": saved["source"]["table"],
        "filters_count": len(saved.get("filters") or []),
        "exports_count": len(saved.get("exports") or []),
        "charts_found": meta.get("charts_found"),
        "native_filters_found": meta.get("native_filters_found"),
        "filter_labels": [f.get("label") for f in (saved.get("filters") or [])],
        "message": (
            f"Отчёт «{saved['title']}» подключён. "
            f"Фильтров: {len(saved.get('filters') or [])}"
            + (
                f" (native в дашборде: {meta.get('native_filters_found')}, "
                f"«Периодичность» не переносится — это настройка графика)"
                if meta.get("native_filters_found") is not None
                else ""
            )
            + ". Его можно выбрать на вкладке «Выгрузка»."
        ),
    }


@app.post("/api/exports", response_model=JobStatus)
@app.post("/exports", response_model=JobStatus)
def create_export(req: ExportRequest) -> JobStatus:
    try:
        return exporter.create_job(req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FilterCompileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/exports/{job_id}", response_model=JobStatus)
@app.get("/exports/{job_id}", response_model=JobStatus)
def get_export(job_id: str) -> JobStatus:
    try:
        return exporter.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"job '{job_id}' not found") from exc


@app.get("/api/exports/{job_id}/download")
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


@app.post("/api/exports/preview")
@app.post("/exports/preview")
def preview_data(req: PreviewRequest) -> dict:
    try:
        m = registry.get(req.dashboard_id)
        export = m.export_by_id(req.export_id)
        preview_export = export
        note = None
        if export.mode == "bundle":
            include = export.include or []
            child_id = "raw" if "raw" in include else (include[0] if include else None)
            if not child_id:
                raise FilterCompileError("В архиве нет таблиц для превью")
            preview_export = m.export_by_id(child_id)
            note = f"Превью для архива показано по файлу «{preview_export.label}»"
        sql = build_export_sql(m, preview_export, req.filters)
        data = ch.query_rows(sql, limit=req.limit)
        return {
            "dashboard_id": req.dashboard_id,
            "export_id": req.export_id,
            "preview_export_id": preview_export.id,
            "export_label": export.label,
            "note": note,
            **data,
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FilterCompileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось получить данные из ClickHouse: {exc}",
        ) from exc


@app.post("/api/exports/preview-sql")
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
                parts.append(
                    {"export_id": child_id, "sql": build_export_sql(m, child, req.filters)}
                )
            return {
                "dashboard_id": req.dashboard_id,
                "export_id": req.export_id,
                "parts": parts,
            }
        sql = build_export_sql(m, export, req.filters)
        return {"dashboard_id": req.dashboard_id, "export_id": req.export_id, "sql": sql}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FilterCompileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/")
def ui_index():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="UI not built")
    return FileResponse(index)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
