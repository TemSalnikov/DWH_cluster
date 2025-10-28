from datetime import datetime, timedelta
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow import DAG
from airflow.decorators import dag, task
from airflow.utils.dates import days_ago
from airflow.models import Param
#import cx_Oracle
from clickhouse_driver import Client
import pandas as pd
from typing import Dict, List, Any
import oracledb
import hashlib
from airflow.utils.log.logging_mixin import LoggingMixin

loger = LoggingMixin().log

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

default_args = {
    'owner': 'airflow',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
}

@dag(
    dag_id='extract_dsm',
    schedule_interval='0 9 6 * *', # в 9 утра каждого месяца 6 числа
    start_date=days_ago(1),
    default_args=default_args,
    catchup=False,
    params={
        'dates_from': Param(
            (datetime.now() - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d"),
            type='string',
            description='Дата начала отчетного периода в формате YYYY-MM-01. Указывать тот месяц, за который требуется отчет. Если требуется прогрузка за 1 месяц, поле "dates_to" оставить пустым.'
        ),
        'dates_to': Param(
            '-',
            type='string',
            description='Дата окончания отчетного периода в формате YYYY-MM-01.'
        )
    },
    tags=['oracle', 'clickhouse', 'data_migration']
)
def extract_dsm():
    
    @task
    def load_altay_data(**kwargs):
        """Загрузка данных из V$ALTAY_DATA"""

        message = 'Нет новых данных для загрузки в mart_dsm_sale'

        # Получаем параметр даты из контекста
        dag_run = kwargs.get('dag_run')
        if dag_run and dag_run.conf:
            report_date_from = dag_run.conf.get('dates_from')
            report_date_to = dag_run.conf.get('dates_to')

            print('dates_from:', report_date_from, '\ndates_to:', report_date_to)

        if report_date_to == '-':
            oracle_query = f"""SELECT * from DATA_MART."V$ALTAY_DATA" where to_char(effective_dttm, 'yyyy-mm-dd') = :report_date_from """ 
            params = {'report_date_from': report_date_from}
        else:
            oracle_query = f"""SELECT * from DATA_MART."V$ALTAY_DATA" where to_char(effective_dttm, 'yyyy-mm-dd') between :report_date_from and :report_date_to""" 
            params = {'report_date_from': report_date_from, 'report_date_to': report_date_to}

        try:
            with get_oracle_connection() as oracle_conn:
                df_oracle = pd.read_sql(oracle_query, oracle_conn, params=params)

                # 1. Проверка наличия данных в БД Oracle
                if df_oracle.empty:
                    print(message)

                else:
                    df_for_insert.columns = [col.lower() for col in df_for_insert.columns]
                    
                    #hash_cols = ["SALES_TYPE_ID", "CD_REG", "CD_U", "STAT_YEAR", "STAT_MONTH"]

                    df_for_insert = df_oracle.assign(
                                                        processed_dttm=pd.Timestamp.now().normalize(), 
                                                        deleted_flag=0
                                                        #hash_diff=lambda df: df.apply(compute_row_hash, columns=hash_cols, axis=1)  # Хеш для выбранных столбцов
                                                    )  # добавляем столбцы processed_dttm и deleted_flag
                    
                    # 2. Вставка данных в clickhouse 
                    ch_client = get_clickhouse_client()
                    ch_client.execute('INSERT INTO mart_dsm_sale VALUES', df_for_insert.to_dict('records'))
                    ch_client.disconnect()

                    if report_date_to == '-':
                        print(f"Успешно загружено {len(df_for_insert)} записей в mart_dsm_stat_product за период {report_date_from}")
                    else:
                        print(f"Успешно загружено {len(df_for_insert)} записей в mart_dsm_stat_product за период с {report_date_from} по {report_date_to}")
                
        except Exception as e:
            print(f"Ошибка при загрузке mart_dsm_sale: {str(e)}")
            raise

    @task
    def load_altay_dict():
        """Загрузка новых данных из V$ALTAY_DICT """

        message = 'Нет новых данных для загрузки в mart_dsm_stat_product'

        oracle_query = f"""SELECT distinct * from DATA_MART."V$ALTAY_DICT" """

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
                    df_click = pd.DataFrame(ch_client.execute(f"""select cd_u from mart_dsm_stat_product"""), columns=['cd_u'])

                    # выбор строк в Oracle, кот. отсутствую в ClickHouse
                    diff_rows = ~df_oracle['cd_u'].isin(df_click['cd_u'])
                    df_insert_del_rows = df_oracle.loc[diff_rows]

                    if len(df_insert_del_rows) == 0:
                        print(message)

                    else:
                        # 3. Вставка данных в clickhouse 
                        ch_table_structure = ch_client.execute('DESCRIBE TABLE mart_dsm_stat_product')
                        ch_columns = [row[0] for row in ch_table_structure]
                        
                        #hash_cols = ["cd_u"]

                        df_for_insert = df_insert_del_rows.assign(
                                                            processed_dttm=pd.Timestamp.now().normalize(), 
                                                            deleted_flag=0
                                                            #hash_diff=lambda df: df.apply(compute_row_hash, columns=hash_cols, axis=1)  # Хеш для выбранных столбцов
                                                        )  # добавляем столбцы processed_dttm и deleted_flag

                        ch_client.insert_dataframe('INSERT INTO mart_dsm_stat_product VALUES', df_for_insert, settings=dict(use_numpy=True))
                        
                        ch_client.disconnect()
                        print(f"Успешно загружено {len(df_for_insert)} записей в mart_dsm_stat_product")
                
        except Exception as e:
            print(f"Ошибка при загрузке mart_dsm_stat_product: {str(e)}")
            raise
    
    @task
    def load_altay_reg():
        """Загрузка новых данных из V$ALTAY_REG """

        message = 'Нет новых данных для загрузки в mart_dsm_region'

        oracle_query = f"""SELECT distinct * from DATA_MART."V$ALTAY_REG" """

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
                    df_click = pd.DataFrame(ch_client.execute(f"""select cd_reg, sales_type_id from mart_dsm_region"""), columns=['cd_reg', 'sales_type_id'])

                    # выбор строк в Oracle, кот. отсутствую в ClickHouse
                    existing_rows_ch = set(zip(df_click['cd_reg'], df_click['sales_type_id']))
                    diff_rows = df_oracle.apply(lambda row: (row['cd_reg'], row['sales_type_id']) not in existing_rows_ch, axis=1)
                    df_insert_del_rows = df_oracle.loc[diff_rows]

                    if len(df_insert_del_rows) == 0:
                        print(message)

                    else:
                        # 3. Вставка данных в clickhouse 
                        ch_table_structure = ch_client.execute('DESCRIBE TABLE mart_dsm_region')
                        ch_columns = [row[0] for row in ch_table_structure]
                        
                        #hash_cols = ['cd_reg', 'sales_type_id']

                        df_for_insert = df_insert_del_rows.assign(
                                                            processed_dttm=pd.Timestamp.now().normalize(), 
                                                            deleted_flag=0
                                                            #hash_diff=lambda df: df.apply(compute_row_hash, columns=hash_cols, axis=1)  # Хеш для выбранных столбцов
                                                        )  # добавляем столбцы processed_dttm и deleted_flag

                        ch_client.insert_dataframe('INSERT INTO mart_dsm_region VALUES', df_for_insert, settings=dict(use_numpy=True))
                        
                        ch_client.disconnect()
                        print(f"Успешно загружено {len(df_for_insert)} записей в mart_dsm_region")
                
        except Exception as e:
            print(f"Ошибка при загрузке mart_dsm_region: {str(e)}")
            raise


    load_altay_data()
    load_altay_dict()
    load_altay_reg()

extract_dsm()
