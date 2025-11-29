#!/usr/bin/env python3
"""
Telegram-бот для управления Google Calendar через GigaChat

Установка: pip install aiogram httpx python-dotenv google-api-python-client google-auth pytz
Запуск: python bot.py

Пример файла .env:

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# GigaChat
GIGACHAT_CLIENT_ID=ваш_client_id
GIGACHAT_CLIENT_SECRET=ваш_client_secret
GIGACHAT_SCOPE=GIGACHAT_API_PERS

# STT (Яндекс SpeechKit - опционально)
STT_API_KEY=ваш_yandex_api_key
STT_FOLDER_ID=ваш_folder_id

# Google Calendar
GOOGLE_CREDENTIALS_FILE=service-account.json
GOOGLE_CALENDAR_ID=primary

# Общие настройки
TIMEZONE=Europe/Moscow
REMINDER_MINUTES_BEFORE=15
REMINDER_CHECK_INTERVAL=60
DATABASE_FILE=events.db
TEMP_DIR=temp
"""

# =============================
# IMPORTS
# =============================
import os
import asyncio
import logging
import sqlite3
import uuid
import base64
import json
import signal
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pytz
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BotCommand
from google.oauth2 import service_account
from googleapiclient.discovery import build


# =============================
# LOGGING SETUP
# =============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Отключаем избыточное логирование библиотек
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('aiogram').setLevel(logging.INFO)
logging.getLogger('googleapiclient').setLevel(logging.WARNING)


# =============================
# CONFIGURATION & SETTINGS
# =============================
@dataclass
class Config:
    """Конфигурация приложения"""
    telegram_bot_token: str
    gigachat_client_id: str
    gigachat_client_secret: str
    gigachat_scope: str
    stt_provider: str  # 'whisper' или 'yandex'
    stt_api_key: Optional[str]
    stt_folder_id: Optional[str]
    whisper_model: str  # Модель Whisper: 'tiny', 'base', 'small', 'medium', 'large'
    google_credentials_file: str
    google_calendar_id: str
    timezone: str
    reminder_minutes_before: int
    reminder_check_interval: int
    database_file: str
    temp_dir: str


def load_config() -> Config:
    """Загружает конфигурацию из переменных окружения"""
    load_dotenv()
    
    # Проверка обязательных переменных
    required = ['TELEGRAM_BOT_TOKEN', 'GIGACHAT_CLIENT_ID', 'GIGACHAT_CLIENT_SECRET', 
                'GOOGLE_CREDENTIALS_FILE']
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")
    
    return Config(
        telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
        gigachat_client_id=os.getenv('GIGACHAT_CLIENT_ID'),
        gigachat_client_secret=os.getenv('GIGACHAT_CLIENT_SECRET'),
        gigachat_scope=os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS'),
        stt_provider=os.getenv('STT_PROVIDER', 'whisper'),  # По умолчанию whisper
        stt_api_key=os.getenv('STT_API_KEY'),
        stt_folder_id=os.getenv('STT_FOLDER_ID'),
        whisper_model=os.getenv('WHISPER_MODEL', 'small'),  # По умолчанию 'small'
        google_credentials_file=os.getenv('GOOGLE_CREDENTIALS_FILE'),
        google_calendar_id=os.getenv('GOOGLE_CALENDAR_ID', 'primary'),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
        reminder_minutes_before=int(os.getenv('REMINDER_MINUTES_BEFORE', '15')),
        reminder_check_interval=int(os.getenv('REMINDER_CHECK_INTERVAL', '60')),
        database_file=os.getenv('DATABASE_FILE', 'events.db'),
        temp_dir=os.getenv('TEMP_DIR', 'temp')
    )


# Глобальная конфигурация
config: Config = None


# =============================
# DATABASE FUNCTIONS
# =============================
def init_db(cfg: Config):
    """Инициализирует SQLite базу данных"""
    conn = sqlite3.connect(cfg.database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            calendar_event_id TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            start_datetime_utc TEXT NOT NULL,
            reminder_datetime_utc TEXT NOT NULL,
            reminder_sent INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаём индексы для быстрого поиска
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_reminder 
        ON events(reminder_sent, reminder_datetime_utc)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_calendar_event 
        ON events(calendar_event_id)
    ''')
    
    conn.commit()
    conn.close()
    logging.info("База данных инициализирована")
    
    # Инициализируем таблицу для дневника питания
    from features.food.food_db import init_food_db
    init_food_db(cfg.database_file)


def save_event(calendar_event_id: str, chat_id: int, title: str, 
               start_dt_local: datetime, timezone: str):
    """Сохраняет событие в БД с проверкой на дубликаты"""
    
    # Переводим в UTC
    start_dt_utc = start_dt_local.astimezone(pytz.UTC)
    # Поля reminder_datetime_utc и reminder_sent остаются в БД для совместимости,
    # но больше не используются (напоминания обрабатывает только Google Calendar)
    reminder_dt_utc = start_dt_utc.isoformat()  # Просто сохраняем время начала для совместимости
    reminder_sent = 1  # Помечаем как "отправлено", чтобы старый код не пытался отправить
    
    conn = sqlite3.connect(config.database_file)
    cursor = conn.cursor()
    
    # Проверяем, не существует ли уже событие с таким же calendar_event_id
    cursor.execute('''
        SELECT id FROM events WHERE calendar_event_id = ?
    ''', (calendar_event_id,))
    existing = cursor.fetchone()
    
    if existing:
        logging.warning(f"Событие {calendar_event_id} уже существует в БД (ID: {existing[0]}), пропускаем сохранение")
        conn.close()
        return
    
    # Проверяем, не существует ли уже событие с таким же названием и временем
    cursor.execute('''
        SELECT id, calendar_event_id FROM events 
        WHERE title = ? AND start_datetime_utc = ? AND chat_id = ?
    ''', (title, start_dt_utc.isoformat(), chat_id))
    duplicate = cursor.fetchone()
    
    if duplicate:
        logging.warning(f"Дубликат события '{title}' на {start_dt_utc.isoformat()} уже существует в БД (ID: {duplicate[0]}, Event ID: {duplicate[1]}), пропускаем сохранение")
        conn.close()
        return
    
    # Сохраняем новое событие
    cursor.execute('''
        INSERT INTO events (calendar_event_id, chat_id, title, start_datetime_utc, 
                           reminder_datetime_utc, reminder_sent)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        calendar_event_id,
        chat_id,
        title,
        start_dt_utc.isoformat(),
        reminder_dt_utc,
        reminder_sent
    ))
    
    conn.commit()
    conn.close()
    logging.info(f"Событие {calendar_event_id} сохранено в БД")


def delete_event_from_db(calendar_event_id: str):
    """Удаляет событие из БД"""
    conn = sqlite3.connect(config.database_file)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM events WHERE calendar_event_id = ?', (calendar_event_id,))
    conn.commit()
    conn.close()
    logging.info(f"Событие {calendar_event_id} удалено из БД")


# =============================
# GIGACHAT INTEGRATION
# =============================

# Глобальный кеш токена
_gigachat_token_cache = {
    'token': None,
    'expires_at': None
}


async def get_gigachat_access_token(cfg: Config) -> str:
    """Получает access token для GigaChat API с кешированием"""
    
    # Проверяем кеш
    if _gigachat_token_cache['token'] and _gigachat_token_cache['expires_at']:
        if datetime.now() < _gigachat_token_cache['expires_at'] - timedelta(minutes=5):
            return _gigachat_token_cache['token']
    
    # Получаем новый токен
    try:
        # Используем CLIENT_SECRET напрямую как base64 (как в рабочем проекте AgafiaBotTG)
        # CLIENT_SECRET уже является base64 строкой вида "client_id:real_secret" в base64
        auth_base64 = cfg.gigachat_client_secret
        rquid = cfg.gigachat_client_id  # RqUID = CLIENT_ID
        
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json',
                    'RqUID': rquid,
                    'Authorization': f'Basic {auth_base64}'
                },
                data={
                    'scope': cfg.gigachat_scope
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"GigaChat auth error: {response.status_code} - {response.text}")
            
            data = response.json()
            token = data['access_token']
            expires_at = datetime.fromtimestamp(data['expires_at'] / 1000)
            
            # Кешируем
            _gigachat_token_cache['token'] = token
            _gigachat_token_cache['expires_at'] = expires_at
            
            logging.info(f"Получен новый GigaChat токен, истекает: {expires_at}")
            return token
            
    except Exception as e:
        logging.error(f"Ошибка получения GigaChat токена: {e}")
        raise


