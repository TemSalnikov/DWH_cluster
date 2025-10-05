from datetime import datetime, timedelta
from airflow import DAG
from airflow.decorators import task, dag
from airflow.sensors.python import PythonSensor
from airflow.utils.log.logging_mixin import LoggingMixin
from airflow.models import Param
from airflow.providers.postgres.hooks.postgres import PostgresHook
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from deep_translator import GoogleTranslator  # pip install deep-translator Оффлайн-перевод не поддерживается, используем кеширование
import requests
import subprocess
import tempfile
import re
import json
import os
import glob
import pandas as pd
import zipfile
import os
import sys
script_path = os.path.abspath(__file__)
project_path = os.path.dirname(script_path)+'/libs'
sys.path.append(project_path)

# from kafka_producer_common_for_xls import create_producer, send_dataframe
from datetime import datetime as dt

# Класс адаптера для ГОСТ-шифров
class GOSTAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers="GOST2012-GOST8912-GOST8912")
        kwargs["ssl_context"] = context  # Передаём контекст в urllib3
        return super().init_poolmanager(*args, **kwargs)

# Конфигурация
API_URL = "https://api.mdlp.crpt.ru/api/v1"
CLIENT_ID = "0dc92a9d-50e2-4d01-8c2c-f9a0ef27ff31"
CLIENT_SECRET = "21842175-2a01-43d7-86f8-dc5f3f3aabfe"
USER_ID = "F8851B3675EC0C2CD9664A83C46CE62FC5F594EB" # Отпечаток сертификата
CERT_SUBJECT = "Благодаренко Юрий Юрьевич"
EXPORT_TASKS_URL = f"{API_URL}/data/export/tasks"
TASK_STATUS_URL = f"{API_URL}/data/export/tasks/{{task_id}}"
GET_RESULT_ID_URL = f"{API_URL}/data/export/results?page=0&size=1000&task_ids={{task_id}}"
DOWNLOAD_URL = f"{API_URL}/data/export/results/{{result_id}}/file"

REPORT_TYPES = [
    "GENERAL_PRICING_REPORT",
    "GENERAL_REPORT_ON_MOVEMENT",
    "GENERAL_REPORT_ON_REMAINING_ITEMS",
    "GENERAL_REPORT_ON_DISPOSAL"
]

