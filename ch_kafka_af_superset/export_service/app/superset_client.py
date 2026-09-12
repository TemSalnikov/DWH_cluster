from __future__ import annotations

from typing import Any

import httpx

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
