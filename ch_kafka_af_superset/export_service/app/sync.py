from __future__ import annotations

import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .superset_client import SupersetClient


def sync_dashboard(
    dashboard_id: int,
    out_path: Path | None = None,
    client: SupersetClient | None = None,
    manifest_id: str | None = None,
    title_override: str | None = None,
) -> dict[str, Any]:
    """
    Build a manifest from Superset dashboard export (native filters + dataset verbose names).
    Falls back to chart-list heuristics if export is unavailable.
    """
    client = client or SupersetClient()
    client.login()
    try:
        bundle = client.export_dashboard_bundle(dashboard_id)
        return _sync_from_export_bundle(
            dashboard_id,
            bundle,
            out_path=out_path,
            manifest_id=manifest_id,
            title_override=title_override,
        )
    except Exception:
        # Fallback for older/permission-limited setups
        return _sync_from_charts_fallback(
            dashboard_id,
            client=client,
            out_path=out_path,
            manifest_id=manifest_id,
            title_override=title_override,
        )


def _sync_from_export_bundle(
    dashboard_id: int,
    bundle: dict[str, Any],
    *,
    out_path: Path | None,
    manifest_id: str | None,
    title_override: str | None,
) -> dict[str, Any]:
    dash = bundle["dashboard"]
    datasets = bundle["datasets"]
    charts = bundle["charts"]

    title = title_override or dash.get("dashboard_title") or f"Dashboard {dashboard_id}"
    metadata = dash.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    native_filters = metadata.get("native_filter_configuration") or []

    # Prefer the dataset that appears most often in chart dataset_uuid
    ds_uuid_counts: Counter[str] = Counter()
    for ch in charts:
        u = ch.get("dataset_uuid")
        if u:
            ds_uuid_counts[u] += 1
    primary_ds = None
    if ds_uuid_counts and datasets:
        # datasets keyed by uuid if present
        by_uuid = {d.get("uuid"): d for d in datasets if d.get("uuid")}
        top_uuid = ds_uuid_counts.most_common(1)[0][0]
        primary_ds = by_uuid.get(top_uuid) or datasets[0]
    elif datasets:
        primary_ds = datasets[0]

    schema = (primary_ds or {}).get("schema") or "bdm"
    table_name = (primary_ds or {}).get("table_name") or "unknown"
    table = f"{schema}.{table_name}"

    column_labels: dict[str, str] = {}
    physical_columns: list[str] = []
    dttm_cols: list[str] = []
    for col in (primary_ds or {}).get("columns") or []:
        name = col.get("column_name")
        if not name:
            continue
        physical_columns.append(name)
        verbose = (col.get("verbose_name") or "").strip()
        if verbose:
            column_labels[name] = verbose
        if col.get("is_dttm"):
            dttm_cols.append(name)

    # Native filter titles override labels for the same columns (dashboard wording)
    filters: list[dict[str, Any]] = []
    seen_cols: set[str] = set()
    for nf in native_filters:
        ftype = nf.get("filterType") or ""
        name = (nf.get("name") or "").strip() or "Фильтр"
        targets = nf.get("targets") or []
        col_name = _target_column(targets)

        if ftype == "filter_timegrain":
            # Grain is a viz setting, not a data WHERE filter — skip
            continue

        # Date/period filters: always use from–to range in our UI
        # (Superset sometimes exposes dates as filter_select with daily values)
        is_date_filter = (
            ftype == "filter_time"
            or (col_name and col_name in dttm_cols)
            or (col_name and _looks_like_date_column(col_name))
            or (ftype == "filter_select" and _looks_like_date_label(name) and (col_name in dttm_cols or _looks_like_date_column(col_name or "")))
        )
        if is_date_filter:
            col_name = col_name or (dttm_cols[0] if dttm_cols else None)
            if not col_name:
                continue
            if col_name in seen_cols:
                continue
            seen_cols.add(col_name)
            column_labels.setdefault(col_name, name)
            filters.append(
                {
                    "id": _filter_id(col_name, name),
                    "label": name,
                    "column": col_name,
                    "type": "date_range",
                    "required": False,
                    "default": "relative:current_year",
                }
            )
            continue

        if ftype in {"filter_select", "filter_range"} or col_name:
            if not col_name:
                continue
            if col_name in seen_cols:
                # Keep first dashboard label; still record label mapping
                column_labels.setdefault(col_name, name)
                continue
            seen_cols.add(col_name)
            column_labels.setdefault(col_name, name)
            lazy = _is_lazy_column(col_name)
            filters.append(
                {
                    "id": _filter_id(col_name, name),
                    "label": name,
                    "column": col_name,
                    "type": "multi_select" if ftype != "filter_range" else "text",
                    "values_from": {
                        "distinct": col_name,
                        "limit": 80 if lazy else 2000,
                        "lazy": lazy,
                    },
                }
            )

    # Defaults heuristics from chart adhoc filters
    defaults_where: list[dict[str, Any]] = []
    filter_counter: Counter[tuple[str, str]] = Counter()
    for ch in charts:
        params = _chart_params(ch)
        for f in params.get("adhoc_filters") or []:
            subj, op = f.get("subject"), f.get("operator")
            if subj and op:
                filter_counter[(subj, op)] += 1
    threshold = max(1, len(charts) // 2) if charts else 1
    for (col, op), cnt in filter_counter.most_common():
        if cnt < threshold:
            continue
        if op in {"NOT IN", "not_in"} and col == "type_of_disposal":
            defaults_where.append({"column": col, "op": "not_in", "value": ["Остаток"]})

    exports: list[dict[str, Any]] = [
        {"id": "raw", "label": "Все строки (CSV)", "mode": "raw"}
    ]
    for ch in charts:
        params = _chart_params(ch)
        if ch.get("viz_type") not in {"table", "pivot_table_v2"}:
            continue
        exports.append(_chart_to_export(ch, params, column_labels))

    exports.append(
        {
            "id": "bundle_tables",
            "label": "Таблицы дашборда (ZIP)",
            "mode": "bundle",
            "include": [e["id"] for e in exports if e["mode"] != "bundle"],
        }
    )

    slug = manifest_id or _slug(title)
    manifest: dict[str, Any] = {
        "id": slug,
        "title": title,
        "superset": {
            "dashboard_id": dashboard_id,
            "dashboard_title": dash.get("dashboard_title") or title,
        },
        "source": {
            "database": "clickhouse",
            "table": table,
            "columns": physical_columns or ["*"],
        },
        "column_labels": column_labels,
        "defaults": {"where": defaults_where},
        "filters": filters,
        "exports": exports,
        "_meta": {
            "charts_found": len(charts),
            "table_exports": sum(1 for e in exports if e["mode"] != "bundle"),
            "native_filters_found": len(native_filters),
            "filters_mapped": len(filters),
        },
    }
    _write_manifest(manifest, out_path)
    return manifest


def _sync_from_charts_fallback(
    dashboard_id: int,
    *,
    client: SupersetClient,
    out_path: Path | None,
    manifest_id: str | None,
    title_override: str | None,
) -> dict[str, Any]:
    charts = client.list_charts_for_dashboard(dashboard_id)
    if not charts:
        raise RuntimeError(
            f"Не найдены чарты для dashboard_id={dashboard_id}. "
            "Проверьте номер дашборда в адресе Superset."
        )
    title = title_override
    for chart in charts:
        for dash in chart.get("dashboards") or []:
            if dash.get("id") == dashboard_id:
                title = title or dash.get("dashboard_title")
    title = title or f"Dashboard {dashboard_id}"

    datasources: Counter[str] = Counter()
    column_counter: Counter[str] = Counter()
    exports_chart: list[dict[str, Any]] = []
    for chart in charts:
        params = chart.get("params")
        if isinstance(params, str):
            params = json.loads(params)
        params = params or {}
        ds = chart.get("datasource_name_text")
        if isinstance(ds, str) and "__" not in ds:
            datasources[ds] += 1
        for key in ("groupby", "groupbyColumns", "groupbyRows"):
            vals = params.get(key) or []
            if isinstance(vals, str):
                vals = [vals]
            for col in vals:
                if isinstance(col, str):
                    column_counter[col] += 1
        if chart.get("viz_type") in {"table", "pivot_table_v2"}:
            exports_chart.append(_chart_to_export(chart, params, {}))

    table = datasources.most_common(1)[0][0] if datasources else "bdm.unknown"
    date_col = next(
        (c for c, _ in column_counter.most_common() if "date" in c.lower()),
        None,
    )
    filters: list[dict[str, Any]] = []
    if date_col:
        filters.append(
            {
                "id": "date",
                "label": "Период",
                "column": date_col,
                "type": "date_range",
                "default": "relative:current_year",
            }
        )
    for col, _ in column_counter.most_common(8):
        if col == date_col:
            continue
        lazy = _is_lazy_column(col)
        filters.append(
            {
                "id": _filter_id(col, col),
                "label": _human_label(col),
                "column": col,
                "type": "multi_select",
                "values_from": {"distinct": col, "limit": 80 if lazy else 2000, "lazy": lazy},
            }
        )

    exports = [{"id": "raw", "label": "Все строки (CSV)", "mode": "raw"}, *exports_chart]
    exports.append(
        {
            "id": "bundle_tables",
            "label": "Таблицы дашборда (ZIP)",
            "mode": "bundle",
            "include": [e["id"] for e in exports],
        }
    )
    slug = manifest_id or _slug(title)
    manifest = {
        "id": slug,
        "title": title,
        "superset": {"dashboard_id": dashboard_id, "dashboard_title": title},
        "source": {"database": "clickhouse", "table": table, "columns": ["*"]},
        "column_labels": {c: _human_label(c) for c in column_counter},
        "defaults": {"where": []},
        "filters": filters,
        "exports": exports,
        "_meta": {"charts_found": len(charts), "table_exports": len(exports_chart)},
    }
    _write_manifest(manifest, out_path)
    return manifest


def _write_manifest(manifest: dict[str, Any], out_path: Path | None) -> None:
    if not out_path:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    to_write = {k: v for k, v in manifest.items() if k != "_meta"}
    out_path.write_text(
        yaml.safe_dump(to_write, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _target_column(targets: list[Any]) -> str | None:
    for t in targets:
        if not isinstance(t, dict):
            continue
        col = t.get("column")
        if isinstance(col, dict):
            name = col.get("name") or col.get("column_name")
            if name:
                return name
        elif isinstance(col, str) and col:
            return col
    return None


def _chart_params(chart: dict[str, Any]) -> dict[str, Any]:
    params = chart.get("params")
    if isinstance(params, str):
        try:
            return json.loads(params)
        except json.JSONDecodeError:
            return {}
    return params or {}


def _chart_to_export(
    chart: dict[str, Any],
    params: dict[str, Any],
    column_labels: dict[str, str],
) -> dict[str, Any]:
    cid = chart.get("id") or chart.get("slice_name") or "chart"
    # export zip charts often have no numeric id — use uuid/name
    raw_id = chart.get("uuid") or cid
    safe_id = "chart_" + _slug(str(raw_id))[:40]
    name = chart.get("slice_name") or safe_id

    group_by = params.get("groupby") or params.get("groupbyColumns") or []
    if params.get("groupbyRows"):
        group_by = list(group_by) + list(params["groupbyRows"])
    seen: set[str] = set()
    group_by_u: list[str] = []
    for c in group_by:
        if isinstance(c, str) and c not in seen:
            seen.add(c)
            group_by_u.append(c)

    metrics_out: list[dict[str, str]] = []
    for m in params.get("metrics") or []:
        if isinstance(m, str):
            label = column_labels.get(m, m)
            metrics_out.append({"label": label, "expr": f"sum(`{m}`)"})
        elif isinstance(m, dict):
            label = m.get("label") or "metric"
            if m.get("expressionType") == "SQL" and m.get("sqlExpression"):
                expr = m["sqlExpression"]
            elif m.get("aggregate") and isinstance(m.get("column"), dict):
                col = m["column"].get("column_name")
                expr = f"{m['aggregate']}(`{col}`)"
                if not m.get("hasCustomLabel") and col:
                    label = m.get("label") or column_labels.get(col, label)
            else:
                expr = "sum(`TODO`)"
            metrics_out.append({"label": label, "expr": expr})

    export: dict[str, Any] = {
        "id": safe_id,
        "label": name,
        "mode": "aggregate" if group_by_u and metrics_out else "raw",
    }
    if group_by_u and metrics_out:
        export["group_by"] = group_by_u
        export["metrics"] = metrics_out
        # Order by first metric desc when possible
        export["order_by"] = [f"`{metrics_out[0]['label']}` DESC"]
    return export


def _looks_like_date_column(col: str) -> bool:
    low = col.lower()
    return any(
        key in low
        for key in ("date", "time", "period", "_dt", "datetime", "day")
    ) and not any(key in low for key in ("update", "create", "expiry_status"))


def _looks_like_date_label(label: str) -> bool:
    low = (label or "").strip().lower()
    return low in {"дата", "период", "date", "period", "время"} or "период" in low or "дата" in low


def _is_lazy_column(col: str) -> bool:
    low = col.lower()
    return any(
        key in low
        for key in (
            "participant",
            "address",
            "inn",
            "tin",
            "gtin",
            "full_trade",
            "sender",
            "recipient",
            "name_of_",
        )
    )


def _filter_id(column: str, label: str) -> str:
    return _slug(column) or _slug(label) or "filter"


def _human_label(col: str) -> str:
    mapping = {
        "name": "Аптечная сеть",
        "owner": "Владелец АС",
        "the_subject_of_the_russian_federation": "Регион",
        "type_of_disposal": "Тип выбытия",
        "trade_name": "Торговое наименование",
        "full_trade_name": "Полное торговое наименование",
        "name_of_the_participant": "Юридическое лицо",
        "marketing_group": "Маркетинговая группа",
        "tin_of_the_participant": "ИНН",
        "name_ac": "Внутреннее наименование организации",
        "typa_participant": "Тип организации",
    }
    return mapping.get(col, col)


def _slug(title: str) -> str:
    tr = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    text = title.lower()
    out = []
    for ch in text:
        if ch in tr:
            out.append(tr[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "|", "/", "\\", ",", ".", "—", "–", "_"}:
            out.append("_")
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "dashboard"
