from __future__ import annotations

from pathlib import Path

import yaml

from .models import DashboardManifest


class ManifestRegistry:
    """Loads dashboard manifests from YAML files. Hot-reload on each list/get."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _iter_files(self) -> list[Path]:
        if not self.directory.exists():
            return []
        return sorted(self.directory.glob("*.yaml")) + sorted(self.directory.glob("*.yml"))

    def all(self) -> list[DashboardManifest]:
        items: list[DashboardManifest] = []
        for path in self._iter_files():
            items.append(self._load(path))
        return items

    def get(self, dashboard_id: str) -> DashboardManifest:
        for path in self._iter_files():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if data.get("id") == dashboard_id:
                return DashboardManifest.model_validate(data)
        raise KeyError(f"manifest '{dashboard_id}' not found in {self.directory}")

    def _load(self, path: Path) -> DashboardManifest:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return DashboardManifest.model_validate(data)
