import requests
import subprocess
import tempfile
import re
import os
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

import time
import csv

# task_id = 'caa506de-52f0-412f-adfa-f8e618a757b6'
# token = '57917097-2d9a-4be7-b62e-0619354ee113'

# 1. Создаём адаптер с ГОСТ-шифрами
class GOSTAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers="GOST2012-GOST8912-GOST8912")
        kwargs["ssl_context"] = context  # Передаём контекст в urllib3
        return super().init_poolmanager(*args, **kwargs)

# 2. Настраиваем сессию
session = requests.Session()
session.mount("https://", GOSTAdapter())

# 3. Указываем сертификаты (если есть) и отключаем проверку (при необходимости)
session.verify = False  # Не для продакшена!
session.cert = ("/home/ubuntu/cert.pem", "/home/ubuntu/key.pem")  # Пути к сертификату и ключу

# Конфигурация
API_URL = "https://api.mdlp.crpt.ru/api/v1"
CLIENT_ID = "0dc92a9d-50e2-4d01-8c2c-f9a0ef27ff31"
CLIENT_SECRET = "21842175-2a01-43d7-86f8-dc5f3f3aabfe"
USER_ID = "F8851B3675EC0C2CD9664A83C46CE62FC5F594EB" # Отпечаток сертификата
CERT_SUBJECT = "Благодаренко Юрий Юрьевич"  # CN сертификата
EXPORT_TASKS_URL = f"{API_URL}/data/export/tasks"
TASK_STATUS_URL = f"{API_URL}/data/export/tasks/{{task_id}}"
GET_RESULT_ID_URL = f"{API_URL}/data/export/results?page=0&size=1000&task_ids={{task_id}}"
GET_MAX_TASKS_COUNT_URL = f"{API_URL}/export/tasks/settings"
GET_LIST_TASKS_URL = f"{API_URL}/data/export/tasks/search"
GET_REF_EGRUL = f"{API_URL}/reestr/egrul"
GET_REF_EGRPI = f"{API_URL}/reestr/egrip"
DOWNLOAD_URL = f"{API_URL}/data/export/results/{{result_id}}/file"
DELTE_RESULT_ID_URL = f"{API_URL}/data/export/results/{{result_id}}"

# data_interval_start = "2025-06-11 00:01:01"
# data_interval_end = "2025-06-20 00:01:01"

REPORT_TYPES = [
    "GENERAL_PRICING_REPORT",
    "GENERAL_REPORT_ON_MOVEMENT",
    "GENERAL_REPORT_ON_REMAINING_ITEMS",
    "GENERAL_REPORT_ON_DISPOSAL"
]

def get_auth_code():
    """Получение кода аутентификации"""
    url = f"{API_URL}/auth"
    payload = {
        "client_secret": CLIENT_SECRET,
        "client_id": CLIENT_ID,
        "user_id": USER_ID,
        "auth_type": "SIGNED_CODE"
    }
    # payload = {
    #     "client_secret": "21842175-2a01-43d7-86f8-dc5f3f3aabfe",
    #     "client_id": "0dc92a9d-50e2-4d01-8c2c-f9a0ef27ff31",
    #     "user_id": "F8851B3675EC0C2CD9664A83C46CE62FC5F594EB",
    #     "auth_type": "SIGNED_CODE"
    #     }
    headers = {'Content-Type': 'application/json;charset=UTF-8'}
    
    #logger.info(f"Запрос кода аутентификации: {url}")
    response = session.get(url)
    response = session.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    #logger.info(f"Ответ получен: {response.status_code}")
    return response.json()['code']


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
        
        #logger.info(f"Выполнение команды: {' '.join(command)}")
        
        # Выполняем команду
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Проверяем результат выполнения
        if result.returncode != 0:
            #logger.error(f"Ошибка подписи: {result.stderr}")
            raise Exception(f"Ошибка подписи: {result.stderr}")
        
        # Читаем результат подписи
        with open(output_file_path, 'r') as f:
            signature = f.read()
        
        # Удаляем заголовки и переносы строк
        signature = re.sub(
            r'-----(BEGIN|END) SIGNATURE-----|[\s\n]+', 
            '', 
            signature
        )
        
        #logger.info("Данные успешно подписаны")
        return signature
    
    except subprocess.CalledProcessError as e:
        #logger.error(f"Ошибка выполнения команды: {e.stderr}")
        raise
    except Exception as e:
        #logger.error(f"Ошибка при подписании данных: {str(e)}")
        raise
    finally:
        # Удаляем временные файлы
        if os.path.exists(input_file_path):
            os.remove(input_file_path)
        if os.path.exists(output_file_path):
            os.remove(output_file_path)


