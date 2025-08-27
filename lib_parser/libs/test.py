from mdlp_api_client import (  # Предполагается, что этот модуль уже создан
    get_auth_code,
    get_session_token,
    create_report_task,
    check_report_status,
    download_report)
from sign_data import sign_data

if __name__ == "__main__":
    auth_code = get_auth_code()
    print(str(auth_code))
    sign_d = sign_data(auth_code)
    print(sign_d)