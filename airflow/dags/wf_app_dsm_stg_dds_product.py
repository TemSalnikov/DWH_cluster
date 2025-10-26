from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.decorators import dag, task
from airflow.models.param import Param
from datetime import datetime, timedelta
import os
import sys
script_path = os.path.abspath(__file__)
project_path = os.path.dirname(script_path)+'/libs/dds'
sys.path.append(project_path)
import task_group_creation_surogate as tg_sur
import functions_dds as fn_dds
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
    tags=['advanced'],
    params = {
        "p_version_prev": Param('2025-01-01 00:01:01', type = "string", title = "Processed_dttm прудыдущей выгрузки"),
        "p_version_new": Param('2999-12-31 23:59:59', type = "string", title = "Processed_dttm новой выгрузки")
    }
)

def wf_app_dsm_stg_dds_product():
    src_table_name = 'stg.'             #название таблицы источника
    tgt_table_name = 'dds.dds_product'  #название целевой таблицы
    hub_table_name = 'dds.hub_product'  #название таблицы Хаба
    pk_list = ['product_id']            #список полей PK
    bk_list = []                        #Список полей бизнесс данных
    name_sur_key = 'product_uuid'      #название сурогатного ключа

    @task
    def check_data_availability() -> bool:
        # Проверяет готовность данных (пример реализации).
        # Возвращает True если данные готовы.

        # Здесь может быть проверка файлов, запрос к API или БД
        # Для примера просто возвращаем True
        return True
    @task
    def prepare_parameters(data_ready: bool, **context) -> dict:

        # Получаем параметры DAG
        if data_ready:
            # Получаем параметры из контекста выполнения
            dag_run_conf = context["dag_run"].conf if "dag_run" in context else {}
            _dag_id = context["dag"] if "dag" in context else ''
            algo_id = str(_dag_id).split(':')[1].strip().strip('>')[3:]
            # Объединяем с параметрами по умолчанию из DAG
            parametrs = {**context["params"], **dag_run_conf}
            return parametrs[algo_id]
        else: raise
    @task
    def get_inc_load_data(source_table: str, pk_list: list, bk_list:list, p_version_prev: str, p_version_new: str) -> str:
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
                {pk_list},
                {bk_list},
                src,
                effective_dttm
            FROM stg.v_iv_{source_table}({p_version_prev}, {p_version_new})
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
    def get_prepared_data(tmp_table: str, hub_table: str, name_sure_column: str) -> str:
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
                h.{name_sur_key},
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
    


    check_task = check_data_availability()
    parametrs_data_task = prepare_parameters(check_task)
    inc_table_task = get_inc_load_data(src_table_name,pk_list, bk_list, parametrs_data_task['p_version_prev'], parametrs_data_task['p_version_new'])
    generate_sur_key_task = tg_sur.hub_load_processing_tasks(hub_table_name, inc_table_task)
    prepared_data_task = get_prepared_data(inc_table_task, hub_table_name, name_sur_key)
    hist_p2i_task = convert_hist_p2i(prepared_data_task, pk_list)
    load_delta_task = load_delta(hist_p2i_task, tgt_table_name, pk_list, bk_list)
    
    check_task >> parametrs_data_task >> inc_table_task >> generate_sur_key_task >> prepared_data_task
    prepared_data_task >> hist_p2i_task >> load_delta_task