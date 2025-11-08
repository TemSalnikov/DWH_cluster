
import sys
venv_path = "/home/userdwh/dwh_cluster/docker_cluster/.venv/lib/python3.12/site-packages"
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

import pandas as pd
import numpy as np

print('hello')

from datetime import datetime, timedelta
#from airflow.utils.log.logging_mixin import LoggingMixin
#import cx_Oracle
import pandas as pd
from clickhouse_driver import Client

from typing import Dict, List, Any
import oracledb
import hashlib

def compute_row_hash(row, columns=None):
    if columns:
        row = row[columns]
    # Преобразуем все значения строки в строки и объединяем их
    row_string = ''.join(str(value) for value in row)
    # Создаем хеш используя SHA-256
    return hashlib.sha256(row_string.encode()).hexdigest()


# Конфигурация подключений
ORACLE_CONN = {
    'user': 'ALTAYV',
    'password': 'sSwM913_xoAY', 
    'host': 'dsmviewer.ru',
    'port': 27091,
    'sid': 'webiasdb2'
}

CLICKHOUSE_CONN: dict[str, str | int] = {
    'host': '192.168.14.235',
    'port': 9001,
    'user': 'admin',
    'password': 'admin',
    'database': 'stg'
}

# Функции подключения к БД
def get_oracle_connection():
    dsn = f"{ORACLE_CONN['host']}:{ORACLE_CONN['port']}/{ORACLE_CONN['sid']}"
    return oracledb.connect(
        user=ORACLE_CONN['user'],
        password=ORACLE_CONN['password'],
        dsn=dsn
    )

def get_clickhouse_client() -> Client:
    """Создает и возвращает клиент ClickHouse"""
    return Client(
        host=CLICKHOUSE_CONN['host'],
        port=CLICKHOUSE_CONN['port'],
        user=CLICKHOUSE_CONN['user'],
        password=CLICKHOUSE_CONN['password'],
        database=CLICKHOUSE_CONN['database']
    )