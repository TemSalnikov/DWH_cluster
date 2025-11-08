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
        return df
    except Exception as e:
        loger.error(f'{str(e)}', exc_info=True)
        raise
    

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

def extract_xls (path = '', name_report = 'Закуп_Продажи_Остатки', name_pharm_chain = 'Алоэ') -> dict:
    loger = LoggingMixin().log
    result = []
    try:
        xls = pd.ExcelFile(path)
        sheet_names = xls.sheet_names
        for sheet_name in sheet_names:
            df = pd.read_excel(path , sheet_name)
            df = df.astype(str)
            loger.info(f'Успешно получено {df[df.columns[0]].count()} строк!')
            
            param_row = df[df.iloc[:,0] == 'Параметры:'].index[0]
            period = df.iloc[param_row,1].split(':')[1].strip()
            start_date, end_date = period.split(' - ')
            start_date = datetime.strptime(start_date, "%d.%m.%Y")
            end_date = datetime.strptime(end_date, "%d.%m.%Y")
            if start_date == end_date:
                end_date= end_date + timedelta(days = 1)

            df = df.dropna(how = 'all').reset_index(drop = True)
            start_row = df[df.iloc[:,0] == 'Номенклатура'].index[0]
            headers = df.iloc[start_row].values
            df.columns = headers
            df = df.drop(df.index[:start_row + 2])
            df = df.reset_index(drop=True)

            
            df = df.dropna(subset=['Номенклатура'])
            if sheet_name.lower() != 'закупки':
                # Преобразование таблицы в длинный формат
                df = df.melt(
                    id_vars='Номенклатура', 
                    var_name='Контрагент', 
                    value_name='Итого'
                )
            
            df = df.dropna(subset=['Количество'])
            df = df.reset_index(drop=True)
            df.rename(columns = {'Номенклатура': 'product', 'Контрагент': 'drugstor', 'Количество':'quantity'}, inplace=True)
            df['uuid_report'] = [str(uuid.uuid4()) for x in range(len(df))]
            df['processed_dttm'] = [str(datetime.datetime.now()) for x in range(len(df))]
            df['name_report'] = [sheet_name.lower() for x in range(len(df))]
            df['name_pharm_chain'] = [name_pharm_chain for x in range(len(df))]
            df['start_date'] = [str(start_date) for x in range(len(df))]
            df['end_date'] = [str(end_date) for x in range(len(df))]

            result.append(df)
            
        result_df = pd.concat(result)
         
        return {
            'table_report':     result_df
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
    