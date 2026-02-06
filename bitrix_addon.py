import requests
import os
import logging

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def _clean_env(value):
    if not value:
        return ""
    return value.strip().strip("'").strip('"')


def _bitrix_headers():
    return {
        "User-Agent": _clean_env(os.getenv("USER_AGENT")) or "Mozilla/5.0",
        "Content-Type": _clean_env(os.getenv("CONTENT_TYPE")) or "application/json"
    }


def _build_bitrix_url(method_name):
    """
    Priority:
    1) BITRIX_WEBHOOK_URL (base URL: https://.../rest/<user>/<token>)
    2) URL_BITRIX_API (legacy full method URL)
    """
    webhook_base = _clean_env(os.getenv("BITRIX_WEBHOOK_URL"))
    if webhook_base:
        return f"{webhook_base.rstrip('/')}/{method_name}.json"

    legacy_method_url = _clean_env(os.getenv("URL_BITRIX_API"))
    if legacy_method_url:
        return f"{legacy_method_url.rsplit('/', 1)[0]}/{method_name}.json"

    raise RuntimeError(
        "Bitrix webhook is not configured. Set BITRIX_WEBHOOK_URL or URL_BITRIX_API in .env"
    )

def get_bitrix_user_by_fullname(fullname):
    """
    Returns a Bitrix24 user by surname/name (and second name when provided).
    Only ACTIVE profiles are eligible.
    """
    def is_active(user):
        active = user.get("ACTIVE")
        if isinstance(active, bool):
            return active
        if isinstance(active, (int, float)):
            return int(active) == 1
        if isinstance(active, str):
            return active.strip().upper() in {"Y", "YES", "TRUE", "1"}
        return False

    def first_active(users):
        for user in users:
            if is_active(user):
                return user
        return None

    try:
        parts = fullname.split()
        if len(parts) < 2:
            logger.warning("Bitrix user lookup requires at least last name and first name")
            return None

        last_name = parts[0]
        first_name = parts[1]
        headers = _bitrix_headers()
        endpoint = _build_bitrix_url("user.search")

        def find_active_user(params, label):
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code != 200:
                logger.warning(
                    "Bitrix user search failed (%s), status=%s",
                    label,
                    response.status_code
                )
                return None

            users = response.json().get("result", [])
            active_user = first_active(users)
            if active_user:
                logger.info("Active Bitrix user found (%s)", label)
                return active_user

            if users:
                logger.info("Bitrix users found but all inactive (%s)", label)
            else:
                logger.info("No Bitrix users found (%s)", label)
            return None

        # Step 1: search by LAST_NAME + FIRST_NAME.
        user = find_active_user(
            {'FILTER[NAME_SEARCH]': f"{last_name} {first_name}"},
            "last_name first_name"
        )
        if user:
            return user

        # Step 2: refine by SECOND_NAME if provided.
        if len(parts) >= 3:
            second_name = parts[2]
            user = find_active_user(
                {
                    'FILTER[NAME_SEARCH]': f"{last_name} {first_name}",
                    'FILTER[SECOND_NAME]': second_name
                },
                "last_name first_name second_name"
            )
            if user:
                return user

        logger.info("No ACTIVE Bitrix24 profile found")
        return None

    except Exception as e:
        logger.exception("Unexpected error in Bitrix user lookup: %s", e)
        return None

def create_bitrix_task_as_user(user_id, task_title, task_description):
    # Заголовки для запроса
    headers = _bitrix_headers()
    task_add_url = _build_bitrix_url("task.item.add")
    
    # Данные для создания задачи
    task_data = {
        "fields": {
            "TITLE": task_title,
            "DESCRIPTION": task_description,
            "RESPONSIBLE_ID": 1,  # ID ответственного
            "CREATED_BY": user_id,  # ID создателя
            "ALLOW_TIME_TRACKING": "N",
            "AUDITORS": [1]  # Массив чисел
        }
    }
    
    try:
        # Отправляем POST запрос для создания задачи
        response = requests.post(
            task_add_url,
            json=task_data,
            headers=headers,
            timeout=15
        )
        
        # Проверяем статус ответа
        if response.status_code == 200:
            result = response.json()
            if 'result' in result:
                logger.info("Bitrix task created successfully (task_id=%s)", result["result"])
                return True
            else:
                logger.error(
                    "Bitrix task create returned error: %s",
                    result.get("error_description", "Unknown error")
                )
                return False
        else:
            logger.error("Bitrix task create request failed (status=%s)", response.status_code)
            return False
            
    except Exception as e:
        logger.exception("Unexpected error while creating Bitrix task: %s", e)
        return False

