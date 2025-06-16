import pymssql

# Параметры подключения к SSAS
server = '194.190.8.171:47366'  # Адрес сервера SSAS
database = 'tabular-model.mdlp-no-part'  # Имя базы данных SSAS
user = 'Altayvitamin'  # Имя пользователя
password = '5nrNv_Z29r'  # Пароль
# ssl_cert = 'path/to/your/ssl/certificate.pem'  # Путь к сертификату SSL (если требуется)
# ssl_key = 'path/to/your/ssl/private.key.pem' # Путь к ключу SSL (если требуется)
# ssl_verify = False # Установите в True, если нужно проверять сертификат

try:
    # Создаем подключение к SSAS с использованием SSL
    conn = pymssql.connect(
        server=server,
        database=database,
        user=user,
        password=password,
        # ssl_cert=ssl_cert,  # Добавьте, если используется сертификат
        # ssl_key=ssl_key,  # Добавьте, если используется ключ
        # ssl_verify=ssl_verify # Добавьте, если нужно проверять сертификат
    )

    # Получаем курсор для выполнения запросов
    cursor = conn.cursor()

    # Выполняем запрос
    sql = 'SELECT * FROM your_table'
    cursor.execute(sql)

    # Получаем результаты запроса
    for row in cursor.fetchall():
        print(row)

except pymssql.Error as e:
    print(f"Ошибка подключения: {e}")
finally:
    # Закрываем подключение
    if 'conn' in locals() and conn:
        conn.close()