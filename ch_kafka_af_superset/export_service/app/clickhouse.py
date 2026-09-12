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
    ) -> list[str]:
        if self.dry_run:
            return [f"(dry-run) sample for {column}"]
        where_sql = where or "1"
        sql = (
            f"SELECT DISTINCT `{column}` AS v FROM {table} "
            f"WHERE {where_sql} AND `{column}` IS NOT NULL "
            f"ORDER BY v LIMIT {int(limit)}"
        )
        client = self._client()
        result = client.query(sql)
        return [str(r[0]) for r in result.result_rows]


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if any(ch in text for ch in (settings.csv_delimiter, '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def iter_placeholder() -> Iterator[str]:
    yield from ()
