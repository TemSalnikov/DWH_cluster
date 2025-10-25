from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.decorators import dag, task
from datetime import datetime, timedelta
import os
import sys
script_path = os.path.abspath(__file__)
project_path = os.path.dirname(script_path)+'/libs/dds'
sys.path.append(project_path)
import task_group_creation_surogate as tg_sur
# from task_group_creation_surogate import hub_load_processing_tasks, get_clickhouse_client

default_args = {
    'owner': 'artem_s',
    'depends_on_past': False,  # Задачи не зависят от прошлых запусков
    'start_date': datetime(2025, 1, 1),
    'email': ['twindt@mail.ru'],
    'email_on_failure': False,  # Не Отправлять email при ошибке
    'email_on_retry': False,   # Не отправлять при ретрае
    'retries': 0,             # 0 попытки при ошибке
    'retry_delay': timedelta(minutes=5),  # Ждать 5 минут перед ретраем
    'execution_timeout': timedelta(minutes=30),  # Макс. время выполнения задачи
}

@dag(
    dag_id='wf_app_dsm_stg_dds_product',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
    tags=['advanced']
)

def wf_app_dsm_stg_dds_product():
    @task
    def get_last_load_data(source_table: str) -> str:
        """Получение последних данных из источника"""
        client = None
        tmp_table_name = f"tmp.tmp_v_sv_all_{source_table}_{tg_sur.uuid.uuid4().hex}"
        
        try:
            logger = LoggingMixin().log
            client = tg_sur.get_clickhouse_client()
            logger.info(f"Подклчение к clickhouse успешно выполнено")
            ### надо подумать над запросом
            query = f"""
            CREATE TABLE {tmp_table_name} AS 
            SELECT 
                product_id,
                src,
                effective_dttm
            FROM stg.v_sv_{source_table}
            """
            logger.info(f"Создан запрос: {query}")

            client.execute(query)
            logger.info(f"Создана временная таблица {tmp_table_name} с данными из {source_table}")
            
            return tmp_table_name
            
        except tg_sur.ClickhouseError as e:
            logger.error(f"Ошибка при получении данных из {source_table}: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")

    @task
    def get_preload_data(tmp_table: str, hub_table: str) -> str:
        """Получение ключей из Hub"""
        client = None
        tmp_table_name = f"tmp.tmp_preload_{tg_sur.uuid.uuid4().hex}"
        
        try:
            logger = LoggingMixin().log
            client = tg_sur.get_clickhouse_client()
            logger.info(f"Подклчение к clickhouse успешно выполнено")
            ### надо подумать над запросом
            query = f"""
            CREATE TABLE {tmp_table_name} AS
            SELECT DISTINCT 
                h.product_uuid,
                t.*
            FROM {tmp_table} t
            JOIN dds.{hub_table} h 
                ON t.product_id = h.product_id AND t.src = h.src AND h.effective_from_dttm <= t.effective_dttm
                AND h.effective_to_dttm > t.effective_dttm
            """
            logger.info(f"Создан запрос: {query}")

            client.execute(query)
            logger.info(f"Создана временная таблица {tmp_table_name}")
            
            return tmp_table_name
            
        except tg_sur.ClickhouseError as e:
            logger.error(f"Ошибка при получении данных из {tmp_table}: {e}")
            raise
        finally:
            if client:
                client.disconnect()
                logger.debug("Подключение к ClickHouse закрыто")
    
