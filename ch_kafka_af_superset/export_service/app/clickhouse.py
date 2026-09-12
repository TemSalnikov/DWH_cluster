from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from .config import settings


class ClickHouseExporter:
    """Streams SELECT result to CSV. In dry_run mode only returns SQL preview."""

    def __init__(self) -> None:
        self.dry_run = settings.dry_run

    def _client(self):
        import clickhouse_connect

        return clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password or None,
            database=settings.clickhouse_database,
        )

    def stream_csv(self, sql: str, dest: Path) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            dest.write_text(
                f"# DRY_RUN\n# SQL:\n{sql}\n",
                encoding="utf-8",
            )
            return 0

        client = self._client()
        # FORMAT via query settings: fetch in batches and write CSV ourselves
        result = client.query(sql)
        delim = settings.csv_delimiter
        rows_written = 0
        with dest.open("w", encoding="utf-8", newline="") as fh:
            fh.write(delim.join(result.column_names) + "\n")
            for row in result.result_rows:
                fh.write(delim.join(_csv_cell(v) for v in row) + "\n")
                rows_written += 1
        return rows_written

    def distinct_values(
        self,
        table: str,
        column: str,
        where: str | None = None,
        limit: int = 2000,
        search: str | None = None,
    ) -> list[str]:
        if self.dry_run:
            return [f"(dry-run) sample for {column}"]
        where_sql = where or "1"
        search_sql = "1"
        if search and search.strip():
            # Escape for LIKE: \, %, _
            q = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
                .replace("'", "\\'")
            )
            search_sql = (
                f"positionCaseInsensitiveUTF8("
                f"trim(BOTH ' \\t\\r\\n' FROM toString(`{column}`)), '{q}') > 0"
            )
        # Drop null/blank/placeholder junk that often leaks into dimension lists
        sql = (
            f"SELECT DISTINCT trim(BOTH ' \\t\\r\\n' FROM toString(`{column}`)) AS v "
            f"FROM {table} "
            f"WHERE ({where_sql}) "
            f"AND `{column}` IS NOT NULL "
            f"AND trim(BOTH ' \\t\\r\\n' FROM toString(`{column}`)) NOT IN "
            f"('', 'nan', 'None', 'null', 'NULL') "
            f"AND ({search_sql}) "
            f"ORDER BY v LIMIT {int(limit)}"
        )
        client = self._client()
        result = client.query(sql)
        return [str(r[0]) for r in result.result_rows]

    def query_rows(self, sql: str, limit: int = 100) -> dict:
        """Run SQL capped by limit; return column names + row dicts for UI preview."""
        capped = f"SELECT * FROM (\n{sql}\n) AS _preview\nLIMIT {int(limit)}"
        if self.dry_run:
            return {
                "columns": ["dry_run"],
                "rows": [{"dry_run": "Включён DRY_RUN — данные не читаются из ClickHouse"}],
                "sql": capped,
                "row_count": 1,
                "truncated": True,
            }
        client = self._client()
        result = client.query(capped)
        columns = list(result.column_names)
        rows = []
        for raw in result.result_rows:
            item = {}
            for name, value in zip(columns, raw):
                if value is None:
                    item[name] = None
                elif hasattr(value, "isoformat"):
                    item[name] = value.isoformat()
                else:
                    item[name] = value
            rows.append(item)
        return {
            "columns": columns,
            "rows": rows,
            "sql": capped,
            "row_count": len(rows),
            "truncated": len(rows) >= limit,
        }


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if any(ch in text for ch in (settings.csv_delimiter, '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def iter_placeholder() -> Iterator[str]:
    yield from ()
