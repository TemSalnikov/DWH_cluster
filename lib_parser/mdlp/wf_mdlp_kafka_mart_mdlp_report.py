from datetime import datetime, timedelta
from airflow import DAG
from airflow.decorators import task, dag
from airflow.sensors.python import PythonSensor
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.models import Variable
# from confluent_kafka import Producer
import requests
import subprocess
import tempfile
import re
import json
import time
import csv
import os

# Конфигурация
API_URL = "https://api.sb.mdlp.crpt.ru/api/v1"
CLIENT_ID = Variable.get("MDLP_CLIENT_ID")
CLIENT_SECRET = Variable.get("MDLP_CLIENT_SECRET")
USER_ID = Variable.get("MDLP_USER_ID")  # Отпечаток сертификата
CERT_SUBJECT = Variable.get("MDLP_CERT_SUBJECT")  # CN сертификата
EXPORT_TASKS_URL = f"{API_URL}/api/v1/data/export/tasks"
TASK_STATUS_URL = f"{API_URL}/api/v1/data/export/tasks/{{task_id}}"
DOWNLOAD_URL = f"{API_URL}/api/v1/data/export/results/{{result_id}}/file"

REPORT_TYPES = [
    "GENERAL_PRICING_REPORT",
    "GENERAL_REPORT_ON_MOVEMENT",
    "GENERAL_REPORT_ON_REMAINING_ITEMS",
    "GENERAL_REPORT_ON_DISPOSAL"
]

KAFKA_CONFIG = {'bootstrap.servers': 'your-kafka-server:9092', 'client.id': 'mdlp_reports_producer'}
KAFKA_TOPIC = 'mdlp_reports'

# Данные аутентификации (рекомендуется использовать Airflow Connections)
CREDENTIALS = {'login': 'your_username', 'password': 'your_password'}

# Настройка логирования
logger = LoggingMixin().log

default_args = {
    'owner': 'airflow',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
}

