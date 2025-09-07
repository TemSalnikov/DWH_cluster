from datetime import datetime, timedelta
#from airflow.utils.log.logging_mixin import LoggingMixin
#from airflow import DAG
#from airflow.decorators import dag, task
#from airflow.utils.dates import days_ago
import cx_Oracle
from clickhouse_driver import Client
import pandas as pd
from typing import Dict, List, Any
import oracledb

CLICKHOUSE_CONN: dict[str, str | int] = {
    'host': '192.168.14.235',
    'port': 9001,
    'user': 'admin',
    'password': 'admin',
    'database': 'stg'
}

def get_clickhouse_client() -> Client:
    """Создает и возвращает клиент ClickHouse"""
    return Client(
        host=CLICKHOUSE_CONN['host'],
        port=CLICKHOUSE_CONN['port'],
        user=CLICKHOUSE_CONN['user'],
        password=CLICKHOUSE_CONN['password'],
        database=CLICKHOUSE_CONN['database']
    )

ch_query = f"""select count(*) from stg.mart_dcm_data"""

ch_client = get_clickhouse_client()
df_ch = ch_client.execute(ch_query)

print(df_ch)