def create_bitrix_task_with_responsible(creator_id, title, description, responsible_id=None, auditors=None):
    """
    Создает задачу в Bitrix24 с указанием ответственного и аудиторов
    
    Args:
        creator_id (int): ID создателя задачи
        title (str): Заголовок задачи
        description (str): Описание задачи
        responsible_id (int, optional): ID ответственного за задачу
        auditors (list, optional): Список ID аудиторов задачи
    
    Returns:
        bool: True если задача создана успешно, False в противном случае
    """
    # Если ответственный не указан, используем значение по умолчанию (1)
    if responsible_id is None:
        responsible_id = 1
    else:
        try:
            responsible_id = int(responsible_id)
        except (TypeError, ValueError):
            # Если не удалось преобразовать в число, используем значение по умолчанию
            responsible_id = 1
    
    # Преобразуем список аудиторов в список целых чисел
    if auditors is None:
        auditors = [1]  # По умолчанию
    else:
        try:
            # Если auditors - строка, пытаемся преобразовать ее в список
            if isinstance(auditors, str):
                import ast
                try:
                    auditors = ast.literal_eval(auditors)
                except (ValueError, SyntaxError):
                    auditors = auditors.strip('[]').replace("'", "").replace('"', '').split(',')
            
            # Проверяем, что все элементы можно преобразовать в целые числа
            auditors = [int(auditor.strip()) if isinstance(auditor, str) else int(auditor) 
                        for auditor in auditors if auditor and str(auditor).strip()]
            
            # Если список пуст после фильтрации, используем значение по умолчанию
            if not auditors:
                auditors = [1]
        except (TypeError, ValueError) as e:
            logger.warning("Invalid Bitrix auditors list; fallback to default. Details: %s", e)
            auditors = [1]  # В случае ошибки используем значение по умолчанию
    
    # Заголовки для запроса
    headers = _bitrix_headers()
    task_add_url = _build_bitrix_url("task.item.add")
    
    # Данные для создания задачи
    task_data = {
        "fields": {
            "TITLE": title,
            "DESCRIPTION": description,
            "RESPONSIBLE_ID": responsible_id,  # ID ответственного
            "CREATED_BY": creator_id,  # ID создателя
            "ALLOW_TIME_TRACKING": "N",
            "AUDITORS": auditors  # Массив ID аудиторов
        }
    }
    
    try:
        # Отправляем POST запрос для создания задачи
        response = requests.post(
            task_add_url,
            json=task_data,
            headers=headers,
            timeout=15
        )
        
        # Проверяем статус ответа
        if response.status_code == 200:
            result = response.json()
            if 'result' in result:
                logger.info("Bitrix task created successfully (task_id=%s)", result["result"])
                return True
            else:
                logger.error(
                    "Bitrix task create returned error: %s",
                    result.get("error_description", "Unknown error")
                )
                return False
        else:
            logger.error("Bitrix task create request failed (status=%s)", response.status_code)
            return False
            
    except Exception as e:
        logger.exception("Unexpected error while creating Bitrix task: %s", e)
        return False

def create_checkin_task(user_id, num_contract, date, name_brig, phone_brig, carring):
    """
    Создает задачу заезда в Bitrix24
    
    Args:
        user_id (int): ID пользователя в Bitrix24
        num_contract (str): Номер договора
        date (str): Дата заезда
        name_brig (str): ФИО бригадира
        phone_brig (str): Номер телефона бригадира
        carring (str): Грузоподъёмность
    """
    task_title = f"Заезд: {num_contract}"
    task_description = (
        f"Номер договора: {num_contract}\n"
        f"Дата заезда: {date}\n"
        f"ФИО бригадира: {name_brig}\n"
        f"Номер бригадира: {phone_brig}\n"
        f"Грузоподъёмность: {carring}\n"
    )
    
    return create_bitrix_task_as_user(user_id, task_title, task_description)

