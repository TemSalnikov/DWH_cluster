import uuid
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.decorators import task
from typing import Dict, List
from clickhouse_driver import Client
from clickhouse_driver.errors import Error as ClickhouseError

logger = LoggingMixin().log

CLICKHOUSE_CONN: dict[str, str | int] = {
    'host': '192.168.14.235',
    'port': 9001,
    'user': 'admin',
    'password': 'admin'
}

def get_clickhouse_client():
    """Создание клиента ClickHouse"""
    try:
        return Client(
                host=CLICKHOUSE_CONN['host'],
                port=CLICKHOUSE_CONN['port'],
                user=CLICKHOUSE_CONN['user'],
                password=CLICKHOUSE_CONN['password']
            )
    except ClickhouseError as e:
        logger.error(f"Ошибка подключения к ClickHouse: {e}")
        raise
@task
def convert_hist_p2i(tmp_table: str, pk_list: list) -> str:
    client = None
    tmp_table_name = f"tmp.tmp_p2i_{uuid.uuid4().hex}"
    if tmp_table:
        try:
            logger = LoggingMixin().log
            client = get_clickhouse_client()
            logger.info(f"Подклчение к clickhouse успешно выполнено")
            tbl=f'stg.mart_data_dsm'

            query = f"""
            CREATE TABLE {tmp_table_name} AS
            SELECT DISTINCT 
                t.*,
                effective_dttm as effective_from_dttm,
                LEAD(effective_dttm, 1, '2999-12-31 23:59:59') OVER(PARTITION BY {', '.join(pk_list)} ORDER BY effective_dttm) as effective_to_dttm
            FROM {tmp_table} t
            """
            logger.info(f"Создан запрос: {query}")

            client.execute(query)
            logger.info(f"Создана временная таблица {tmp_table_name}")
                
            return tmp_table_name
        except ClickhouseError as e:
                logger.error(f"Ошибка при получении данных из {tmp_table}: {e}")
                raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")
    else:
         return ''
