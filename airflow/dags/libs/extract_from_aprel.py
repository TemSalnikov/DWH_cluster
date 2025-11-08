from datetime import datetime, timedelta
import hashlib
import pandas as pd
import os

def create_text_hash(row, columns):
    # Объединяем значения столбцов в строку
    combined = ''.join(str(row[col]) for col in columns)
    # Создаем хеш SHA256 и преобразуем в hex-строку
    return hashlib.sha256(combined.encode()).hexdigest()


def extract_custom (path = '', name_report = 'Закупки', name_pharm_chain = 'Апрель') -> dict:
    #loger = LoggingMixin().log
    try:
        report_date = os.path.basename(path).split('.')[0]
        print(report_date)
    except Exception as e:
        print(f'ERROR: {str(e)}')
        raise



def extract_xls (path, name_report, name_pharm_chain) -> dict:
    if name_report == 'Закупки':
        return extract_custom(path, name_report, name_pharm_chain)
    if name_report == 'Остатки':
        return extract_remain(path, name_report, name_pharm_chain)
    if name_report == 'Продажи':
        return extract_sale(path, name_report, name_pharm_chain)
    return {}

if __name__ == "__main__":
    extract_xls(path='/home/ubuntu/Загрузки/отчеты/Апрель/Закуп/2023/12_2024.xlsx', name_report = 'Закупки', name_pharm_chain = 'Апрель')