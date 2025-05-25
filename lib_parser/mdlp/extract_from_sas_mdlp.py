import requests
import pandas as pd
from xml.etree import ElementTree as ET

def connect():
    # Настройки подключения
    server = "194.190.8.171:47366"  # или IP-адрес
    database = "tabular-model.composite-no-part"
    username = "altayvitamin"
    password = "5nrNv_Z29r"

    # URL endpoint (обычно это /msmdpump.dll или /olap/msmdpump.dll)
    endpoint = f"https://{server}/olap/msmdpump.dll"

    # SOAP-запрос для выполнения DAX
    soap_request = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <Execute xmlns="urn:schemas-microsoft-com:xml-analysis">
        <Command>
            <Statement>EVALUATE YourTable</Statement>
        </Command>
        <Properties>
            <PropertyList>
            <Catalog>{database}</Catalog>
            <Format>Tabular</Format>
            </PropertyList>
        </Properties>
        </Execute>
    </soap:Body>
    </soap:Envelope>"""

    # Отправка запроса
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "urn:schemas-microsoft-com:xml-analysis:Execute"
    }

    response = requests.post(
        endpoint,
        data=soap_request,
        headers=headers,
        auth=requests.auth.HTTPBasicAuth(username, password),
        verify=True  # Отключить, если используете самоподписанный сертификат
    )

    # Обработка ответа
    root = ET.fromstring(response.content)
    rows = []
    columns = []

    for cell in root.findall(".//{urn:schemas-microsoft-com:xml-analysis:rowset}row"):
        row = {}
        for child in cell:
            row[child.tag.split("}")[1]] = child.text
        rows.append(row)

    df = pd.DataFrame(rows)
    print(df.head())



    

if __name__ == "__main__":
    connect()