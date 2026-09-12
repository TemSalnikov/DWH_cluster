from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .superset_client import SupersetClient


def sync_dashboard(
    dashboard_id: int,
    out_path: Path | None = None,
    client: SupersetClient | None = None,
) -> dict[str, Any]:
    """
    Build a draft manifest from Superset charts linked to dashboard_id.
    Native filters are best-effort (dashboard GET often unavailable via JWT).
    """
    client = client or SupersetClient()
    client.login()
    charts = client.list_charts_for_dashboard(dashboard_id)
    if not charts:
        raise RuntimeError(f"no charts found for dashboard_id={dashboard_id}")

    title = None
    for chart in charts:
        for dash in chart.get("dashboards") or []:
            if dash.get("id") == dashboard_id:
                title = dash.get("dashboard_title") or title

    datasources = Counter()
    filter_counter: Counter[tuple[str, str]] = Counter()
    column_counter: Counter[str] = Counter()
    exports: list[dict[str, Any]] = []

    for chart in charts:
        params = chart.get("params")
        if isinstance(params, str):
            params = json.loads(params)
        params = params or {}
        ds = chart.get("datasource_name_text") or params.get("datasource")
        if ds:
            # bdm.table or "34__table"
            if isinstance(ds, str) and "__" not in ds:
                datasources[ds] += 1

        for f in params.get("adhoc_filters") or []:
            subj = f.get("subject")
            op = f.get("operator")
            if subj and op:
                filter_counter[(subj, op)] += 1

        for key in ("groupby", "groupbyColumns", "groupbyRows"):
            vals = params.get(key) or []
            if isinstance(vals, str):
                vals = [vals]
            for col in vals:
                if isinstance(col, str):
                    column_counter[col] += 1

        viz = chart.get("viz_type")
        if viz in {"table", "pivot_table_v2"}:
            exports.append(_chart_to_export(chart, params))

    table = datasources.most_common(1)[0][0] if datasources else "bdm.unknown"
    # heuristics: filters present on >= 50% charts
    threshold = max(1, len(charts) // 2)
    defaults_where: list[dict[str, Any]] = []
    for (col, op), cnt in filter_counter.most_common():
        if cnt < threshold:
            continue
        if op in {"NOT IN", "not_in"} and col == "type_of_disposal":
            defaults_where.append(
                {"column": col, "op": "not_in", "value": ["Остаток"]}
            )
        # TEMPORAL_RANGE "No filter" — skip as default constraint

    # filter UI candidates from frequent groupby columns
    filter_cols = [c for c, _ in column_counter.most_common(8) if c != "date_of_disposal"]
    date_col = "date_of_disposal" if column_counter.get("date_of_disposal") else None

    filters: list[dict[str, Any]] = []
    if date_col:
        filters.append(
            {
                "id": "date",
                "label": "Период",
                "column": date_col,
                "type": "date_range",
                "required": False,
                "default": "relative:current_year",
            }
        )
    for col in filter_cols[:5]:
        filters.append(
            {
                "id": col,
                "label": col,
                "column": col,
                "type": "multi_select",
                "values_from": {"distinct": col, "limit": 2000},
            }
        )

    slug = _slug(title or f"dashboard_{dashboard_id}")
    manifest: dict[str, Any] = {
        "id": slug,
        "title": title or f"Dashboard {dashboard_id}",
        "superset": {
            "dashboard_id": dashboard_id,
            "dashboard_title": title,
        },
        "source": {
            "database": "clickhouse",
            "table": table,
            "columns": ["*"],
        },
        "defaults": {"where": defaults_where},
        "filters": filters,
        "exports": [
            {
                "id": "raw",
                "label": "Все строки (CSV)",
                "mode": "raw",
            },
            *exports,
            {
                "id": "bundle_tables",
                "label": "Таблицы дашборда (ZIP)",
                "mode": "bundle",
                "include": ["raw"] + [e["id"] for e in exports],
            },
        ],
    }

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return manifest


def _chart_to_export(chart: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    cid = chart["id"]
    name = chart.get("slice_name") or f"chart_{cid}"
    group_by = params.get("groupby") or params.get("groupbyColumns") or []
    if params.get("groupbyRows"):
        group_by = list(group_by) + list(params["groupbyRows"])
    # unique preserve order
    seen: set[str] = set()
    group_by_u: list[str] = []
    for c in group_by:
        if isinstance(c, str) and c not in seen:
            seen.add(c)
            group_by_u.append(c)

    metrics_out: list[dict[str, str]] = []
    for m in params.get("metrics") or []:
        if isinstance(m, str):
            metrics_out.append({"label": m, "expr": f"sum(`TODO_{m}`)"})
        elif isinstance(m, dict):
            label = m.get("label") or "metric"
            if m.get("expressionType") == "SQL" and m.get("sqlExpression"):
                expr = m["sqlExpression"]
            elif m.get("aggregate") and m.get("column"):
                col = m["column"].get("column_name")
                expr = f"{m['aggregate']}(`{col}`)"
            else:
                expr = f"sum(`TODO`)"
            metrics_out.append({"label": label, "expr": expr})

    export: dict[str, Any] = {
        "id": f"chart_{cid}",
        "label": name,
        "mode": "aggregate" if group_by_u and metrics_out else "raw",
        "superset_chart_id": cid,
    }
    if group_by_u and metrics_out:
        export["group_by"] = group_by_u
        export["metrics"] = metrics_out
    return export


def _slug(title: str) -> str:
    mapping = {
        " ": "_",
        "|": "",
        "/": "_",
        "\\": "_",
        ",": "",
        ".": "",
    }
    text = title.lower()
    for a, b in mapping.items():
        text = text.replace(a, b)
    # keep ascii + underscores + cyrillic
    allowed = []
    for ch in text:
        if ch.isalnum() or ch == "_":
            allowed.append(ch)
    slug = "".join(allowed).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "dashboard"
