from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    airflow_api_url: str = "http://airflow-webserver:8080/api/v1"
    airflow_username: str = "airflow"
    airflow_password: str = "airflow"
    timezone: str = "Europe/Moscow"
    page_limit: int = 100


settings = Settings()