@task
def load_delta(src_table: str, tgt_table:str, pk_list: list, bk_list:list):
    ### tgt_table - указывается аксессор получения актуального среза на чистую версию dds-таблицы
    
    client = None
    tmp_tables = []
    try:
        logger = LoggingMixin().log
        client = get_clickhouse_client()
        logger.info(f"Подклчение к clickhouse успешно выполнено")
        
        logger.info(f"Создания Hash бизнесс данных таблицы источника")
        tmp_hash_tbl = f"tmp.tmp_hash_{uuid.uuid4().hex}"
        query = f"""
            CREATE TABLE {tmp_hash_tbl} AS
            SELECT  
               *,
               sha256(concat({bk_list})) as hash_diff
            FROM {src_table} t
            """
        logger.info(f"Создан запрос: {query}")
        client.execute(query)
        logger.info(f"Запрос успешно выполнен")
        tmp_tables.append(tmp_hash_tbl)
        
        logger.info(f"Получение данных из DDS таблицы")
        tmp_tgt_tbl = f"tmp.tmp_tgt_{uuid.uuid4().hex}"
        query = f"""
            CREATE TABLE {tmp_tgt_tbl} AS
            SELECT  
               t.{pk_list},
               t.{bk_list},
               t.effective_from_dttm,
               t.effective_to_dttm,
               t.src,
               t.hash_diff
            FROM {tgt_table} t
            JOIN {tmp_hash_tbl} h
            USING({pk_list})
            """
        logger.info(f"Создан запрос: {query}")
        client.execute(query)
        logger.info(f"Запрос успешно выполнен")
        tmp_tables.append(tmp_tgt_tbl)

        logger.info(f"Объединение таблиц src и dds")
        tmp_union_tbl = f"tmp.tmp_union_{uuid.uuid4().hex}"
        query = f"""
            CREATE TABLE {tmp_union_tbl} AS
            SELECT * 
            FROM ( 
            SELECT  
               {pk_list},
               {bk_list},
               effective_from_dttm,
               effective_to_dttm,
               src,
               hash_diff,
               'src' as tbl
            FROM {tmp_hash_tbl}
            UNION
            SELECT  
               {pk_list},
               {bk_list},
               effective_from_dttm,
               effective_to_dttm,
               src,
               hash_diff,
               'tgt' as tbl
            FROM {tmp_tgt_tbl} )
            """
        logger.info(f"Создан запрос: {query}")
        client.execute(query)
        logger.info(f"Запрос успешно выполнен")
        tmp_tables.append(tmp_union_tbl)
        
        logger.info(f"Merge history")
        tmp_mrg_hist_tbl = f"tmp.tmp_mrg_hist_{uuid.uuid4().hex}"
        query = f"""
            CREATE TABLE {tmp_mrg_hist_tbl} AS
            SELECT  
               {pk_list},
               {bk_list},
               effective_from_dttm,
               effective_to_dttm,
               LEAD(effective_from_dttm, 1, '2999-12-31 23:59:59') OVER(PARTITION BY {', '.join(pk_list)} ORDER BY effective_from_dttm ASC, effective_to_dttm DESC) as new_effective_to_dttm,
               src,
               hash_diff,
               tbl
            FROM {tmp_union_tbl} 
            """
        logger.info(f"Создан запрос: {query}")
        client.execute(query)
        logger.info(f"Запрос успешно выполнен")
        tmp_tables.append(tmp_mrg_hist_tbl)

        logger.info(f"Формирование deleted_flg")
        tmp_dlt_tbl = f"tmp.tmp_dlt_{uuid.uuid4().hex}"
        query = f"""
            CREATE TABLE {tmp_dlt_tbl} AS
            SELECT  
               d.{pk_list},
               d.{bk_list},
               d.effective_from_dttm,
               d.effective_to_dttm,
               True as deleted_flg,
               '00000000000000000000000000000000' as hash_diff
            FROM (
            SELECT *
            FROM {tmp_mrg_hist_tbl}
            WHERE tbl = 'tgt' and effective_to_dttm != new_effective_to_dttm) t
            JOIN {tgt_table} d
            UNION({pk_list}, effective_from_dttm) 
            """
        logger.info(f"Создан запрос: {query}")
        client.execute(query)
        logger.info(f"Запрос успешно выполнен")
        tmp_tables.append(tmp_dlt_tbl)

        logger.info(f"Формирование delta таблицы")
        tmp_delta_tbl = f"tmp.tmp_delta_{uuid.uuid4().hex}"
        query = f"""
            CREATE TABLE {tmp_delta_tbl} AS
            SELECT * 
            FROM ( 
            SELECT  
               {pk_list},
               {bk_list},
               effective_from_dttm,
               new_effective_to_dttm as effective_to_dttm,
               src,
               hash_diff
            FROM {tmp_mrg_hist_tbl}
            WHERE effective_from_dttm != new_effective_to_dttm
            UNION
            SELECT  
               {pk_list},
               {bk_list},
               effective_from_dttm,
               effective_to_dttm,
               src,
               hash_diff
            FROM {tmp_dlt_tbl} )
            """
        logger.info(f"Создан запрос: {query}")
        client.execute(query)
        logger.info(f"Запрос успешно выполнен")
        tmp_tables.append(tmp_delta_tbl)

        logger.info(f"Запись данных в tgt таблицу")
        query = f"""
            INSERT INTO {tgt_table} 
            SELECT  
               {pk_list},
               {bk_list},
               effective_from_dttm,
               effective_to_dttm,
               src,
               hash_diff
            FROM {tmp_delta_tbl}
            """
        logger.info(f"Создан запрос: {query}")
        client.execute(query)
        logger.info(f"Запрос успешно выполнен")
            
        
    except ClickhouseError as e:
            logger.error(f"Ошибка: {e}")
            raise
    finally:
        if client:
            for tmp_table in tmp_tables:
                query = f"""
                    DROP TABLE IF EXISTS {tmp_table}
                    """
                client.execute(query)
            client.disconnect()
            logger.debug("Подключение к ClickHouse закрыто")