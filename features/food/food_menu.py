"""
Модуль для интерактивного меню выбора даты дневника питания
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import pytz
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from features.food.food_db import get_food_logs_by_date, FoodLog

# Названия дней недели на русском
WEEKDAY_NAMES = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
WEEKDAY_NAMES_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

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


def build_food_main_menu() -> InlineKeyboardMarkup:
    """Создает главное меню выбора даты для дневника питания"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📌 Сегодня", callback_data="FOOD:DAY:TODAY")
    builder.button(text="📅 Выбрать дату (неделя)", callback_data="FOOD:WEEK:0")
    builder.button(text="🗓️ Выбрать дату (месяц)", callback_data="FOOD:MONTH:CURRENT")
    builder.button(text="⬅️ Назад", callback_data="FOOD:MENU:BACK")
    
    builder.adjust(1)  # Все кнопки в один столбец
    return builder.as_markup()


def build_week_keyboard(week_offset: int, timezone: str = 'Europe/Moscow') -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора даты из недели
    
    Args:
        week_offset: Смещение недели (0 = текущая неделя, 1 = следующая, -1 = предыдущая)
        timezone: Временная зона
        
    Returns:
        InlineKeyboardMarkup с кнопками дат недели
    """
    builder = InlineKeyboardBuilder()
    
    # Получаем текущую дату в нужной временной зоне
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    
    # Находим понедельник текущей недели
    days_since_monday = now.weekday()  # 0 = понедельник, 6 = воскресенье
    monday = now - timedelta(days=days_since_monday)
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Применяем смещение недели
    week_start = monday + timedelta(weeks=week_offset)
    
    # Создаем кнопки для каждого дня недели
    for i in range(7):
        day = week_start + timedelta(days=i)
        date_str = day.strftime('%Y-%m-%d')
        weekday_short = WEEKDAY_NAMES[day.weekday()]
        day_num = day.day
        month_num = day.month
        
        # Формат: "Пн 25.11"
        button_text = f"{weekday_short} {day_num:02d}.{month_num:02d}"
        
        # Если это сегодня - добавляем индикатор
        if day.date() == now.date():
            button_text = f"• {button_text}"
        
        builder.button(text=button_text, callback_data=f"FOOD:DAY:{date_str}")
    
    # Кнопки навигации
    builder.button(text="◀️ Пред.", callback_data=f"FOOD:WEEK:{week_offset - 1}")
    builder.button(text="▶️ След.", callback_data=f"FOOD:WEEK:{week_offset + 1}")
    builder.button(text="⬅️ Назад", callback_data="FOOD:MENU")
    
    builder.adjust(3, 3, 1, 2, 1)  # 3 кнопки в первой строке, 3 во второй, 1 в третьей, 2 в четвертой, 1 в пятой
    return builder.as_markup()


def build_month_keyboard(year: int, month: int, timezone: str = 'Europe/Moscow') -> InlineKeyboardMarkup:
    """
    Создает календарную клавиатуру для выбора даты из месяца
    
    Args:
        year: Год
        month: Месяц (1-12)
        timezone: Временная зона
        
    Returns:
        InlineKeyboardMarkup с календарной сеткой
    """
    builder = InlineKeyboardBuilder()
    
    # Получаем первый день месяца и количество дней
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)
    
    days_in_month = last_day.day
    
    # Находим день недели первого дня месяца (0 = понедельник)
    first_weekday = first_day.weekday()
    
    # Добавляем пустые кнопки для дней до начала месяца
    for _ in range(first_weekday):
        builder.button(text=" ", callback_data="FOOD:NOOP")
    
    # Добавляем кнопки для дней месяца
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    
    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day)
        date_str = date.strftime('%Y-%m-%d')
        
        # Если это сегодня - выделяем
        if date.date() == now.date():
            button_text = f"•{day}"
        else:
            button_text = str(day)
        
        builder.button(text=button_text, callback_data=f"FOOD:DAY:{date_str}")
    
    # Добавляем пустые кнопки до конца недели (чтобы календарь был прямоугольным)
    last_weekday = last_day.weekday()
    empty_days = 6 - last_weekday
    for _ in range(empty_days):
        builder.button(text=" ", callback_data="FOOD:NOOP")
    
    # Кнопки навигации по месяцам
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1
    
    builder.button(text="◀️", callback_data=f"FOOD:MONTH:{prev_year}-{prev_month:02d}")
    builder.button(text=f"{MONTH_NAMES[month - 1]} {year}", callback_data="FOOD:NOOP")  # Неактивная кнопка с названием месяца
    builder.button(text="▶️", callback_data=f"FOOD:MONTH:{next_year}-{next_month:02d}")
    builder.button(text="⬅️ Назад", callback_data="FOOD:MENU")
    
    # Настройка расположения: 7 кнопок в строке для календаря
    # Вычисляем количество строк календаря
    calendar_buttons = first_weekday + days_in_month + empty_days
    calendar_rows = (calendar_buttons + 6) // 7  # Округляем вверх
    
    # Создаем список параметров для adjust: 7 кнопок для каждой строки календаря, затем 3 для навигации, затем 1 для "Назад"
    adjust_params = [7] * calendar_rows + [3, 1]
    builder.adjust(*adjust_params)
    
    return builder.as_markup()


def format_food_logs(date_str: str, logs: List[FoodLog], timezone: str = 'Europe/Moscow') -> str:
    """
    Форматирует записи дневника питания для вывода
    
    Args:
        date_str: Дата в формате YYYY-MM-DD
        logs: Список записей FoodLog
        timezone: Временная зона
        
    Returns:
        Отформатированная строка с записями
    """
    if not logs:
        # Форматируем дату по-русски
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            date_formatted = date_obj.strftime('%d.%m.%Y')
        except ValueError:
            date_formatted = date_str
        
        return f"ℹ️ За {date_formatted} записей нет."
    
    # Форматируем дату по-русски
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        date_formatted = date_obj.strftime('%d.%m.%Y')
    except ValueError:
        date_formatted = date_str
    
    tz = pytz.timezone(timezone)
    
    response = f"✅ Дневник питания за {date_formatted}\n\n"
    
    for log in logs:
        # Извлекаем время из created_at
        try:
            created_dt = datetime.fromisoformat(log.created_at.replace('Z', '+00:00'))
            if created_dt.tzinfo is None:
                created_dt = pytz.UTC.localize(created_dt)
            created_dt = created_dt.astimezone(tz)
            time_str = created_dt.strftime('%H:%M')
        except (ValueError, AttributeError):
            time_str = "??:??"
        
        # Получаем название типа приёма пищи
        meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
        
        # Парсим items
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
            
            items_text = ', '.join(items_list) if items_list else "не указано"
        except (json.JSONDecodeError, AttributeError, TypeError):
            items_text = log.raw_text[:50] if log.raw_text else "не указано"
        
        response += f"— {time_str}  ({meal_name}): {items_text}\n"
    
    response += f"\nВсего записей: {len(logs)}"
    
    return response


async def handle_food_menu_command(message: Message, database_file: str, timezone: str) -> None:
    """
    Обработчик команды /food_menu
    
    Args:
        message: Сообщение от пользователя
        database_file: Путь к файлу БД
        timezone: Временная зона
    """
    logging.info(f"handle_food_menu_command вызван для user_id={message.from_user.id}")
    try:
        keyboard = build_food_main_menu()
        logging.info(f"Клавиатура создана: {keyboard}")
        await message.answer(
            "🍽 Дневник питания\n\n"
            "Выберите дату для просмотра записей:",
            reply_markup=keyboard
        )
        logging.info(f"Сообщение с клавиатурой отправлено")
    except Exception as e:
        logging.error(f"Ошибка в handle_food_menu_command: {e}", exc_info=True)
        raise


async def handle_food_callback(callback: CallbackQuery, database_file: str, timezone: str) -> None:
    """
    Обработчик callback для меню дневника питания
    
    Args:
        callback: CallbackQuery от пользователя
        database_file: Путь к файлу БД
        timezone: Временная зона
    """
    data = callback.data
    
    if not data.startswith("FOOD:"):
        await callback.answer("Неизвестная команда")
        return
    
    parts = data.split(":", 2)
    
    if len(parts) < 2:
        await callback.answer("Ошибка в данных")
        return
    
    action = parts[1]
    sub_action = parts[2] if len(parts) > 2 else None
    user_id = str(callback.from_user.id)
    
    try:
        if action == "MENU":
            # Проверяем, не является ли это закрытием меню
            if sub_action == "BACK":
                # Закрываем меню, полностью удаляя сообщение
                try:
                    await callback.message.delete()
                except Exception as e:
                    # Если не удалось удалить сообщение, пробуем скрыть клавиатуру
                    logging.debug(f"Не удалось удалить сообщение: {e}, пробуем скрыть клавиатуру")
                    try:
                        await callback.message.edit_reply_markup(reply_markup=None)
                    except Exception as e2:
                        logging.debug(f"Не удалось скрыть клавиатуру: {e2}")
                await callback.answer("Меню закрыто")
            else:
                # Возврат в главное меню
                keyboard = build_food_main_menu()
                try:
                    await callback.message.edit_text(
                        "🍽 Дневник питания\n\n"
                        "Выберите дату для просмотра записей:",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    # Если сообщение уже такое же (message is not modified), просто отвечаем на callback
                    if "message is not modified" in str(e).lower() or "not modified" in str(e).lower():
                        logging.debug(f"Сообщение уже содержит главное меню, пропускаем edit_text")
                    else:
                        raise
                await callback.answer()
            
        elif action == "WEEK":
            # Показать неделю
            week_offset = int(parts[2]) if len(parts) > 2 else 0
            keyboard = build_week_keyboard(week_offset, timezone)
            
            # Получаем дату начала недели для заголовка
            tz = pytz.timezone(timezone)
            now = datetime.now(tz)
            days_since_monday = now.weekday()
            monday = now - timedelta(days=days_since_monday)
            week_start = monday + timedelta(weeks=week_offset)
            week_end = week_start + timedelta(days=6)
            
            title = f"📅 Выберите дату (неделя {week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m')})"
            
            try:
                await callback.message.edit_text(title, reply_markup=keyboard)
            except Exception as e:
                # Если сообщение уже такое же (message is not modified), просто отвечаем на callback
                if "message is not modified" in str(e).lower() or "not modified" in str(e).lower():
                    logging.debug(f"Сообщение уже содержит недельный календарь, пропускаем edit_text")
                else:
                    raise
            await callback.answer()
            
        elif action == "MONTH":
            # Показать месяц
            if parts[2] == "CURRENT":
                # Текущий месяц
                tz = pytz.timezone(timezone)
                now = datetime.now(tz)
                year = now.year
                month = now.month
            else:
                # YYYY-MM
                year_str, month_str = parts[2].split("-")
                year = int(year_str)
                month = int(month_str)
            
            keyboard = build_month_keyboard(year, month, timezone)
            title = f"🗓️ {MONTH_NAMES[month - 1]} {year}"
            
            try:
                await callback.message.edit_text(title, reply_markup=keyboard)
            except Exception as e:
                # Если сообщение уже такое же (message is not modified), просто отвечаем на callback
                if "message is not modified" in str(e).lower() or "not modified" in str(e).lower():
                    logging.debug(f"Сообщение уже содержит месячный календарь, пропускаем edit_text")
                else:
                    raise
            await callback.answer()
            
        elif action == "DAY":
            # Показать дневник за дату
            if parts[2] == "TODAY":
                # Сегодня
                tz = pytz.timezone(timezone)
                now = datetime.now(tz)
                date_str = now.strftime('%Y-%m-%d')
            else:
                # YYYY-MM-DD
                date_str = parts[2]
            
            # Получаем записи из БД
            logs = get_food_logs_by_date(database_file, user_id, date_str)
            
            # Форматируем и отправляем
            response = format_food_logs(date_str, logs, timezone)
            
            try:
                await callback.message.edit_text(response, reply_markup=None)
            except Exception as e:
                # Если сообщение уже такое же (message is not modified), просто отвечаем на callback
                if "message is not modified" in str(e).lower() or "not modified" in str(e).lower():
                    logging.debug(f"Сообщение уже содержит дневник за дату, пропускаем edit_text")
                else:
                    raise
            await callback.answer()
            
        elif action == "NOOP":
            # Пустое действие (для пустых кнопок в календаре)
            await callback.answer()
            
        else:
            await callback.answer("Неизвестное действие")
            
    except Exception as e:
        # Проверяем, не является ли это ошибкой "message is not modified"
        if "message is not modified" in str(e).lower() or "not modified" in str(e).lower():
            logging.debug(f"Сообщение не изменено (message is not modified), это нормально")
            await callback.answer()
        else:
            logging.error(f"Ошибка обработки callback для дневника питания: {e}", exc_info=True)
            await callback.answer("❌ Произошла ошибка")
            try:
                await callback.message.edit_text("❌ Произошла ошибка при обработке запроса.")
            except:
                pass