def get_session_token(auth_code: str, signature: str):
    """Получение токена доступа"""
    url = f"{API_URL}/token"
    payload = {
        "code": auth_code,
        "signature": signature
    }
    headers = {'Content-Type': 'application/json'}
    
    #logger.info(f"Запрос токена сессии: {url}")
    response = session.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    token_data = response.json()
    #logger.info(f"Токен получен, срок жизни: {token_data['life_time']} минут")
    return token_data['token']


# period расчитывается по формуле из документации API МДЛП 
# если period_type = 1027_IC_Period_Month_11_2019, то period = текущий_год * 12 +номер_месяца_в_году_выгрузки.
# если period_type = 1028_IC_Period_Week, то period = (год_выгрузки - 1970) * 52,1786 + номер_недели_в_году_выгрузки.
def create_report_task(report_type, token, period = "24305",  period_type = "1027_IC_Period_Month_11_2019"): 
    """Создание задачи на формирование отчета"""
    headers = {
        'Authorization': f'token {token}',
        'Content-Type': 'application/json'
    }
    
    # Параметры запроса (настраиваются под конкретные нужды)
    payload = {
        "report_id": report_type,
        "params": {
            "1026_IC_Period_Type_WM": period_type,
            "1027_IC_Period_Month_11_2019": period
            # "date_from": "{data_interval_start}",
            # "date_to": "{data_interval_end}"
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

def _get_result_id(task_id, token):
    """Проверка статуса задачи (внутренняя функция для сенсора)"""
    headers = {'Authorization': f'token {token}'}
    url = GET_RESULT_ID_URL.format(task_id=task_id)
    response = session.get(
        url,
        headers=headers
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to check task status: {response.text}")
    result = response.json()
    if result['list']:
        return result['list'][0]
    return

def check_report_status(task_id, token):
    """Проверка статуса задачи (внутренняя функция для сенсора)"""
    headers = {'Authorization': f'token {token}'}
    url = TASK_STATUS_URL.format(task_id=task_id)
    response = session.get(
        url,
        headers=headers
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"Failed to check task status: {response.text}")
    
    status = response.json()['current_status']
    if status == 'COMPLETED':
        # return _get_result_id(task_id, token)
        result_data = _get_result_id(task_id, token)
        if result_data['download_status'] == "SUCCESS" and result_data['available'] == "AVAILABLE":
            return result_data['result_id']
        else: return False
    elif status == 'FAILED':
        raise RuntimeError(f"Task failed: {response.json().get('error_message', 'Unknown error')}")
    
    return False


def download_report(report_type, token, result_id):
    """Скачивание готового отчета"""
    # Проверяем статус и получаем result_id
    
    
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
    
    # Сохраняем файл временно
    file_path = f"/tmp/{report_type}_{result_id}.zip"
    with open(file_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return file_path

def complete_report(result_id, token, file_path):
    """Проверка загрузки файла и удаление выгрузки на стороне МДЛП"""
    if file_path:
        headers = {'Authorization': f'token {token}'}
        url = DELTE_RESULT_ID_URL.format(result_id=result_id)
        response = session.delete(
            url,
            headers=headers
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to check task status: {response.text}")
        return response.json()
    raise RuntimeError(f"Failed to download report: {response.text}")
    

# def wait_for_report(report_type, task_id, token):
#         return PythonSensor(
#             task_id=f'wait_for_{report_type}',
#             python_callable=lambda: check_report_status(task_id, token),
#             op_kwargs={},
#             mode='poke',
#             poke_interval=5 * 60,  # Проверка каждые 5 минут
#             timeout=24 * 60 * 60,   # Таймаут 24 часа
#             exponential_backoff=True,
#             soft_fail=False
        # )

def _get_max_tasks_count(token):
    """Проверка статуса задачи (внутренняя функция для сенсора)"""
    headers = {'Authorization': f'token {token}'}
    url = GET_MAX_TASKS_COUNT_URL
    response = session.get(
        url,
        headers=headers
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to check task status: {response.text}")
    return response.json()
    
def _get_list_tasks(token):
    """Проверка статуса задачи (внутренняя функция для сенсора)"""
    headers = {'Authorization': f'token {token}'}
    url = GET_LIST_TASKS_URL
    response = session.post(
        url,
        headers=headers,
        json={
                "current_statuses": ["PREPARATION","COMPLETED", "FAILED"]
            }
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to check task status: {response.text}")
    return response.json()

def _get_ref_egrul(token):
    """Проверка статуса задачи (внутренняя функция для сенсора)"""
    headers = {'Authorization': f'token {token}'}
    url = GET_REF_EGRUL
    response = session.get(
        url,
        headers=headers
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to check task status: {response.text}")
    return response.json()
def _get_ref_egrpi(token):
    """Проверка статуса задачи (внутренняя функция для сенсора)"""
    headers = {'Authorization': f'token {token}'}
    url = GET_REF_EGRPI
    response = session.get(
        url,
        headers=headers
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to check task status: {response.text}")
    return response.json()

if __name__=="__main__":
    # result_id = check_report_status(task_id, token)
    # file_path = download_report("GENERAL_PRICING_REPORT",  token, result_id)
    # complete = complete_report(task_id, token, file_path)
    # print(file_path)

    # result_id = check_report_status(task_id, token)
    # print(result_id)

    auth_code = get_auth_code()
    auth_signature = sign_data(auth_code)
    session_token = get_session_token(auth_code, auth_signature)

    # egrul = _get_ref_egrul(session_token)
    # print(egrul)
    # egrpi = _get_ref_egrpi(session_token)
    # print(egrpi)
    # max_count_tasks = _get_max_tasks_count(session_token)
    # print(max_count_tasks)

    # list_tasks =  _get_list_tasks(session_token)
    # print(list_tasks)
    task_ids = []
    # task_ids =[
    #         {'task_id':'e52e612d-53cc-4081-b737-26fc334362b8', 'report_type':"GENERAL_PRICING_REPORT"},
    #         {'task_id':'6547ce9b-5b74-4cdb-8ad6-094a60334d13', 'report_type':"GENERAL_REPORT_ON_MOVEMENT"},
    #         {'task_id':'5bada038-439e-4a9a-b400-a5f6dde9cbbf', 'report_type':"GENERAL_REPORT_ON_REMAINING_ITEMS"},
    #         {'task_id':'4f527b14-5e3c-4a27-9779-62df6118362e', 'report_type':"GENERAL_REPORT_ON_DISPOSAL"}]
    for report_type in REPORT_TYPES:
        task = create_report_task(report_type, session_token, period='24302')
        task_ids.append({'task_id': task, 'report_type': report_type})
        time.sleep(61)
    for task_id in task_ids:

        # wait_sensor = wait_for_report(report_type, task_id, session_token)
        result_id = check_report_status(task_id['task_id'], session_token)
        file_path = download_report(task_id['report_type'],  session_token, result_id)
        time.sleep(61)
        print(file_path)
    #нельза использовать complete_report пока нет прав доступа: GENERAL_PRICING_REPORT /
    # #GENERAL_REPORT_ON_MOVEMENT / GENERAL_REPORT_ON_REMAINING_ITEMS /
    # #GENERAL_REPORT_ON_DISPOSAL / VIRTUAL_WAREHOUSE_REPORT (в зависимости от
    # #типа задания на выгрузку)
    #     #complete = complete_report(task_id, session_token, file_path) 
    