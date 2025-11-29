"""
Модуль для работы с базой данных дневника питания

CRUD операции для таблицы food_logs
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class FoodLog:
    """Модель записи о еде в БД"""
    id: Optional[int]
    user_id: str
    created_at: str  # ISO datetime
    event_date: str  # YYYY-MM-DD
    meal_type: str  # breakfast|lunch|dinner|snack|unknown
    items_json: str  # JSON массив items
    raw_text: str
    source: str  # 'telegram'
    parse_mode: str  # 'rules'|'llm'
    tz: str


def init_food_db(database_file: str):
    """
    Инициализирует таблицу food_logs в БД
    
    Args:
        database_file: Путь к файлу БД SQLite
    """
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS food_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            event_date TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            items_json TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            source TEXT DEFAULT 'telegram',
            parse_mode TEXT DEFAULT 'rules',
            tz TEXT NOT NULL
        )
    ''')
    
    # Создаём индексы для быстрого поиска
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_food_user_date 
        ON food_logs(user_id, event_date)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_food_created 
        ON food_logs(created_at)
    ''')
    
    # Индекс для быстрого поиска последней записи пользователя
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_food_logs_user_created 
        ON food_logs(user_id, created_at, id)
    ''')
    
    conn.commit()
    conn.close()
    logging.info("Таблица food_logs инициализирована")


def save_food_log(
    database_file: str,
    user_id: str,
    event_date: str,
    meal_type: str,
    items: List[Dict[str, Any]],
    raw_text: str,
    parse_mode: str = 'rules',
    tz: str = 'Europe/Moscow'
) -> int:
    """
    Сохраняет запись о еде в БД
    
    Args:
        database_file: Путь к файлу БД
        user_id: ID пользователя Telegram
        event_date: Дата события (YYYY-MM-DD)
        meal_type: Тип приёма пищи (breakfast|lunch|dinner|snack|unknown)
        items: Список продуктов [{"name": "...", "qty_text": "...", "grams": null, "ml": null}]
        raw_text: Исходный текст сообщения
        parse_mode: Режим парсинга ('rules'|'llm')
        tz: Временная зона
        
    Returns:
        ID созданной записи
        
    Raises:
        ValueError: Если event_date в будущем (дополнительная защита от обхода)
    """
    # Дополнительная валидация даты (защита от обхода)
    try:
        import pytz
        from datetime import datetime
        from features.food.date_validation import validate_food_date
        
        now_dt = datetime.now(pytz.timezone(tz))
        is_valid, error_msg = validate_food_date(event_date, now_dt, tz)
        
        if not is_valid:
            logging.error(f"Попытка сохранить запись с будущей датой (обход валидации): user_id={user_id}, event_date={event_date}, today={now_dt.date()}")
            raise ValueError(error_msg or "Нельзя записывать питание будущим числом")
    except ValueError:
        # Пробрасываем ValueError дальше (это ошибка валидации)
        raise
    except ImportError:
        # Если модуль валидации недоступен, пропускаем проверку (fail-safe)
        logging.warning("Модуль date_validation недоступен, пропускаем дополнительную валидацию")
    except Exception as e:
        # В случае других ошибок валидации - логируем, но не блокируем (fail-safe)
        logging.warning(f"Ошибка дополнительной валидации даты: {e}")
    
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    
    created_at = datetime.now().isoformat()
    items_json = json.dumps(items, ensure_ascii=False)
    
    cursor.execute('''
        INSERT INTO food_logs (user_id, created_at, event_date, meal_type, items_json, raw_text, source, parse_mode, tz)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        str(user_id),
        created_at,
        event_date,
        meal_type,
        items_json,
        raw_text,
        'telegram',
        parse_mode,
        tz
    ))
    
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    logging.info(f"Сохранена запись о еде: ID={log_id}, user_id={user_id}, date={event_date}, meal={meal_type}")
    return log_id


def get_food_logs_by_date(
    database_file: str,
    user_id: str,
    event_date: str
) -> List[FoodLog]:
    """
    Получает все записи о еде за указанную дату
    
    Args:
        database_file: Путь к файлу БД
        user_id: ID пользователя Telegram
        event_date: Дата (YYYY-MM-DD)
        
    Returns:
        Список записей FoodLog
    """
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, created_at, event_date, meal_type, items_json, raw_text, source, parse_mode, tz
        FROM food_logs
        WHERE user_id = ? AND event_date = ?
        ORDER BY created_at ASC
    ''', (str(user_id), event_date))
    
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for row in rows:
        logs.append(FoodLog(
            id=row[0],
            user_id=row[1],
            created_at=row[2],
            event_date=row[3],
            meal_type=row[4],
            items_json=row[5],
            raw_text=row[6],
            source=row[7],
            parse_mode=row[8],
            tz=row[9]
        ))
    
    return logs


def get_food_logs_last(
    database_file: str,
    user_id: str,
    limit: int = 10
) -> List[FoodLog]:
    """
    Получает последние N записей о еде
    
    Args:
        database_file: Путь к файлу БД
        user_id: ID пользователя Telegram
        limit: Количество записей
        
    Returns:
        Список записей FoodLog
    """
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, created_at, event_date, meal_type, items_json, raw_text, source, parse_mode, tz
        FROM food_logs
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (str(user_id), limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for row in rows:
        logs.append(FoodLog(
            id=row[0],
            user_id=row[1],
            created_at=row[2],
            event_date=row[3],
            meal_type=row[4],
            items_json=row[5],
            raw_text=row[6],
            source=row[7],
            parse_mode=row[8],
            tz=row[9]
        ))
    
    return logs


def get_last_food_log(
    database_file: str,
    user_id: str
) -> Optional[FoodLog]:
    """
    Получает последнюю запись о еде для пользователя
    
    Args:
        database_file: Путь к файлу БД
        user_id: ID пользователя Telegram
        
    Returns:
        FoodLog или None, если записей нет
    """
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, created_at, event_date, meal_type, items_json, raw_text, source, parse_mode, tz
        FROM food_logs
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    ''', (str(user_id),))
    
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        return None
    
    return FoodLog(
        id=row[0],
        user_id=row[1],
        created_at=row[2],
        event_date=row[3],
        meal_type=row[4],
        items_json=row[5],
        raw_text=row[6],
        source=row[7],
        parse_mode=row[8],
        tz=row[9]
    )


def delete_food_log(
    database_file: str,
    user_id: str,
    log_id: int
) -> bool:
    """
    Удаляет запись о еде по ID
    
    Args:
        database_file: Путь к файлу БД
        user_id: ID пользователя Telegram
        log_id: ID записи
        
    Returns:
        True если удалено, False если не найдено
    """
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM food_logs
        WHERE id = ? AND user_id = ?
    ''', (log_id, str(user_id)))
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if deleted:
        logging.info(f"Удалена запись о еде: ID={log_id}, user_id={user_id}")
    else:
        logging.warning(f"Запись о еде не найдена: ID={log_id}, user_id={user_id}")
    
    return deleted


def get_food_logs_in_range(
    database_file: str,
    user_id: str,
    date_from: str,
    date_to: str
) -> List[FoodLog]:
    """
    Получает все записи о еде за диапазон дат
    
    Args:
        database_file: Путь к файлу БД
        user_id: ID пользователя Telegram
        date_from: Начальная дата включительно (YYYY-MM-DD)
        date_to: Конечная дата исключительно (YYYY-MM-DD), т.е. >= date_from AND < date_to
        
    Returns:
        Список записей FoodLog, отсортированный по event_date ASC, created_at ASC
    """
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, created_at, event_date, meal_type, items_json, raw_text, source, parse_mode, tz
        FROM food_logs
        WHERE user_id = ? AND event_date >= ? AND event_date < ?
        ORDER BY event_date ASC, created_at ASC
    ''', (str(user_id), date_from, date_to))
    
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for row in rows:
        logs.append(FoodLog(
            id=row[0],
            user_id=row[1],
            created_at=row[2],
            event_date=row[3],
            meal_type=row[4],
            items_json=row[5],
            raw_text=row[6],
            source=row[7],
            parse_mode=row[8],
            tz=row[9]
        ))
    
    return logs


def get_food_summary(
    database_file: str,
    user_id: str,
    event_date: str
) -> Dict[str, Any]:
    """
    Получает сводку по еде за день
    
    Args:
        database_file: Путь к файлу БД
        user_id: ID пользователя Telegram
        event_date: Дата (YYYY-MM-DD)
        
    Returns:
        Словарь с сводкой: {
            'date': 'YYYY-MM-DD',
            'total_logs': int,
            'meals': {'breakfast': int, 'lunch': int, 'dinner': int, 'snack': int, 'unknown': int},
            'all_items': [список всех продуктов]
        }
    """
    logs = get_food_logs_by_date(database_file, user_id, event_date)
    
    meals_count = {
        'breakfast': 0,
        'lunch': 0,
        'dinner': 0,
        'snack': 0,
        'unknown': 0
    }
    
    all_items = []
    
    for log in logs:
        meals_count[log.meal_type] = meals_count.get(log.meal_type, 0) + 1
        
        try:
            items = json.loads(log.items_json)
            all_items.extend([item.get('name', '') for item in items if item.get('name')])
        except (json.JSONDecodeError, AttributeError):
            pass
    
    return {
        'date': event_date,
        'total_logs': len(logs),
        'meals': meals_count,
        'all_items': list(set(all_items))  # Уникальные продукты
    }

