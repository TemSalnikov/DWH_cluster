from __future__ import annotations

import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .clickhouse import ClickHouseExporter
from .config import settings
from .filters import FilterCompileError, build_export_sql
from .models import ExportRequest, JobStatus
from .registry import ManifestRegistry


class ExportService:
    def __init__(self, registry: ManifestRegistry) -> None:
        self.registry = registry
        self.ch = ClickHouseExporter()
        self._jobs: dict[str, JobStatus] = {}

    def create_job(self, req: ExportRequest) -> JobStatus:
        job_id = uuid.uuid4().hex[:12]
        job = JobStatus(
            job_id=job_id,
            status="pending",
            dashboard_id=req.dashboard_id,
            export_id=req.export_id,
        )
        self._jobs[job_id] = job
        try:
            self._run(job, req)
        except Exception as exc:  # noqa: BLE001 — surface to API status
            job.status = "failed"
            job.error = str(exc)
        return job

    def get_job(self, job_id: str) -> JobStatus:
        if job_id not in self._jobs:
            raise KeyError(job_id)
        return self._jobs[job_id]

    def file_path(self, job: JobStatus) -> Path | None:
        if not job.file_name:
            return None
        return settings.exports_path / job.file_name

    def _run(self, job: JobStatus, req: ExportRequest) -> None:
        job.status = "running"
        manifest = self.registry.get(req.dashboard_id)
        export = manifest.export_by_id(req.export_id)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = settings.exports_path
        out_dir.mkdir(parents=True, exist_ok=True)

        if export.mode == "bundle":
            include = export.include or []
            if not include:
                raise FilterCompileError("bundle export requires include: [...]")
            zip_name = f"{manifest.id}_{export.id}_{stamp}.zip"
            zip_path = out_dir / zip_name
            sql_parts: list[str] = []
            total_rows = 0
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for child_id in include:
                    child = manifest.export_by_id(child_id)
                    if child.mode == "bundle":
                        continue
                    sql = build_export_sql(manifest, child, req.filters)
                    sql_parts.append(f"-- {child_id}\n{sql}")
                    tmp = out_dir / f".{job.job_id}_{child_id}.csv"
                    rows = self.ch.stream_csv(sql, tmp)
                    total_rows += rows
                    zf.write(tmp, arcname=f"{child_id}.csv")
                    tmp.unlink(missing_ok=True)
            job.sql_preview = "\n\n".join(sql_parts)
            job.file_name = zip_name
            job.rows_written = total_rows
            job.status = "done"
            return

        sql = build_export_sql(manifest, export, req.filters)
        job.sql_preview = sql
        file_name = f"{manifest.id}_{export.id}_{stamp}.csv"
        rows = self.ch.stream_csv(sql, out_dir / file_name)
        job.file_name = file_name
        job.rows_written = rows
        job.status = "done"
