"""
1. Подключение к clickhouse на слое tmp -> создать временную таблицу там
2. Подключение к oracle-базе 
    -> вычитываю по заданным параметрам данные в таблицу в clickHouse 
    -> вычитываю из временной таблицы данные + добавляю необходимые поля (effective_dttm + deleted_flag)
    -> положить в целевую таблицу clickhouse на слой stg
    -> удалить временные таблицы
a
"""

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

#loger = LoggingMixin().log

def create_text_hash(row, columns):
    # Объединяем значения столбцов в строку
    combined = ''.join(str(row[col]) for col in columns)
    # Создаем хеш SHA256 и преобразуем в hex-строку
    return hashlib.sha256(combined.encode()).hexdigest()

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

# Декоратор DAG
"""
@dag(
    dag_id='altay_data_import',
    schedule_interval='@daily',
    start_date=days_ago(1),
    catchup=False,
    default_args={
        'owner': 'airflow',
        'retries': 1,
        'retry_delay': timedelta(minutes=5)
    },
    tags=['oracle', 'clickhouse', 'data_migration']
)
def altay_data_import_dag():
    
    @task
    """
def load_altay_data(execution_date: datetime = None):
    """Загрузка данных из V$ALTAY_DATA с фильтрацией по периоду"""
    if execution_date is None:
        execution_date = datetime.now()
        
    #start_date = (execution_date - timedelta(days=1))
    #end_date = execution_date
    start_date = execution_date - timedelta(days=63)
    print(start_date)
    params = {'start_date': start_date, 'end_date': execution_date}
    
    oracle_query = f"""SELECT * from DATA_MART."V$ALTAY_DATA" where rownum <= 5 """
    
    #where STAT_DATE between :start_date and :end_date
    #oracle_query = f'''SELECT count(*) from DATA_MART."V$ALTAY_DATA" '''

    ch_query = f"""select * from stg.mart_dcm_data where deleted_flag = 0"""

    try:
        with get_oracle_connection() as oracle_conn:
            df_oracle = pd.read_sql(oracle_query, oracle_conn)
            print(df_oracle)
            print(type(df_oracle))

            if not df_oracle.empty:
                ch_client = get_clickhouse_client()
                df_ch = ch_client.execute(ch_query)

                #ch_client.execute('INSERT INTO stg.mart_dcm_data VALUES', oracle_query.to_dict('records'))

                #df_ch = ch_client.execute(ch_query)
                #print(df_ch)

                #print(type(df_ch))
                hash_cols = ["SALES_TYPE_ID", "CD_REG", "CD_U", "STAT_YEAR", "STAT_MONTH"]
                print(111111)
                df_insert_del_rows = (df_oracle.merge(
                                                    df_ch, 
                                                    on=["cd_reg", "cd_u", "stat_year", "stat_month", "sales_type_id"], 
                                                    how="left"
                                                ) # left join
                                                .query("_merge == 'left_only'")  # удаляем not null-строки из второй таблицы
                                                .drop('_merge', axis=1)          # удаляем доп.столбец
                                                .assign(
                                                    effective_dttm=pd.Timestamp.now().normalize(), 
                                                    deleted_flag=1,
                                                    hash_diff=lambda df: df.apply(compute_row_hash, columns=hash_cols, axis=1)  # Хеш для выбранных столбцов
                                                )  # добавляем столбцы effective_dttm и deleted_flag
                                                )

                print(df_insert_del_rows)

                df_insert_add_rows = (ch_client.merge(
                                                    df_ch, 
                                                    on=["cd_reg", "cd_u", "stat_year", "stat_month", "sales_type_id"], 
                                                    how="right"
                                                ) # left join
                                                .query("_merge == 'right_only'")  # удаляем not null-строки из первой таблицы
                                                .drop('_merge', axis=1)          # удаляем доп.столбец
                                                .assign(
                                                    effective_dttm=pd.Timestamp.now().normalize(), 
                                                    deleted_flag=1,
                                                    hash_diff=lambda df: df.apply(compute_row_hash, columns=hash_cols, axis=1)  # Хеш для всех столбцов
                                                )  # добавляем столбцы effective_dttm и deleted_flag
                                                )

                # запись данных в таблицу:
                #ch_client.execute('INSERT INTO altay_data VALUES', df_insert_del_rows.to_dict('records'))
                #ch_client.execute('INSERT INTO altay_data VALUES', df_insert_add_rows.to_dict('records'))

                ch_client.disconnect()
                print(f"Успешно загружено {len(df_insert_del_rows) + len(df_insert_add_rows)} записей в altay_data")
            else:
                print("Нет новых данных для загрузки в altay_data")
            
    except Exception as e:
        print(f"Ошибка при загрузке altay_data: {str(e)}")
        raise

load_altay_data()