async def normalize_text_with_gigachat(text: str, cfg: Config) -> str:
    """
    Нормализует текст после распознавания Whisper:
    - исправляет орфографию и пунктуацию
    - выравнивает регистр
    - расставляет пробелы
    - НЕ меняет смысл (не меняет время, дату, названия)
    """
    token = await get_gigachat_access_token(cfg)
    
    system_prompt = """Ты помощник для исправления орфографии, пунктуации и ошибок распознавания речи в русском тексте.

Задача:
- Исправь орфографические ошибки (например: "маникер" → "маникюр")
- Исправь ошибки распознавания речи:
  * "картофельная пирожок" → "картофельное пюре"
  * "картофельный пирожок" → "картофельное пюре"
  * "отстану кашу" → "овсяную кашу"
  * "миню" → "меню"
  * "рамм" → "грамм"
  * "завтраку" → "завтра" (если это про дату, не про еду)
  * "завтрак" → "завтра" (если это про дату/встречу, например "завтрак врачу" = "завтра к врачу", НЕ про еду)
  * Если видишь название продукта + "грамм" или "г" без числа перед ним, но есть число в тексте - восстанови связь
- Исправь пунктуацию (расставь запятые, точки)
- Выровняй регистр (первая буква предложения заглавная, остальное строчное)
- Расставь пробелы правильно
- НЕ меняй смысл текста
- НЕ меняй время, дату, названия услуг/встреч
- НЕ добавляй информацию, которой нет в исходном тексте
- Если видишь "100 грамм" или "200 грамм" - сохрани числа

Примеры:
Вход: "запиши меня завтра на маникер на 3-часот дня. Продолжительно с 2 часа."
Выход: "Запиши меня завтра на маникюр на 3 часа дня. Продолжительность 2 часа."

Вход: "картофельная пирожок грамм"
Выход: "Картофельное пюре грамм"

Вход: "картофельная пирожок 100 грамм"
Выход: "Картофельное пюре 100 грамм"

Вход: "меню картофельная пирожок 100 грамм"
Выход: "Меню картофельное пюре 100 грамм"

Вход: "послезавтра в 10:00 созвон с командой, 30 минут, онлайн"
Выход: "Послезавтра в 10:00 созвон с командой, 30 минут, онлайн."

Вход: "и запиши меня на завтраку врачу на 11 часов"
Выход: "И запиши меня на завтра к врачу на 11 часов."

Вход: "запиши меня на завтрак врачу"
Выход: "Запиши меня на завтра к врачу."

ВАЖНО: "завтраку" или "завтрак" в контексте встреч/врача/записи = "завтра" (tomorrow), НЕ "завтрак" (breakfast)!

Верни ТОЛЬКО исправленный текст, без пояснений."""
    
    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                'https://gigachat.devices.sberbank.ru/api/v1/chat/completions',
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                json={
                    'model': 'GigaChat',
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    'temperature': 0.1,
                    'max_tokens': 300
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"GigaChat normalization error: {response.status_code} - {response.text}")
            
            normalized = response.json()['choices'][0]['message']['content'].strip()
            logging.info(f"Текст нормализован: '{text}' → '{normalized}'")
            return normalized
            
    except Exception as e:
        logging.error(f"Ошибка нормализации текста через GigaChat: {e}")
        # В случае ошибки возвращаем исходный текст
        return text


async def detect_intent_with_gigachat(text: str, cfg: Config) -> str:
    """
    Определяет интент сообщения через GigaChat: 'food' или 'calendar'
    
    Args:
        text: Текст сообщения
        cfg: Конфигурация
        
    Returns:
        'food' - сообщение о еде (дневник питания)
        'calendar' - сообщение о календарном событии
    """
    token = await get_gigachat_access_token(cfg)
    
    system_prompt = """Ты помощник для классификации сообщений пользователя.

Задача: Определи категорию сообщения.

Категории:
1. "food" - сообщения о еде, питании, продуктах, приёмах пищи (завтрак, обед, ужин, перекус)
   Примеры: "меню творог 200 грамм", "съел овсянку", "завтрак омлет и кофе", "картофельное пюре 300 грамм"
   
2. "calendar" - сообщения о событиях, встречах, записях, напоминаниях
   Примеры: "завтра в 15:00 встреча", "запиши на маникюр", "созвон с командой", "врач в понедельник"

Важно:
- Если сообщение начинается с "меню" или "миню" или "мену" - это ВСЕГДА "food"
- Если есть продукты и количество (граммы, мл) - это "food"
- Если есть время встречи, запись, встреча - это "calendar"

Верни ТОЛЬКО JSON в формате:
{
  "category": "food" или "calendar"
}

Без пояснений, только JSON."""
    
    try:
        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            response = await client.post(
                'https://gigachat.devices.sberbank.ru/api/v1/chat/completions',
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                json={
                    'model': 'GigaChat',
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    'temperature': 0.1,
                    'max_tokens': 50
                }
            )
            
            if response.status_code != 200:
                logging.warning(f"GigaChat intent detection error: {response.status_code} - {response.text}")
                return 'calendar'  # По умолчанию календарь
            
            content = response.json()['choices'][0]['message']['content'].strip()
            logging.info(f"GigaChat intent response: {content}")
            
            # Парсим JSON
            try:
                if content.startswith('```'):
                    content = content.split('```')[1]
                    if content.startswith('json'):
                        content = content[4:]
                content = content.strip()
                
                data = json.loads(content)
                category = data.get('category', 'calendar').lower()
                
                if category in ['food', 'calendar']:
                    logging.info(f"GigaChat определил категорию: {category}")
                    return category
                else:
                    logging.warning(f"GigaChat вернул неизвестную категорию: {category}, используем calendar")
                    return 'calendar'
                    
            except (json.JSONDecodeError, KeyError) as e:
                logging.warning(f"Ошибка парсинга ответа GigaChat для определения интента: {e}, content: {content}")
                # Пробуем найти категорию в тексте
                if 'food' in content.lower():
                    return 'food'
                elif 'calendar' in content.lower():
                    return 'calendar'
                return 'calendar'  # По умолчанию
            
    except Exception as e:
        logging.error(f"Ошибка определения интента через GigaChat: {e}")
        return 'calendar'  # По умолчанию календарь


