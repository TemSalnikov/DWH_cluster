from datetime import datetime, timedelta
# import openpyxl as pyxl
# import json
import uuid
import pandas as pd
from airflow.utils.log.logging_mixin import LoggingMixin
import hashlib

def create_text_hash(row, columns):
    # Объединяем значения столбцов в строку
    combined = ''.join(str(row[col]) for col in columns)
    # Создаем хеш SHA256 и преобразуем в hex-строку
    return hashlib.sha256(combined.encode()).hexdigest()

def extract_custom (path = '', name_report = 'Закупки', name_pharm_chain = 'Антэй') -> dict:
    loger = LoggingMixin().log
    try:
        xls = pd.ExcelFile(path)
        sheet_names = xls.sheet_names
        df = pd.read_excel(path , e)
        df = df.astype(str)
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')

        report_date = df.columns[1]
        period = df.iloc[0,1]
        start_date, end_date = period.split(' - ')
        start_date = datetime.strptime(start_date, "%d.%m.%Y")
        end_date = datetime.strptime(end_date, "%d.%m.%Y")
        if start_date == end_date:
            end_date= end_date + timedelta(days = 1)
        df = df.dropna(how = 'all').reset_index(drop = True)
        start_row = df[df.iloc[:,0] == 'Организация'].index[0]
        headers = df.iloc[start_row].values

        df.columns = headers
        df = df.drop(df.index[:start_row + 3])
        df = df.reset_index(drop=True)

       
        df['uuid_report'] = [str(uuid.uuid4()) for x in range(len(df))]
        df['hash_drugstore'] = df.apply(create_text_hash, columns = ['Организация', 'ИНН', 'Склад'], axis=1)
        df.rename(columns = {'Организация': 'drugstore', 'ИНН':'inn', 'Склад':'address', 'Товар':'product', 'Поставщик':'supplier', 'КолПрих':'quantity', 'ЦенаРасчет':'price', 'СумРасчетПрих':'total_cost'}, inplace=True)
        df_drugstore = df[['hash_drugstore','drugstore', 'inn', 'address']].drop_duplicates()
        df_report = df[['uuid_report','hash_drugstore', 'product', 'supplier', 'quantity', 'price', 'total_cost']]
        df_report['name_report'] = [name_report for x in range(len(df))]
        df_report['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
        df_report['report_date'] = [report_date for x in range(len(df))]
        df_report['start_date'] = [str(start_date) for x in range(len(df))]
        df_report['end_date'] = [str(end_date) for x in range(len(df))]
        df_report['processed_dttm'] = [str(datetime.now()) for x in range(len(df))]
        return {
            'table_report':     df_report,
            'table_drugstor':   df_drugstore
            }

    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise

def extract_remain (path = '', name_report = 'Остатки', name_pharm_chain = 'Антэй') -> dict:
    loger = LoggingMixin().log
    try:
        xls = pd.ExcelFile(path)
        sheet_names = xls.sheet_names
        df = pd.read_excel(path , sheet_names[0])
        df = df.astype(str)
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')

        report_date = df.columns[1]
        period = df.iloc[0,1]
        start_date, end_date = period.split(' - ')
        start_date = datetime.strptime(start_date, "%d.%m.%Y")
        end_date = datetime.strptime(end_date, "%d.%m.%Y")
        if start_date == end_date:
            end_date= end_date + timedelta(days = 1)
            
        start_row = df[df.iloc[:,0] == 'Организация'].index[0]
        headers = df.iloc[start_row].values

        df.columns = headers
        df = df.drop(df.index[:start_row + 3])
        df = df.reset_index(drop=True)

        df['uuid_report'] = [str(uuid.uuid4()) for x in range(len(df))]
        df['hash_drugstore'] = df.apply(create_text_hash, columns = ['Организация', 'ИНН', 'Склад'], axis=1)
        df.rename(columns = {'Организация': 'drugstore', 'ИНН':'inn', 'Склад':'address', 'Товар':'product', 'ОстатокКонец':'quantity'}, inplace=True)
        df_drugstore = df[['hash_drugstore','drugstore', 'inn', 'address']].drop_duplicates()
        df_report = df[['uuid_report','hash_drugstore', 'product', 'quantity']]
        df_report['name_report'] = [name_report for x in range(len(df))]
        df_report['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
        df_report['report_date'] = [report_date for x in range(len(df))]
        df_report['start_date'] = [str(start_date) for x in range(len(df))]
        df_report['end_date'] = [str(end_date) for x in range(len(df))]
        df_report['processed_dttm'] = [str(datetime.now()) for x in range(len(df))]
        return {
            'table_report':     df_report,
            'table_drugstor':   df_drugstore
            }

    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise

def extract_sale (path = '', name_report = 'Продажи', name_pharm_chain = 'Антэй') -> dict:
    loger = LoggingMixin().log
    try:
        xls = pd.ExcelFile(path)
        sheet_names = xls.sheet_names
        df = pd.read_excel(path , sheet_names[0])
        df = df.astype(str)
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')

        report_date = df.columns[1]
        period = df.iloc[0,1]
        start_date, end_date = period.split(' - ')
        start_date = datetime.strptime(start_date, "%d.%m.%Y")
        end_date = datetime.strptime(end_date, "%d.%m.%Y")
        if start_date == end_date:
            end_date= end_date + timedelta(days = 1)

        start_row = df[df.iloc[:,0] == 'Организация'].index[0]
        headers = df.iloc[start_row].values

        df.columns = headers
        df = df.drop(df.index[:start_row + 3])
        df = df.reset_index(drop=True)

        df['uuid_report'] = [str(uuid.uuid4()) for x in range(len(df))]
        df['hash_drugstore'] = df.apply(create_text_hash, columns = ['Организация', 'ИНН', 'Склад'], axis=1)
        df.rename(columns = {'Организация': 'drugstore', 'ИНН':'inn', 'Склад':'address', 'Товар':'product', 'КолРас':'quantity'}, inplace=True)
        df_drugstore = df[['hash_drugstore','drugstore', 'inn', 'address']].drop_duplicates()
        df_report = df[['uuid_report','hash_drugstore', 'product', 'quantity']]
        df_report['name_report'] = [name_report for x in range(len(df))]
        df_report['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
        df_report['report_date'] = [report_date for x in range(len(df))]
        df_report['start_date'] = [str(start_date) for x in range(len(df))]
        df_report['end_date'] = [str(end_date) for x in range(len(df))]
        df_report['processed_dttm'] = [str(datetime.now()) for x in range(len(df))]
        return {
            'table_report':     df_report,
            'table_drugstor':   df_drugstore
            }

    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
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
    extract_xls(path='/home/ubuntu/Загрузки/отчеты/Антей/Закуп/2023/03_2023.xlsx', name_report = 'Закупки', name_pharm_chain = 'Антэй')
