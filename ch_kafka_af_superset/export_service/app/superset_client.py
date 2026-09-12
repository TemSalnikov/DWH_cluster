from __future__ import annotations

import io
import zipfile
from typing import Any

import httpx
import yaml

from .config import settings


class SupersetClient:
    """Minimal read-only Superset API client for manifest sync."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.superset_url).rstrip("/")
        self.username = username or settings.superset_username
        self.password = password or settings.superset_password
        self._token: str | None = None

    def login(self) -> None:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base_url}/api/v1/security/login",
                json={
                    "username": self.username,
                    "password": self.password,
                    "provider": "db",
                    "refresh": True,
                },
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self.login()
        assert self._token
        return {"Authorization": f"Bearer {self._token}"}

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    def get_bytes(self, path: str, params: dict[str, Any] | None = None) -> bytes:
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            return resp.content

    def export_dashboard_bundle(self, dashboard_id: int) -> dict[str, Any]:
        """
        Download dashboard export ZIP and parse dashboard/datasets/charts YAML.
        Endpoint works with JWT even when GET /dashboard/{id} returns 404.
        """
        raw = self.get_bytes(
            "/api/v1/dashboard/export/",
            params={"q": f"!({dashboard_id})"},
        )
        dashboards: list[dict[str, Any]] = []
        datasets: list[dict[str, Any]] = []
        charts: list[dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                if not name.endswith((".yaml", ".yml")):
                    continue
                data = yaml.safe_load(zf.read(name)) or {}
                low = name.lower()
                if "/dashboards/" in low:
                    dashboards.append(data)
                elif "/datasets/" in low:
                    datasets.append(data)
                elif "/charts/" in low:
                    charts.append(data)
        if not dashboards:
            raise RuntimeError(f"В export ZIP нет дашборда id={dashboard_id}")
        return {
            "dashboard": dashboards[0],
            "datasets": datasets,
            "charts": charts,
        }

    def list_charts_for_dashboard(self, dashboard_id: int) -> list[dict[str, Any]]:
        """Dashboard list/detail may 404 for JWT; recover via chart.dashboards."""
        by_id: dict[int, dict[str, Any]] = {}
        page = 0
        while page <= 50:
            q = f"(page:{page},page_size:100)"
            data = self.get("/api/v1/chart/", params={"q": q})
            batch = data.get("result") or []
            if not batch:
                break
            for chart in batch:
                for dash in chart.get("dashboards") or []:
                    if dash.get("id") == dashboard_id:
                        by_id[chart["id"]] = chart
                        break
            if len(batch) < 100:
                break
            page += 1
        return list(by_id.values())