async def call_gigachat(text: str, cfg: Config) -> dict:
    """Отправляет запрос в GigaChat API"""
    
    token = await get_gigachat_access_token(cfg)
    
    # Получаем текущую дату и время для контекста
    now = datetime.now(pytz.timezone(cfg.timezone))
    current_date = now.strftime('%Y-%m-%d')
    current_weekday = now.strftime('%A')
    current_time = now.strftime('%H:%M')
    current_hour = now.hour
    
    # Вычисляем даты для примеров в промпте
    from datetime import timedelta
    current_date_plus_1_day = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    current_date_plus_2_days = (now + timedelta(days=2)).strftime('%Y-%m-%d')
    current_date_minus_1_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Вычисляем ближайшую пятницу для примера
    days_until_friday = (4 - now.weekday()) % 7
    if days_until_friday == 0 and now.hour >= 18:  # Если сегодня пятница и уже вечер
        days_until_friday = 7
    next_friday_date = (now + timedelta(days=days_until_friday)).strftime('%Y-%m-%d')
    current_date_plus_7_days = (now + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Улучшенный промпт с примерами
    system_prompt = f"""Ты помощник, который разбирает естественный текст пользователя о встречах и возвращает СТРОГО JSON без пояснений.

Текущая дата: {current_date} ({current_weekday})
Текущее время: {current_time}
Временная зона: {cfg.timezone}

Поля JSON:
- title: короткое название встречи (строка, БЕЗ служебных слов и даты/времени)
- date: дата в формате YYYY-MM-DD (строка)
- time: время начала в формате HH:MM, 24 часа (строка или null)
- duration_minutes: длительность в минутах (число или null)
- duration_hours: длительность в часах (число с плавающей точкой или null, например 2.0 или 1.5)
- confidence_duration: уверенность в длительности - "high" или "low" (строка, ОБЯЗАТЕЛЬНО)
- description: дополнительное описание (строка)
- location: место встречи, если указано "онлайн" - пиши "online" (строка или null)

Правила для title:
1. УБЕРИ служебные слова: "запиши", "запиши меня", "запланируй", "поставь", "создай", "добавь"
2. УБЕРИ фрагменты с датой: "завтра", "сегодня", "послезавтра", "в пятницу"
3. УБЕРИ фрагменты со временем: "в 15:00", "в 3 часа", "на 3 часа дня", "в 10 утра"
4. УБЕРИ фрагменты с длительностью: "на 2 часа", "на час", "30 минут", "продолжительность 2 часа"
5. Оставь ТОЛЬКО суть: название услуги/встречи/события
6. Приведи к нормальному виду: первая буква заглавная, остальное строчное
7. КРИТИЧНО: Если в тексте есть "завтрак" в контексте встречи/врача/записи (например, "завтрак врачу", "на завтрак к врачу") - это НЕ еда, это "завтра" (tomorrow)! 
   В этом случае title = "Врач" или "Прием у врача", НЕ "Завтрак у врача"!
8. Примеры: "маникюр" → "Маникюр", "встреча с юристом" → "Встреча с юристом", "созвон с командой" → "Созвон с командой"
9. Примеры с "завтрак" = "завтра": "запиши на завтрак врачу" → title: "Врач", date: завтра, НЕ "Завтрак у врача"!

Правила для времени (КРИТИЧЕСКИ ВАЖНО - учитывай контекст времени суток):
1. ЯВНЫЕ указания времени суток:
   - "утром", "утра", "AM" = утро (00:00-11:59)
   - "днём", "дня", "после полудня" = день (12:00-17:59)
   - "вечером", "вечера", "PM" = вечер (18:00-23:59)
   - "ночью", "ночи" = ночь (00:00-05:59)
2. Контекстное определение AM/PM (КРИТИЧЕСКИ ВАЖНО - если не указано явно):
   ТЕКУЩЕЕ ВРЕМЯ: {current_time} ({current_hour} часов)
   
   ПРАВИЛО ДЛЯ ВЕЧЕРА (после 18:00, сейчас {current_hour} часов):
   - Если сейчас вечер ({current_hour} часов, после 18:00) и пользователь говорит "11:00" или "11 часов" или "11.00" БЕЗ "утра/дня" - это ОБЯЗАТЕЛЬНО 23:00 (11 PM), НИКОГДА НЕ 11:00!
   - Если сейчас вечер ({current_hour} часов, после 18:00) и пользователь говорит "10:00" или "10 часов" БЕЗ "утра/дня" - это 22:00 (10 PM)
   - Если сейчас вечер ({current_hour} часов, после 18:00) и пользователь говорит "9:00" или "9 часов" БЕЗ "утра/дня" - это 21:00 (9 PM)
   - Если сейчас вечер ({current_hour} часов, после 18:00) и пользователь говорит "8:00" или "8 часов" БЕЗ "утра/дня" - это 20:00 (8 PM)
   - ВАЖНО: Если сейчас вечер (после 18:00), а пользователь говорит время меньше 12 (1-11), это ВСЕГДА вечернее время (13:00-23:00)!
   - КРИТИЧНО: Если сейчас {current_hour} часов (вечер) и указано "11" - это 23:00, НЕ 11:00!
   
   ПРАВИЛО ДЛЯ УТРА/ДНЯ:
   - Если сейчас утро ({current_hour} часов, до 12:00) и пользователь говорит "11:00" или "11 часов" БЕЗ "вечера/ночи" - это 11:00 (11 AM)
   - Если сейчас день ({current_hour} часов, 12:00-17:59) и пользователь говорит "11:00" или "11 часов" БЕЗ "утра/вечера" - это 11:00 (11 AM)
3. Стандартные правила:
   - "3 часа дня" = 15:00, "3 часа утра" = 03:00
   - "3-часот дня" = 15:00 (исправь опечатку)
   - "полдень" = 12:00, "полночь" = 00:00
   - "в 15:00" = 15:00, "в 3 часа" = 15:00 (если не указано "утра")
   - "11 часов вечера" = 23:00, "11 часов ночи" = 23:00
   - "11 часов утра" = 11:00, "11 часов дня" = 11:00

Правила для длительности (ОЧЕНЬ ВАЖНО - всегда ищи упоминания длительности в тексте):
1. "на 2 часа" = 120 минут (2.0 часа), "на час" = 60 минут (1.0 час), "на 3 часа" = 180 минут (3.0 часа)
2. "продолжительность 2 часа" = 120 минут (2.0 часа), "продолжительность 3 часа" = 180 минут (3.0 часа)
3. "длительность 2 часа" = 120 минут (2.0 часа), "длительность 3 часа" = 180 минут (3.0 часа)
4. "2 часа длительность" = 120 минут (2.0 часа), "3 часа длительность" = 180 минут (3.0 часа)
5. "полчаса" = 30 минут (0.5 часа), "1.5 часа" = 90 минут (1.5 часа), "полтора часа" = 90 минут (1.5 часа)
6. "2 часа" = 120 минут (2.0 часа) (если это длительность, а не время начала)
7. "3 часа" = 180 минут (3.0 часа) (если это длительность, а не время начала)
8. "час" = 60 минут (1.0 час), "два часа" = 120 минут (2.0 часа), "три часа" = 180 минут (3.0 часа)
9. "30 минут" = 30 минут (0.5 часа), "45 минут" = 45 минут (0.75 часа), "90 минут" = 90 минут (1.5 часа)
10. Если в тексте есть слова "продолжительность", "длительность", "на X часа/минут" ПОСЛЕ указания времени - это длительность!
11. Если указано "на 11:00 часов дня" - это ВРЕМЯ (11:00), а не длительность
12. Если указано "на 3 часа" БЕЗ "дня/утра" и ПОСЛЕ времени - это длительность (180 минут = 3.0 часа)

Правила для confidence_duration (КРИТИЧЕСКИ ВАЖНО):
confidence_duration = "high" если:
- В тексте есть ЯВНОЕ указание длительности с ЧИСЛОМ: "продолжительность 2 часа", "на 3 часа", "длительность 1.5 часа", "30 минут"
- И ты УВЕРЕН в извлечённом числе (нет противоречий, число логично)

confidence_duration = "low" если:
- В тексте есть слова "продолжительность", "длительность", "на X часа", но:
  * НЕ удалось извлечь нормальное число (текст искажён, есть мусор)
  * Найдены противоречивые числа (например, "2 часа" и "3 часа" в одном тексте)
  * Число выглядит нелогично (например, "продолжительность 25 часов")
- В тексте есть намёк на длительность ("продолжительность", "длительность", "на столько-то"), но нет явного числа
- Текст сильно искажён распознаванием речи, и длительность неясна

ВАЖНО: Всегда возвращай duration_hours = duration_minutes / 60.0 (если duration_minutes указано)

Общие правила для даты (КРИТИЧЕСКИ ВАЖНО):
1. Пользователь пишет по-русски
2. Текущая дата: {current_date} ({current_weekday})
3. Правила вычисления даты (ВЫЧИСЛЯЙ ДАТЫ ПРАВИЛЬНО!):
   - "сегодня" = {current_date} (ТОЛЬКО если событие сегодня и время еще не прошло)
   - "завтра" = {current_date} + 1 день (ВСЕГДА будущая дата, НЕ {current_date}!)
   - "послезавтра" = {current_date} + 2 дня (ВСЕГДА будущая дата, НЕ {current_date}!)
   - "через 3 дня" = {current_date} + 3 дня
   - "через неделю" = {current_date} + 7 дней
   - "через 2 недели" = {current_date} + 14 дней
   - КРИТИЧНО: Если пользователь говорит "завтра" - это НИКОГДА не {current_date}, это {current_date} + 1 день!
   - КРИТИЧНО: Если пользователь говорит "послезавтра" - это НИКОГДА не {current_date}, это {current_date} + 2 дня!
4. Дни недели (ближайший такой день в будущем):
   - "в понедельник" = ближайший понедельник после {current_date}
   - "в пятницу" = ближайшая пятница после {current_date}
   - "в среду" = ближайшая среда после {current_date}
   - ВАЖНО: Если сегодня уже этот день недели, но время прошло - берем следующий такой день
5. Если указан диапазон времени "с 15:00 до 16:30", то time=15:00, duration_minutes=90
6. Если время НЕ указано - верни time: null и duration_minutes: null
7. Если длительность НЕ указана, но есть время - верни duration_minutes: null
8. Если указано "онлайн", "zoom", "meet" - добавь location: "online"
9. КРИТИЧНО: Если пользователь говорит "завтра", "послезавтра", "через X дней" - это ВСЕГДА будущая дата, НЕ сегодня!

Примеры:

Вход: "Запиши меня завтра на маникюр на 3 часа дня. Продолжительность 2 часа."
Выход: {{"title": "Маникюр", "date": "{current_date}", "time": "15:00", "duration_minutes": 120, "duration_hours": 2.0, "confidence_duration": "high", "description": "", "location": null}}
ВАЖНО: "завтра" означает {current_date} + 1 день! Вычисляй дату правильно! Если сегодня {current_date}, то завтра = {current_date} + 1 день

Вход: "Запиши меня завтра на маникюр на 11:00 часов дня. Продолжительность 3 часа."
Выход: {{"title": "Маникюр", "date": "{current_date}", "time": "11:00", "duration_minutes": 180, "duration_hours": 3.0, "confidence_duration": "high", "description": "", "location": null}}
ВАЖНО: "завтра" означает {current_date} + 1 день! Вычисляй дату правильно! Если сегодня {current_date}, то завтра = {current_date} + 1 день

Вход: "Завтра в 15:00 встреча с Катей по ипотеке, час"
Выход: {{"title": "Встреча с Катей по ипотеке", "date": "{current_date}", "time": "15:00", "duration_minutes": 60, "duration_hours": 1.0, "confidence_duration": "high", "description": "", "location": null}}
ПРИМЕЧАНИЕ: "завтра" = {current_date} + 1 день, вычисляй правильно! Если сегодня {current_date}, то завтра = {current_date} + 1 день

Вход: "Завтра в 11:00 встреча" (если сейчас вечер, после 18:00, например {current_time})
Выход: {{"title": "Встреча", "date": "{current_date}", "time": "23:00", "duration_minutes": null, "duration_hours": null, "confidence_duration": "low", "description": "", "location": null}}
ПРИМЕЧАНИЕ: "завтра" = {current_date} + 1 день, вычисляй правильно! Если сегодня {current_date}, то завтра = {current_date} + 1 день

Вход: "Сегодня на 11.00 маникюр" (если сейчас вечер, после 18:00, например {current_time})
Выход: {{"title": "Маникюр", "date": "{current_date}", "time": "23:00", "duration_minutes": null, "duration_hours": null, "confidence_duration": "low", "description": "", "location": null}}

Вход: "Завтра в 11:00 утра встреча"
Выход: {{"title": "Встреча", "date": "{current_date}", "time": "11:00", "duration_minutes": null, "duration_hours": null, "confidence_duration": "low", "description": "", "location": null}}
ВАЖНО: "завтра" означает {current_date} + 1 день! Вычисляй дату правильно!

Вход: "Завтра в 11 часов вечера встреча"
Выход: {{"title": "Встреча", "date": "{current_date}", "time": "23:00", "duration_minutes": null, "duration_hours": null, "confidence_duration": "low", "description": "", "location": null}}
ВАЖНО: "завтра" означает {current_date} + 1 день! Вычисляй дату правильно!

Вход: "Запиши меня на завтрак врачу на 11 часов"
Выход: {{"title": "Врач", "date": "{current_date_plus_1_day}", "time": "11:00", "duration_minutes": null, "duration_hours": null, "confidence_duration": "low", "description": "", "location": null}}
КРИТИЧНО: "завтрак врачу" = "завтра к врачу" (tomorrow to doctor), НЕ "завтрак у врача" (breakfast at doctor)! title = "Врач", date = завтра!

Вход: "И запиши меня на завтраку врачу на 11 часов, продолжительность 1 час"
Выход: {{"title": "Врач", "date": "{current_date_plus_1_day}", "time": "11:00", "duration_minutes": 60, "duration_hours": 1.0, "confidence_duration": "high", "description": "", "location": null}}
КРИТИЧНО: "завтраку врачу" = "завтра к врачу" (tomorrow to doctor), НЕ "завтрак у врача" (breakfast at doctor)! title = "Врач", date = завтра!

Вход: "Послезавтра в 10:00 созвон с командой, 30 минут, онлайн"
Выход: {{"title": "Созвон с командой", "date": "{current_date}", "time": "10:00", "duration_minutes": 30, "duration_hours": 0.5, "confidence_duration": "high", "description": "", "location": "online"}}
ВАЖНО: "послезавтра" означает {current_date} + 2 дня! Вычисляй дату правильно!

Вход: "В пятницу в 18:00 ужин с друзьями"
Выход: {{"title": "Ужин с друзьями", "date": "2024-01-19", "time": "18:00", "duration_minutes": null, "duration_hours": null, "confidence_duration": "high", "description": "", "location": null}}

Вход: "Через неделю планёрка с 9:00 до 10:30"
Выход: {{"title": "Планёрка", "date": "2024-01-22", "time": "09:00", "duration_minutes": 90, "duration_hours": 1.5, "confidence_duration": "high", "description": "", "location": null}}

Вход: "Завтра на маникюр в 14:00, длительность 3 часа"
Выход: {{"title": "Маникюр", "date": "2024-01-16", "time": "14:00", "duration_minutes": 180, "duration_hours": 3.0, "confidence_duration": "high", "description": "", "location": null}}

Вход: "Сделай завтра запись на маникюр на 3 часа дня, продолжительность начнём всё для кон radioactive nur dakika"
Выход: {{"title": "Маникюр", "date": "2024-01-16", "time": "15:00", "duration_minutes": null, "duration_hours": null, "confidence_duration": "low", "description": "", "location": null}}

Вход: "Завтра на маникюр в 13:00, продолжительность 2 часа но маникюр продолжительность начнём"
Выход: {{"title": "Маникюр", "date": "2024-01-16", "time": "13:00", "duration_minutes": 120, "duration_hours": 2.0, "confidence_duration": "low", "description": "", "location": null}}

Возвращай ТОЛЬКО JSON, без markdown, без пояснений."""
    
    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                'https://gigachat.devices.sberbank.ru/api/v1/chat/completions',
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}'
                },
                json={
                    'model': 'GigaChat',
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    'temperature': 0.1,
                    'max_tokens': 500
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"GigaChat API error: {response.status_code} - {response.text}")
            
            return response.json()
            
    except Exception as e:
        logging.error(f"Ошибка вызова GigaChat: {e}")
        raise


