# PRD: Telegram-бот для управления Google Calendar через GigaChat

## Оглавление

1. [Обзор проекта](#обзор-проекта)
2. [Общие требования](#общие-требования)
3. [Стек и библиотеки](#стек-и-библиотеки)
4. [Переменные окружения](#переменные-окружения)
5. [Настройка Google Calendar](#настройка-google-calendar)
6. [Логика Telegram-бота](#логика-telegram-бота)
7. [Распознавание речи (STT)](#распознавание-речи-stt)
8. [Интеграция с GigaChat](#интеграция-с-gigachat)
9. [Google Calendar - создание события](#google-calendar--создание-события)
10. [SQLite - хранение событий](#sqlite--хранение-событий)
11. [Напоминания через Telegram](#напоминания-через-telegram)
12. [Логирование](#логирование)
13. [Graceful Shutdown](#graceful-shutdown)
14. [Сценарий для пользователя](#сценарий-для-пользователя)
15. [Качество кода](#качество-кода)
16. [Troubleshooting](#troubleshooting)

---

## Обзор проекта

Telegram-бот для управления Google Календарём через голосовые и текстовые сообщения с использованием GigaChat для парсинга естественного языка.

**Основной флоу:**

1. Пользователь отправляет текст или голосовое сообщение боту
2. Бот распознаёт речь (если голосовое) через STT-провайдер
3. Отправляет текст в GigaChat для извлечения параметров встречи (JSON)
4. Создаёт событие в Google Календаре
5. Сохраняет событие в SQLite
6. Отправляет подтверждение пользователю
7. За заданное время до события отправляет напоминание в Telegram

**Ключевые особенности:**

- Один Python-файл (`bot.py`)
- Long polling (без вебхуков, HTTPS, сертификатов)
- Работает на Linux-сервере без публичного домена
- Простая аутентификация через Service Account для Google Calendar

---

## Общие требования

Создай **ОДИН файл** `bot.py`, в котором:

1. Есть блок импорта и глобальная конфигурация
2. Есть механизм загрузки настроек из `.env` (через `python-dotenv`)
3. Есть следующие компоненты:
   - Инициализация Telegram-бота (на `aiogram` v3)
   - Функции работы с GigaChat (получение токена, вызов API, парсинг)
   - Функции работы с STT (базовая реализация с TODO)
   - Функции работы с Google Calendar (создание, получение, удаление событий)
   - Функции работы с SQLite (инициализация БД, сохранение, получение событий)
   - Фоновая задача для отправки напоминаний
   - Обработка сигналов для graceful shutdown
   - Запуск через `asyncio.run(main())`

Разбей код внутри одного файла на **логичные секции** с комментариями:

```python
# =============================
# CONFIGURATION & SETTINGS
# =============================

# =============================
# DATABASE FUNCTIONS
# =============================

# =============================
# GIGACHAT INTEGRATION
# =============================

# =============================
# GOOGLE CALENDAR INTEGRATION
# =============================

# =============================
# SPEECH-TO-TEXT (STT)
# =============================

# =============================
# TELEGRAM BOT HANDLERS
# =============================

# =============================
# REMINDER WORKER
# =============================

# =============================
# MAIN APPLICATION
# =============================
```

---

## Стек и библиотеки

Используй следующие библиотеки:

- **Python 3.10+**
- **aiogram (v3)** — для Telegram-бота через long polling
- **httpx** — для HTTP-запросов (GigaChat, STT, Google) с поддержкой async
- **python-dotenv** — для чтения `.env`
- **google-api-python-client** — для Google Calendar API
- **google-auth** — для аутентификации через Service Account
- **sqlite3** — для локальной SQLite-базы (встроенный модуль)
- **asyncio** — для фоновых задач
- **dataclasses** или **pydantic** — для моделей данных (опционально)

В начале файла добавь комментарий с командой установки:

```python
"""
Установка зависимостей:
pip install aiogram httpx python-dotenv google-api-python-client google-auth pytz

Для STT (Яндекс SpeechKit):
pip install pydub  # для конвертации аудио (опционально)
"""
```

---

## Переменные окружения

В начале файла опиши (комментарием) пример `.env`:

```python
"""
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
```

**Функция `load_config()`:**

```python
@dataclass
class Config:
    telegram_bot_token: str
    gigachat_client_id: str
    gigachat_client_secret: str
    gigachat_scope: str
    stt_api_key: str | None
    stt_folder_id: str | None
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
        stt_api_key=os.getenv('STT_API_KEY'),
        stt_folder_id=os.getenv('STT_FOLDER_ID'),
        google_credentials_file=os.getenv('GOOGLE_CREDENTIALS_FILE'),
        google_calendar_id=os.getenv('GOOGLE_CALENDAR_ID', 'primary'),
        timezone=os.getenv('TIMEZONE', 'Europe/Moscow'),
        reminder_minutes_before=int(os.getenv('REMINDER_MINUTES_BEFORE', '15')),
        reminder_check_interval=int(os.getenv('REMINDER_CHECK_INTERVAL', '60')),
        database_file=os.getenv('DATABASE_FILE', 'events.db'),
        temp_dir=os.getenv('TEMP_DIR', 'temp')
    )
```

---

## Настройка Google Calendar

Для личного использования **рекомендуется Service Account** (проще, чем OAuth2).

### Пошаговая инструкция:

1. **Создай проект в Google Cloud Console:**
   - Перейди на https://console.cloud.google.com/
   - Создай новый проект (например, "Calendar Bot")

2. **Включи Google Calendar API:**
   - В меню "APIs & Services" → "Library"
   - Найди "Google Calendar API" и включи его

3. **Создай Service Account:**
   - В меню "APIs & Services" → "Credentials"
   - Нажми "Create Credentials" → "Service Account"
   - Укажи имя (например, "calendar-bot")
   - Нажми "Create and Continue"
   - Роль не требуется (можно пропустить)
   - Нажми "Done"

4. **Скачай JSON-ключ:**
   - Найди созданный Service Account в списке
   - Нажми на него → вкладка "Keys"
   - "Add Key" → "Create new key" → "JSON"
   - Сохрани файл как `service-account.json`

5. **Дай доступ Service Account к календарю:**
   - Открой скачанный JSON-файл
   - Скопируй email Service Account (поле `client_email`)
   - Открой Google Calendar (https://calendar.google.com/)
   - Настройки календаря → "Настройки доступа"
   - Добавь email Service Account с правами "Вносить изменения в мероприятия"

6. **Укажи путь к файлу в `.env`:**
   ```
   GOOGLE_CREDENTIALS_FILE=service-account.json
   ```

### Код для аутентификации:

```python
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_google_calendar_service(config: Config):
    """Создаёт сервис Google Calendar через Service Account"""
    credentials = service_account.Credentials.from_service_account_file(
        config.google_credentials_file,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    return build('calendar', 'v3', credentials=credentials)
```

---

## Логика Telegram-бота

Реализуй в одном файле:

### Инициализация

```python
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message

bot = Bot(token=config.telegram_bot_token)
dp = Dispatcher()
router = Router()
dp.include_router(router)
```

### Обработчики команд

#### 1. `/start`

```python
@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "👋 Привет! Я помогу быстро создавать встречи в Google Календаре.\n\n"
        "📝 Отправь мне текст или голосовое сообщение, например:\n"
        "• «Завтра в 15:00 встреча с Катей по ипотеке, час»\n"
        "• «Послезавтра в 10:00 созвон с командой, 30 минут, онлайн»\n"
        "• «В пятницу в 18:00 ужин с друзьями»\n\n"
        f"⏰ За {config.reminder_minutes_before} минут до встречи пришлю напоминание.\n\n"
        "Команды:\n"
        "/help - справка\n"
        "/list - показать ближайшие события\n"
        "/cancel <название> - отменить событие"
    )
```

#### 2. `/help`

```python
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📖 Справка по использованию бота:\n\n"
        "1️⃣ Отправь текст или голосовое с описанием встречи\n"
        "2️⃣ Я создам событие в твоём Google Календаре\n"
        "3️⃣ Перед встречей пришлю напоминание\n\n"
        "Примеры запросов:\n"
        "• «Завтра в 14:00 встреча с клиентом, 2 часа»\n"
        "• «Послезавтра в 9:00 планёрка, 45 минут, онлайн»\n"
        "• «В понедельник в 16:00 звонок с партнёром»\n\n"
        "Команды:\n"
        "/start - начало работы\n"
        "/list - показать ближайшие 5 событий\n"
        "/cancel <название> - отменить событие по названию"
    )
```

#### 3. `/list` (показать ближайшие события)

```python
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
```

#### 4. `/cancel` (отменить событие)

```python
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
```

#### 5. Текстовые сообщения

```python
@router.message(F.text & ~F.text.startswith('/'))
async def handle_text_message(message: Message):
    """Обработчик текстовых сообщений"""
    try:
        await message.answer("⏳ Обрабатываю запрос...")
        await handle_natural_language(message.text, message.chat.id, message)
        
    except Exception as e:
        logging.error(f"Ошибка обработки текста: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке запроса.\n"
            "Попробуйте переформулировать или обратитесь к /help"
        )
```

#### 6. Голосовые сообщения

```python
@router.message(F.voice)
async def handle_voice_message(message: Message):
    """Обработчик голосовых сообщений"""
    try:
        await message.answer("🎤 Распознаю голосовое сообщение...")
        
        # Создаём временную директорию, если её нет
        os.makedirs(config.temp_dir, exist_ok=True)
        
        # Скачиваем файл
        file = await bot.get_file(message.voice.file_id)
        file_path = os.path.join(config.temp_dir, f"voice_{uuid.uuid4()}.ogg")
        await bot.download_file(file.file_path, file_path)
        
        # Распознаём речь
        text = await speech_to_text(file_path, config)
        
        # Удаляем временный файл
        try:
            os.remove(file_path)
        except:
            pass
        
        await message.answer(f"📝 Распознано: {text}")
        await handle_natural_language(text, message.chat.id, message)
        
    except Exception as e:
        logging.error(f"Ошибка обработки голосового сообщения: {e}")
        await message.answer(
            "❌ Не удалось распознать голосовое сообщение.\n"
            "Попробуйте отправить текстом."
        )
```

### Основная функция обработки

```python
async def handle_natural_language(text: str, chat_id: int, message: Message):
    """Обрабатывает естественный язык: парсинг через GigaChat → создание события"""
    try:
        # 1. Парсим текст через GigaChat
        parsed_event = await parse_event_from_gigachat(text, config)
        
        # 2. Проверяем, что событие в будущем
        now = datetime.now(pytz.timezone(config.timezone))
        if parsed_event.start_datetime < now:
            await message.answer("❌ Нельзя создать событие в прошлом. Укажите будущую дату.")
            return
        
        # 3. Создаём событие в Google Calendar
        event_id = await create_calendar_event(parsed_event, chat_id, config)
        
        # 4. Сохраняем в БД
        save_event(
            calendar_event_id=event_id,
            chat_id=chat_id,
            title=parsed_event.title,
            start_dt_local=parsed_event.start_datetime,
            reminder_minutes=config.reminder_minutes_before,
            timezone=config.timezone
        )
        
        # 5. Отправляем подтверждение
        end_time = parsed_event.start_datetime + timedelta(minutes=parsed_event.duration_minutes or 60)
        response = (
            f"✅ Создала событие:\n\n"
            f"📌 {parsed_event.title}\n"
            f"🕐 {parsed_event.start_datetime.strftime('%d.%m.%Y %H:%M')} - "
            f"{end_time.strftime('%H:%M')}\n"
        )
        if parsed_event.description:
            response += f"📝 {parsed_event.description}\n"
        response += f"\n⏰ Напомню за {config.reminder_minutes_before} минут"
        
        await message.answer(response)
        logging.info(f"Создано событие {event_id} для пользователя {chat_id}")
        
    except ValueError as e:
        await message.answer(f"❌ {str(e)}")
    except Exception as e:
        logging.error(f"Ошибка создания события: {e}")
        await message.answer("❌ Не удалось создать событие. Попробуйте ещё раз.")
```

---

## Распознавание речи (STT)

Базовая реализация с примером для Яндекс SpeechKit:

```python
async def speech_to_text(file_path: str, config: Config) -> str:
    """
    Распознаёт речь из аудиофайла через STT-провайдер
    
    TODO: Реализовать интеграцию с выбранным STT-провайдером
    Варианты:
    - Яндекс SpeechKit (https://cloud.yandex.ru/docs/speechkit/)
    - Google Speech-to-Text
    - OpenAI Whisper API
    """
    
    if not config.stt_api_key:
        raise ValueError("STT_API_KEY не настроен в .env")
    
    # Пример для Яндекс SpeechKit
    try:
        async with httpx.AsyncClient() as client:
            with open(file_path, 'rb') as audio_file:
                response = await client.post(
                    'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize',
                    headers={
                        'Authorization': f'Api-Key {config.stt_api_key}',
                    },
                    params={
                        'lang': 'ru-RU',
                        'folderId': config.stt_folder_id,
                    },
                    content=audio_file.read()
                )
                
                if response.status_code != 200:
                    raise Exception(f"STT API error: {response.status_code}")
                
                result = response.json()
                return result.get('result', '')
                
    except Exception as e:
        logging.error(f"Ошибка STT: {e}")
        raise ValueError("Не удалось распознать речь")
```

---

## Интеграция с GigaChat

### Получение токена доступа

```python
# Глобальный кеш токена
_gigachat_token_cache = {
    'token': None,
    'expires_at': None
}

async def get_gigachat_access_token(config: Config) -> str:
    """Получает access token для GigaChat API с кешированием"""
    
    # Проверяем кеш
    if _gigachat_token_cache['token'] and _gigachat_token_cache['expires_at']:
        if datetime.now() < _gigachat_token_cache['expires_at'] - timedelta(minutes=5):
            return _gigachat_token_cache['token']
    
    # Получаем новый токен
    try:
        auth_string = f"{config.gigachat_client_id}:{config.gigachat_client_secret}"
        auth_base64 = base64.b64encode(auth_string.encode()).decode()
        
        async with httpx.AsyncClient(verify=False) as client:  # verify=False для Sberbank API
            response = await client.post(
                'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json',
                    'RqUID': str(uuid.uuid4()),
                    'Authorization': f'Basic {auth_base64}'
                },
                data={
                    'scope': config.gigachat_scope
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"GigaChat auth error: {response.status_code}")
            
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
```

### Вызов GigaChat API

```python
async def call_gigachat(text: str, config: Config) -> dict:
    """Отправляет запрос в GigaChat API"""
    
    token = await get_gigachat_access_token(config)
    
    # Улучшенный промпт с примерами
    system_prompt = """Ты помощник, который разбирает естественный текст пользователя о встречах и возвращает СТРОГО JSON без пояснений.

Поля JSON:
- title: короткое название встречи (строка)
- date: дата в формате YYYY-MM-DD (строка)
- time: время начала в формате HH:MM, 24 часа (строка или null)
- duration_minutes: длительность в минутах (число или null)
- description: дополнительное описание (строка)
- location: место встречи, если указано "онлайн" - пиши "online" (строка или null)

Правила:
1. Пользователь пишет по-русски, текущая временная зона: {timezone}
2. "Сегодня" = текущая дата, "завтра" = +1 день, "послезавтра" = +2 дня
3. Дни недели: "в понедельник", "в пятницу" = ближайший такой день
4. "Через неделю" = +7 дней, "через 2 недели" = +14 дней
5. Если указан диапазон времени "с 15:00 до 16:30", то time=15:00, duration_minutes=90
6. Если указано "час" = 60 минут, "полчаса" = 30 минут, "2 часа" = 120 минут
7. Если время НЕ указано - верни time: null и duration_minutes: null
8. Если длительность НЕ указана, но есть время - верни duration_minutes: null
9. Если указано "онлайн", "zoom", "meet" - добавь location: "online"

Примеры:

Вход: "Завтра в 15:00 встреча с Катей по ипотеке, час"
Выход: {"title": "Встреча с Катей по ипотеке", "date": "2024-01-16", "time": "15:00", "duration_minutes": 60, "description": "", "location": null}

Вход: "Послезавтра в 10:00 созвон с командой, 30 минут, онлайн"
Выход: {"title": "Созвон с командой", "date": "2024-01-17", "time": "10:00", "duration_minutes": 30, "description": "", "location": "online"}

Вход: "В пятницу в 18:00 ужин с друзьями"
Выход: {"title": "Ужин с друзьями", "date": "2024-01-19", "time": "18:00", "duration_minutes": null, "description": "", "location": null}

Вход: "Через неделю планёрка с 9:00 до 10:30"
Выход: {"title": "Планёрка", "date": "2024-01-22", "time": "09:00", "duration_minutes": 90, "description": "", "location": null}

Возвращай ТОЛЬКО JSON, без markdown, без пояснений."""
    
    system_prompt = system_prompt.replace('{timezone}', config.timezone)
    
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
```

### Парсинг ответа GigaChat

```python
@dataclass
class ParsedEvent:
    """Модель распознанного события"""
title: str
    start_datetime: datetime
duration_minutes: int | None
description: str
    location: str | None = None

async def parse_event_from_gigachat(text: str, config: Config) -> ParsedEvent:
    """Парсит текст через GigaChat и возвращает структурированное событие"""
    
    # Вызываем GigaChat
    response = await call_gigachat(text, config)
    
    # Извлекаем контент
    content = response['choices'][0]['message']['content']
    logging.info(f"GigaChat ответ: {content}")
    
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
        
    except json.JSONDecodeError:
        # Пытаемся найти JSON через регулярку
        import re
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
        
        tz = pytz.timezone(config.timezone)
        start_datetime = tz.localize(datetime.strptime(datetime_str, '%Y-%m-%d %H:%M'))
        
    except Exception as e:
        logging.error(f"Ошибка парсинга даты/времени: {e}")
        raise ValueError("Некорректный формат даты или времени")
    
    return ParsedEvent(
        title=data['title'],
        start_datetime=start_datetime,
        duration_minutes=data.get('duration_minutes'),
        description=data.get('description', ''),
        location=data.get('location')
    )
```

---

## Google Calendar - создание события

```python
async def create_calendar_event(event: ParsedEvent, chat_id: int, config: Config) -> str:
    """Создаёт событие в Google Calendar и возвращает event_id"""
    
    service = get_google_calendar_service(config)
    
    # Вычисляем время окончания
    duration = event.duration_minutes or 60  # По умолчанию 60 минут
    end_datetime = event.start_datetime + timedelta(minutes=duration)
    
    # Формируем тело события
    event_body = {
        'summary': event.title,
        'description': event.description,
        'start': {
            'dateTime': event.start_datetime.isoformat(),
            'timeZone': config.timezone,
        },
        'end': {
            'dateTime': end_datetime.isoformat(),
            'timeZone': config.timezone,
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': config.reminder_minutes_before},
            ],
        },
    }
    
    # Добавляем location, если указано
    if event.location:
        event_body['location'] = event.location
    
    # Создаём событие
    try:
        created_event = service.events().insert(
            calendarId=config.google_calendar_id,
            body=event_body
        ).execute()
        
        event_id = created_event['id']
        logging.info(f"Создано событие в Google Calendar: {event_id}")
        return event_id
        
    except Exception as e:
        logging.error(f"Ошибка создания события в Google Calendar: {e}")
        raise ValueError("Не удалось создать событие в календаре")
```

---

## SQLite - хранение событий

```python
def init_db(config: Config):
    """Инициализирует SQLite базу данных"""
    conn = sqlite3.connect(config.database_file)
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

def save_event(calendar_event_id: str, chat_id: int, title: str, 
               start_dt_local: datetime, reminder_minutes: int, timezone: str):
    """Сохраняет событие в БД"""
    
    # Переводим в UTC
    start_dt_utc = start_dt_local.astimezone(pytz.UTC)
    reminder_dt_local = start_dt_local - timedelta(minutes=reminder_minutes)
    reminder_dt_utc = reminder_dt_local.astimezone(pytz.UTC)
    
    conn = sqlite3.connect(config.database_file)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO events (calendar_event_id, chat_id, title, start_datetime_utc, 
                           reminder_datetime_utc, reminder_sent)
        VALUES (?, ?, ?, ?, ?, 0)
    ''', (
        calendar_event_id,
        chat_id,
        title,
        start_dt_utc.isoformat(),
        reminder_dt_utc.isoformat()
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
```

---

## Напоминания через Telegram

```python
async def reminder_worker(bot: Bot, config: Config):
    """Фоновая задача для отправки напоминаний"""
    logging.info("Запущен reminder_worker")
    
    while True:
        try:
            # Текущее время UTC
            now_utc = datetime.now(pytz.UTC)
            
            # Получаем события для напоминания
            conn = sqlite3.connect(config.database_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, calendar_event_id, chat_id, title, start_datetime_utc
                FROM events
                WHERE reminder_sent = 0 
                AND reminder_datetime_utc <= ?
            ''', (now_utc.isoformat(),))
            
            events = cursor.fetchall()
            
            for event_id, calendar_event_id, chat_id, title, start_datetime_utc in events:
                try:
                    # Конвертируем время в локальную таймзону
                    start_dt = datetime.fromisoformat(start_datetime_utc).replace(tzinfo=pytz.UTC)
                    start_local = start_dt.astimezone(pytz.timezone(config.timezone))
                    
                    # Отправляем напоминание
                    message = (
                        f"⏰ Напоминание!\n\n"
                        f"📌 {title}\n"
                        f"🕐 {start_local.strftime('%d.%m.%Y в %H:%M')}\n\n"
                        f"Через {config.reminder_minutes_before} минут"
                    )
                    
                    await bot.send_message(chat_id, message)
                    
                    # Отмечаем как отправленное
                    cursor.execute('''
                        UPDATE events SET reminder_sent = 1 WHERE id = ?
                    ''', (event_id,))
                    conn.commit()
                    
                    logging.info(f"Отправлено напоминание для события {calendar_event_id}")
                    
                except Exception as e:
                    logging.error(f"Ошибка отправки напоминания для события {event_id}: {e}")
            
            conn.close()
            
        except Exception as e:
            logging.error(f"Ошибка в reminder_worker: {e}")
        
        # Ждём перед следующей проверкой
        await asyncio.sleep(config.reminder_check_interval)
```

---

## Логирование

Настрой логирование в начале файла:

```python
import logging

# Настройка логирования
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
```

**Что логировать:**

- `INFO`: создание событий, отправка напоминаний, команды пользователей
- `WARNING`: повторные попытки запросов, некритичные ошибки
- `ERROR`: ошибки API, парсинга, сетевые ошибки
- `DEBUG`: детальная информация для отладки (опционально)

---

## Graceful Shutdown

Добавь обработку сигналов для корректного завершения:

```python
import signal

# Глобальный флаг для остановки
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Обработчик сигналов для graceful shutdown"""
    logging.info(f"Получен сигнал {sig}, завершаем работу...")
    shutdown_event.set()

async def main():
    """Главная функция приложения"""
    global config
    
    # Загружаем конфигурацию
    try:
        config = load_config()
    except Exception as e:
        logging.error(f"Ошибка загрузки конфигурации: {e}")
        return
    
    # Инициализируем БД
    init_db(config)
    
    # Создаём временную директорию
    os.makedirs(config.temp_dir, exist_ok=True)
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Запускаем reminder_worker
    reminder_task = asyncio.create_task(reminder_worker(bot, config))
    
    # Запускаем polling в отдельной задаче
    polling_task = asyncio.create_task(dp.start_polling(bot))
    
    logging.info("Бот запущен")
    
    # Ждём сигнала завершения
    await shutdown_event.wait()
    
    # Останавливаем polling
    logging.info("Останавливаем polling...")
    polling_task.cancel()
    
    # Останавливаем reminder_worker
    logging.info("Останавливаем reminder_worker...")
    reminder_task.cancel()
    
    # Ждём завершения задач
    await asyncio.gather(polling_task, reminder_task, return_exceptions=True)
    
    # Закрываем бота
    await bot.session.close()
    
    logging.info("Бот остановлен")

if __name__ == '__main__':
    asyncio.run(main())
```

---

## Сценарий для пользователя

### Установка

```bash
# 1. Установи зависимости
pip install aiogram httpx python-dotenv google-api-python-client google-auth pytz

# Опционально для STT:
pip install pydub
```

### Настройка

```bash
# 2. Создай файл .env
cat > .env << EOF
TELEGRAM_BOT_TOKEN=твой_токен_от_BotFather
GIGACHAT_CLIENT_ID=твой_client_id
GIGACHAT_CLIENT_SECRET=твой_client_secret
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GOOGLE_CREDENTIALS_FILE=service-account.json
GOOGLE_CALENDAR_ID=primary
TIMEZONE=Europe/Moscow
REMINDER_MINUTES_BEFORE=15
EOF

# 3. Настрой Google Calendar (см. раздел "Настройка Google Calendar")
# 4. Положи файл service-account.json в директорию с ботом
```

### Запуск

```bash
# Запусти бота
python bot.py

# Или в фоне (Linux)
nohup python bot.py > bot.log 2>&1 &
```

### Использование

1. Найди своего бота в Telegram
2. Отправь `/start`
3. Отправь текст или голосовое сообщение:
   - "Завтра в 15:00 встреча с Катей по ипотеке, час"
   - "Послезавтра в 10:00 созвон с командой, 30 минут, онлайн"
   - "В пятницу в 18:00 ужин с друзьями"

4. Бот создаст событие и ответит:
   ```
   ✅ Создала событие:
   
   📌 Встреча с Катей по ипотеке
   🕐 16.01.2024 15:00 - 16:00
   
   ⏰ Напомню за 15 минут
   ```

5. За 15 минут до встречи получишь напоминание:
   ```
   ⏰ Напоминание!
   
   📌 Встреча с Катей по ипотеке
   🕐 16.01.2024 в 15:00
   
   Через 15 минут
   ```

### Дополнительные команды

- `/list` — показать ближайшие 5 событий
- `/cancel Встреча с Катей` — отменить событие
- `/help` — справка

---

## Качество кода

### Требования:

1. **Type hints** — используй аннотации типов для всех функций
2. **Обработка ошибок** — оборачивай сетевые запросы в try-except
3. **Логирование** — логируй все важные события и ошибки
4. **Читаемость** — разделяй код на небольшие функции
5. **Комментарии** — добавляй docstrings к функциям
6. **Константы** — выноси магические числа в константы или конфиг

### Обработка ошибок:

```python
# Сетевые ошибки с retry
async def call_api_with_retry(func, max_retries=3):
    """Вызывает функцию с повторными попытками"""
    for attempt in range(max_retries):
        try:
            return await func()
        except httpx.RequestError as e:
            if attempt == max_retries - 1:
                raise
            logging.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

# Валидация данных
def validate_event_data(data: dict) -> None:
    """Проверяет корректность данных события"""
    required_fields = ['title', 'date', 'time']
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        raise ValueError(f"Отсутствуют обязательные поля: {', '.join(missing)}")

# Обработка конфликтов времени
async def check_time_conflicts(start_dt: datetime, end_dt: datetime, config: Config) -> bool:
    """Проверяет конфликты времени в календаре"""
    service = get_google_calendar_service(config)
    events = service.events().list(
        calendarId=config.google_calendar_id,
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True
    ).execute()
    return len(events.get('items', [])) > 0
```

---

## Troubleshooting

### Проблема: Бот не отвечает

**Решение:**
- Проверь, что `TELEGRAM_BOT_TOKEN` корректный
- Проверь логи: `tail -f bot.log`
- Убедись, что бот запущен: `ps aux | grep bot.py`

### Проблема: Ошибка аутентификации GigaChat

**Решение:**
- Проверь `GIGACHAT_CLIENT_ID` и `GIGACHAT_CLIENT_SECRET`
- Убедись, что scope правильный: `GIGACHAT_API_PERS`
- Проверь, что сертификаты Sberbank доступны (или используй `verify=False`)

### Проблема: Не создаются события в Google Calendar

**Решение:**
- Проверь, что Service Account email добавлен в календарь с правами на изменение
- Проверь путь к `service-account.json`
- Убедись, что Google Calendar API включён в проекте

### Проблема: Не приходят напоминания

**Решение:**
- Проверь, что `reminder_worker` запущен (смотри логи)
- Проверь `REMINDER_CHECK_INTERVAL` — возможно, слишком большой
- Убедись, что события сохраняются в БД: `sqlite3 events.db "SELECT * FROM events;"`

### Проблема: Ошибка распознавания речи

**Решение:**
- Проверь `STT_API_KEY` и `STT_FOLDER_ID`
- Убедись, что формат аудио поддерживается (OGG)
- Попробуй конвертировать аудио в другой формат (используй `pydub`)

### Проблема: GigaChat не распознаёт дату/время

**Решение:**
- Попробуй более явный формат: "16 января в 15:00" вместо "завтра в 3 дня"
- Проверь, что `TIMEZONE` настроен правильно
- Посмотри логи — там будет ответ GigaChat

### Проблема: Высокое потребление памяти

**Решение:**
- Очищай временные файлы: проверь директорию `temp/`
- Ограничь размер лога: используй `RotatingFileHandler`
- Периодически очищай старые события из БД

---

## Итоговая структура файла

```python
#!/usr/bin/env python3
"""
Telegram-бот для управления Google Calendar через GigaChat

Установка: pip install aiogram httpx python-dotenv google-api-python-client google-auth pytz
Запуск: python bot.py
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
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pytz
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message
from google.oauth2 import service_account
from googleapiclient.discovery import build

# =============================
# CONFIGURATION & SETTINGS
# =============================
# ... (код конфигурации)

# =============================
# LOGGING SETUP
# =============================
# ... (настройка логирования)

# =============================
# DATABASE FUNCTIONS
# =============================
# ... (init_db, save_event, delete_event_from_db)

# =============================
# GIGACHAT INTEGRATION
# =============================
# ... (get_gigachat_access_token, call_gigachat, parse_event_from_gigachat)

# =============================
# GOOGLE CALENDAR INTEGRATION
# =============================
# ... (get_google_calendar_service, create_calendar_event)

# =============================
# SPEECH-TO-TEXT (STT)
# =============================
# ... (speech_to_text)

# =============================
# TELEGRAM BOT HANDLERS
# =============================
# ... (cmd_start, cmd_help, cmd_list_events, cmd_cancel_event, 
#      handle_text_message, handle_voice_message, handle_natural_language)

# =============================
# REMINDER WORKER
# =============================
# ... (reminder_worker)

# =============================
# GRACEFUL SHUTDOWN
# =============================
# ... (signal_handler, shutdown_event)

# =============================
# MAIN APPLICATION
# =============================
# ... (main)

if __name__ == '__main__':
    asyncio.run(main())
```

---

**Готово!** Этот документ содержит полную спецификацию для создания Telegram-бота с интеграцией GigaChat и Google Calendar. Следуй инструкциям последовательно, и у тебя получится рабочее приложение.
