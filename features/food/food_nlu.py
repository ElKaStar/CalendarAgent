"""
Модуль для парсинга сообщений о еде (Natural Language Understanding)

Режимы:
- RULES: без внешних моделей, по простым эвристикам
- LLM: опционально, если доступен LLM-провайдер (GigaChat)
"""
import re
import json
import logging
import httpx
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import pytz
from features.food.config import FOOD_CODE_WORDS, SPEECH_CORRECTIONS_PATTERNS, SPEECH_CORRECTIONS_CODE_WORDS


@dataclass
class ParsedFoodLog:
    """Модель распознанной записи о еде"""
    event_date: str  # YYYY-MM-DD
    meal_type: str  # breakfast|lunch|dinner|snack|unknown
    items: List[Dict[str, Any]]  # [{"name": "...", "qty_text": "...", "grams": null, "ml": null}]
    confidence: str  # "high" | "low"
    notes: str  # Дополнительные заметки
    raw_text: str  # Исходный текст


def parse_food_message(text: str, now_dt: datetime, user_tz: str) -> ParsedFoodLog:
    """
    Парсит сообщение о еде и извлекает структурированные данные
    
    Args:
        text: Текст сообщения
        now_dt: Текущая дата/время (datetime объект)
        user_tz: Временная зона пользователя (например, 'Europe/Moscow')
        
    Returns:
        ParsedFoodLog с извлечёнными данными
    """
    if not text or not text.strip():
        raise ValueError("Пустой текст сообщения")
    
    text_clean = text.strip()
    text_lower = text_clean.lower()
    
    # Определяем дату события
    event_date = _extract_date(text_lower, now_dt, user_tz)
    
    # Определяем тип приёма пищи
    meal_type = _extract_meal_type(text_lower)
    
    # Извлекаем список продуктов
    items = _extract_items(text_clean, text_lower)
    
    # Определяем уверенность
    confidence = "high" if items else "low"
    
    # Заметки (оставляем исходный текст)
    notes = text_clean
    
    return ParsedFoodLog(
        event_date=event_date,
        meal_type=meal_type,
        items=items,
        confidence=confidence,
        notes=notes,
        raw_text=text_clean
    )


def _extract_date(text_lower: str, now_dt: datetime, user_tz: str) -> str:
    """
    Извлекает дату из текста
    
    Поддерживает:
    - "сегодня" → сегодня
    - "завтра" → завтра
    - "вчера" → вчера
    - "послезавтра" → послезавтра
    - "YYYY-MM-DD" → явная дата
    """
    tz = pytz.timezone(user_tz)
    now_local = now_dt.astimezone(tz) if now_dt.tzinfo else tz.localize(now_dt)
    today = now_local.date()
    
    # Проверяем явную дату YYYY-MM-DD
    date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text_lower)
    if date_match:
        try:
            parsed_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            pass
    
    # Ключевые слова
    if 'вчера' in text_lower:
        target_date = today - timedelta(days=1)
    elif 'послезавтра' in text_lower:
        target_date = today + timedelta(days=2)
    elif 'завтра' in text_lower:
        target_date = today + timedelta(days=1)
    else:
        # По умолчанию - сегодня
        target_date = today
    
    return target_date.strftime('%Y-%m-%d')


def _extract_meal_type(text_lower: str) -> str:
    """
    Определяет тип приёма пищи
    
    Returns:
        'breakfast' | 'lunch' | 'dinner' | 'snack' | 'unknown'
    """
    # Завтрак
    if re.search(r'\b(завтрак|утром|утренний|утро)\b', text_lower):
        return 'breakfast'
    
    # Обед
    if re.search(r'\b(обед|днём|дневной|день|в обед)\b', text_lower):
        return 'lunch'
    
    # Ужин
    if re.search(r'\b(ужин|вечером|вечерний|вечер|на ужин)\b', text_lower):
        return 'dinner'
    
    # Перекус
    if re.search(r'\b(перекус|полдник|ланч|бранч|снэк)\b', text_lower):
        return 'snack'
    
    return 'unknown'


