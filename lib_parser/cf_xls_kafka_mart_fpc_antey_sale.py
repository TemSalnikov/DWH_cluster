from datetime import datetime, timedelta
from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.models.param import Param
from airflow.exceptions import AirflowSkipException
from airflow.utils.log.logging_mixin import LoggingMixin
from typing import Optional, Dict
import os
import sys
script_path = os.path.abspath(__file__)
project_path = os.path.dirname(script_path)
sys.path.append(project_path+'libs')
import file_processing

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
    dag_id='cf_xls_kafka_mart_fpc_antey_sale',
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
    params = {'directory': '/opt/airflow/data/reports/Антей/Продажи/',
              'name_report': 'Продажи',
              'name_pharm_chain': 'Антей',
              'prefix_topic': 'fpc_antey'
            #   'db_config': {'host': 'postgres',
            #                 'database': 'meta',
            #                 'user': 'meta',
            #                 'password': 'meta',
            #                 'port': '5432'
            #                 }
            },
    tags=['advanced']
)
def cf_xls_kafka_mart_fpc_antey_sale():
    @task
    def check_data_availability() -> bool:
        # Проверяет готовность данных (пример реализации).
        # Возвращает True если данные готовы.

        # Здесь может быть проверка файлов, запрос к API или БД
        # Для примера просто возвращаем True
        return True
    @task
    def prepare_parameters(data_ready: bool, **context) -> Optional[Dict]:

        # Получаем параметры DAG
        if data_ready:
            # Получаем параметры из контекста выполнения
            dag_run_conf = context["dag_run"].conf if "dag_run" in context else {}

            # Объединяем с параметрами по умолчанию из DAG
            parametrs = {**context["params"], **dag_run_conf}
            return parametrs
        else: raise


    @task
    def get_folders(parametrs:Dict)-> Optional[list]:
        return file_processing.get_list_folders(parametrs['directory'])

    @task
    def get_files(parametrs:Dict, folders:list)-> Optional[dict]:
        loger = file_processing.LoggingMixin().log
        files = {}
        for folder in folders:
            loger.info(f'Получения списка файлов из папки {folder}')
            files[folder] = file_processing.get_list_files(parametrs['directory'], folder)
        loger.info(f'Получен перечень файлов: {files}')
        return files

    @task
    def get_meta_folders(parametrs:Dict)-> Optional[list]:
        loger = file_processing.LoggingMixin().log
        query = f"""select name_folder from files.folders c
                join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{parametrs['directory']}'"""
        loger.info(f'Сформирован запрос: {query}')
        folders = file_processing.get_meta_data(
            # parametrs['db_config'], 
            query)
        loger.info(f'Получен перечень папок: {folders}')
        return folders

    @task
    def get_meta_files(parametrs:Dict, folders:list)-> Optional[dict]:  # здесь в folders нужно передовать список папок из get_folders, а не get_meta_folders
        loger = file_processing.LoggingMixin().log
        files = {}
        for folder in folders:
            loger.info(f'Получения списка файлов из папки {folder}')
            query = f"""select name_file  from files.files f
                        join files.folders c on f.id_folder = c.id_folder and c.name_folder = '{folder}'
                        join files.directories d on c.id_dir = d.id_dir and d.name_dir = '{parametrs['directory']}' """
            loger.info(f'Сформирован запрос: {query}')
            files[folder] = file_processing.get_meta_data(
                # parametrs['db_config'], 
                query)
            loger.info(f'Получен перечень файлов: {files}')
        return files

    @task
    def get_folders_for_processing(meta_folder_list:list, folders_list:list)-> Optional[list]:
        return file_processing.check_new_folders(meta_folder_list, folders_list)

    @task
    def get_files_for_processing(processinf_folders: list, meta_files_dict:dict, files_dict:dict)-> Optional[dict]:
        files = {}
        for folder in processinf_folders:
            files_list= file_processing.check_new_files(files_dict[folder], meta_files_dict[folder])
            if files_list:
                files[folder] = files_list

        return files

    @task
    def trigger_or_skip(parametrs: Optional[Dict], processing_files: Optional[Dict], **context):
        loger = LoggingMixin().log
        loger.info(f'Полученный контекст: {context}!')
        from airflow.api.common.trigger_dag import trigger_dag
        if processing_files:
            parametrs['files'] = processing_files
            _dag_id = context["dag"] if "dag" in context else ''
            _dag_id = str(_dag_id).split(':')[1].strip().strip('>')
            loger.info(f'Успешно получено dag_id {_dag_id}!')
            result = trigger_dag(
                dag_id='wf'+ _dag_id[2:],
                run_id=f"triggered_by_{context['dag_run'].run_id}",
                conf={_dag_id[3:]:parametrs},
                execution_date=None,
                replace_microseconds=False
            )
            if not result:
                raise RuntimeError("Не удалось запустить дочерний DAG")
        else:
            raise AirflowSkipException("Условия не выполнены, пропускаем запуск целевого DAG")


    start_flow = check_data_availability()
    parametrs = prepare_parameters(start_flow)
    folders = get_folders(parametrs)
    meta_folders = get_meta_folders(parametrs)
    files = get_files(parametrs, folders)
    meta_files = get_meta_files(parametrs, folders)
    processinf_folders = get_folders_for_processing(meta_folders, folders)
    processing_files = get_files_for_processing(processinf_folders, meta_files, files)
    trigger_or_skip(parametrs, processing_files)

cf_xls_kafka_mart_fpc_antey_sale()