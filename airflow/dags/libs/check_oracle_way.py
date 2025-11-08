
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
    x=[]
    x.append(1)
    x.append('123')
    print('vdebvnn')
    print('enrkgfneknv')
    return Client(
        host=CLICKHOUSE_CONN['host'],
        port=CLICKHOUSE_CONN['port'],
        user=CLICKHOUSE_CONN['user'],
        password=CLICKHOUSE_CONN['password'],
        database=CLICKHOUSE_CONN['database']
    )

message = 'Нет новых данных для загрузки в mart_dcm_reg'

oracle_query = f"""SELECT distinct * from DATA_MART."V$ALTAY_REG" where rownum <= 100"""

try:
    with get_oracle_connection() as oracle_conn:
        df_oracle = pd.read_sql(oracle_query, oracle_conn)
        
        # 1. Проверка наличия данных в БД Oracle
        if df_oracle.empty:
            print(message)

        else:
            # 2. Проверка наличия новых данных в БД Oracle
            # преобразования наименований столбцов, т.к. в Oracle указаны в верхнем регистре, в ClickHouse - в нижнем
            df_oracle.columns = [col.lower() for col in df_oracle.columns]

            ch_client = get_clickhouse_client()
            df_click = pd.DataFrame(ch_client.execute(f"""select cd_reg, sales_type_id from mart_dcm_reg"""), columns=['cd_reg', 'sales_type_id'])

            # выбор строк в Oracle, кот. отсутствую в ClickHouse
            existing_rows_ch = set(zip(df_click['cd_reg'], df_click['sales_type_id']))
            diff_rows = df_oracle.apply(lambda row: (row['cd_reg'], row['sales_type_id']) not in existing_rows_ch, axis=1)
            df_insert_del_rows = df_oracle.loc[diff_rows]

            if len(df_insert_del_rows) < 0:
                print(message)

            else:
                # 3. Вставка данных в clickhouse 
                ch_table_structure = ch_client.execute('DESCRIBE TABLE mart_dcm_reg')
                ch_columns = [row[0] for row in ch_table_structure]
                
                hash_cols = ['cd_reg', 'sales_type_id']

                df_for_insert = df_insert_del_rows.assign(
                                                    effective_dttm=pd.Timestamp.now().normalize(), 
                                                    deleted_flag=0,
                                                    hash_diff=lambda df: df.apply(compute_row_hash, columns=hash_cols, axis=1)  # Хеш для выбранных столбцов
                                                )  # добавляем столбцы effective_dttm и deleted_flag

                ch_client.insert_dataframe('INSERT INTO mart_dcm_reg VALUES', df_for_insert, settings=dict(use_numpy=True))
                
                ch_client.disconnect()
                print(f"Успешно загружено {len(df_for_insert)} записей в mart_dcm_reg")
        
except Exception as e:
    print(f"Ошибка при загрузке mart_dcm_reg: {str(e)}")
    raise

if __name__ == "__main__":
    get_clickhouse_client()

