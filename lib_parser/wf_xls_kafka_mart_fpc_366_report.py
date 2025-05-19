from airflow.decorators import dag, task
from datetime import datetime, timedelta
from file_processing import write_meta_file
# import os
# import sys
# script_path = os.path.abspath(__file__)
# project_path = os.path.dirname(script_path)
# sys.path.append(project_path+'/'+'366_custom')
# sys.path.append(project_path+'/'+'366_remain')
# sys.path.append(project_path+'/'+'366_sale')
# from kafka_producer_custom_366 import call_producer as call_producer_custom
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

def wf_xls_kafka_mart_fpc_366_report(conf:dict):

    @task
    def extract_from_custom(conf:dict):
        pass
        # for folder, files in conf['files']:
        #     for file in files:
        #         call_producer_custom(conf['directory']+'/'+folder+'/'+file)
    # def extract_from_remain(conf:dict):
    #     call_producer_remain(conf['directory'])
    # def extract_from_sale(conf:dict):
    #     call_producer_sale(conf['directory'])
    @task
    def save_metrics(conf:dict):
        pass

    extract_from_custom('{{ dag_run.conf }}')

    # extract_from_remain('{{ dag_run.conf }}')
    # extract_from_sale('{{ dag_run.conf }}')

wf_xls_kafka_mart_fpc_366_report