def _extract_items(text_clean: str, text_lower: str) -> List[Dict[str, Any]]:
    """
    Извлекает список продуктов из текста
    
    Разделители: запятые, точки с запятой, "и", "с", "плюс"
    
    Returns:
        Список словарей: [{"name": "...", "qty_text": "...", "grams": null, "ml": null}]
    """
    items = []
    
    # Сначала исправляем ошибки распознавания кодовых слов в начале текста
    # Это нужно сделать ДО удаления кодовых слов
    for wrong, correct in SPEECH_CORRECTIONS_CODE_WORDS.items():
        # Проверяем начало текста (с учетом возможной точки после слова)
        # Используем более широкий паттерн для поиска в начале
        pattern = rf'^{re.escape(wrong)}([.\s,]+)'
        if re.match(pattern, text_clean, re.IGNORECASE):
            text_clean = re.sub(pattern, rf'{correct}\1', text_clean, count=1, flags=re.IGNORECASE)
            logging.info(f"Исправлена ошибка распознавания кодового слова: '{wrong}' → '{correct}'")
            break
        # Если просто начинается с wrong и есть пробел после
        elif text_clean.lower().startswith(wrong + ' '):
            text_clean = re.sub(rf'^{re.escape(wrong)}', correct, text_clean, count=1, flags=re.IGNORECASE)
            logging.info(f"Исправлена ошибка распознавания кодового слова (с пробелом): '{wrong}' → '{correct}'")
            break
        # Также проверяем без разделителя после (на случай "минукартофель")
        elif text_clean.lower().startswith(wrong) and len(text_clean) > len(wrong):
            # Проверяем, что следующая буква не является частью слова
            next_char = text_clean[len(wrong):len(wrong)+1]
            if next_char and not next_char.isalpha():
                text_clean = re.sub(rf'^{re.escape(wrong)}', correct, text_clean, count=1, flags=re.IGNORECASE)
                logging.info(f"Исправлена ошибка распознавания кодового слова (без разделителя): '{wrong}' → '{correct}'")
                break
    
    # Убираем кодовые слова и служебные слова в начале
    # Кодовые слова для дневника питания, убираем их первыми (с точкой или без)
    code_words_pattern = '|'.join([re.escape(cw) for cw in FOOD_CODE_WORDS])
    # Убираем кодовое слово с точкой или пробелом после него
    text_clean = re.sub(rf'^({code_words_pattern})[.\s]+', '', text_clean, flags=re.IGNORECASE)
    
    # Исправляем частые ошибки распознавания речи для продуктов
    for pattern, replacement in SPEECH_CORRECTIONS_PATTERNS.items():
        text_clean = re.sub(pattern, replacement, text_clean, flags=re.IGNORECASE)
        text_lower = text_clean.lower()
    
    # Исправляем ошибки распознавания чисел с запятой ДО разделения на части
    # "1,20 грамма" → "120 грамма" (предполагая что это 120, а не 1.20)
    def fix_comma_number(m):
        return str(int(m.group(1)) * 100 + int(m.group(2)))
    text_clean = re.sub(r'(\d+),(\d{2})(?=\s*(?:г|грамм|грамма|граммов|мл|миллилитр|миллилитра|миллилитров|литр|литра|литров)\b)', fix_comma_number, text_clean, flags=re.IGNORECASE)
    # Исправляем "грамма2", "грамм2" и т.д. ДО разделения на части
    text_clean = re.sub(r'(грамма|грамм|рамма|рамм)(\d+)', r'\1', text_clean, flags=re.IGNORECASE)
    
    # Убираем глаголы и служебные слова после "menu"
    text_clean = re.sub(r'^(еда|меню|съел|съела|съели|поел|поела|поели|перекус|завтрак|обед|ужин)[:\s]+', '', text_clean, flags=re.IGNORECASE)
    # Убираем глаголы, которые могут идти после "menu" (например, "menu сегодня съел гречку")
    text_clean = re.sub(r'\b(сегодня|завтра|вчера|послезавтра)\s+(съел|съела|съели|поел|поела|поели)\s+', '', text_clean, flags=re.IGNORECASE)
    text_clean = text_clean.strip()
    
    # Убираем указания даты/времени
    text_clean = re.sub(r'\b(сегодня|завтра|вчера|послезавтра|утром|днём|вечером)\b', '', text_clean, flags=re.IGNORECASE)
    text_clean = re.sub(r'\s+', ' ', text_clean).strip()
    
    if not text_clean:
        return items
    
    # Разделяем по разделителям
    # Сначала по точкам с запятой
    parts = re.split(r'[;；]', text_clean)
    
    # Затем по запятым внутри каждой части
    all_parts = []
    for part in parts:
        all_parts.extend(re.split(r'[,，]', part))
    
    # Также разделяем по "и", "с", "плюс" (но только если они не в середине слова)
    final_parts = []
    for part in all_parts:
        # Разделяем по "и", "с", "плюс" только если они стоят отдельно
        sub_parts = re.split(r'\s+(?:и|с|плюс)\s+', part, flags=re.IGNORECASE)
        final_parts.extend(sub_parts)
    
    # Очищаем и добавляем в список
    for part in final_parts:
        part = part.strip()
        if not part:
            continue
        
        # Убираем лишние пробелы
        part = re.sub(r'\s+', ' ', part)
        
        # Извлекаем количество (если есть)
        qty_text = None
        grams = None
        ml = None
        
        # Ошибки распознавания уже исправлены на уровне всего текста ДО разделения
        
        # Ищем граммы/миллилитры - ищем паттерн "число + единица" с пробелами
        # Паттерн: число, затем пробелы, затем единица измерения (г, грамм, мл, и т.д.)
        # Также включаем ошибочные варианты распознавания: "рамм", "рамма", "раммов"
        qty_match = re.search(r'(\d+)\s+(г|грамм|грамма|граммов|рамм|рамма|раммов|мл|миллилитр|миллилитра|миллилитров|литр|литра|литров)\b', part, re.IGNORECASE)
        if not qty_match:
            # Пробуем без пробела (например, "120грамма" или "120рамм")
            qty_match = re.search(r'(\d+)(г|грамм|грамма|граммов|рамм|рамма|раммов|мл|миллилитр|миллилитра|миллилитров|литр|литра|литров)\b', part, re.IGNORECASE)
        if qty_match:
            qty_text = qty_match.group(0).strip()
            value = int(qty_match.group(1))
            unit = qty_match.group(2).lower()
            # Нормализуем единицу измерения (исправляем "рамм" на "грамм")
            if unit in ['рамм', 'рамма', 'раммов']:
                # Исправляем единицу измерения
                if unit == 'рамм':
                    unit = 'грамм'
                elif unit == 'рамма':
                    unit = 'грамма'
                elif unit == 'раммов':
                    unit = 'граммов'
                qty_text = f"{value} {unit}"  # Обновляем qty_text с правильной единицей
            
            if unit in ['г', 'грамм', 'грамма', 'граммов']:
                grams = value
            elif unit in ['мл', 'миллилитр', 'миллилитра', 'миллилитров', 'л', 'литр', 'литра', 'литров']:
                ml = value
            # Убираем количество из названия (включая пробелы до и после)
            # Используем более точное регулярное выражение, чтобы не оставлять части слов
            # Включаем ошибочные варианты: "рамм", "рамма", "раммов"
            # Сначала пробуем с пробелом
            part = re.sub(r'\s*\d+\s+(г|грамм|грамма|граммов|рамм|рамма|раммов|мл|миллилитр|миллилитра|миллилитров|литр|литра|литров)\b\.?\s*', ' ', part, flags=re.IGNORECASE)
            # Если не сработало, пробуем без пробела
            if qty_text and qty_text in part:
                part = re.sub(r'\d+(г|грамм|грамма|граммов|рамм|рамма|раммов|мл|миллилитр|миллилитра|миллилитров|литр|литра|литров)\b\.?', '', part, flags=re.IGNORECASE)
            # Убираем оставшиеся части слов типа "рамм" или "рамм." (если остались после удаления количества)
            # Но сначала исправляем "рамм" на "грамм" если это отдельное слово
            part = re.sub(r'\bрамм\b', 'грамм', part, flags=re.IGNORECASE)
            part = re.sub(r'\bрамма\b', 'грамма', part, flags=re.IGNORECASE)
            part = re.sub(r'\bраммов\b', 'граммов', part, flags=re.IGNORECASE)
            # Теперь убираем оставшиеся части, если они остались
            part = re.sub(r'\b(рамм|рамма|раммов|рамм\.)\b\.?', '', part, flags=re.IGNORECASE)
            part = part.strip()
        
        # Ищем другие указания количества (например, "2 яблока")
        qty_match = re.search(r'(\d+)\s+', part)
        if qty_match and not qty_text:
            qty_text = qty_match.group(0).strip()
        
        # Нормализуем название (первая буква заглавная)
        name = part.strip()
        
        # Если часть содержит только количество (после удаления количества name пустой),
        # то связываем это количество с предыдущим продуктом
        if not name and (grams is not None or ml is not None or qty_text):
            # Если есть предыдущий продукт, добавляем к нему количество
            if items:
                last_item = items[-1]
                if last_item.get('grams') is None and last_item.get('ml') is None:
                    # Обновляем предыдущий продукт с количеством
                    last_item['grams'] = grams
                    last_item['ml'] = ml
                    last_item['qty_text'] = qty_text
                    logging.info(f"Связано количество '{qty_text}' с предыдущим продуктом '{last_item.get('name')}'")
            continue
        
        if name:
            name = name[0].upper() + name[1:].lower() if len(name) > 1 else name.upper()
        
        if name:
            items.append({
                "name": name,
                "qty_text": qty_text,
                "grams": grams,
                "ml": ml
            })
    
    return items