@dag(
    dag_id='wf_mdlp_kafka_mart_mdlp_report',
    schedule_interval='@daily',
    start_date=datetime(2023, 1, 1),
    default_args=default_args,
    catchup=False,
    tags=['mdlp', 'reports'],
    doc_md=__doc__
)
def wf_mdlp_kafka_mart_mdlp_report():
    
    @task
    def get_auth_code():
        """Получение кода аутентификации"""
        url = f"{API_URL}/auth"
        payload = {
            "client_secret": CLIENT_SECRET,
            "client_id": CLIENT_ID,
            "user_id": USER_ID,
            "auth_type": "SIGNED_CODE"
        }
        headers = {'Content-Type': 'application/json'}
        
        logger.info(f"Запрос кода аутентификации: {url}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        logger.info(f"Ответ получен: {response.status_code}")
        return response.json()['code']

    @task
    def sign_data(data: str, is_document: bool = False) -> str:
        """Подписание данных с использованием КриптоПро CSP"""
        # Создаем временные файлы
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as input_file:
            input_file.write(data)
            input_file_path = input_file.name
        
        output_file_path = input_file_path + '.sig'
        
        try:
            # Формируем команду для подписи
            command = [
                r'C:\Program Files\Crypto Pro\CSP\csptest.exe',
                '-sfsign',
                '-sign',
                '-in', input_file_path,
                '-out', output_file_path,
                '-my', CERT_SUBJECT,
                '-detached',
                '-base64',
                '-add'
            ]
            
            logger.info(f"Выполнение команды: {' '.join(command)}")
            
            # Выполняем команду
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Проверяем результат выполнения
            if result.returncode != 0:
                logger.error(f"Ошибка подписи: {result.stderr}")
                raise Exception(f"Ошибка подписи: {result.stderr}")
            
            # Читаем результат подписи
            with open(output_file_path, 'r') as f:
                signature = f.read()
            
            # Удаляем заголовки и переносы строк
            signature = re.sub(
                r'-----(BEGIN|END) SIGNATURE-----|\s+', 
                '', 
                signature
            )
            
            logger.info("Данные успешно подписаны")
            return signature
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка выполнения команды: {e.stderr}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при подписании данных: {str(e)}")
            raise
        finally:
            # Удаляем временные файлы
            if os.path.exists(input_file_path):
                os.remove(input_file_path)
            if os.path.exists(output_file_path):
                os.remove(output_file_path)

    @task
    def get_session_token(auth_code: str, signature: str):
        """Получение токена доступа"""
        url = f"{API_URL}/token"
        payload = {
            "code": auth_code,
            "signature": signature
        }
        headers = {'Content-Type': 'application/json'}
        
        logger.info(f"Запрос токена сессии: {url}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        token_data = response.json()
        logger.info(f"Токен получен, срок жизни: {token_data['life_time']} минут")
        return token_data['token']

    
    @task
    def create_report_task(report_type, token):
        """Создание задачи на формирование отчета"""
        headers = {
            'Authorization': f'token {token}',
            'Content-Type': 'application/json'
        }
        
        # Параметры запроса (настраиваются под конкретные нужды)
        payload = {
            "task_type": report_type,
            "filters": {
                "date_from": "{{ data_interval_start }}",
                "date_to": "{{ data_interval_end }}"
            }
        }
        
        response = requests.post(
            EXPORT_TASKS_URL,
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to create task for {report_type}: {response.text}")
        
        return response.json()['task_id']
    
    def _check_report_status(task_id, token):
        """Проверка статуса задачи (внутренняя функция для сенсора)"""
        headers = {'Authorization': f'token {token}'}
        response = requests.get(
            TASK_STATUS_URL.format(task_id=task_id),
            headers=headers
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to check task status: {response.text}")
        
        status = response.json()['status']
        if status == 'COMPLETED':
            return response.json()['result_id']
        elif status == 'FAILED':
            raise RuntimeError(f"Task failed: {response.json().get('error_message', 'Unknown error')}")
        
        return False
    
    @task
    def download_report(report_type, task_id, token):
        """Скачивание готового отчета"""
        # Проверяем статус и получаем result_id
        result_id = _check_report_status(task_id, token)
        
        if not result_id:
            raise RuntimeError("Report not ready for download")
        
        headers = {'Authorization': f'token {token}'}
        response = requests.get(
            DOWNLOAD_URL.format(result_id=result_id),
            headers=headers,
            stream=True
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download report: {response.text}")
        
        # Сохраняем файл временно
        file_path = f"/tmp/{report_type}_{result_id}.csv"
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return file_path
    
    # @task
    # def send_to_kafka(file_path, report_type):
    #     """Отправка данных отчета в Kafka"""
    #     producer = Producer(KAFKA_CONFIG)
    #     sent_count = 0
        
    #     try:
    #         with open(file_path, 'r') as f:
    #             reader = csv.DictReader(f)
    #             for row in reader:
    #                 # Добавляем тип отчета в данные
    #                 row['report_type'] = report_type
    #                 message = json.dumps(row)
                    
    #                 producer.produce(
    #                     topic=KAFKA_TOPIC,
    #                     value=message.encode('utf-8'),
    #                     callback=lambda err, msg: print(
    #                         f"Delivered to {msg.topic()}[{msg.partition()}]" if not err else f"Delivery failed: {err}"
    #                     )
    #                 )
    #                 producer.poll(0)
    #                 sent_count += 1
            
    #         # Ожидаем доставки всех сообщений
    #         producer.flush()
    #         print(f"Sent {sent_count} messages to Kafka")
            
    #     finally:
    #         # Удаляем временный файл
    #         os.remove(file_path)
    #         print(f"Removed temporary file: {file_path}")
    
    # Создаем сенсор для ожидания готовности отчета
    def wait_for_report(report_type, task_id, token):
        return PythonSensor(
            task_id=f'wait_for_{report_type}',
            python_callable=lambda: _check_report_status(task_id, token),
            op_kwargs={},
            mode='poke',
            poke_interval=5 * 60,  # Проверка каждые 5 минут
            timeout=24 * 60 * 60,   # Таймаут 24 часа
            exponential_backoff=True,
            soft_fail=False
        )
    
    # Основной поток выполнения
    auth_code = get_auth_code()
    auth_signature = sign_data(auth_code)
    session_token = get_session_token(auth_code, auth_signature)
    
    for report_type in REPORT_TYPES:
        task_id = create_report_task(report_type, session_token)
        wait_sensor = wait_for_report(report_type, task_id, session_token)
        file_path = download_report(report_type, task_id, session_token)
        # send_task = send_to_kafka(file_path, report_type)
        
        task_id >> wait_sensor >> file_path #>> send_task

# Инициализация DAG
wf_mdlp_kafka_mart_mdlp_report()