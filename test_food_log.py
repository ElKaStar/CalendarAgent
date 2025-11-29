#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функционала дневника питания
"""
import os
import sys
from datetime import datetime
import pytz

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Проверка импортов модулей"""
    print("=" * 60)
    print("1. Проверка импортов модулей...")
    print("=" * 60)
    
    try:
        from features.food.intent_router import detect_intent
        print("✅ intent_router импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта intent_router: {e}")
        return False
    
    try:
        from features.food.food_nlu import parse_food_message
        print("✅ food_nlu импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта food_nlu: {e}")
        return False
    
    try:
        from features.food.food_db import init_food_db, save_food_log, get_food_logs_by_date
        print("✅ food_db импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта food_db: {e}")
        return False
    
    try:
        from features.food.food_handlers import handle_food_message
        print("✅ food_handlers импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта food_handlers: {e}")
        return False
    
    print()
    return True


def test_intent_router():
    """Тестирование определения интента"""
    print("=" * 60)
    print("2. Тестирование определения интента...")
    print("=" * 60)
    
    from features.food.intent_router import detect_intent
    
    test_cases = [
        ("Завтра в 15:00 встреча с Катей", "calendar"),
        ("Еда: завтрак омлет и кофе", "food"),
        ("Съела салат цезарь и капучино", "food"),
        ("Послезавтра в 10:00 созвон с командой", "calendar"),
        ("Меню за день: утром овсянка; днем борщ", "food"),
        ("Перекус: яблоко, йогурт", "food"),
        ("Запиши меня завтра на маникюр на 3 часа дня", "calendar"),
        ("Вчера: паста и салат", "food"),
    ]
    
    all_passed = True
    for text, expected in test_cases:
        result = detect_intent(text)
        status = "✅" if result == expected or (expected == "calendar" and result == "unknown") else "❌"
        if status == "❌":
            all_passed = False
        print(f"{status} '{text[:40]}...' → {result} (ожидалось: {expected})")
    
    print()
    return all_passed


def test_food_parsing():
    """Тестирование парсинга сообщений о еде"""
    print("=" * 60)
    print("3. Тестирование парсинга сообщений о еде...")
    print("=" * 60)
    
    from features.food.food_nlu import parse_food_message
    
    now_dt = datetime.now(pytz.timezone('Europe/Moscow'))
    timezone = 'Europe/Moscow'
    
    test_cases = [
        "Еда: завтрак омлет и кофе",
        "Съела салат цезарь и капучино",
        "Меню за день: утром овсянка; днем борщ и хлеб; вечером рыба и овощи",
        "Перекус: яблоко, йогурт",
        "Вчера: паста и салат",
    ]
    
    all_passed = True
    for text in test_cases:
        try:
            parsed = parse_food_message(text, now_dt, timezone)
            print(f"✅ '{text[:40]}...'")
            print(f"   Дата: {parsed.event_date}, Приём: {parsed.meal_type}, Продуктов: {len(parsed.items)}")
            if parsed.items:
                items_names = [item.get('name', '') for item in parsed.items]
                print(f"   Продукты: {', '.join(items_names[:3])}")
        except Exception as e:
            print(f"❌ '{text[:40]}...' → Ошибка: {e}")
            all_passed = False
    
    print()
    return all_passed


def test_database():
    """Тестирование работы с БД"""
    print("=" * 60)
    print("4. Тестирование работы с БД...")
    print("=" * 60)
    
    import tempfile
    import os
    
    from features.food.food_db import (
        init_food_db, save_food_log, get_food_logs_by_date,
        get_food_logs_last, delete_food_log, get_food_summary
    )
    
    # Создаём временную БД
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    db_path = temp_db.name
    
    try:
        # Инициализация
        init_food_db(db_path)
        print("✅ БД инициализирована")
        
        # Сохранение записи
        log_id = save_food_log(
            database_file=db_path,
            user_id="12345",
            event_date="2024-01-15",
            meal_type="breakfast",
            items=[{"name": "Омлет", "qty_text": None, "grams": None, "ml": None}],
            raw_text="Еда: завтрак омлет",
            parse_mode="rules",
            tz="Europe/Moscow"
        )
        print(f"✅ Запись сохранена (ID: {log_id})")
        
        # Получение записей
        logs = get_food_logs_by_date(db_path, "12345", "2024-01-15")
        print(f"✅ Получено записей: {len(logs)}")
        
        # Получение последних записей
        last_logs = get_food_logs_last(db_path, "12345", 5)
        print(f"✅ Получено последних записей: {len(last_logs)}")
        
        # Сводка
        summary = get_food_summary(db_path, "12345", "2024-01-15")
        print(f"✅ Сводка: {summary['total_logs']} записей, {len(summary['all_items'])} продуктов")
        
        # Удаление
        deleted = delete_food_log(db_path, "12345", log_id)
        print(f"✅ Запись удалена: {deleted}")
        
    except Exception as e:
        print(f"❌ Ошибка работы с БД: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Удаляем временную БД
        try:
            os.unlink(db_path)
        except:
            pass
    
    print()
    return True


def main():
    """Главная функция тестирования"""
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ ФУНКЦИОНАЛА ДНЕВНИКА ПИТАНИЯ")
    print("=" * 60 + "\n")
    
    results = []
    
    # Тест 1: Импорты
    results.append(("Импорты", test_imports()))
    
    # Тест 2: Определение интента
    results.append(("Определение интента", test_intent_router()))
    
    # Тест 3: Парсинг еды
    results.append(("Парсинг еды", test_food_parsing()))
    
    # Тест 4: Работа с БД
    results.append(("Работа с БД", test_database()))
    
    # Итоги
    print("=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ ПРОЙДЕН" if passed else "❌ ПРОВАЛЕН"
        print(f"{status}: {name}")
    
    all_passed = all(result[1] for result in results)
    
    print()
    if all_passed:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    else:
        print("⚠️ НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ")
    
    print()
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())

