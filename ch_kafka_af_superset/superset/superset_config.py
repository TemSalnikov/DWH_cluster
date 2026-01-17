import os
# Настройки пула для ClickHouse
from sqlalchemy.pool import QueuePool

SECRET_KEY = 'thisISaSECRET_1234'
MAPBOX_API_KEY = os.getenv('MAPBOX_API_KEY', '')
CACHE_CONFIG = {
    'CACHE_TYPE': 'redis',
    'CACHE_DEFAULT_TIMEOUT': 0,
    # 'CACHE_DEFAULT_TIMEOUT': 300,
    'CACHE_KEY_PREFIX': 'superset_',
    'CACHE_REDIS_HOST': 'redis',
    'CACHE_REDIS_PORT': 6379,
    'CACHE_REDIS_DB': 1,
    'CACHE_REDIS_URL': 'redis://redis:6379/1'}

SQLALCHEMY_DATABASE_URI = \
    'postgresql+psycopg2://superset:superset@postgres:5432/superset'
SQLALCHEMY_TRACK_MODIFICATIONS = True
# Увеличьте время ожидания соединения
SUPERSET_WEBSERVER_TIMEOUT = 300

# GLOBAL_ASYNC_QUERIES_JWT_SECRET = "YOUR_STRONG_32_BYTE_SECRET_KEY"

FEATURE_FLAGS = {
    "GENERIC_CHART_AXES": True,
    # "GLOBAL_ASYNC_QUERIES": True,
    # "ASYNC_EXPORT": True,
    
}

# Добавление русского языка в список доступных языков
LANGUAGES = {
    "ru": {"flag": "ru", "name": "Русский"},
    "en": {"flag": "us", "name": "English"}    
}

# Установка русского языка в качестве языка по умолчанию
BABEL_DEFAULT_LOCALE = "ru"

# Конфигурация базы данных
DATAABASE_POOL_SIZE = 10
DATABASE_POOL_RECYCLE = 3600
DATABASE_ENGINE_POOL_TIMEOUT = 300
DATABASE_ENGINE_POOL_RECYCLE = 3600

