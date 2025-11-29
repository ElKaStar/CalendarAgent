"""
Модуль валидации дат для FoodPipeline и CalendarPipeline
"""
import logging
from datetime import datetime, date
from typing import Tuple, Optional
import pytz


def validate_food_date(
    event_date_str: str,
    now_dt: datetime,
    user_tz: str
) -> Tuple[bool, Optional[str]]:
    """
    Валидация даты для дневника питания:
    - НЕЛЬЗЯ создавать записи в будущем: event_date > today
    - МОЖНО создавать записи за прошлые даты и за сегодня: event_date <= today
    
    Args:
        event_date_str: Дата в формате YYYY-MM-DD
        now_dt: Текущая дата-время в timezone пользователя
        user_tz: Временная зона пользователя (строка)
        
    Returns:
        Tuple[bool, Optional[str]]: (ok, error_message)
        - ok=True если валидация прошла
        - ok=False если валидация не прошла, error_message содержит сообщение об ошибке
    """
    try:
        # Получаем сегодняшнюю дату в timezone пользователя
        tz = pytz.timezone(user_tz)
        if now_dt.tzinfo is None:
            now_dt = tz.localize(now_dt)
        else:
            now_dt = now_dt.astimezone(tz)
        
        today = now_dt.date()
        
        # Парсим event_date
        try:
            event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
        except ValueError:
            # Если дата битая, присваиваем today
            logging.warning(f"Некорректная дата event_date: {event_date_str}, используем today")
            return True, None  # Разрешаем, дата будет заменена на today
        
        # Проверяем: event_date не должна быть в будущем
        if event_date > today:
            error_msg = (
                f"❌ Нельзя записывать питание будущим числом.\n"
                f"📅 Указанная дата: {event_date_str}\n"
                f"✅ Можно: сегодня или прошлые даты."
            )
            return False, error_msg
        
        # Валидация прошла
        return True, None
        
    except Exception as e:
        logging.error(f"Ошибка валидации даты для дневника питания: {e}", exc_info=True)
        # В случае ошибки разрешаем (fail-safe)
        return True, None


def validate_calendar_datetime(
    start_dt: datetime,
    now_dt: datetime,
    user_tz: str,
    is_all_day: bool = False,
    start_date: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Валидация даты/времени для календаря:
    - НЕЛЬЗЯ создавать события в прошлом: start_dt < now
    - МОЖНО создавать события на сейчас и в будущем: start_dt >= now
    - Для all-day событий: если дата < today → reject, если дата >= today → allow
    
    Args:
        start_dt: Дата-время начала события (datetime с timezone)
        now_dt: Текущая дата-время в timezone пользователя
        user_tz: Временная зона пользователя (строка)
        is_all_day: True если это all-day событие (без времени)
        start_date: Дата для all-day события в формате YYYY-MM-DD (если is_all_day=True)
        
    Returns:
        Tuple[bool, Optional[str]]: (ok, error_message)
        - ok=True если валидация прошла
        - ok=False если валидация не прошла, error_message содержит сообщение об ошибке
    """
    try:
        # Нормализуем timezone
        tz = pytz.timezone(user_tz)
        if now_dt.tzinfo is None:
            now_dt = tz.localize(now_dt)
        else:
            now_dt = now_dt.astimezone(tz)
        
        if start_dt.tzinfo is None:
            start_dt = tz.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(tz)
        
        # Для all-day событий проверяем только дату
        if is_all_day and start_date:
            try:
                event_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                today = now_dt.date()
                
                if event_date < today:
                    error_msg = (
                        f"❌ Нельзя создавать встречу в прошлом.\n"
                        f"📅 Указанная дата: {start_date}\n"
                        f"✅ Можно: сегодня или в будущем."
                    )
                    return False, error_msg
                
                # Валидация прошла для all-day
                return True, None
            except ValueError:
                # Если дата битая, разрешаем (fail-safe)
                return True, None
        
        # Для событий с временем: проверяем, что start_dt >= now
        # Допускаем небольшой tolerance (1-2 минуты) для "сейчас"
        tolerance_seconds = 120  # 2 минуты
        
        time_diff = (start_dt - now_dt).total_seconds()
        
        if time_diff < -tolerance_seconds:
            # Событие в прошлом (более чем на tolerance)
            start_str = start_dt.strftime('%d.%m.%Y %H:%M')
            error_msg = (
                f"❌ Нельзя создавать встречу в прошлом.\n"
                f"🕒 Указанное время: {start_str}\n"
                f"✅ Можно: сейчас или в будущем."
            )
            return False, error_msg
        
        # Валидация прошла
        return True, None
        
    except Exception as e:
        logging.error(f"Ошибка валидации даты для календаря: {e}", exc_info=True)
        # В случае ошибки разрешаем (fail-safe)
        return True, None

