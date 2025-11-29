"""
Обработчики команд и сообщений для дневника питания
"""
import json
import csv
import io
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Optional
import pytz
from aiogram.types import Message, FSInputFile

from features.food.food_nlu import parse_food_message, parse_food_message_with_gigachat, ParsedFoodLog
from features.food.food_db import (
    save_food_log,
    get_food_logs_by_date,
    get_food_logs_last,
    delete_food_log,
    get_food_summary,
    get_last_food_log,
    FoodLog
)
from features.food.config import FOOD_CODE_WORDS


MEAL_TYPE_NAMES = {
    'breakfast': 'Завтрак',
    'lunch': 'Обед',
    'dinner': 'Ужин',
    'snack': 'Перекус',
    'unknown': 'Не указано'
}

MEAL_TYPE_NAMES_RU = {
    'breakfast': 'завтрак',
    'lunch': 'обед',
    'dinner': 'ужин',
    'snack': 'перекус',
    'unknown': 'не указано'
}


async def handle_food_message(
    text: str,
    chat_id: int,
    message: Message,
    database_file: str,
    timezone: str,
    config=None
) -> None:
    """
    Обрабатывает сообщение о еде: парсит и сохраняет в БД
    
    Args:
        text: Текст сообщения
        chat_id: ID чата Telegram
        message: Объект сообщения для ответа
        database_file: Путь к файлу БД
        timezone: Временная зона пользователя
        config: Конфигурация (опционально, для использования GigaChat)
    """
    try:
        # Валидация входного текста
        if not text or not text.strip():
            logging.warning(f"Пустой текст в handle_food_message для user_id={chat_id}")
            await message.answer(
                "❌ Получен пустой текст.\n"
                "Попробуйте указать продукты более явно, например:\n"
                "'меню творог 200 грамм' или 'меню овсянка и яблоко'"
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
                    logging.warning(f"Текст содержит повторяющиеся слова (возможно мусор от STT): user_id={chat_id}, text='{text[:100]}...'")
                    await message.answer(
                        "❌ Не удалось распознать продукты в сообщении.\n"
                        "Распознан только шум или повторяющиеся слова.\n"
                        "Попробуйте указать продукты более явно, например:\n"
                        "'меню творог 200 грамм' или 'меню овсянка и яблоко'"
                    )
                    return
        
        # Парсим сообщение
        now_dt = datetime.now(pytz.timezone(timezone))
        
        # Пробуем использовать GigaChat для парсинга, если доступен
        parsed = None
        parse_mode = 'rules'
        if config:
            try:
                from bot import get_gigachat_access_token
                token = await get_gigachat_access_token(config)
                parsed = await parse_food_message_with_gigachat(text, now_dt, timezone, token)
                parse_mode = 'llm'
                logging.info(f"Продукты распарсены через GigaChat: {len(parsed.items)} продуктов")
            except Exception as e:
                logging.warning(f"Ошибка парсинга через GigaChat, используем rules: {e}")
        
        # Если GigaChat не использовался или произошла ошибка, используем rules
        if parsed is None:
            parsed = parse_food_message(text, now_dt, timezone)
        
        # Проверяем, что есть продукты для сохранения
        if not parsed.items:
            logging.warning(f"Не удалось извлечь продукты из текста: '{text[:100]}...'")
            await message.answer(
                f"❌ Не удалось распознать продукты в сообщении.\n"
                f"Попробуйте указать продукты более явно, например:\n"
                f"'меню творог 200 грамм' или 'меню овсянка и яблоко'"
            )
            return
        
        # Валидация даты для дневника питания: нельзя создавать записи в будущем
        from features.food.date_validation import validate_food_date
        
        # Если event_date отсутствует или битая, присваиваем today
        if not parsed.event_date:
            today = now_dt.date()
            parsed.event_date = today.strftime('%Y-%m-%d')
            logging.info(f"event_date отсутствует, присваиваем today: {parsed.event_date}")
        
        # Валидируем дату
        is_valid, error_msg = validate_food_date(parsed.event_date, now_dt, timezone)
        if not is_valid:
            logging.warning(f"Валидация даты не прошла: user_id={chat_id}, raw_text='{text[:100]}...', event_date={parsed.event_date}, today={now_dt.date()}")
            await message.answer(error_msg)
            return
        
        # Сохраняем в БД
        log_id = save_food_log(
            database_file=database_file,
            user_id=str(chat_id),
            event_date=parsed.event_date,
            meal_type=parsed.meal_type,
            items=parsed.items,
            raw_text=parsed.raw_text,
            parse_mode=parse_mode,
            tz=timezone
        )
        logging.info(f"Сохранена запись о еде: ID={log_id}, user_id={chat_id}, date={parsed.event_date}, items={len(parsed.items)}")
        
        # Формируем ответ
        meal_name = MEAL_TYPE_NAMES.get(parsed.meal_type, parsed.meal_type)
        
        # Формируем список продуктов с количеством
        items_list = []
        for item in parsed.items:
            item_name = item.get('name', '')
            qty_info = ""
            
            # Добавляем информацию о количестве
            if item.get('grams'):
                qty_info = f" ({item['grams']}г)"
            elif item.get('ml'):
                qty_info = f" ({item['ml']}мл)"
            elif item.get('qty_text'):
                # Исправляем "рамм" на "грамм" в qty_text
                qty_text = item['qty_text']
                qty_text = qty_text.replace('рамм', 'грамм').replace('рамма', 'грамма').replace('раммов', 'граммов')
                qty_text = qty_text.replace('рамм.', 'грамм').replace('рамма.', 'грамма')
                qty_info = f" ({qty_text})"
            
            items_list.append(f"{item_name}{qty_info}")
        
        items_text = ', '.join(items_list) if items_list else 'не указано'
        
        response = (
            f"✅ Записала в дневник питания:\n\n"
            f"📅 Дата: {parsed.event_date}\n"
            f"🍽 Приём пищи: {meal_name}\n"
            f"📝 Продукты: {items_text}\n"
        )
        
        if parsed.confidence == 'low':
            response += f"\n⚠️ Низкая уверенность в распознавании. Проверьте запись."
        
        await message.answer(response)
        
    except ValueError as e:
        logging.warning(f"Ошибка парсинга сообщения о еде: {e}, текст: '{text[:100]}...'")
        await message.answer(f"❌ {str(e)}")
    except Exception as e:
        logging.error(f"Ошибка обработки сообщения о еде: {e}, текст: '{text[:100]}...'", exc_info=True)
        await message.answer("❌ Не удалось обработать запрос о еде. Попробуйте ещё раз.")


async def handle_food_help(message: Message) -> None:
    """Обработчик команды /food_help"""
    help_text = (
        "🍽 Дневник питания\n\n"
        f"📝 Кодовые слова: {', '.join([f'\"{cw}\"' for cw in FOOD_CODE_WORDS])}\n"
        f"Начните сообщение с любого из этих слов, чтобы гарантированно записать в дневник питания:\n"
        f"• «{FOOD_CODE_WORDS[0]} овсянка 200 грамм» или «{FOOD_CODE_WORDS[1] if len(FOOD_CODE_WORDS) > 1 else FOOD_CODE_WORDS[0]} овсянка 200 грамм»\n"
        f"• «{FOOD_CODE_WORDS[0]} творог 40г» или «{FOOD_CODE_WORDS[1] if len(FOOD_CODE_WORDS) > 1 else FOOD_CODE_WORDS[0]} творог 40г»\n"
        f"• «{FOOD_CODE_WORDS[0]} завтрак: омлет и кофе»\n\n"
        "Записи о еде (без кодового слова):\n"
        "• «Еда: завтрак омлет и кофе»\n"
        "• «Меню за день: утром овсянка; днем борщ и хлеб; вечером рыба и овощи»\n"
        "• «Съела салат цезарь и капучино»\n"
        "• «Перекус: яблоко, йогурт»\n"
        "• «Вчера: паста и салат»\n\n"
        "Команды:\n"
        "/food_today - что записано за сегодня\n"
        "/food_day YYYY-MM-DD - лог за дату\n"
        "/food_last N - последние N записей\n"
        "/food_sum YYYY-MM-DD - сводка за день\n"
        "/food_delete ID - удалить запись\n"
        "/food_export YYYY-MM-DD - экспорт CSV"
    )
    await message.answer(help_text)


async def handle_food_today(message: Message, database_file: str, timezone: str) -> None:
    """Обработчик команды /food_today"""
    try:
        now = datetime.now(pytz.timezone(timezone))
        today = now.date().strftime('%Y-%m-%d')
        
        logs = get_food_logs_by_date(database_file, str(message.chat.id), today)
        
        if not logs:
            await message.answer("📅 За сегодня записей о еде нет")
            return
        
        response = f"🍽 Дневник питания за сегодня ({today}):\n\n"
        
        for log in logs:
            meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
            try:
                items = json.loads(log.items_json)
                items_text = ', '.join([item.get('name', '') for item in items])
            except (json.JSONDecodeError, AttributeError):
                items_text = "не удалось распарсить"
            
            response += f"• {meal_name}: {items_text}\n"
            response += f"  📝 {log.raw_text[:50]}...\n\n"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка получения записей за сегодня: {e}", exc_info=True)
        await message.answer("❌ Не удалось получить записи за сегодня")


async def handle_food_day(message: Message, database_file: str, timezone: str) -> None:
    """Обработчик команды /food_day YYYY-MM-DD"""
    try:
        # Извлекаем дату из команды
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("❌ Укажите дату: /food_day YYYY-MM-DD")
            return
        
        date_str = parts[1]
        try:
            # Проверяем формат даты
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            await message.answer("❌ Неверный формат даты. Используйте: YYYY-MM-DD")
            return
        
        logs = get_food_logs_by_date(database_file, str(message.chat.id), date_str)
        
        if not logs:
            await message.answer(f"📅 За {date_str} записей о еде нет")
            return
        
        response = f"🍽 Дневник питания за {date_str}:\n\n"
        
        for log in logs:
            meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
            try:
                items = json.loads(log.items_json)
                items_text = ', '.join([item.get('name', '') for item in items])
            except (json.JSONDecodeError, AttributeError):
                items_text = "не удалось распарсить"
            
            response += f"• {meal_name}: {items_text}\n"
            response += f"  📝 {log.raw_text[:50]}...\n\n"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка получения записей за дату: {e}", exc_info=True)
        await message.answer("❌ Не удалось получить записи за указанную дату")


async def handle_food_last(message: Message, database_file: str, timezone: str) -> None:
    """Обработчик команды /food_last N"""
    try:
        # Извлекаем количество из команды
        parts = message.text.split()
        limit = 10  # По умолчанию
        if len(parts) >= 2:
            try:
                limit = int(parts[1])
                if limit < 1 or limit > 50:
                    limit = 10
            except ValueError:
                pass
        
        logs = get_food_logs_last(database_file, str(message.chat.id), limit)
        
        if not logs:
            await message.answer("📅 Записей о еде нет")
            return
        
        response = f"🍽 Последние {len(logs)} записей:\n\n"
        
        for log in logs:
            meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
            try:
                items = json.loads(log.items_json)
                items_text = ', '.join([item.get('name', '') for item in items])
            except (json.JSONDecodeError, AttributeError):
                items_text = "не удалось распарсить"
            
            response += f"• {log.event_date} - {meal_name}: {items_text}\n"
            response += f"  📝 {log.raw_text[:50]}...\n\n"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка получения последних записей: {e}", exc_info=True)
        await message.answer("❌ Не удалось получить последние записи")


async def handle_food_sum(message: Message, database_file: str, timezone: str) -> None:
    """Обработчик команды /food_sum YYYY-MM-DD"""
    try:
        # Извлекаем дату из команды
        parts = message.text.split()
        if len(parts) < 2:
            # По умолчанию - сегодня
            now = datetime.now(pytz.timezone(timezone))
            date_str = now.date().strftime('%Y-%m-%d')
        else:
            date_str = parts[1]
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                await message.answer("❌ Неверный формат даты. Используйте: YYYY-MM-DD")
                return
        
        summary = get_food_summary(database_file, str(message.chat.id), date_str)
        
        response = f"📊 Сводка по питанию за {date_str}:\n\n"
        response += f"📝 Всего записей: {summary['total_logs']}\n\n"
        response += "🍽 Приёмы пищи:\n"
        
        for meal_type, count in summary['meals'].items():
            if count > 0:
                meal_name = MEAL_TYPE_NAMES.get(meal_type, meal_type)
                response += f"• {meal_name}: {count}\n"
        
        if summary['all_items']:
            response += f"\n📦 Продукты ({len(summary['all_items'])}):\n"
            response += ', '.join(summary['all_items'][:20])  # Первые 20
            if len(summary['all_items']) > 20:
                response += f" ... и ещё {len(summary['all_items']) - 20}"
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка получения сводки: {e}", exc_info=True)
        await message.answer("❌ Не удалось получить сводку")


async def handle_food_delete(message: Message, database_file: str, timezone: str) -> None:
    """Обработчик команды /food_delete ID"""
    try:
        # Извлекаем ID из команды
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("❌ Укажите ID записи: /food_delete ID")
            return
        
        try:
            log_id = int(parts[1])
        except ValueError:
            await message.answer("❌ ID должен быть числом")
            return
        
        deleted = delete_food_log(database_file, str(message.chat.id), log_id)
        
        if deleted:
            await message.answer(f"✅ Запись #{log_id} удалена")
        else:
            await message.answer(f"❌ Запись #{log_id} не найдена или не принадлежит вам")
        
    except Exception as e:
        logging.error(f"Ошибка удаления записи: {e}", exc_info=True)
        await message.answer("❌ Не удалось удалить запись")


async def handle_food_delete_last(message: Message, database_file: str, timezone: str) -> None:
    """Обработчик команды /dellast - удалить последнюю запись"""
    user_id = str(message.from_user.id)
    logging.info(f"Команда /dellast от user_id={user_id}")
    
    try:
        # Получаем последнюю запись
        last_log = get_last_food_log(database_file, user_id)
        
        if last_log is None:
            await message.answer("ℹ️ У вас нет записей для удаления.")
            return
        
        # Форматируем время из created_at
        try:
            tz = pytz.timezone(timezone)
            created_dt = datetime.fromisoformat(last_log.created_at.replace('Z', '+00:00'))
            if created_dt.tzinfo is None:
                created_dt = pytz.UTC.localize(created_dt)
            created_dt = created_dt.astimezone(tz)
            time_str = created_dt.strftime('%H:%M')
        except (ValueError, AttributeError):
            time_str = "??:??"
        
        # Получаем название типа приёма пищи
        meal_name = MEAL_TYPE_NAMES_RU.get(last_log.meal_type, last_log.meal_type)
        
        # Форматируем список продуктов
        items_text = ""
        try:
            items = json.loads(last_log.items_json)
            if items:
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
                
                items_text = ', '.join(items_list) if items_list else last_log.raw_text[:100]
            else:
                items_text = last_log.raw_text[:100] if last_log.raw_text else "не указано"
        except (json.JSONDecodeError, AttributeError, TypeError):
            items_text = last_log.raw_text[:100] if last_log.raw_text else "не указано"
        
        # Удаляем запись
        deleted = delete_food_log(database_file, user_id, last_log.id)
        
        if not deleted:
            logging.error(f"Не удалось удалить запись ID={last_log.id} для user_id={user_id}")
            await message.answer("❌ Не удалось удалить запись. Попробуйте ещё раз.")
            return
        
        # Логируем удаление
        logging.info(f"Удалена последняя запись: user_id={user_id}, deleted_id={last_log.id}, event_date={last_log.event_date}, created_at={last_log.created_at}")
        
        # Формируем подтверждение
        response = (
            f"🗑️ Удалила последнюю запись из дневника питания:\n\n"
            f"📅 Дата: {last_log.event_date}\n"
            f"🕒 Время: {time_str}\n"
            f"🍽 Приём пищи: {meal_name}\n"
            f"📝 Запись: {items_text}"
        )
        
        await message.answer(response)
        
    except Exception as e:
        logging.error(f"Ошибка обработки /dellast для user_id={user_id}: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при удалении записи")


async def handle_food_export(message: Message, database_file: str, timezone: str) -> None:
    """Обработчик команды /food_export YYYY-MM-DD"""
    try:
        # Извлекаем дату из команды
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("❌ Укажите дату: /food_export YYYY-MM-DD")
            return
        
        date_str = parts[1]
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            await message.answer("❌ Неверный формат даты. Используйте: YYYY-MM-DD")
            return
        
        logs = get_food_logs_by_date(database_file, str(message.chat.id), date_str)
        
        if not logs:
            await message.answer(f"📅 За {date_str} записей о еде нет")
            return
        
        # Создаём CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Заголовки
        writer.writerow(['ID', 'Дата', 'Приём пищи', 'Продукты', 'Исходный текст', 'Создано'])
        
        # Данные
        for log in logs:
            try:
                items = json.loads(log.items_json)
                items_text = ', '.join([item.get('name', '') for item in items])
            except (json.JSONDecodeError, AttributeError):
                items_text = ""
            
            meal_name = MEAL_TYPE_NAMES.get(log.meal_type, log.meal_type)
            writer.writerow([
                log.id,
                log.event_date,
                meal_name,
                items_text,
                log.raw_text,
                log.created_at
            ])
        
        # Сохраняем во временный файл
        import os
        import tempfile
        
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        csv_file = os.path.join(temp_dir, f'food_export_{date_str}_{message.chat.id}.csv')
        with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(output.getvalue())
        
        # Отправляем файл
        document = FSInputFile(csv_file, filename=f'food_log_{date_str}.csv')
        await message.answer_document(document)
        
        # Удаляем временный файл
        try:
            os.remove(csv_file)
        except:
            pass
        
    except Exception as e:
        logging.error(f"Ошибка экспорта: {e}", exc_info=True)
        await message.answer("❌ Не удалось экспортировать данные")

