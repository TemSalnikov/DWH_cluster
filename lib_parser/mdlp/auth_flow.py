from datetime import datetime
from airflow.decorators import dag, task
from airflow.models import Variable
import requests
import uuid
import base64
import os
import subprocess
import tempfile
import logging
import re

# Конфигурация
API_URL = "https://api.sb.mdlp.crpt.ru/api/v1"
CLIENT_ID = Variable.get("MDLP_CLIENT_ID")
CLIENT_SECRET = Variable.get("MDLP_CLIENT_SECRET")
USER_ID = Variable.get("MDLP_USER_ID")  # Отпечаток сертификата
CERT_SUBJECT = Variable.get("MDLP_CERT_SUBJECT")  # CN сертификата

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mdlp_api")

@dag(
    schedule_interval=None,
    start_date=datetime(2023, 1, 1),
    catchup=False,
    tags=['mdlp_api'],
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
    def prepare_document():
        """Подготовка XML документа"""
        doc = """
        <documents xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="1.27">
            <register_end_packing action_id="311">
                <subject_id>0000000100930</subject_id>
            </register_end_packing>
        </documents>
        """
        # Удаляем лишние пробелы и переносы
        return ' '.join(doc.split())

    @task
    def send_document(token: str, document: str, doc_signature: str):
        """Отправка документа в систему"""
        url = f"{API_URL}/documents/send"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'token {token}'
        }
        
        # Кодируем документ в base64
        document_b64 = base64.b64encode(document.encode('utf-8')).decode('utf-8')
        
        payload = {
            "document": document_b64,
            "sign": doc_signature,
            "request_id": str(uuid.uuid4())
        }
        
        logger.info(f"Отправка документа: {url}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Документ отправлен, ID: {result['document_id']}")
        return result

    # Поток выполнения задач
    auth_code = get_auth_code()
    auth_signature = sign_data(auth_code)
    session_token = get_session_token(auth_code, auth_signature)
    
    document = prepare_document()
    doc_signature = sign_data(document, is_document=True)
    
    send_document(session_token, document, doc_signature)

mdlp_dag = wf_mdlp_kafka_mart_mdlp_report()