@dataclass
class ParsedEvent:
    """Модель распознанного события"""
    title: str
    start_datetime: datetime
    duration_minutes: Optional[int]
    duration_hours: Optional[float] = None  # Длительность в часах (для более точной работы)
    confidence_duration: str = "high"  # "high" или "low" - уверенность в длительности
    raw_text: str = ""  # Исходный распознанный текст
    description: str = ""
    location: Optional[str] = None


async def parse_event_from_gigachat(text: str, cfg: Config) -> ParsedEvent:
    """Парсит текст через GigaChat и возвращает структурированное событие"""
    
    logging.info(f"Отправляем в GigaChat текст: {text[:200]}")
    
    # Вызываем GigaChat
    response = await call_gigachat(text, cfg)
    
    # Извлекаем контент
    content = response['choices'][0]['message']['content']
    logging.info(f"GigaChat ответ: {content}")
    
    # Проверяем, что ответ не пустой
    if not content or content.strip() == '{}' or content.strip() == '':
        raise ValueError("GigaChat вернул пустой ответ. Попробуйте переформулировать запрос более конкретно, например: 'Завтра в 15:00 встреча с Катей, час'")
    
    # Пытаемся распарсить JSON
    try:
        # Убираем markdown форматирование, если есть
        content = content.strip()
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        content = content.strip()
        
        data = json.loads(content)
        
        # Проверяем, что это не пустой JSON объект
        if isinstance(data, dict) and len(data) == 0:
            raise ValueError("GigaChat вернул пустой ответ (пустой JSON объект).")
        
    except json.JSONDecodeError:
        # Пытаемся найти JSON через регулярку
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("GigaChat не вернул корректный JSON. Попробуйте переформулировать запрос.")
    
    # Валидация обязательных полей
    if not data.get('title'):
        raise ValueError("Не удалось определить название встречи")
    
    if not data.get('date'):
        raise ValueError("Не удалось определить дату встречи")
    
    if not data.get('time'):
        raise ValueError("Не удалось определить время встречи. Укажите время явно (например, '15:00')")
    
    # Преобразуем в datetime
    try:
        date_str = data['date']
        time_str = data['time']
        datetime_str = f"{date_str} {time_str}"
        
        tz = pytz.timezone(cfg.timezone)
        start_datetime = tz.localize(datetime.strptime(datetime_str, '%Y-%m-%d %H:%M'))
        
        # Проверяем, что дата/время в будущем
        now = datetime.now(tz)
        # Разрешаем события на сегодня, если время еще не прошло
        # Блокируем только события в прошлом (дата в прошлом ИЛИ дата сегодня, но время уже прошло)
        if start_datetime.date() < now.date():
            # Дата в прошлом - ошибка
            logging.warning(f"GigaChat вернул дату в прошлом: {date_str} {time_str}, текущее время: {now.strftime('%Y-%m-%d %H:%M')}")
            raise ValueError(f"Дата события ({date_str}) в прошлом. Укажите будущую дату (завтра, послезавтра и т.д.)")
        elif start_datetime.date() == now.date() and start_datetime.time() <= now.time():
            # Дата сегодня, но время уже прошло - ошибка
            logging.warning(f"GigaChat вернул время, которое уже прошло сегодня: {date_str} {time_str}, текущее время: {now.strftime('%Y-%m-%d %H:%M')}")
            raise ValueError(f"Время события ({time_str}) уже прошло сегодня. Укажите будущее время или завтра.")
        # Если дата сегодня и время еще не прошло - разрешаем
        # Если дата в будущем - разрешаем
        
    except ValueError as e:
        if "Дата события" in str(e) or "Время события" in str(e):
            raise  # Пробрасываем наши ошибки
        logging.error(f"Ошибка парсинга даты/времени: {e}")
        raise ValueError("Некорректный формат даты или времени")
    
    # Нормализуем заголовок: первая буква заглавная, остальное строчное
    title = data['title'].strip()
    if title:
        title = title[0].upper() + title[1:].lower() if len(title) > 1 else title.upper()
    
    # Обрабатываем длительность
    duration_minutes = data.get('duration_minutes')
    duration_hours = data.get('duration_hours')
    confidence_duration = data.get('confidence_duration', 'high')
    
    # Если duration_hours не указано, но есть duration_minutes - вычисляем
    if duration_hours is None and duration_minutes is not None:
        duration_hours = duration_minutes / 60.0
    
    # Если duration_minutes не указано, но есть duration_hours - вычисляем
    if duration_minutes is None and duration_hours is not None:
        duration_minutes = int(duration_hours * 60)
    
    # Валидация confidence_duration
    if confidence_duration not in ['high', 'low']:
        confidence_duration = 'high'  # По умолчанию high
    
    # Логируем confidence для отладки
    if confidence_duration == 'low':
        logging.warning(f"Низкая уверенность в длительности для текста: '{text[:100]}...'")
    
    return ParsedEvent(
        title=title,
        start_datetime=start_datetime,
        duration_minutes=duration_minutes,
        duration_hours=duration_hours,
        confidence_duration=confidence_duration,
        raw_text=text,  # Сохраняем исходный текст
        description=data.get('description', ''),
        location=data.get('location')
    )