async def parse_food_message_with_gigachat(
    text: str, 
    now_dt: datetime, 
    user_tz: str,
    gigachat_token: str
) -> ParsedFoodLog:
    """
    Парсит сообщение о еде через GigaChat и возвращает структурированные данные
    
    Args:
        text: Текст сообщения
        now_dt: Текущая дата/время (datetime объект)
        user_tz: Временная зона пользователя
        gigachat_token: Токен доступа к GigaChat API
        
    Returns:
        ParsedFoodLog с извлечёнными данными
    """
    current_date = now_dt.date().strftime('%Y-%m-%d')
    
    system_prompt = f"""Ты помощник, который разбирает естественный текст пользователя о еде и питании и возвращает СТРОГО JSON без пояснений.

Текущая дата: {current_date}
Временная зона: {user_tz}

Поля JSON:
- date: дата события в формате YYYY-MM-DD (строка)
- meal_type: тип приёма пищи - "breakfast"|"lunch"|"dinner"|"snack"|"unknown" (строка)
- items: массив продуктов (массив объектов)

Каждый элемент items должен содержать:
- name: название продукта (строка, БЕЗ количества)
- quantity: количество (число или null) - числовое значение
- unit: единица измерения (строка или null) - "грамм", "г", "мл", "литр", "л" и т.д.
- grams: количество в граммах (число или null) - для совместимости, вычисляется из quantity и unit
- ml: количество в миллилитрах (число или null) - для совместимости, вычисляется из quantity и unit
- qty_text: текстовое описание количества (строка или null, например "100 грамм", "200 мл")

Правила для date:
- "сегодня" = {current_date}
- "завтра" = +1 день от {current_date}
- "вчера" = -1 день от {current_date}
- "послезавтра" = +2 дня от {current_date}

Правила для meal_type:
- "завтрак", "утром", "утренний" = "breakfast"
- "обед", "днём", "дневной" = "lunch"
- "ужин", "вечером", "вечерний" = "dinner"
- "перекус", "полдник", "ланч" = "snack"
- если не указано = "unknown"

Правила для items (КРИТИЧЕСКИ ВАЖНО):
1. Разделяй продукты по запятым, точкам с запятой, "и", "с"
2. Извлекай количество и единицы измерения из каждого продукта:
   - "творог 200 грамм" → {{"name": "Творог", "quantity": 200, "unit": "грамм", "grams": 200, "ml": null, "qty_text": "200 грамм"}}
   - "овсянка 100г" → {{"name": "Овсянка", "quantity": 100, "unit": "г", "grams": 100, "ml": null, "qty_text": "100г"}}
   - "молоко 250 мл" → {{"name": "Молоко", "quantity": 250, "unit": "мл", "grams": null, "ml": 250, "qty_text": "250 мл"}}
   - "пшеничная каша, 100 грамм" → {{"name": "Пшеничная каша", "quantity": 100, "unit": "грамм", "grams": 100, "ml": null, "qty_text": "100 грамм"}}
3. Если количество указано отдельно после запятой (например, "Пшеничная каша, 100 грамм"), 
   связывай его с предыдущим продуктом
4. Если продукт указан без количества: quantity=null, unit=null, grams=null, ml=null, qty_text=null
5. Исправляй ошибки распознавания: "рамм" → "грамм", "рамма" → "грамма"
6. Всегда заполняй quantity и unit, если есть количество. Затем вычисляй grams или ml:
   - Если unit в ["г", "грамм", "грамма", "граммов"] → grams = quantity, ml = null
   - Если unit в ["мл", "миллилитр", "литр", "л"] → ml = quantity, grams = null

Примеры:

Вход: "меню творог 200 грамм"
Выход: {{"date": "{current_date}", "meal_type": "unknown", "items": [{{"name": "Творог", "quantity": 200, "unit": "грамм", "grams": 200, "ml": null, "qty_text": "200 грамм"}}]}}

Вход: "Пшеничная каша, 100 грамм"
Выход: {{"date": "{current_date}", "meal_type": "unknown", "items": [{{"name": "Пшеничная каша", "quantity": 100, "unit": "грамм", "grams": 100, "ml": null, "qty_text": "100 грамм"}}]}}

Вход: "завтрак омлет и кофе"
Выход: {{"date": "{current_date}", "meal_type": "breakfast", "items": [{{"name": "Омлет", "quantity": null, "unit": null, "grams": null, "ml": null, "qty_text": null}}, {{"name": "Кофе", "quantity": null, "unit": null, "grams": null, "ml": null, "qty_text": null}}]}}

Вход: "обед борщ 300 грамм и хлеб"
Выход: {{"date": "{current_date}", "meal_type": "lunch", "items": [{{"name": "Борщ", "quantity": 300, "unit": "грамм", "grams": 300, "ml": null, "qty_text": "300 грамм"}}, {{"name": "Хлеб", "quantity": null, "unit": null, "grams": null, "ml": null, "qty_text": null}}]}}

Возвращай ТОЛЬКО JSON, без markdown, без пояснений."""
    
    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(
                'https://gigachat.devices.sberbank.ru/api/v1/chat/completions',
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {gigachat_token}'
                },
                json={
                    'model': 'GigaChat',
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    'temperature': 0.1,
                    'max_tokens': 1000
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"GigaChat API error: {response.status_code} - {response.text}")
            
            content = response.json()['choices'][0]['message']['content'].strip()
            logging.info(f"GigaChat food parsing response (raw): {content}")
            
            # Логируем структуру JSON для проверки
            try:
                content_for_log = content
                if content_for_log.startswith('```'):
                    content_for_log = content_for_log.split('```')[1]
                    if content_for_log.startswith('json'):
                        content_for_log = content_for_log[4:]
                content_for_log = content_for_log.strip()
                parsed_for_log = json.loads(content_for_log)
                items_count = len(parsed_for_log.get('items', []))
                logging.info(f"GigaChat вернул JSON: date={parsed_for_log.get('date')}, meal_type={parsed_for_log.get('meal_type')}, items_count={items_count}")
                if items_count > 0:
                    first_item = parsed_for_log['items'][0]
                    logging.info(f"Первый продукт из GigaChat: {json.dumps(first_item, ensure_ascii=False)}")
            except:
                pass
            
            # Парсим JSON
            try:
                if content.startswith('```'):
                    content = content.split('```')[1]
                    if content.startswith('json'):
                        content = content[4:]
                content = content.strip()
                
                data = json.loads(content)
                
            except json.JSONDecodeError:
                # Пытаемся найти JSON через регулярку
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                else:
                    raise ValueError("GigaChat не вернул корректный JSON для парсинга продуктов")
            
            # Валидация и преобразование
            event_date = data.get('date', current_date)
            meal_type = data.get('meal_type', 'unknown')
            items = data.get('items', [])
            
            # Валидация items
            if not isinstance(items, list):
                items = []
            
            # Нормализуем items
            normalized_items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                # Извлекаем поля из ответа GigaChat
                name = item.get('name', '').strip()
                quantity = item.get('quantity')
                unit = item.get('unit')
                grams = item.get('grams')
                ml = item.get('ml')
                qty_text = item.get('qty_text')
                
                # Если есть quantity и unit, но нет grams/ml, вычисляем их
                if quantity is not None and unit:
                    unit_lower = unit.lower()
                    if unit_lower in ['г', 'грамм', 'грамма', 'граммов']:
                        grams = quantity
                        ml = None
                        if not qty_text:
                            qty_text = f"{quantity} {unit}"
                    elif unit_lower in ['мл', 'миллилитр', 'миллилитра', 'миллилитров', 'л', 'литр', 'литра', 'литров']:
                        ml = quantity
                        grams = None
                        if not qty_text:
                            qty_text = f"{quantity} {unit}"
                
                normalized_item = {
                    "name": name,
                    "quantity": quantity,
                    "unit": unit,
                    "qty_text": qty_text,
                    "grams": grams,
                    "ml": ml
                }
                
                # Нормализуем название (первая буква заглавная)
                if normalized_item['name']:
                    name = normalized_item['name']
                    normalized_item['name'] = name[0].upper() + name[1:].lower() if len(name) > 1 else name.upper()
                
                if normalized_item['name']:
                    normalized_items.append(normalized_item)
                    logging.info(f"Нормализован продукт: name='{normalized_item['name']}', quantity={quantity}, unit='{unit}', grams={grams}, ml={ml}")
            
            confidence = "high" if normalized_items else "low"
            
            return ParsedFoodLog(
                event_date=event_date,
                meal_type=meal_type,
                items=normalized_items,
                confidence=confidence,
                notes=text,
                raw_text=text
            )
            
    except Exception as e:
        logging.error(f"Ошибка парсинга продуктов через GigaChat: {e}", exc_info=True)
        raise ValueError(f"Не удалось распарсить продукты через GigaChat: {e}")

