from airflow.decorators import dag, task
from datetime import datetime, timedelta
from file_processing import write_meta_file
import os
import sys
script_path = os.path.abspath(__file__)
project_path = os.path.dirname(script_path)
sys.path.append(project_path+'/366_custom')
# sys.path.append(project_path+'/'+'366_remain')
# sys.path.append(project_path+'/'+'366_sale')
from kafka_producer_custom_366 import call_producer as call_producer_custom
# from kafka_producer_remain_366 import call_producer as call_producer_remain
# from kafka_producer_sale_366 import call_producer as call_producer_sale

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
    dag_id='wf_xls_kafka_mart_fpc_366_report',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
    tags=['advanced']
)

def wf_xls_kafka_mart_fpc_366_report():

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
            
            # Объединяем с параметрами по умолчанию из DAG
            parametrs = {**context["params"], **dag_run_conf}
            return parametrs
        else: raise
    @task
    def extract_from_xls(conf:dict):
        # pass
        for folder, files in conf['files']:
            for file in files:
                if call_producer_custom(conf['directory']+'/'+folder+'/'+file):
                    write_meta_file(
                        # conf['db_config'], 
                        conf['directory'],
                        folder,
                        file)
    # def extract_from_remain(conf:dict):
    #     call_producer_remain(conf['directory'])
    # def extract_from_sale(conf:dict):
    #     call_producer_sale(conf['directory'])
    # @task
    # def save_metrics(conf:dict):
    #     pass
    
    start_flow = check_data_availability()
    parametrs = prepare_parameters(start_flow)
    extract_from_xls(parametrs)

    # extract_from_remain('{{ dag_run.conf }}')
    # extract_from_sale('{{ dag_run.conf }}')

wf_xls_kafka_mart_fpc_366_report()
