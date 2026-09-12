from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Paths are relative to export_service/ unless absolute.
    manifests_dir: str = "manifests"
    export_dir: str = "data/exports"

    superset_url: str = "http://192.168.14.226:8088"
    superset_username: str = "admin"
    superset_password: str = "admin"

    clickhouse_host: str = "clickhouse01"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "bdm"

    csv_delimiter: str = ";"
    dry_run: bool = False

    @property
    def root_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def manifests_path(self) -> Path:
        p = Path(self.manifests_dir)
        return p if p.is_absolute() else self.root_dir / p

    @property
    def exports_path(self) -> Path:
        p = Path(self.export_dir)
        return p if p.is_absolute() else self.root_dir / p


settings = Settings()