# =============================
# GOOGLE CALENDAR INTEGRATION
# =============================
def get_google_calendar_service(cfg: Config):
    """Создаёт сервис Google Calendar через Service Account"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            cfg.google_credentials_file,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        return build('calendar', 'v3', credentials=credentials)
    except Exception as e:
        logging.error(f"Ошибка создания Google Calendar сервиса: {e}")
        raise


async def create_calendar_event(event: ParsedEvent, chat_id: int, cfg: Config) -> str:
    """Создаёт событие в Google Calendar и возвращает event_id"""
    
    service = get_google_calendar_service(cfg)
    
    # Вычисляем время окончания
    # Предпочитаем duration_hours для более точной работы, если доступно
    if event.duration_hours is not None:
        duration_minutes = int(event.duration_hours * 60)
    elif event.duration_minutes is not None:
        duration_minutes = event.duration_minutes
    else:
        duration_minutes = 60  # По умолчанию 60 минут
    
    end_datetime = event.start_datetime + timedelta(minutes=duration_minutes)
    
    # Формируем тело события
    event_body = {
        'summary': event.title,
        'description': event.description,
        'start': {
            'dateTime': event.start_datetime.isoformat(),
            'timeZone': cfg.timezone,
        },
        'end': {
            'dateTime': end_datetime.isoformat(),
            'timeZone': cfg.timezone,
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 1440},  # 24 часа до начала (email)
                {'method': 'popup', 'minutes': 1440},  # 24 часа до начала (popup)
                {'method': 'email', 'minutes': 180},   # 3 часа до начала (email)
                {'method': 'popup', 'minutes': 180},   # 3 часа до начала (popup)
            ],
        },
    }
    
    # Добавляем location, если указано
    if event.location:
        event_body['location'] = event.location
    
    # Создаём событие
    try:
        created_event = service.events().insert(
            calendarId=cfg.google_calendar_id,
            body=event_body
        ).execute()
        
        event_id = created_event['id']
        logging.info(f"Создано событие в Google Calendar: {event_id}")
        return event_id
        
    except Exception as e:
        logging.error(f"Ошибка создания события в Google Calendar: {e}")
        raise ValueError("Не удалось создать событие в календаре")


# =============================
# SPEECH-TO-TEXT (STT)
# =============================




async def speech_to_text_yandex(file_path: str, api_key: str, folder_id: str) -> str:
    """
    Распознаёт речь через Яндекс SpeechKit
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(file_path, 'rb') as audio_file:
                response = await client.post(
                    'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize',
                    headers={
                        'Authorization': f'Api-Key {api_key}',
                    },
                    params={
                        'lang': 'ru-RU',
                        'folderId': folder_id,
                    },
                    content=audio_file.read()
                )
                
                if response.status_code != 200:
                    raise Exception(f"Yandex SpeechKit error: {response.status_code} - {response.text}")
                
                result = response.json()
                return result.get('result', '')
                
    except Exception as e:
        logging.error(f"Ошибка Яндекс SpeechKit: {e}")
        raise ValueError("Не удалось распознать речь через Яндекс SpeechKit")


async def speech_to_text_local_whisper(file_path: str, cfg: Config) -> str:
    """
    Распознаёт речь через локальную библиотеку whisper.
    Использует модуль stt_whisper.py с кэшированием модели.
    """
    from stt_whisper import transcribe_audio
    
    # Промпт для улучшения распознавания русских слов, связанных с едой и календарём
    # Помогает модели лучше распознавать специфические слова
    initial_prompt = (
        "Картофельное пюре, овсяная каша, пшеничная каша, творог, гречка, салат, "
        "завтрак, обед, ужин, перекус, меню, грамм, миллилитр, "
        "запись, встреча, маникюр, врач, доктор, консультация, "
        "созвон, звонок, онлайн, офлайн, сегодня, завтра, послезавтра"
    )
    
    try:
        # Выполняем распознавание в отдельном потоке, чтобы не блокировать event loop
        # Добавляем таймаут 60 секунд для распознавания
        text = await asyncio.wait_for(
            asyncio.to_thread(
                transcribe_audio,
                file_path,
                cfg.whisper_model,
                initial_prompt
            ),
            timeout=60.0
        )
        if not text or not text.strip():
            logging.warning("Whisper вернул пустой текст")
            return ""
        return text
    except asyncio.TimeoutError:
        logging.error("Распознавание через Whisper превысило таймаут (60 секунд)")
        raise ValueError("Распознавание речи заняло слишком много времени. Попробуйте ещё раз.")
    except Exception as e:
        logging.error(f"Ошибка локального whisper: {e}", exc_info=True)
        raise ValueError(f"Не удалось распознать речь через локальный whisper: {e}")


async def speech_to_text(file_path: str, cfg: Config) -> str:
    """
    Распознаёт речь из аудиофайла через настроенный STT-провайдер.
    
    Поддерживаемые провайдеры:
    - 'whisper': Локальный Whisper (по умолчанию)
    - 'yandex': Яндекс SpeechKit (требует STT_API_KEY и STT_FOLDER_ID)
    """
    
    provider = cfg.stt_provider.lower()
    
    if provider == 'whisper':
        try:
            logging.info(f"Используется локальный Whisper (модель: {cfg.whisper_model}) для распознавания речи")
            return await speech_to_text_local_whisper(file_path, cfg)
        except Exception as e:
            logging.error(f"Ошибка Whisper: {e}", exc_info=True)
            raise ValueError(f"Не удалось распознать речь через Whisper: {e}")
    
    elif provider == 'yandex':
        if not cfg.stt_api_key or not cfg.stt_folder_id:
            raise ValueError(
                "Яндекс SpeechKit требует настройки:\n"
                "STT_API_KEY=ваш_ключ\n"
                "STT_FOLDER_ID=ваш_folder_id"
            )
        try:
            logging.info("Используется Яндекс SpeechKit для распознавания речи")
            return await speech_to_text_yandex(file_path, cfg.stt_api_key, cfg.stt_folder_id)
        except Exception as e:
            logging.error(f"Ошибка Яндекс SpeechKit: {e}", exc_info=True)
            raise ValueError(f"Не удалось распознать речь через Яндекс SpeechKit: {e}")
    
    else:
        raise ValueError(
            f"Неизвестный STT провайдер: {provider}. "
            "Поддерживаемые значения: 'whisper', 'yandex'"
        )


# =============================
# TELEGRAM BOT HANDLERS
# =============================

# Инициализация бота
bot: Bot = None
dp = Dispatcher()
router = Router()
dp.include_router(router)


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "👋 Привет! Я помогу быстро создавать встречи в Google Календаре.\n\n"
        "📝 Отправь мне текст или голосовое сообщение, например:\n"
        "• «Завтра в 15:00 встреча с Катей по ипотеке, час»\n"
        "• «Послезавтра в 10:00 созвон с командой, 30 минут, онлайн»\n"
        "• «В пятницу в 18:00 ужин с друзьями»\n\n"
        f"⏰ Напоминания будут приходить от Google Calendar (за 24 часа и за 3 часа до начала).\n\n"
        "Команды:\n"
        "/help - справка\n"
        "/list - показать ближайшие события\n"
        "/cancel <название> - отменить событие"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📖 Справка по использованию бота:\n\n"
        "1️⃣ Отправь текст или голосовое с описанием встречи\n"
        "2️⃣ Я создам событие в твоём Google Календаре\n"
        "3️⃣ Напоминания придут от Google Calendar (за 24 часа и за 3 часа до начала)\n\n"
        "Примеры запросов:\n"
        "• «Завтра в 14:00 встреча с клиентом, 2 часа»\n"
        "• «Послезавтра в 9:00 планёрка, 45 минут, онлайн»\n"
        "• «В понедельник в 16:00 звонок с партнёром»\n\n"
        "Команды календаря:\n"
        "/start - начало работы\n"
        "/list - показать ближайшие 5 событий\n"
        "/cancel <название> - отменить событие по названию\n\n"
        "Команды дневника питания:\n"
        "/food_help - справка по дневнику питания\n"
        "Кодовые слова для записи в дневник: используйте /food_help для списка\n"
        "/food_today - что записано за сегодня\n"
        "/food_day YYYY-MM-DD - лог за дату\n"
        "/food_last N - последние N записей\n"
        "/food_sum YYYY-MM-DD - сводка за день\n"
        "/food_delete ID - удалить запись\n"
        "/food_export YYYY-MM-DD - экспорт CSV"
    )


