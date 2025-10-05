import os
import sys
import zipfile
import pandas as pd
import json
from datetime import datetime
from deep_translator import GoogleTranslator
import argparse
import uuid

# Добавляем путь к библиотекам
sys.path.append(os.path.join(os.path.dirname(__file__), 'libs'))
from kafka_producer_common_for_xls import create_producer, send_dataframe

def translate_columns(columns):
    """Перевод названий столбцов с русского на английский"""
    translated = []
    for col in columns:
        # if "ИНН" in col:
        #     translated.append(col.replace("ИНН", "INN"))
        # elif "ГТИН" in col or "GTIN" in col:
        #     translated.append("gtin")
        # else:
        try:
            # Пытаемся перевести
            trans = GoogleTranslator(source='ru', target='en').translate(col)
            # Нормализация названия столбца
            trans = (trans.lower()
                        .replace(',', '')
                        .replace('.', '')
                        .replace(' ', '_')
                        .replace('-', '_')
                        .replace('__', '_'))
            translated.append(trans)
        except:
            # Fallback: транслитерация
            translated.append(col)
    return translated

def extract_report(zip_path):
    try:
        # Извлечение из архива
        extract_dir = "/tmp/mdlp/extracted"
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            if not file_list:
                print({"status": "error", "message": "Empty ZIP archive"})
                raise
                
            csv_filename = file_list[0]
            zip_ref.extract(csv_filename, extract_dir)
            csv_path = os.path.join(extract_dir, csv_filename)
            # Очистка
            # os.remove(zip_path)
            return csv_path
    except Exception as e:
        print(f'Error:{e}')
        raise
def check_data_inreport(csv_path):
    df = pd.read_csv(csv_path, encoding='utf-8')
        
    if df.empty or len(df) < 3:
        # res = {"status": "empty", "report_type": report_type, "date_to": date_to}
        # print(res)
        # raise
        return False
    return True

def process_report(csv_path, report_type, date_to):
    """Обработка отчёта: извлечение, преобразование и отправка в Kafka"""
    try:
        # # Извлечение из архива
        # extract_dir = "/tmp/extracted"
        # os.makedirs(extract_dir, exist_ok=True)
        
        # with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        #     file_list = zip_ref.namelist()
        #     if not file_list:
        #         print({"status": "error", "message": "Empty ZIP archive"})
        #         raise
                
        #     csv_filename = file_list[0]
        #     zip_ref.extract(csv_filename, extract_dir)
        #     csv_path = os.path.join(extract_dir, csv_filename)
        
        # Чтение CSV
        df = pd.read_csv(csv_path, encoding='utf-8')
        df = df.astype(str)
        # if df.empty or len(df) < 3:
        #     res = {"status": "empty", "report_type": report_type, "date_to": date_to}
        #     print(res)
        #     # raise
        #     return False
        
        # Добавление метаданных
        df['type_report'] = report_type
        df['date_to'] = date_to
        df['create_dttm'] = str(datetime.now())
        df['deleted_flag'] = False
        df['uuid_report'] = str(uuid.uuid4())

        print(f'columns under translate: {df.columns}')
        
        # Перевод названий столбцов
        columns= translate_columns(df.columns)
        print(f'columns after translate: {columns}')
        df.columns = columns
        
        # Отправка в Kafka
        bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka1:19092,kafka2:19092,kafka3:19092").split(',')
        producer = create_producer(bootstrap_servers)
        topic_name = f"mdlp_{report_type.lower()}"
        send_dataframe(producer, topic_name, df)
        producer.close()
        
        # Очистка
        os.remove(csv_path)
        
        
        # return {"status": "success", "report_type": report_type, "date_to": date_to}
        res = {"status": "success", "report_type": report_type, "date_to": date_to}
        print(res)
        # return str(res)
    
    except Exception as e:
        print({"status": "error", "message": str(e), "report_type": report_type, "date_to": date_to})
        raise

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)

    process_parser = subparsers.add_parser('process_report')
    process_parser.add_argument('--csv-path', required=True)
    process_parser.add_argument('--report-type', required=True)
    process_parser.add_argument('--date-to', required=True)

    extract_parser = subparsers.add_parser('extract_report')
    extract_parser.add_argument('--zip-path', required=True)

    check_data_parser = subparsers.add_parser('check_data_inreport')
    check_data_parser.add_argument('--csv-path', required=True)
  


    args = parser.parse_args()

    try:
        if args.command == 'process_report':
            result = process_report(args.csv_path, args.report_type, args.date_to)
            print(json.dumps(result))
            
        elif args.command == 'extract_report':
            result = extract_report(args.zip_path)
            print(result)
            
        elif args.command == 'check_data_inreport':
            result = check_data_inreport(args.csv_path)
            print(result)

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    
    # result = process_report(args.zip_path, args.report_type, args.date_to)
    # print(json.dumps(result))