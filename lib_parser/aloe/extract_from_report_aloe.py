from datetime import datetime, timedelta
# import openpyxl as pyxl
import json
import uuid
import pandas as pd
from airflow.utils.log.logging_mixin import LoggingMixin
import hashlib


def create_text_hash(row, columns):
    # Объединяем значения столбцов в строку
    combined = ''.join(str(row[col]) for col in columns)
    # Создаем хеш SHA256 и преобразуем в hex-строку
    return hashlib.sha256(combined.encode()).hexdigest()

def extract_data(path = '', sheet_name = '', name_pharm_chain = ''):
    loger = LoggingMixin().log
    try: 
        df = pd.read_excel(path , sheet_name)
        df = df.astype(str)
        # df['name_report'] = sheet_name
        # df['name_pharm_chain'] = name_pharm_chain
        # df['processed_dttm'] = [str(datetime.datetime.now()) for x in range(len(df))]
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')
    except Exception as e:
        loger.error(f'{str(e)}', exc_info=True)
        raise
    return df

def table_conversion(df: pd.DataFrame):
    # Удаление пустых строк и строк с метаданными
    df = df.dropna(how='all').reset_index(drop=True)

    period_str = df.iloc[0,1]

    dates_str = period_str.split(":")[1].strip()  # "01.06.2023 - 30.06.2023"
    start_date_str, end_date_str = dates_str.split("\xa0-\xa0")

    # Преобразуем строки в объекты datetime
    start_date = datetime.strptime(start_date_str, "%d.%m.%Y").date()
    end_date = datetime.strptime(end_date_str, "%d.%m.%Y").date()

    # Если даты равны, прибавляем 1 день к end_date
    if start_date == end_date:
        end_date += timedelta(days=1)

    start_row = df[df.iloc[:, 0] == 'Номенклатура'].index[0]

    apteka_addresses = df.iloc[start_row, 1:].tolist()  # Берем все столбцы, кроме первого

    # Данные начинаются со строки start_row + 2
    data = df.iloc[start_row + 2:, :].copy()
    data.columns = ['Номенклатура'] + apteka_addresses  # Устанавливаем правильные заголовки

    # Преобразуем таблицу: каждая аптека становится отдельной строкой
    result = pd.DataFrame(columns=['Номенклатура', 'Количество', 'Аптека'])

    for apteka in apteka_addresses:
        temp_df = data[['Номенклатура', apteka]].copy()
        temp_df.columns = ['Номенклатура', 'Количество']
        temp_df['Аптека'] = apteka
        result = pd.concat([result, temp_df], ignore_index=True)

    # Удаляем строки, где количество NaN или 0
    result = result.dropna(subset=['Количество'])
    result['Количество'] = pd.to_numeric(result['Количество'], errors='coerce')
    result = result.dropna(subset=['Количество'])

    result['start_date'] = [str(start_date) for x in range(len(result))]
    result['end_date'] = [str(end_date) for x in range(len(result))]

    # Сбрасываем индексы и выводим результат
    result = result.reset_index(drop=True)
    # print(result)
    return result