@router.message(Command("list", "events"))
async def cmd_list_events(message: Message):
    """Показывает ближайшие 5 событий из календаря"""
    try:
        service = get_google_calendar_service(config)
        now = datetime.now(pytz.timezone(config.timezone)).isoformat()
        
        events_result = service.events().list(
            calendarId=config.google_calendar_id,
            timeMin=now,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            await message.answer("📅 Ближайших событий не найдено")
            return
        
        response = "📅 Ближайшие события:\n\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            start_local = start_dt.astimezone(pytz.timezone(config.timezone))
            
            response += f"• {event['summary']}\n"
            response += f"  🕐 {start_local.strftime('%d.%m.%Y %H:%M')}\n\n"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка при получении списка событий: {e}")
        await message.answer("❌ Не удалось получить список событий")


@router.message(Command("cancel"))
async def cmd_cancel_event(message: Message):
    """Отменяет событие по названию"""
    # Извлекаем название события из команды
    text = message.text.replace('/cancel', '').strip()
    
    if not text:
        await message.answer("❌ Укажите название события для отмены:\n/cancel Встреча с Катей")
        return
    
    try:
        service = get_google_calendar_service(config)
        now = datetime.now(pytz.timezone(config.timezone)).isoformat()
        
        # Ищем событие по названию
        events_result = service.events().list(
            calendarId=config.google_calendar_id,
            timeMin=now,
            q=text,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            await message.answer(f"❌ Событие «{text}» не найдено")
            return
        
        # Удаляем первое найденное событие
        event = events[0]
        service.events().delete(
            calendarId=config.google_calendar_id,
            eventId=event['id']
        ).execute()
        
        # Удаляем из БД
        delete_event_from_db(event['id'])
        
        await message.answer(f"✅ Событие «{event['summary']}» отменено")
        logging.info(f"Событие {event['id']} отменено пользователем {message.chat.id}")
        
    except Exception as e:
        logging.error(f"Ошибка при отмене события: {e}")
        await message.answer("❌ Не удалось отменить событие")


# =============================
# FOOD LOG COMMANDS
# =============================

@router.message(Command("food_help"))
async def cmd_food_help(message: Message):
    """Обработчик команды /food_help"""
    from features.food.food_handlers import handle_food_help
    await handle_food_help(message)


@router.message(Command("food_today"))
async def cmd_food_today(message: Message):
    """Обработчик команды /food_today"""
    from features.food.food_handlers import handle_food_today
    await handle_food_today(message, config.database_file, config.timezone)


@router.message(Command("food_day"))
async def cmd_food_day(message: Message):
    """Обработчик команды /food_day"""
    from features.food.food_handlers import handle_food_day
    await handle_food_day(message, config.database_file, config.timezone)


@router.message(Command("food_last"))
async def cmd_food_last(message: Message):
    """Обработчик команды /food_last"""
    from features.food.food_handlers import handle_food_last
    await handle_food_last(message, config.database_file, config.timezone)


@router.message(Command("food_sum"))
async def cmd_food_sum(message: Message):
    """Обработчик команды /food_sum"""
    from features.food.food_handlers import handle_food_sum
    await handle_food_sum(message, config.database_file, config.timezone)


@router.message(Command("food_delete"))
async def cmd_food_delete(message: Message):
    """Обработчик команды /food_delete"""
    from features.food.food_handlers import handle_food_delete
    await handle_food_delete(message, config.database_file, config.timezone)


@router.message(Command("food_export"))
async def cmd_food_export(message: Message):
    """Обработчик команды /food_export"""
    from features.food.food_handlers import handle_food_export
    await handle_food_export(message, config.database_file, config.timezone)


@router.message(Command("food_menu"))
async def cmd_food_menu(message: Message):
    """Обработчик команды /food_menu"""
    logging.info(f"Команда /food_menu получена от пользователя {message.from_user.id}")
    try:
        from features.food.food_menu import handle_food_menu_command
        await handle_food_menu_command(message, config.database_file, config.timezone)
        logging.info(f"Команда /food_menu обработана успешно")
    except Exception as e:
        logging.error(f"Ошибка обработки команды /food_menu: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при открытии меню дневника питания")


@router.message(Command("menutoday"))
async def cmd_menu_today(message: Message):
    """Обработчик команды /menutoday"""
    from features.food.food_menu_commands import handle_menu_today
    await handle_menu_today(message, config.database_file, config.timezone)


@router.message(Command("menuweek"))
async def cmd_menu_week(message: Message):
    """Обработчик команды /menuweek"""
    from features.food.food_menu_commands import handle_menu_week
    await handle_menu_week(message, config.database_file, config.timezone)


@router.message(Command("menumonth"))
async def cmd_menu_month(message: Message):
    """Обработчик команды /menumonth"""
    from features.food.food_menu_commands import handle_menu_month
    await handle_menu_month(message, config.database_file, config.timezone)


@router.message(Command("dellast"))
async def cmd_dellast(message: Message):
    """Обработчик команды /dellast"""
    from features.food.food_handlers import handle_food_delete_last
    await handle_food_delete_last(message, config.database_file, config.timezone)


@router.callback_query(lambda c: c.data and c.data.startswith("FOOD:"))
async def handle_food_callback_query(callback: CallbackQuery):
    """Обработчик callback для меню дневника питания"""
    from features.food.food_menu import handle_food_callback
    await handle_food_callback(callback, config.database_file, config.timezone)


@router.message(F.text & ~F.text.startswith('/'))
async def handle_text_message(message: Message):
    """Обработчик текстовых сообщений"""
    try:
        await message.answer("⏳ Обрабатываю запрос...")
        
        # Определяем интент через GigaChat: еда или календарь
        logging.info(f"Определяем категорию сообщения через GigaChat: '{message.text[:100]}...'")
        intent = await detect_intent_with_gigachat(message.text, config)
        logging.info(f"GigaChat определил категорию: {intent}")
        
        # Показываем пользователю определенную категорию
        category_name = "🍽 Дневник питания" if intent == 'food' else "📅 Календарь"
        await message.answer(f"📋 Категория: {category_name}")
        
        if intent == 'food':
            # Обрабатываем как запись о еде
            from features.food.food_handlers import handle_food_message
            logging.info(f"Сообщение направлено в FoodPipeline: '{message.text[:100]}...' (intent={intent})")
            await handle_food_message(
                text=message.text,
                chat_id=message.chat.id,
                message=message,
                database_file=config.database_file,
                timezone=config.timezone,
                config=config
            )
            logging.info(f"Обработка сообщения о еде завершена для: '{message.text[:100]}...'")
        else:
            # Обрабатываем как календарное событие (по умолчанию)
            logging.info(f"Сообщение направлено в CalendarPipeline: '{message.text[:100]}...'")
            await handle_natural_language(message.text, message.chat.id, message)
        
    except Exception as e:
        logging.error(f"Ошибка обработки текста: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке запроса.\n"
            "Попробуйте переформулировать или обратитесь к /help"
        )


@router.message(F.voice)
async def handle_voice_message(message: Message):
    """Обработчик голосовых сообщений"""
    try:
        # Проверяем, есть ли уже распознанный текст от Telegram (transcription)
        # В Telegram Bot API transcription доступен, если пользователь включил эту функцию
        # В aiogram 3.x transcription может быть в voice.transcription или через extra_data
        transcription_text = None
        
        # Способ 1: Проверяем прямое поле transcription (если доступно)
        if message.voice:
            # Проверяем через getattr для безопасного доступа
            transcription_text = getattr(message.voice, 'transcription', None)
            
            # Способ 2: Проверяем через extra_data (если transcription там)
            if not transcription_text and hasattr(message.voice, 'model_extra'):
                model_extra = getattr(message.voice, 'model_extra', {})
                transcription_text = model_extra.get('transcription') if model_extra else None
            
            # Способ 3: Проверяем через model_dump (Pydantic v2)
            if not transcription_text:
                try:
                    voice_dict = message.voice.model_dump(exclude_none=True) if hasattr(message.voice, 'model_dump') else {}
                    transcription_text = voice_dict.get('transcription')
                except:
                    pass
        
        # Если transcription найден, используем его
        if transcription_text:
            logging.info(f"Используется transcription от Telegram: {transcription_text}")
            # Нормализуем текст перед обработкой
            try:
                normalized_text = await normalize_text_with_gigachat(transcription_text, config)
                
                # Определяем интент через GigaChat: еда или календарь
                logging.info(f"Определяем категорию (Telegram transcription, с нормализацией) через GigaChat: '{normalized_text[:100]}...'")
                intent = await detect_intent_with_gigachat(normalized_text, config)
                logging.info(f"GigaChat определил категорию: {intent}")
                
                # Показываем пользователю определенную категорию и распознанный текст
                category_name = "🍽 Дневник питания" if intent == 'food' else "📅 Календарь"
                await message.answer(f"📝 Использую распознанный текст от Telegram: {normalized_text}\n\n📋 Категория: {category_name}")
                
                if intent == 'food':
                    # Обрабатываем как запись о еде
                    from features.food.food_handlers import handle_food_message
                    logging.info(f"Голосовое сообщение (Telegram transcription) направлено в FoodPipeline: '{normalized_text[:100]}...'")
                    await handle_food_message(
                        text=normalized_text,
                        chat_id=message.chat.id,
                        message=message,
                        database_file=config.database_file,
                        timezone=config.timezone,
                        config=config
                    )
                else:
                    # Обрабатываем как календарное событие (по умолчанию)
                    logging.info(f"Голосовое сообщение (Telegram transcription) направлено в CalendarPipeline: '{normalized_text[:100]}...'")
                    await handle_natural_language(normalized_text, message.chat.id, message)
            except Exception as e:
                logging.warning(f"Ошибка нормализации текста от Telegram, используем исходный: {e}")
                # Определяем интент через GigaChat: еда или календарь
                logging.info(f"Определяем категорию (Telegram transcription, без нормализации) через GigaChat: '{transcription_text[:100]}...'")
                intent = await detect_intent_with_gigachat(transcription_text, config)
                logging.info(f"GigaChat определил категорию: {intent}")
                
                # Показываем пользователю определенную категорию и распознанный текст
                category_name = "🍽 Дневник питания" if intent == 'food' else "📅 Календарь"
                await message.answer(f"📝 Использую распознанный текст от Telegram: {transcription_text}\n\n📋 Категория: {category_name}")
                
                if intent == 'food':
                    # Обрабатываем как запись о еде
                    from features.food.food_handlers import handle_food_message
                    logging.info(f"Голосовое сообщение (Telegram transcription) направлено в FoodPipeline: '{transcription_text[:100]}...'")
                    await handle_food_message(
                        text=transcription_text,
                        chat_id=message.chat.id,
                        message=message,
                        database_file=config.database_file,
                        timezone=config.timezone,
                        config=config
                    )
                else:
                    # Обрабатываем как календарное событие
                    logging.info(f"Голосовое сообщение (Telegram transcription) направлено в CalendarPipeline: '{transcription_text[:100]}...'")
                    await handle_natural_language(transcription_text, message.chat.id, message)
            return
        
        # Если transcription не найден, логируем для отладки
        logging.info("Transcription от Telegram не найден. Пользователь может включить его в настройках Telegram (Настройки → Язык → Распознавание речи)")
        
        # Проверяем, настроен ли STT провайдер
        if config.stt_provider.lower() == 'whisper':
            try:
                from stt_whisper import check_ffmpeg, get_whisper_model
                if not check_ffmpeg():
                    logging.warning("ffmpeg не установлен, но Whisper выбран как провайдер")
                    await message.answer(
                        "🎤 Голосовое сообщение получено!\n\n"
                        "⚠️ Whisper требует установки ffmpeg.\n\n"
                        "Установите ffmpeg:\n"
                        "• Windows: https://ffmpeg.org/download.html\n"
                        "• Linux: sudo apt-get install ffmpeg\n"
                        "• macOS: brew install ffmpeg\n\n"
                        "После установки ffmpeg попробуйте отправить голосовое сообщение снова."
                    )
                    return
                # Предзагружаем модель при первом использовании
                get_whisper_model()
                logging.info("Whisper готов к использованию")
            except ImportError:
                logging.warning("openai-whisper не установлен")
                await message.answer(
                    "🎤 Голосовое сообщение получено!\n\n"
                    "⚠️ Whisper не установлен.\n\n"
                    "Установите: pip install openai-whisper\n\n"
                    "Пока что отправьте, пожалуйста, текстом ✍️"
                )
                return
            except Exception as e:
                logging.error(f"Ошибка инициализации Whisper: {e}", exc_info=True)
                await message.answer(
                    "❌ Ошибка инициализации Whisper. Попробуйте отправить текстом ✍️"
                )
                return
        elif config.stt_provider.lower() == 'yandex':
            if not config.stt_api_key or not config.stt_folder_id:
                logging.warning("Яндекс SpeechKit выбран, но не настроен")
                await message.answer(
                    "🎤 Голосовое сообщение получено!\n\n"
                    "⚠️ Яндекс SpeechKit не настроен.\n\n"
                    "Настройте в .env:\n"
                    "STT_API_KEY=ваш_yandex_key\n"
                    "STT_FOLDER_ID=ваш_folder_id\n\n"
                    "Пока что отправьте, пожалуйста, текстом ✍️"
                )
                return
        else:
            logging.warning(f"Неизвестный STT провайдер: {config.stt_provider}")
            await message.answer(
                "🎤 Голосовое сообщение получено!\n\n"
                "⚠️ STT провайдер не настроен корректно.\n\n"
                "Настройте STT_PROVIDER в .env (whisper или yandex)\n\n"
                "Пока что отправьте, пожалуйста, текстом ✍️"
            )
            return
        
        logging.info("Начинаем распознавание голосового сообщения через STT провайдер")
        await message.answer("🎤 Распознаю голосовое сообщение...")
        
        # Создаём временную директорию, если её нет
        os.makedirs(config.temp_dir, exist_ok=True)
        
        # Скачиваем файл от Telegram
        logging.info(f"Скачиваем голосовое сообщение: {message.voice.file_id}")
        file = await bot.get_file(message.voice.file_id)
        telegram_file_path = os.path.join(config.temp_dir, f"voice_{uuid.uuid4()}.ogg")
        await bot.download_file(file.file_path, telegram_file_path)
        logging.info(f"Голосовое сообщение сохранено: {telegram_file_path}")
        
        # Конвертируем и распознаём речь
        converted_file_path = None
        try:
            # Если используется Whisper, конвертируем через ffmpeg
            if config.stt_provider.lower() == 'whisper':
                from stt_whisper import download_and_convert_voice
                logging.info("Конвертируем голосовое сообщение через ffmpeg для Whisper...")
                converted_file_path = download_and_convert_voice(telegram_file_path, config.temp_dir)
                file_to_transcribe = converted_file_path
            else:
                file_to_transcribe = telegram_file_path
            
            # Распознаём речь
            logging.info(f"Начинаем распознавание речи через {config.stt_provider}")
            text = await speech_to_text(file_to_transcribe, config)
            logging.info(f"Речь распознана: '{text[:100] if text else 'пусто'}'")
            
        except Exception as e:
            logging.error(f"Ошибка при обработке голосового сообщения: {e}", exc_info=True)
            await message.answer(
                "❌ Не удалось распознать голосовое сообщение. Попробуйте ещё раз или отправьте текстом."
            )
            return
        finally:
            # Удаляем временные файлы
            for temp_file in [telegram_file_path, converted_file_path]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        logging.info(f"Удалён временный файл: {temp_file}")
                    except Exception as e:
                        logging.warning(f"Не удалось удалить временный файл {temp_file}: {e}")
        
        if not text or not text.strip():
            logging.warning("Распознанный текст пустой или None")
            await message.answer(
                "❌ Не удалось распознать речь в голосовом сообщении.\n"
                "Попробуйте отправить текстом или проверьте настройки STT."
            )
            return
        
        # Нормализуем текст после распознавания Whisper
        try:
            logging.info(f"Начинаем нормализацию текста через GigaChat: '{text[:100]}...'")
            normalized_text = await normalize_text_with_gigachat(text, config)
            logging.info(f"Текст нормализован: '{text[:100]}...' → '{normalized_text[:100]}...'")
            
            # Валидация текста: проверка на пустой/некорректный текст
            if not normalized_text or not normalized_text.strip():
                logging.warning("Нормализованный текст пустой")
                await message.answer(
                    "❌ Не удалось распознать речь в голосовом сообщении.\n"
                    "Попробуйте отправить текстом или проверьте настройки STT."
                )
                return
            
            # Проверка на повторяющиеся слова (признак мусора от STT)
            # Убираем пунктуацию для проверки
            text_clean = re.sub(r'[^\w\s]', ' ', normalized_text.lower())
            words = [w for w in text_clean.split() if w.strip()]
            if len(words) > 0:
                # Проверяем, не состоит ли текст из одного повторяющегося слова/фразы
                unique_words = set(words)
                # Если уникальных слов <= 2, а всего слов >= 4 - это повторения
                if len(unique_words) <= 2 and len(words) >= 4:
                    # Дополнительная проверка: если одно слово повторяется более 3 раз
                    word_counts = Counter(words)
                    max_count = max(word_counts.values()) if word_counts else 0
                    if max_count >= 3:
                        logging.warning(f"Текст содержит повторяющиеся слова (возможно мусор от STT): '{normalized_text[:100]}...'")
                        await message.answer(
                            "❌ Не удалось распознать речь в голосовом сообщении.\n"
                            "Распознан только шум или повторяющиеся слова.\n"
                            "Попробуйте отправить текстом или говорить более четко."
                        )
                        return
            
            # Определяем интент через GigaChat: еда или календарь
            logging.info(f"Определяем категорию голосового сообщения через GigaChat: '{normalized_text[:100]}...'")
            intent = await detect_intent_with_gigachat(normalized_text, config)
            logging.info(f"GigaChat определил категорию: {intent}")
            
            # Показываем пользователю определенную категорию и распознанный текст
            category_name = "🍽 Дневник питания" if intent == 'food' else "📅 Календарь"
            await message.answer(f"📝 Распознано: {normalized_text}\n\n📋 Категория: {category_name}")
            
            if intent == 'food':
                # Обрабатываем как запись о еде
                from features.food.food_handlers import handle_food_message
                logging.info(f"Голосовое сообщение направлено в FoodPipeline: '{normalized_text[:100]}...'")
                await handle_food_message(
                    text=normalized_text,
                    chat_id=message.chat.id,
                    message=message,
                    database_file=config.database_file,
                    timezone=config.timezone,
                    config=config
                )
            else:
                # Обрабатываем как календарное событие
                logging.info(f"Голосовое сообщение направлено в CalendarPipeline: '{normalized_text[:100]}...'")
                await handle_natural_language(normalized_text, message.chat.id, message)
        except Exception as e:
            logging.error(f"Ошибка нормализации текста, используем исходный: {e}", exc_info=True)
            
            # Валидация исходного текста: проверка на пустой/некорректный текст
            if not text or not text.strip():
                logging.warning("Исходный текст пустой после ошибки нормализации")
                await message.answer(
                    "❌ Не удалось распознать речь в голосовом сообщении.\n"
                    "Попробуйте отправить текстом или проверьте настройки STT."
                )
                return
            
            # Проверка на повторяющиеся слова (признак мусора от STT)
            # Убираем пунктуацию для проверки
            text_clean = re.sub(r'[^\w\s]', ' ', text.lower())
            words = [w for w in text_clean.split() if w.strip()]
            if len(words) > 0:
                # Проверяем, не состоит ли текст из одного повторяющегося слова/фразы
                unique_words = set(words)
                # Если уникальных слов <= 2, а всего слов >= 4 - это повторения
                if len(unique_words) <= 2 and len(words) >= 4:
                    # Дополнительная проверка: если одно слово повторяется более 3 раз
                    word_counts = Counter(words)
                    max_count = max(word_counts.values()) if word_counts else 0
                    if max_count >= 3:
                        logging.warning(f"Текст содержит повторяющиеся слова (возможно мусор от STT): '{text[:100]}...'")
                        await message.answer(
                            "❌ Не удалось распознать речь в голосовом сообщении.\n"
                            "Распознан только шум или повторяющиеся слова.\n"
                            "Попробуйте отправить текстом или говорить более четко."
                        )
                        return
            
            await message.answer(f"📝 Распознано: {text}")
            
            # Определяем интент через GigaChat: еда или календарь
            logging.info(f"Определяем категорию голосового сообщения через GigaChat (без нормализации): '{text[:100]}...'")
            intent = await detect_intent_with_gigachat(text, config)
            logging.info(f"GigaChat определил категорию: {intent}")
            
            # Показываем пользователю определенную категорию
            category_name = "🍽 Дневник питания" if intent == 'food' else "📅 Календарь"
            await message.answer(f"📋 Категория: {category_name}")
            
            if intent == 'food':
                # Обрабатываем как запись о еде
                from features.food.food_handlers import handle_food_message
                logging.info(f"Голосовое сообщение направлено в FoodPipeline: '{text[:100]}...'")
                await handle_food_message(
                    text=text,
                    chat_id=message.chat.id,
                    message=message,
                    database_file=config.database_file,
                    timezone=config.timezone,
                    config=config
                )
            else:
                # Обрабатываем как календарное событие
                logging.info(f"Голосовое сообщение направлено в CalendarPipeline: '{text[:100]}...'")
                await handle_natural_language(text, message.chat.id, message)
        
    except ValueError as e:
        # Ошибка конфигурации STT
        logging.error(f"Ошибка STT конфигурации: {e}")
        await message.answer(
            f"❌ {str(e)}\n\n"
            "Попробуйте отправить текстом ✍️"
        )
    except Exception as e:
        logging.error(f"Ошибка обработки голосового сообщения: {e}")
        await message.answer(
            "❌ Не удалось распознать голосовое сообщение.\n"
            "Попробуйте отправить текстом ✍️"
        )


async def handle_natural_language(text: str, chat_id: int, message: Message):
    """Обрабатывает естественный язык: парсинг через GigaChat → создание события"""
    try:
        # 1. Парсим текст через GigaChat
        try:
            parsed_event = await parse_event_from_gigachat(text, config)
        except ValueError as e:
            # Если GigaChat вернул пустой ответ, возможно это была запись о еде
            # Попробуем обработать как еду
            if "пустой ответ" in str(e).lower() or "не вернул корректный json" in str(e).lower() or "{}" in str(e):
                logging.warning(f"GigaChat вернул пустой ответ для текста: '{text[:100]}...'. Пробуем обработать как еду.")
                logging.info(f"Определяем категорию (fallback после пустого ответа GigaChat) через GigaChat: '{text[:100]}...'")
                intent = await detect_intent_with_gigachat(text, config)
                logging.info(f"GigaChat определил категорию: {intent}")
                
                # Показываем пользователю определенную категорию
                category_name = "🍽 Дневник питания" if intent == 'food' else "📅 Календарь"
                await message.answer(f"📋 Категория: {category_name}")
                
                if intent == 'food':
                    from features.food.food_handlers import handle_food_message
                    logging.info(f"Сообщение с пустым ответом GigaChat направлено в FoodPipeline: '{text[:100]}...'")
                    await handle_food_message(
                        text=text,
                        chat_id=chat_id,
                        message=message,
                        database_file=config.database_file,
                        timezone=config.timezone,
                        config=config
                    )
                    return
                else:
                    # Даже если интент не food, но есть маркеры еды - пробуем обработать как еду
                    # Проверяем еще раз через GigaChat
                    logging.warning(f"GigaChat вернул пустой ответ для календаря. Пробуем определить категорию через GigaChat еще раз.")
                    intent = await detect_intent_with_gigachat(text, config)
                    logging.info(f"GigaChat определил категорию (повторная проверка): {intent}")
                    
                    # Показываем пользователю определенную категорию
                    category_name = "🍽 Дневник питания" if intent == 'food' else "📅 Календарь"
                    await message.answer(f"📋 Категория: {category_name}")
                    
                    from features.food.food_handlers import handle_food_message
                    try:
                        await handle_food_message(
                            text=text,
                            chat_id=chat_id,
                            message=message,
                            database_file=config.database_file,
                            timezone=config.timezone
                        )
                        return
                    except:
                        pass  # Если не получилось - пробрасываем ошибку дальше
            # Если не еда, пробрасываем ошибку дальше
            raise
        
        # 2. Валидация даты/времени для календаря: нельзя создавать события в прошлом
        from features.food.date_validation import validate_calendar_datetime
        
        now = datetime.now(pytz.timezone(config.timezone))
        is_valid, error_msg = validate_calendar_datetime(
            parsed_event.start_datetime,
            now,
            config.timezone,
            is_all_day=False
        )
        
        if not is_valid:
            logging.warning(f"Валидация даты календаря не прошла: user_id={chat_id}, request_text='{text[:100]}...', start_dt={parsed_event.start_datetime}, now={now}")
            await message.answer(error_msg)
            return
        
        # 3. Создаём событие в Google Calendar
        event_id = await create_calendar_event(parsed_event, chat_id, config)
        
        # 4. Сохраняем в БД
        save_event(
            calendar_event_id=event_id,
            chat_id=chat_id,
            title=parsed_event.title,
            start_dt_local=parsed_event.start_datetime,
            timezone=config.timezone
        )
        
        # 5. Отправляем подтверждение
        # Вычисляем время окончания (предпочитаем duration_hours для точности)
        if parsed_event.duration_hours is not None:
            duration_minutes = int(parsed_event.duration_hours * 60)
        elif parsed_event.duration_minutes is not None:
            duration_minutes = parsed_event.duration_minutes
        else:
            duration_minutes = 60
        
        end_time = parsed_event.start_datetime + timedelta(minutes=duration_minutes)
        response = (
            f"✅ Создала событие:\n\n"
            f"📌 {parsed_event.title}\n"
            f"🕐 {parsed_event.start_datetime.strftime('%d.%m.%Y %H:%M')} - "
            f"{end_time.strftime('%H:%M')}\n"
        )
        if parsed_event.description:
            response += f"📝 {parsed_event.description}\n"
        if parsed_event.location:
            response += f"📍 {parsed_event.location}\n"
        
        # Предупреждение при низкой уверенности в длительности
        if parsed_event.confidence_duration == "low":
            response += f"\n⚠️ Внимание: длительность определена с низкой уверенностью из-за искажений в распознанном тексте.\n"
            response += f"Если длительность неверна, отредактируйте событие в Google Календаре.\n"
        
        response += f"\n🔔 Напоминания: за 24 часа и за 3 часа до начала (через Google Календарь)."
        
        await message.answer(response)
        logging.info(f"Создано событие {event_id} для пользователя {chat_id}")
        
    except ValueError as e:
        await message.answer(f"❌ {str(e)}")
    except Exception as e:
        logging.error(f"Ошибка создания события: {e}")
        await message.answer("❌ Не удалось создать событие. Попробуйте ещё раз.")


# =============================
# REMINDER WORKER - УДАЛЁН
# =============================
# Логика напоминаний полностью удалена.
# Теперь используются только стандартные напоминания Google Calendar
# (настроены на 24 часа и 3 часа до начала события).


# =============================
# GRACEFUL SHUTDOWN
# =============================

# Глобальный флаг для остановки
shutdown_event = asyncio.Event()


def signal_handler(sig, frame):
    """Обработчик сигналов для graceful shutdown"""
    logging.info(f"Получен сигнал {sig}, завершаем работу...")
    shutdown_event.set()


# =============================
# MAIN APPLICATION
# =============================
async def main():
    """Главная функция приложения"""
    global config, bot
    
    # Загружаем конфигурацию
    try:
        config = load_config()
        logging.info("Конфигурация загружена успешно")
    except Exception as e:
        logging.error(f"Ошибка загрузки конфигурации: {e}")
        return
    
    # Инициализируем БД
    try:
        init_db(config)
    except Exception as e:
        logging.error(f"Ошибка инициализации БД: {e}")
        return
    
    # Создаём временную директорию
    os.makedirs(config.temp_dir, exist_ok=True)
    
    # Инициализируем бота
    bot = Bot(token=config.telegram_bot_token)
    
    # Настраиваем меню команд в Telegram
    try:
        await bot.set_my_commands([
            BotCommand(command="menutoday", description="Меню за сегодня"),
            BotCommand(command="menuweek", description="Меню на этой неделе"),
            BotCommand(command="menumonth", description="Меню за этот месяц"),
        ])
        logging.info("Меню команд настроено")
    except Exception as e:
        logging.warning(f"Не удалось настроить меню команд: {e}")
    
    # Router уже включён глобально (строка 595), не нужно включать снова
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logging.info("🚀 Бот запущен и готов к работе!")
    logging.info("Напоминания обрабатываются только через Google Calendar (24 часа и 3 часа до начала)")
    
    # Запускаем polling - это блокирующий вызов, который работает до остановки
    try:
        await dp.start_polling(bot, drop_pending_updates=False)
    except KeyboardInterrupt:
        logging.info("Получен сигнал остановки")
    except Exception as e:
        logging.error(f"Ошибка в polling: {e}")
    finally:
        # Закрываем бота
        await bot.session.close()
        
        logging.info("✅ Бот остановлен")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Получен KeyboardInterrupt")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")

