from datetime import datetime, timedelta
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.decorators import dag, task
from airflow.utils.dates import days_ago
from clickhouse_driver import Client
import pandas as pd
import oracledb
import hashlib

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

# Настройка логирования
logger = LoggingMixin().log

def compute_row_hash(row, columns=None):
    """Создает хеш строки"""
    if columns:
        row = row[columns]
    # Преобразуем все значения строки в строки и объединяем их
    row_string = ''.join(str(value) for value in row)
    # Создаем хеш используя SHA-256
    return hashlib.sha256(row_string.encode()).hexdigest()

@dag(
    dag_id='wf_dsm_mart_dsm_sale_product',
    schedule_interval='0 9 6 * *', # в 9 утра каждого месяца 6 числа
    start_date=days_ago(1),
    #default_args=default_args,
    catchup=False,
    tags=['oracle', 'clickhouse', 'data_migration']
)
def wf_dsm_mart_dsm_sale_product():
    
    src_table_name = 'DATA_MART."V$ALTAY_DICT"' #название таблицы-источника
    tgt_table_name = 'mart_dsm_stat_product' #название целевой таблицы
    pk_list = ['cd_u'] #список полей PK источника
    tmp_table_name = f"tmp.tmp_{tgt_table_name}" # Название для временной таблицы

    @task.short_circuit # декоратор для условного выполнения
    def check_new_data_altay_dict(*args, **kwargs):
        """Проверка наличия новых данных из V$ALTAY_DICT """
        
        message = f'Нет новых данных для загрузки в {tgt_table_name}'

        oracle_query = f"""SELECT distinct * from {src_table_name}"""

        try:
            with get_oracle_connection() as oracle_conn:
                df_oracle = pd.read_sql(oracle_query, oracle_conn)
                
                # 1. Проверка наличия данных в БД Oracle
                if df_oracle.empty:
                    logger.info(message)

                else:
                    # 2. Дельта новых данных в БД Oracle
                    # 2.1. Преобразование наименований столбцов, т.к. в Oracle указаны в верхнем регистре, в ClickHouse - в нижнем
                    df_oracle.columns = [col.lower() for col in df_oracle.columns]

                    ch_client = get_clickhouse_client()
                    df_click = pd.DataFrame(ch_client.execute(f"""select cd_u from {tgt_table_name}"""), columns=pk_list) # прове
                    

                    # 3. Выбор строк в Oracle, кот. отсутствуют в ClickHouse
                    diff_rows = ~df_oracle['cd_u'].isin(df_click['cd_u'])
                    
                    # 4. Данных нет
                    if sum(diff_rows) == 0:
                        logger.info(message)
                        return False

                    else:
                        # 5. Данные есть, создание временной таблицы
                        hash_cols = [row for row in df_oracle.columns.tolist() if row not in pk_list]

                        df_insert_del_rows = df_oracle.loc[diff_rows]
                        df_for_insert = df_insert_del_rows.assign(
                                                        processed_dttm=pd.Timestamp.now().normalize(), 
                                                        deleted_flag=0,
                                                        hash_diff=lambda df: df.apply(compute_row_hash, columns=hash_cols, axis=1)  # Хеш для выбранных столбцов
                                                    )

                        # 5.1. Создание временной таблицы по новым данным из Oracle
                        create_tbl_query = f"""
                            CREATE TABLE IF NOT EXISTS {tmp_table_name} (
                                nm_atc5 String,
                                original String,
                                brended String,
                                recipereq String,
                                jnvlp String,
                                ephmra1 String,
                                nm_ephmra1 String,
                                ephmra2 String,
                                nm_ephmra2 String,
                                ephmra3 String,
                                nm_ephmra3 String,
                                ephmra4 String,
                                nm_ephmra4 String,
                                nm_ti String,
                                farm_group String,
                                localized_status String,
                                nm_f String,
                                bad1 String,
                                nm_bad1 String,
                                bad2 String,
                                nm_bad2 String,
                                kk1_1 String,
                                kk1_name_am String,
                                kk2 String,
                                kk2_name_vozr String,
                                kk3_1 String,
                                kk3_name_deistv String,
                                kk4_1 String,
                                kk4_name_pokaz String,
                                nm_dt String,
                                cd_u Int64,
                                cd_ias Int64,
                                nm_full String,
                                nm_t String,
                                nm_br String,
                                nm_pack String,
                                group_nm_rus String,
                                corp String,
                                nm_d String,
                                mv Float64,
                                mv_nm_mu String,
                                count_in_bl Int64,
                                count_bl Int64,
                                nm_c String,
                                atc1 String,
                                nm_atc1 String,
                                atc2 String,
                                nm_atc2 String,
                                atc3 String,
                                nm_atc3 String,
                                atc4 String,
                                nm_atc4 String,
                                atc5 String,
                                processed_dttm DateTime,
                                deleted_flag Boolean,
                                hash_diff Text 
                            )
                            ENGINE = MergeTree()
                            order by (cd_u)
                        """               
                        ch_client.execute(create_tbl_query)

                        # 5.2. Вставка дельты
                        ch_client.insert_dataframe(f"INSERT INTO {tmp_table_name} VALUES", df_for_insert, settings=dict(use_numpy=True))
                        
                        logger.info(f"Найдено {sum(diff_rows)} новых записей в {tmp_table_name}")
                        return True

        except Exception as e:
            logger.error(f"Ошибка при проверке новых данных в {src_table_name}: {str(e)}")
            raise
        finally:
            ch_client.disconnect()

    @task
    def load_altay_dict(*args, **kwargs):
        f"""Загрузка новых данных из временной таблицы {tmp_table_name}"""

        try:
            ch_client = get_clickhouse_client()
            ch_client.execute(f'INSERT INTO {tgt_table_name} select * from {tmp_table_name}')

            # 6. Проверка прогрузки всех данных
            df_tmp = pd.DataFrame(ch_client.execute(f"""select cd_u from {tmp_table_name}"""), columns=pk_list)
            df_fact = pd.DataFrame(ch_client.execute(f"""select cd_u from {tgt_table_name} where processed_dttm = today()"""), columns=pk_list)

            diff_rows = ~df_tmp['cd_u'].isin(df_fact['cd_u'])

            if sum(diff_rows) == 0:
                logger.info(f"Успешно загружены все записи. {len(df_tmp)} записей в {tgt_table_name}.")
                return
            else:
                class NotAllDatasLoad(Exception):
                    pass
                raise NotAllDatasLoad
        except NotAllDatasLoad as n:
            ch_client.execute(f"drop table {tmp_table_name}")
            logger.error(f"Не все данные прогружены из {tmp_table_name} в {tgt_table_name}. Прогружено {len(df_tmp)-sum(diff_rows)} из {len(df_tmp)}.")
        except Exception as e:
            ch_client.execute(f"drop table {tmp_table_name}")
            logger.error(f"Ошибка при загрузке {tgt_table_name}: {str(e)}")
        finally:
            ch_client.disconnect()
    
    # 7. Удаление временной таблицы
    @task
    def clean_up_temp_altay_dict(*args, **kwargs):
        """Удаление временной таблицы """
        ch_client = get_clickhouse_client()
        ch_client.execute(f"drop table {tmp_table_name}")
        logger.info(f"Временная таблица {tmp_table_name} удалена.")
        ch_client.disconnect()

    # Определяем зависимости между задачами
    check_result = check_new_data_altay_dict()
    load_task = load_altay_dict()
    clean_task = clean_up_temp_altay_dict()

    # Последовательное выполнение: проверка -> загрузка -> очистка
    check_result >> load_task >> clean_task

# Инициализация DAG
wf_dsm_mart_dsm_sale_product()