from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Op = Literal[
    "eq",
    "neq",
    "in",
    "not_in",
    "gte",
    "lt",
    "between",
    "date_range",
]


class WhereClause(BaseModel):
    column: str
    op: Op
    value: Any


class ValuesFrom(BaseModel):
    distinct: str
    where: str | None = None
    limit: int = 2000


class FilterDef(BaseModel):
    id: str
    label: str
    column: str
    type: Literal["date_range", "multi_select", "text"] = "multi_select"
    required: bool = False
    default: Any | None = None
    values_from: ValuesFrom | None = None


class MetricDef(BaseModel):
    label: str
    expr: str


class ExportDef(BaseModel):
    id: str
    label: str
    mode: Literal["raw", "aggregate", "bundle"] = "raw"
    columns: list[str] | None = None
    group_by: list[str] | None = None
    metrics: list[MetricDef] | None = None
    extra_where: list[WhereClause] = Field(default_factory=list)
    order_by: list[str] | None = None
    include: list[str] | None = None  # for bundle
    safety_cap: int | None = None


class SourceDef(BaseModel):
    database: str = "clickhouse"
    table: str
    columns: list[str] = Field(default_factory=lambda: ["*"])


class SupersetRef(BaseModel):
    dashboard_id: int
    dashboard_title: str | None = None


class DefaultsDef(BaseModel):
    where: list[WhereClause] = Field(default_factory=list)


class DashboardManifest(BaseModel):
    id: str
    title: str
    superset: SupersetRef
    source: SourceDef
    defaults: DefaultsDef = Field(default_factory=DefaultsDef)
    filters: list[FilterDef] = Field(default_factory=list)
    exports: list[ExportDef] = Field(default_factory=list)

    def export_by_id(self, export_id: str) -> ExportDef:
        for item in self.exports:
            if item.id == export_id:
                return item
        raise KeyError(f"export '{export_id}' not found in manifest '{self.id}'")

    def filter_by_id(self, filter_id: str) -> FilterDef:
        for item in self.filters:
            if item.id == filter_id:
                return item
        raise KeyError(f"filter '{filter_id}' not found in manifest '{self.id}'")


class ExportRequest(BaseModel):
    dashboard_id: str
    export_id: str = "raw"
    filters: dict[str, Any] = Field(default_factory=dict)


class JobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"]
    dashboard_id: str
    export_id: str
    sql_preview: str | None = None
    file_name: str | None = None
    rows_written: int | None = None
    error: str | None = None