TEMP_DIR = "/tmp"
POSTGRES_CONN_ID = "mdlp_postgres_conn"

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
    params={
        'period_type': Param(
            "1027_IC_Period_Month_11_2019",
            # type="string",
            description='Тип периода (1027_IC_Period_Month_11_2019 или 1028_IC_Period_Week)'
        ),
        'dates_to': Param(
            ["2025-07-18","2025-07-25"],
            # type="string",
            format='list',
            description='Дата окончания периода в формате YYYY-MM-DD'
        )
    },
    doc_md=__doc__
)
def wf_mdlp_kafka_mart_mdlp_report():
    
    # Создаем сессию с ГОСТ-адаптером
    def create_gost_session():
        session = requests.Session()
        session.mount("https://", GOSTAdapter())
        session.verify = False  # Отключаем проверку сертификата
        session.cert = ("/home/downloads/cert.pem", "/home/downloads/key.pem")  # Пути к сертификату и ключу
        return session

    @task
    def get_auth_code():
        """Получение кода аутентификации"""
        session = create_gost_session()
        url = f"{API_URL}/auth"
        payload = {
            "client_secret": CLIENT_SECRET,
            "client_id": CLIENT_ID,
            "user_id": USER_ID,
            "auth_type": "SIGNED_CODE"
        }
        
        headers = {'Content-Type': 'application/json;charset=UTF-8'}
        
        logger.info(f"Запрос кода аутентификации: {url}")
        response = session.post(url, json=payload, headers=headers)
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
                '/opt/cprocsp/bin/amd64/csptest',
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
        session = create_gost_session()
        url = f"{API_URL}/token"
        payload = {
            "code": auth_code,
            "signature": signature
        }
        headers = {'Content-Type': 'application/json'}
        
        logger.info(f"Запрос токена сессии: {url}")
        response = session.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        token_data = response.json()
        logger.info(f"Токен получен, срок жизни: {token_data['life_time']} минут")
        return token_data['token']

    @task
    def create_report_task(report_type, token, **context):
        """Создание задачи на формирование отчета"""
        session = create_gost_session()
        headers = {
            'Authorization': f'token {token}',
            'Content-Type': 'application/json'
        }
        
        # Получаем параметры из контекста
        params = context['params']
        period_type = params['period_type']
        dates_to = params['dates_to'] or context['data_interval_end'].strftime('%Y-%m-%d')
        
        for date_to in dates_to:
            # Параметры запроса
            payload = {
                "report_id": report_type,
                "params": {
                    "1026_IC_Period_Type_WM": period_type,
                    period_type: calculate_period_value(period_type, date_to)
                }
            }
            
            response = session.post(
                EXPORT_TASKS_URL,
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Failed to create task for {report_type}: {response.text}")
        
        return response.json()['task_id']
    
    def calculate_period_value(period_type, date_to):
        """Расчет значения периода по типу периода и дате окончания"""
        dt_date = dt.strptime(date_to, '%Y-%m-%d')
        
        if period_type == "1027_IC_Period_Month_11_2019":
            # Год * 12 + номер месяца
            return dt_date.year * 12 + dt_date.month
        elif period_type == "1028_IC_Period_Week":
            # (Год - 1970) * 52.1786 + номер недели
            return int((dt_date.year - 1970) * 52.1786 + dt_date.isocalendar()[1])
        else:
            raise ValueError(f"Unsupported period type: {period_type}")

    def _get_result_id(task_id, token):
        """Получение result_id по task_id"""
        session = create_gost_session()
        headers = {'Authorization': f'token {token}'}
        url = GET_RESULT_ID_URL.format(task_id=task_id)
        response = session.get(url, headers=headers)
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to get result ID: {response.text}")
        
        result = response.json()
        if result['list']:
            return result['list'][0]
        return None

    def check_report_status(task_id, token):
        """Проверка статуса задачи"""
        session = create_gost_session()
        headers = {'Authorization': f'token {token}'}
        url = TASK_STATUS_URL.format(task_id=task_id)
        response = session.get(url, headers=headers)
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to check task status: {response.text}")
        
        status = response.json()['current_status']
        if status == 'COMPLETED':
            result_data = _get_result_id(task_id, token)
            if result_data and result_data['download_status'] == "SUCCESS" and result_data['available'] == "AVAILABLE":
                return result_data['result_id']
        elif status == 'FAILED':
            raise RuntimeError(f"Task failed: {response.json().get('error_message', 'Unknown error')}")
        
        return False

    @task
    def download_report(report_type, task_id, token, **context):
        """Скачивание готового отчета"""
        session = create_gost_session()
        result_id = check_report_status(task_id, token)
        
        if not result_id:
            raise RuntimeError("Report not ready for download")
        
        headers = {'Authorization': f'token {token}'}
        response = session.get(
            DOWNLOAD_URL.format(result_id=result_id),
            headers=headers,
            stream=True
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download report: {response.text}")
        
        # Сохраняем файл как ZIP архив с метаданными
        params = context['params']
        date_to = params['date_to'] or context['data_interval_end'].strftime('%Y-%m-%d')
        zip_path = f"{TEMP_DIR}/{report_type}_{date_to}_{task_id}.zip"
        
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return zip_path
    
    @task
    def extract_report(zip_path, report_type, **context):
        """Извлечение CSV из ZIP архива"""
        try:
            # Получаем параметры из контекста
            params = context['params']
            date_to = params['date_to'] or context['data_interval_end'].strftime('%Y-%m-%d')
            
            # Создаем директорию для извлечения
            extract_dir = f"{TEMP_DIR}/extracted"
            os.makedirs(extract_dir, exist_ok=True)
            
            # Извлекаем файлы
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                if not file_list:
                    raise ValueError(f"ZIP архив пуст: {zip_path}")
                
                # Извлекаем первый файл (ожидаем CSV)
                csv_filename = file_list[0]
                zip_ref.extract(csv_filename, extract_dir)
                csv_path = os.path.join(extract_dir, csv_filename)
                
                # Переименовываем с метаданными
                new_path = f"{TEMP_DIR}/{report_type}_{date_to}_{os.path.basename(zip_path).split('.')[0]}.csv"
                os.rename(csv_path, new_path)
            
            # Удаляем архив
            os.remove(zip_path)
            logger.info(f"Отчет извлечен: {new_path}")
            return new_path
            
        except Exception as e:
            logger.error(f"Ошибка извлечения отчета {zip_path}: {str(e)}")
            return None
    def translate_text(text, source='ru', target='en'):
        try:
            return GoogleTranslator(source=source, target=target).translate(text)
        except Exception as e:
            print(f"Translation failed for '{text}': {str(e)}")
            return text.lower().replace(' ', '_')  # Fallback
    def translate_columns(df):
        """Автоматически переводит названия столбцов с русского на английский."""
        translated_columns = []
        for col in df.columns:
            # Специальные случаи для сложных названий
            if "ИНН" in col:
                translated = col.replace("ИНН", "INN")
            elif "ГТИН" in col or "GTIN" in col:
                translated = "gtin"
            else:
                translated = translate_text(col)
            
            # Дополнительная обработка
            translated = (translated.lower()
                        .replace(',', '')
                        .replace('.', '')
                        .replace(' ', '_')
                        .replace('-', '_')
                        .replace('__', '_'))
            translated_columns.append(translated)
        
        return translated_columns

    @task
    def process_and_send_reports(extract_tasks, **context):
        """Обработка отчетов и отправка в Kafka"""
        from kafka_producer_common_for_xls import create_producer, send_dataframe
        from airflow.models import Variable
        
        # Получаем параметры из контекста
        params = context['params']
        date_to = params['date_to'] or context['data_interval_end'].strftime('%Y-%m-%d')
        
        # Конфигурация Kafka
        kafka_servers = Variable.get("KAFKA_BOOTSTRAP_SERVERS", 
                                    default_var="kafka1:19092,kafka2:19092,kafka3:19092")
        bootstrap_servers = kafka_servers.split(',')
        
        # Шаблон для поиска отчетов
        report_files = glob.glob(f"{TEMP_DIR}/*.csv")
        
        if not report_files:
            logger.info("Не найдено отчетов для обработки")
            return
        
        logger.info(f"Найдено отчетов для обработки: {len(report_files)}")
        
        for file_path in report_files:
            try:
                # Извлекаем тип отчета из имени файла
                report_type = os.path.basename(file_path).split('_')[0]
                logger.info(f"Обработка отчета: {report_type}, файл: {file_path}")
                
                # Чтение CSV файла
                df = pd.read_csv(file_path, encoding='utf-8', sep=';')
                
                # Проверка наличия данных
                if len(df) < 1:
                    logger.warning(f"Отчет {file_path} не содержит данных. Удаляем.")
                    os.remove(file_path)
                    continue
                
                # Добавляем метаданные
                df['type_report'] = report_type
                df['date_to'] = date_to
                df['create_dttm'] = dt.now()
                
                # Перевод названий столбцов
                df.columns = translate_columns(df.columns)
                
                # Создание продюсера Kafka
                producer = create_producer(bootstrap_servers)
                
                # Отправка данных
                topic_name = f"mdlp_{report_type.lower()}"
                send_dataframe(producer, topic_name, df)
                producer.close()
                
                # Удаление файла после успешной отправки
                os.remove(file_path)
                logger.info(f"Отчет успешно отправлен в Kafka и удален: {file_path}")
                
                # Возвращаем метаданные для сохранения в PostgreSQL
                yield {
                    'report_type': report_type,
                    'date_to': date_to,
                    'file_path': file_path
                }
                
            except Exception as e:
                logger.error(f"Ошибка обработки отчета {file_path}: {str(e)}")

    @task
    def save_meta_to_postgres(meta_data):
        """Сохранение метаданных в PostgreSQL"""
        if not meta_data:
            return
        
        hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        conn = hook.get_conn()
        cursor = conn.cursor()
        
        try:
            # Создаем таблицу если не существует
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS mdlp_report_meta (
                id SERIAL PRIMARY KEY,
                report_type VARCHAR(100) NOT NULL,
                date_to DATE NOT NULL,
                processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
            cursor.execute(create_table_sql)
            
            # Вставляем данные
            insert_sql = """
            INSERT INTO mdlp_report_meta (report_type, date_to)
            VALUES (%s, %s)
            """
            
            for data in meta_data:
                cursor.execute(insert_sql, (data['report_type'], data['date_to']))
            
            conn.commit()
            logger.info(f"Сохранено {len(meta_data)} записей в PostgreSQL")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения в PostgreSQL: {str(e)}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    # Создаем сенсор для ожидания готовности отчета
    def wait_for_report(report_type, task_id, token):
        return PythonSensor(
            task_id=f'wait_for_{report_type}',
            python_callable=lambda: check_report_status(task_id, token),
            op_kwargs={},
            mode='poke',
            poke_interval=5 * 60,
            timeout=24 * 60 * 60,
            exponential_backoff=True,
            soft_fail=False
        )
    
    @task
    def get_report(task_id, session_token, **context):
    # Список для хранения задач извлечения отчетов
        
        return extract_tasks
    
    # Основной поток выполнения
    auth_code = get_auth_code()
    auth_signature = sign_data(auth_code)
    session_token = get_session_token(auth_code, auth_signature)
    
    # extract_tasks = get_report(session_token)
    extract_tasks = []
    
    for report_type in REPORT_TYPES:
        task_ids = create_report_task(report_type, session_token)
        wait_sensor = wait_for_report(report_type, task_ids, session_token)
        zip_path = download_report(report_type, task_ids, session_token)
        csv_path = extract_report(zip_path, report_type)
        
        # Формируем цепочку зависимостей
        task_ids >> wait_sensor >> zip_path >> csv_path
        extract_tasks.append(csv_path)
    
    
    # Добавляем задачи обработки и сохранения метаданных
    processed_reports = process_and_send_reports(extract_tasks)
    save_meta = save_meta_to_postgres(processed_reports)

# Инициализация DAG
wf_mdlp_kafka_mart_mdlp_report()