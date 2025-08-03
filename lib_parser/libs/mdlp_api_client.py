import requests
import json
import subprocess
import os
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from airflow.providers.postgres.hooks.postgres import PostgresHook
import logging
import sys
import random
import time


# Конфигурация
API_URL = "https://api.mdlp.crpt.ru/api/v1"
CLIENT_ID = "0dc92a9d-50e2-4d01-8c2c-f9a0ef27ff31"
CLIENT_SECRET = "21842175-2a01-43d7-86f8-dc5f3f3aabfe"
USER_ID = "F8851B3675EC0C2CD9664A83C46CE62FC5F594EB"
CERT_SUBJECT = "Благодаренко Юрий Юрьевич"
CERT_PATH = "/opt/airflow/key/cert.pem"
KEY_PATH = "/opt/airflow/key/cert.key"
TEMP_DIR = "/tmp"
REPORT_TYPES = [
    "GENERAL_PRICING_REPORT",
    "GENERAL_REPORT_ON_MOVEMENT",
    "GENERAL_REPORT_ON_REMAINING_ITEMS",
    "GENERAL_REPORT_ON_DISPOSAL"
]
# Глобальная переменная для отслеживания времени последнего запроса
LAST_REQUEST_TIME = 0
MIN_INTERVAL = 61  # Минимальный интервал между запросами в секундах



# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

class GOSTAdapter(HTTPAdapter):
    """Адаптер для ГОСТ-шифрования"""
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        try:
            context.set_ciphers("GOST2012-GOST8912-GOST8912:GOST2001-GOST89-GOST89:@SECLEVEL=1")
        except:
            logger.warning("Using DEFAULT ciphers")
            context.set_ciphers("DEFAULT")
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)

def ensure_request_interval():
    """Обеспечение минимального интервала между запросами с использованием PostgreSQL"""
    conn = None
    try:
        hook = PostgresHook(postgres_conn_id="mdlp_postgres_conn")
        conn = hook.get_conn()
        cur = conn.cursor()
        
        # Создаем таблицу, если не существует
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mdlp_api_state (
                id SERIAL PRIMARY KEY,
                key VARCHAR(50) UNIQUE NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Инициализируем или получаем время последнего запроса
        cur.execute("""
            INSERT INTO mdlp_api_state (key, value)
            VALUES ('last_request_time', '0')
            ON CONFLICT (key) DO UPDATE
            SET value = mdlp_api_state.value
            RETURNING value;
        """)
        
        last_request_time = float(cur.fetchone()[0])
        current_time = time.time()
        elapsed = current_time - last_request_time
        
        if elapsed < MIN_INTERVAL:
            sleep_time = MIN_INTERVAL - elapsed
            logger.info(f"Ожидание {sleep_time:.2f} секунд перед запросом...")
            time.sleep(sleep_time)
        
        # Обновляем время последнего запроса
        cur.execute("""
            UPDATE mdlp_api_state
            SET value = %s, updated_at = CURRENT_TIMESTAMP
            WHERE key = 'last_request_time'
        """, (str(time.time()),))
        
        conn.commit()
        return sleep_time if elapsed < MIN_INTERVAL else 0
    except Exception as e:
        logger.error(f"Ошибка работы с PostgreSQL: {str(e)}")
        # Fallback: ждем минимальный интервал
        time.sleep(MIN_INTERVAL)
        return MIN_INTERVAL
    finally:
        if conn:
            conn.close()
    
def create_session():
    """Создание сессии с ГОСТ-шифрованием"""
    session = requests.Session()
    session.mount("https://", GOSTAdapter())
    session.verify = False
    session.cert = (CERT_PATH, KEY_PATH)
    return session

def get_auth_code():
    """Получение кода аутентификации"""
    # ensure_request_interval()
    session = create_session()
    url = f"{API_URL}/auth"
    payload = {
        "client_secret": CLIENT_SECRET,
        "client_id": CLIENT_ID,
        "user_id": USER_ID,
        "auth_type": "SIGNED_CODE"
    }
    response = session.post(url, json=payload)
    response.raise_for_status()
    
    return response.json()['code']

def get_session_token(auth_code, signature):
    """Получение токена сессии"""
    wait_time = ensure_request_interval()
    logger.info(f"Задержка перед запросом: {wait_time:.2f} сек")
    session = create_session()
    url = f"{API_URL}/token"
    print(f'URL: {url}')
    payload = {
        "code": auth_code,
        "signature": signature
    }
    print(f'Body request: {payload}')
    response = session.post(url, json=payload)
    response.raise_for_status()
    print(f'response: {response}')
    
    return response.json()['token']

def create_report_task(token, report_type, period_type, date_to):
    """Создание задачи на отчет"""
    wait_time = ensure_request_interval()
    logger.info(f"Задержка перед запросом: {wait_time:.2f} сек")
    session = create_session()
    url = f"{API_URL}/data/export/tasks"
    headers = {'Authorization': f'token {token}',
        'Content-Type': 'application/json'}
    
    payload = {
        "report_id": report_type,
        "params": {
            "1026_IC_Period_Type_WM": period_type,
            period_type: str(_calculate_period(period_type, date_to))
        }
    }
    print(f'url:{url}')
    print(f'headers:{headers}')
    print(f'payload:{payload}')
    
    response = session.post(url, json=payload, headers=headers)
    response.raise_for_status()
    print(f'response:{response}')
    
    return response.json()['task_id']

def check_report_status(token, task_id):
    """Проверка статуса отчета"""
    wait_time = ensure_request_interval()
    logger.info(f"Задержка перед запросом: {wait_time:.2f} сек")
    session = create_session()
    url = f"{API_URL}/data/export/tasks/{task_id}"
    headers = {'Authorization': f'token {token}'}
    response = session.get(url, headers=headers)
    response.raise_for_status()
    
    status = response.json()['current_status']
    if status == 'COMPLETED':
        result_id = _get_result_id(token, task_id)
        if result_id:
            
            return result_id
    elif status == 'FAILED':
        raise RuntimeError(f"Task failed: {response.json().get('error_message')}")
    
    return None

def download_report(token, result_id, report_type, date_to):
    """Скачивание готового отчета"""
    wait_time = ensure_request_interval()
    logger.info(f"Задержка перед запросом: {wait_time:.2f} сек")
    session = create_session()
    url = f"{API_URL}/data/export/results/{result_id}/file"
    headers = {'Authorization': f'token {token}'}
    
    response = session.get(url, headers=headers, stream=True)
    response.raise_for_status()
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    file_path = f"{TEMP_DIR}/{report_type}_{date_to}_{result_id}.zip"
    
    with open(file_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return file_path

def _calculate_period(period_type, date_to):
    """Расчет значения периода"""
    from datetime import datetime
    dt_date = datetime.strptime(date_to, '%Y-%m-%d')
    
    if period_type == "1027_IC_Period_Month_11_2019":
        return dt_date.year * 12 + dt_date.month
    elif period_type == "1028_IC_Period_Week":
        return int((dt_date.year - 1970) * 52.1786 + dt_date.isocalendar()[1])
    else:
        raise ValueError(f"Unsupported period type: {period_type}")

def _get_result_id(token, task_id):
    """Получение ID результата"""
    session = create_session()
    url = f"{API_URL}/data/export/results?page=0&size=1000&task_ids={task_id}"
    headers = {'Authorization': f'token {token}'}
    
    response = session.get(url, headers=headers)
    response.raise_for_status()
    
    if response.json()['list']:
        return response.json()['list'][0]['result_id']
    return None