from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .models import DashboardManifest, ExportDef, FilterDef, WhereClause


class FilterCompileError(ValueError):
    pass


def _quote_ident(name: str) -> str:
    if name == "*":
        return "*"
    # Allow human labels in aliases: letters/digits/_/./space/,/%/-
    cleaned = (
        name.replace("_", "")
        .replace(".", "")
        .replace(" ", "")
        .replace(",", "")
        .replace("%", "")
        .replace("-", "")
    )
    if not cleaned or not cleaned.isalnum():
        raise FilterCompileError(f"unsafe identifier: {name}")
    if "." in name and all(p.replace("_", "").isalnum() for p in name.split(".")):
        return ".".join(f"`{p}`" for p in name.split("."))
    return f"`{name}`"


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return f"'{value.isoformat()}'"
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def _list_literals(values: list[Any]) -> str:
    if not values:
        raise FilterCompileError("empty IN/NOT IN list")
    return ", ".join(_literal(v) for v in values)


def compile_where(clause: WhereClause) -> str:
    col = _quote_ident(clause.column)
    op = clause.op
    val = clause.value

    if op == "eq":
        return f"{col} = {_literal(val)}"
    if op == "neq":
        return f"{col} != {_literal(val)}"
    if op == "in":
        return f"{col} IN ({_list_literals(list(val))})"
    if op == "not_in":
        return f"{col} NOT IN ({_list_literals(list(val))})"
    if op == "gte":
        return f"{col} >= {_literal(val)}"
    if op == "lt":
        return f"{col} < {_literal(val)}"
    if op == "between":
        if not isinstance(val, (list, tuple)) or len(val) != 2:
            raise FilterCompileError("between expects [from, to]")
        return f"{col} >= {_literal(val[0])} AND {col} < {_literal(val[1])}"
    if op == "date_range":
        start, end = _resolve_date_range(val)
        return f"{col} >= {_literal(start)} AND {col} < {_literal(end)}"
    raise FilterCompileError(f"unsupported op: {op}")


def _resolve_date_range(value: Any) -> tuple[date, date]:
    """Accept {'from': 'YYYY-MM-DD', 'to': 'YYYY-MM-DD'} or relative:* strings."""
    if isinstance(value, str) and value.startswith("relative:"):
        key = value.split(":", 1)[1]
        today = date.today()
        if key == "current_year":
            return date(today.year, 1, 1), date(today.year + 1, 1, 1)
        if key == "last_30d":
            return today - timedelta(days=30), today + timedelta(days=1)
        if key == "current_month":
            start = date(today.year, today.month, 1)
            if today.month == 12:
                end = date(today.year + 1, 1, 1)
            else:
                end = date(today.year, today.month + 1, 1)
            return start, end
        raise FilterCompileError(f"unknown relative range: {key}")

    if isinstance(value, dict):
        start = value.get("from") or value.get("start")
        end = value.get("to") or value.get("end")
        if not start or not end:
            raise FilterCompileError("date_range requires from/to")
        start_d = date.fromisoformat(str(start)[:10])
        end_d = date.fromisoformat(str(end)[:10])
        # treat `to` as inclusive calendar day -> exclusive upper bound next day
        return start_d, end_d + timedelta(days=1)

    raise FilterCompileError("invalid date_range value")


def compile_user_filters(
    manifest: DashboardManifest,
    user_filters: dict[str, Any],
) -> list[str]:
    """Map UI filter payload -> WHERE fragments. Only allowlisted columns."""
    allowed = {f.id: f for f in manifest.filters}
    parts: list[str] = []

    for fid, fdef in allowed.items():
        raw = user_filters.get(fid, fdef.default)
        if raw is None or raw == "" or raw == []:
            if fdef.required:
                raise FilterCompileError(f"filter '{fid}' is required")
            continue
        parts.append(_compile_filter_def(fdef, raw))

    unknown = set(user_filters) - set(allowed)
    if unknown:
        raise FilterCompileError(f"unknown filters: {sorted(unknown)}")
    return parts


def _compile_filter_def(fdef: FilterDef, raw: Any) -> str:
    if fdef.type == "date_range":
        return compile_where(WhereClause(column=fdef.column, op="date_range", value=raw))
    if fdef.type == "multi_select":
        values = raw if isinstance(raw, list) else [raw]
        return compile_where(WhereClause(column=fdef.column, op="in", value=values))
    if fdef.type == "text":
        return compile_where(WhereClause(column=fdef.column, op="eq", value=raw))
    raise FilterCompileError(f"unsupported filter type: {fdef.type}")


def build_export_sql(
    manifest: DashboardManifest,
    export: ExportDef,
    user_filters: dict[str, Any],
) -> str:
    where_parts = [compile_where(w) for w in manifest.defaults.where]
    where_parts.extend(compile_user_filters(manifest, user_filters))
    where_parts.extend(compile_where(w) for w in export.extra_where)
    where_sql = " AND ".join(where_parts) if where_parts else "1"

    table = _quote_ident(manifest.source.table)

    if export.mode == "raw":
        cols = export.columns or manifest.source.columns or ["*"]
        col_sql = ", ".join(_quote_ident(c) for c in cols)
        sql = f"SELECT {col_sql}\nFROM {table}\nWHERE {where_sql}"
        if export.safety_cap:
            sql += f"\nLIMIT {int(export.safety_cap)}"
        return sql

    if export.mode == "aggregate":
        if not export.group_by or not export.metrics:
            raise FilterCompileError("aggregate export needs group_by and metrics")
        group_sql = ", ".join(_quote_ident(c) for c in export.group_by)
        metric_sql = ", ".join(
            f"{m.expr} AS {_quote_ident(m.label)}" for m in export.metrics
        )
        sql = (
            f"SELECT {group_sql}, {metric_sql}\n"
            f"FROM {table}\n"
            f"WHERE {where_sql}\n"
            f"GROUP BY {group_sql}"
        )
        if export.order_by:
            # order_by entries are trusted labels/exprs from manifest, not user input
            sql += "\nORDER BY " + ", ".join(export.order_by)
        if export.safety_cap:
            sql += f"\nLIMIT {int(export.safety_cap)}"
        return sql

    raise FilterCompileError(f"mode '{export.mode}' is not directly executable")
