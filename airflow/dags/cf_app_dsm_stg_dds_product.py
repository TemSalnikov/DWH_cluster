from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.api.common.trigger_dag import trigger_dag
# from airflow.models.param import Param
from airflow.exceptions import AirflowSkipException
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.providers.postgres.hooks.postgres import PostgresHook
from clickhouse_driver import Client
from typing import Optional
import os
import sys
script_path = os.path.abspath(__file__)
project_path = os.path.dirname(script_path)+'/libs'
sys.path.append(project_path)
# import file_processing
from functions_dwh.db_connection import get_clickhouse_client


default_args = {
    'owner': 'artem_s',
    'depends_on_past': False,  # Задачи не зависят от прошлых запусков
    'start_date': datetime(2025, 1, 1),
    'email': ['twindt@mail.ru'],
    'email_on_failure': False,  # Не Отправлять email при ошибке
    'email_on_retry': False,   # Не отправлять при ретрае
    'retries': 0,             # 2 попытки при ошибке
    'retry_delay': timedelta(minutes=5),  # Ждать 5 минут перед ретраем
    'execution_timeout': timedelta(minutes=30),  # Макс. время выполнения задачи
    'provide_context': True
}


@dag(
    dag_id='cf_app_dsm_stg_dds_product',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
    tags=['advanced']
)
def cf_xls_kafka_mart_fpc_25_all():
    src_table_name = 'mart_dsm_stat_product'    #название таблицы источника
    tgt_table_name = 'dds.product'              #название целевой таблицы

    @task
    def check_data_availability() -> bool:
        # Проверяет готовность данных (пример реализации).
        # Возвращает True если данные готовы.

        # Здесь может быть проверка файлов, запрос к API или БД
        # Для примера просто возвращаем True
        return True

    @task
    def get_max_stg(table_name:str)-> Optional[list]:
        loger = LoggingMixin().log
        query = f"""select max(processed_dttm) as max_processed_dttm from stg.{table_name}"""
        loger.info(f'Сформирован запрос: {query}')
        try:

            ch_client = get_clickhouse_client()
            q_res = ch_client.execute(query)
            loger.info(f'Результат запроса: {q_res[0][0]}') 
            ch_client.disconnect()
              
            return datetime.strftime(q_res[0][0],'%Y-%m-%d %H:%M:%S')
        except Exception as e:
            loger.error(f"Ошибка при работе с DB: {e}")
            raise
        finally:
            if ch_client:
                ch_client.disconnect()


    @task
    def get_last_load_dds(**context)-> Optional[list]:
        loger = LoggingMixin().log
        _dag_id = context["dag"] if "dag" in context else ''
        dag_id = str(_dag_id).split(':')[1].strip().strip('>')
        loger.info(f'Получен dag_id: {dag_id}')
        query = f"""select loaded_stg_processed_dttm 
                    from versions
                    where dag_id = '{'wf'+ dag_id[2:]}'
                    and dds_processed_dttm = (select max(dds_processed_dttm) from versions)"""
        loger.info(f'Сформирован запрос: {query}')
        try:

            conn = None
            hook = PostgresHook(postgres_conn_id="postgres_conn")
            conn = hook.get_conn()
            cursor = conn.cursor()
            
            cursor.execute(query)

            res_list = cursor.fetchall()
            result = [x[0] for x in res_list]
            loger.info(f'Полученный processed_dttm: {result}')  
            return datetime.strftime(result[0], '%Y-%m-%d %H:%M:%S')
        except Exception as e:
            loger.error(f"Ошибка при работе с PostgreSQL: {e}")
            raise
        finally:
            if conn:
                conn.close()
            

    
    @task
    def trigger_or_skip(p_version_prev: str, p_version_new: str, **context):
        loger = LoggingMixin().log
        loger.info(f'Полученный контекст: {context}!')
        _dag_id = context["dag"] if "dag" in context else ''
        _dag_id = str(_dag_id).split(':')[1].strip().strip('>')
        loger.info(f'Успешно получено dag_id {_dag_id}!')
        loger.info(f'p_version_prev: {p_version_prev}, p_version_new: {p_version_new}')
        if p_version_prev is not None and p_version_new is not None and datetime.strptime(p_version_prev, '%Y-%m-%d %H:%M:%S') < datetime.strptime(p_version_new, '%Y-%m-%d %H:%M:%S'):
            parametrs = {"p_version_prev": p_version_prev, "p_version_new": p_version_new}
            
            result = trigger_dag(
                dag_id='wf'+ _dag_id[2:],
                run_id=f"triggered_by_{context['dag_run'].run_id}",
                conf=parametrs,
                execution_date=None,
                replace_microseconds=False
            )
            if not result:
                raise RuntimeError("Не удалось запустить дочерний DAG")
        else:
            raise AirflowSkipException("Условия не выполнены, пропускаем запуск целевого DAG")


    start_flow = check_data_availability()
    get_max_stg_task = get_max_stg(src_table_name)
    get_last_load_dds_task = get_last_load_dds()
    trigger_or_skip_task = trigger_or_skip(get_last_load_dds_task, get_max_stg_task)
    start_flow >> get_max_stg_task >> get_last_load_dds_task >> trigger_or_skip_task

cf_xls_kafka_mart_fpc_25_all()