def transform_xl_to_json (path = '',sheet_name = 'Sheet1' , name_report = 'Закуп_Продажи_Остатки', name_pharm_chain = 'Алоэ') -> dict:
    loger = LoggingMixin().log
    try:
        xls = pd.ExcelFile(path)
        sheet_names = xls.sheet_names
        df = pd.read_excel(path , sheet_names[0])
        df = df.astype(str)
        loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')


        
        df_drugstore = df[['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'ID аптеки', 'Адрес аптеки']].drop_duplicates()
        df_supplier = df[['Поставщик', 'ИНН поставщика']].drop_duplicates()
        df_product = df[['SKU Наименование', 'SKU ID', 'Производитель']].drop_duplicates()
        # df_drugstore['uuid_drugstore'] = [str(uuid.uuid4()) for x in range(len(df_drugstore))]
        # df_supplier['uuid_supplier'] = [str(uuid.uuid4()) for x in range(len(df_supplier))]
        # df_product['uuid_product'] = [str(uuid.uuid4()) for x in range(len(df_product))]

        df_drugstore['hash_drugstore'] = df_drugstore.apply(create_text_hash, columns = ['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'Адрес аптеки'], axis=1)
        df_drugstore['hash_drugstore_addr'] = df_drugstore.apply(create_text_hash, columns = ['Адрес аптеки'], axis=1)
        df_supplier['hash_supplier'] = df_supplier.apply(create_text_hash, columns = ['Поставщик', 'ИНН поставщика'], axis=1)
        df_product['hash_product'] = df_product.apply(create_text_hash, columns = ['SKU Наименование', 'SKU ID'], axis=1)

        df['uuid_report'] = [str(uuid.uuid4()) for x in range(len(df))]
        # df['name_report'] = [name_report for x in range(len(df))]
        # df['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
        # df['processed_dttm'] = [str(datetime.datetime.now()) for x in range(len(df))]
        df = df.merge(df_drugstore, on = ['Бренд аптеки', 'ЮЛ аптеки', 'ИНН аптеки', 'ID аптеки', 'Адрес аптеки'], how = 'left')
        df = df.merge(df_supplier, on = ['Поставщик', 'ИНН поставщика'], how = 'left')
        df = df.merge(df_product, on = ['SKU Наименование', 'SKU ID', 'Производитель'], how = 'left')
        df_report = df[['uuid_report', 'Период', 'Количество, уп','Сумма ЗЦ, руб. без НДС', 'hash_drugstore', 'hash_drugstore_addr', 'hash_supplier', 'hash_product']]
        df_report.rename(columns = {'Период':'period', 'Количество, уп':'quantity',
        'Сумма ЗЦ, руб. без НДС':'total_cost'}, inplace=True)
        # df_report['name_report'] = [name_report for x in range(len(df))]
        # df_report['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
        df_report['processed_dttm'] = [str(datetime.datetime.now()) for x in range(len(df))]
        df_drugstore.rename(columns = {'Бренд аптеки': 'name', 'ЮЛ аптеки': 'legal_name', 'ИНН аптеки':'inn', 'ID аптеки':'id', 'Адрес аптеки':'address'}, inplace=True)
        df_supplier.rename(columns={'Поставщик':'name', 'ИНН поставщика':'inn'}, inplace=True)
        df_product.rename(columns={'SKU Наименование':'name', 'SKU ID':'id', 'Производитель':'manufacturer'}, inplace=True)
        # dict_report = df_report.to_dict(orient="split")
        # dict_drugstor = df_drugstore.to_dict(orient="split")
        # dict_supplier = df_supplier.to_dict(orient="split")
        # dict_product = df_product.to_dict(orient="split")
        # dict_result = {
        #     'name_pharm_chain': name_pharm_chain,
        #     'name_report':      name_report,
        #     'processed_dttm':   str(datetime.datetime.now()),
        #     'table_report':     dict_report,
        #     'table_drugstor':   dict_drugstor,
        #     'table_suplier':    dict_supplier,
        #     'table_product':    dict_product
        #     }
        # json_result = json.dumps(dict_result).encode('utf-8')
        loger.info(f'Операция преобразования данных успешно выполнена!')
        # for _, row in df_drugstore.iterrows():
        #     json_row = row.to_json()
        return {
            'table_report':     df_report,
            'table_drugstor':   df_drugstore,
            'table_suplier':    df_supplier,
            'table_product':    df_product
            }
    except Exception as e:
        loger.info(f'ERROR: {str(e)}', exc_info=True)
        raise
    # print(df.head())
    # print (df.columns)
    

if __name__ == "__main__":
    # transform_xl_to_json(path='/home/ubuntu/Загрузки/отчеты/36,6/закуп/2024/12_2024.xlsx')
    df = extract_data(path='/home/ubuntu/Загрузки/отчеты/Алоэ/Закуп_Продажи_Остатки/2025/01_2025.xlsx', sheet_name = 'продажи')
    result = table_conversion(df)
    print(result)
    