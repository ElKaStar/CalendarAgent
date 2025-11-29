"""
Обработчики команд меню дневника питания: /menutoday, /menuweek, /menumonth
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pytz
from aiogram.types import Message

from features.food.food_db import get_food_logs_by_date, get_food_logs_in_range, FoodLog

# Названия месяцев на русском
MONTH_NAMES = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

MEAL_TYPE_NAMES = {
    'breakfast': 'завтрак',
    'lunch': 'обед',
    'dinner': 'ужин',
    'snack': 'перекус',
    'unknown': 'не указано'
}


def format_items_from_log(log: FoodLog) -> str:
    """
    Форматирует список продуктов из записи
    
    Args:
        log: Запись FoodLog
        
    Returns:
        Строка с продуктами
    """
    try:
        items = json.loads(log.items_json)
        items_list = []
        for item in items:
            item_name = item.get('name', '')
            qty_text = item.get('qty_text', '')
            grams = item.get('grams')
            ml = item.get('ml')
            
            item_str = item_name
            if qty_text:
                item_str += f" {qty_text}"
            elif grams:
                item_str += f" {grams} г"
            elif ml:
                item_str += f" {ml} мл"
            
            items_list.append(item_str)
        
        return ', '.join(items_list) if items_list else log.raw_text[:100] if log.raw_text else "не указано"
    except (json.JSONDecodeError, AttributeError, TypeError):
        return log.raw_text[:100] if log.raw_text else "не указано"


def format_time_from_log(log: FoodLog, timezone: str) -> str:
    """
    Извлекает и форматирует время из created_at
    
    Args:
        log: Запись FoodLog
        timezone: Временная зона
        
    Returns:
        Строка времени в формате HH:MM
    """
    try:
        tz = pytz.timezone(timezone)
        created_dt = datetime.fromisoformat(log.created_at.replace('Z', '+00:00'))
        if created_dt.tzinfo is None:
            created_dt = pytz.UTC.localize(created_dt)
        created_dt = created_dt.astimezone(tz)
        return created_dt.strftime('%H:%M')
    except (ValueError, AttributeError):
        return "??:??"


async def handle_menu_today(message: Message, database_file: str, timezone: str) -> None:
    """
    Обработчик команды /menutoday - меню за сегодня
    
    Args:
        message: Сообщение от пользователя
        database_file: Путь к файлу БД
        timezone: Временная зона
    """
    user_id = str(message.from_user.id)
    logging.info(f"Команда /menutoday от user_id={user_id}")
    
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        today = now.date()
        today_str = today.strftime('%Y-%m-%d')
        
        logs = get_food_logs_by_date(database_file, user_id, today_str)
        logging.info(f"Найдено записей за {today_str}: {len(logs)}")
        
        if not logs:
            await message.answer("ℹ️ За сегодня записей нет.")
            return
        
        response = f"🍽 Меню за сегодня ({today_str})\n\n"
        
        for log in logs:
            time_str = format_time_from_log(log, timezone)
            meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
            items_text = format_items_from_log(log)
            
            response += f"— {time_str} ({meal_name}): {items_text}\n"
        
        response += f"\nВсего записей: {len(logs)}"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка обработки /menutoday для user_id={user_id}: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при получении меню за сегодня")


async def handle_menu_week(message: Message, database_file: str, timezone: str) -> None:
    """
    Обработчик команды /menuweek - меню за текущую неделю
    
    Args:
        message: Сообщение от пользователя
        database_file: Путь к файлу БД
        timezone: Временная зона
    """
    user_id = str(message.from_user.id)
    logging.info(f"Команда /menuweek от user_id={user_id}")
    
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        today = now.date()
        
        # Находим понедельник текущей недели (ISO неделя)
        days_since_monday = today.weekday()  # 0 = понедельник, 6 = воскресенье
        monday = today - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        next_monday = monday + timedelta(days=7)
        
        date_from = monday.strftime('%Y-%m-%d')
        date_to = next_monday.strftime('%Y-%m-%d')  # Исключительно
        
        logging.info(f"Диапазон недели: {date_from} - {date_to} (exclusive)")
        
        logs = get_food_logs_in_range(database_file, user_id, date_from, date_to)
        logging.info(f"Найдено записей за неделю: {len(logs)}")
        
        if not logs:
            await message.answer("ℹ️ За текущую неделю записей нет.")
            return
        
        response = f"🍽 Меню за неделю: {date_from} — {sunday.strftime('%Y-%m-%d')}\n\n"
        
        # Группируем по датам
        logs_by_date: Dict[str, List[FoodLog]] = {}
        for log in logs:
            if log.event_date not in logs_by_date:
                logs_by_date[log.event_date] = []
            logs_by_date[log.event_date].append(log)
        
        # Сортируем даты
        sorted_dates = sorted(logs_by_date.keys())
        
        for date_str in sorted_dates:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            response += f"📅 {date_str}\n"
            
            for log in logs_by_date[date_str]:
                time_str = format_time_from_log(log, timezone)
                meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
                items_text = format_items_from_log(log)
                
                response += f" — {time_str} ({meal_name}): {items_text}\n"
            
            response += "\n"
        
        response += f"Итого за неделю: {len(logs)} записей"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка обработки /menuweek для user_id={user_id}: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при получении меню за неделю")


async def handle_menu_month(message: Message, database_file: str, timezone: str) -> None:
    """
    Обработчик команды /menumonth - меню за текущий месяц
    
    Args:
        message: Сообщение от пользователя
        database_file: Путь к файлу БД
        timezone: Временная зона
    """
    user_id = str(message.from_user.id)
    logging.info(f"Команда /menumonth от user_id={user_id}")
    
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        today = now.date()
        
        # Первый день текущего месяца
        first_day = today.replace(day=1)
        
        # Первый день следующего месяца
        if today.month == 12:
            next_month_first = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month_first = today.replace(month=today.month + 1, day=1)
        
        date_from = first_day.strftime('%Y-%m-%d')
        date_to = next_month_first.strftime('%Y-%m-%d')  # Исключительно
        
        logging.info(f"Диапазон месяца: {date_from} - {date_to} (exclusive)")
        
        logs = get_food_logs_in_range(database_file, user_id, date_from, date_to)
        logging.info(f"Найдено записей за месяц: {len(logs)}")
        
        if not logs:
            month_name = MONTH_NAMES[today.month - 1]
            await message.answer(f"ℹ️ За текущий месяц ({month_name} {today.year}) записей нет.")
            return
        
        month_name = MONTH_NAMES[today.month - 1]
        response = f"🍽 Меню за месяц: {month_name.upper()} {today.year}\n\n"
        
        # Группируем по датам
        logs_by_date: Dict[str, List[FoodLog]] = {}
        for log in logs:
            if log.event_date not in logs_by_date:
                logs_by_date[log.event_date] = []
            logs_by_date[log.event_date].append(log)
        
        # Сортируем даты
        sorted_dates = sorted(logs_by_date.keys())
        
        for date_str in sorted_dates:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            response += f"📅 {date_str}\n"
            
            for log in logs_by_date[date_str]:
                time_str = format_time_from_log(log, timezone)
                meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
                items_text = format_items_from_log(log)
                
                response += f" — {time_str} ({meal_name}): {items_text}\n"
            
            response += "\n"
        
        response += f"Итого за месяц: {len(logs)} записей"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка обработки /menumonth для user_id={user_id}: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при получении меню за месяц")

