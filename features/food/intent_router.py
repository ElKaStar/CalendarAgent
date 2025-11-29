"""
Модуль для определения интента сообщения (еда vs календарь)

Определяет, куда направить сообщение: в FoodPipeline или CalendarPipeline
"""
import re
import logging
from typing import Literal
from features.food.config import FOOD_CODE_WORDS, SPEECH_CORRECTIONS_CODE_WORDS


def detect_intent(text: str) -> Literal['calendar', 'food', 'unknown']:
    """
    Определяет интент сообщения: календарь, еда или неизвестно
    
    Приоритет:
    1) Явные календарные интенты (дата+время+встреча/запись/маникюр/врач/созвонимся) → CalendarPipeline
    2) Иначе если еда → FoodPipeline
    3) Иначе → CalendarPipeline (как сейчас)
    
    Args:
        text: Текст сообщения
        
    Returns:
        'calendar' - отправить в календарный pipeline
        'food' - отправить в food pipeline
        'unknown' - неопределённый интент (по умолчанию календарь)
    """
    if not text or not text.strip():
        logging.warning(f"detect_intent: пустой текст")
        return 'unknown'
    
    text_lower = text.lower().strip()
    logging.info(f"detect_intent: исходный текст='{text[:100]}...', text_lower='{text_lower[:100]}...'")
    
    # Убираем многоточия в конце (могут мешать распознаванию)
    text_lower = re.sub(r'\.{2,}$', '', text_lower)
    text_lower = text_lower.strip()
    
    # Исправляем частые ошибки распознавания речи для кодовых слов
    for wrong, correct in SPEECH_CORRECTIONS_CODE_WORDS.items():
        # Проверяем начало текста (с учетом возможной точки после слова)
        # Также проверяем без разделителя (на случай "минукартофель")
        if (text_lower.startswith(wrong) or 
            re.match(rf'^{re.escape(wrong)}[.\s]+', text_lower, re.IGNORECASE) or
            text_lower.startswith(wrong + ' ')):
            text_lower = re.sub(rf'^{re.escape(wrong)}([.\s]+)', rf'{correct}\1', text_lower, count=1, flags=re.IGNORECASE)
            # Если не сработало с разделителем, пробуем без него
            if text_lower.startswith(wrong):
                text_lower = re.sub(rf'^{re.escape(wrong)}', correct, text_lower, count=1, flags=re.IGNORECASE)
            logging.info(f"Исправлена ошибка распознавания: '{wrong}' → '{correct}', text_lower теперь: '{text_lower[:50]}...'")
            break  # Исправляем только первое совпадение
    
    # -1. Кодовые слова - наивысший приоритет для дневника питания
    # Если сообщение начинается с любого кодового слова (с точкой или без), это всегда запись о еде
    for code_word in FOOD_CODE_WORDS:
        code_word_lower = code_word.lower()
        # Проверяем начало текста: "menu", "menu ", "menu.", "menu. " и т.д.
        if (text_lower.startswith(code_word_lower) or 
            re.match(rf'^{re.escape(code_word_lower)}[.\s]+', text_lower, re.IGNORECASE)):
            logging.info(f"Определён food интент (кодовое слово '{code_word}') для текста: '{text[:100]}...'")
            return 'food'
    
    # 0. Сначала проверяем явные маркеры еды (высший приоритет)
    # Если есть "съел/съела" + продукты, это точно еда, даже если есть календарные слова
    explicit_food_markers = [
        r'\b(съел|съела|съели|съесть|поел|поела|поели|поесть)\b',
    ]
    food_products = [
        r'\b(омлет|кофе|чай|салат|борщ|хлеб|рыба|овощи|паста|йогурт|яблоко|овсянка|каша|суп|мясо|курица|говядина|свинина|творог|кефир|сыр|молоко|гречка|рис|манка|пшено|перловка|яйца|блины|вареники|пельмени|котлеты|шашлык|шаурма|цезарь|оливье|винегрет|щи|солянка|рассольник|уха|капучино|латте|эспрессо|американо|раф|гляссе|мокко|фраппе)\b',
    ]
    
    has_food_verb = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in explicit_food_markers)
    has_food_product = any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in food_products)
    
    if has_food_verb and has_food_product:
        logging.info(f"Определён food интент (явные маркеры еды) для текста: '{text[:100]}...'")
        return 'food'
    
    # 1. Проверяем явные календарные интенты (высокий приоритет)
    # Но только если нет маркеров еды
    calendar_keywords = [
        r'\b(запиши|запиши меня|запланируй|поставь|создай|добавь|напомни)\b',
        r'\b(встреча|созвон|звонок|конференция|совещание|планёрка)\b',
        r'\b(маникюр|педикюр|стрижка|врач|доктор|терапевт|стоматолог)\b',
        r'\b(в \d{1,2}:\d{2}|в \d{1,2} час|на \d{1,2}:\d{2}|на \d{1,2} час)\b',
        r'\b(через неделю|через \d+ (день|дня|дней))\b',
    ]
    
    # Календарные слова (даты) - но только если нет маркеров еды
    calendar_dates = [
        r'\b(завтра|послезавтра|в понедельник|в вторник|в среду|в четверг|в пятницу|в субботу|в воскресенье)\b',
    ]
    
    calendar_pattern = '|'.join(calendar_keywords)
    calendar_dates_pattern = '|'.join(calendar_dates)
    
    # Если есть явные календарные команды (не просто даты) - это календарь
    if re.search(calendar_pattern, text_lower, re.IGNORECASE):
        logging.info(f"Определён календарный интент для текста: '{text[:100]}...'")
        return 'calendar'
    
    # 2. Проверяем интенты еды
    food_keywords = [
        r'\b(еда|съел|съела|съела|съели|съесть|поел|поела|поели|поесть)\b',
        r'\b(завтрак|обед|ужин|перекус|полдник|ланч|бранч)\b',
        r'\b(меню|калории|калорий|питание|диета|блюдо|блюда)\b',
        # Названия продуктов (основные)
        r'\b(омлет|кофе|чай|салат|борщ|хлеб|рыба|овощи|паста|йогурт|яблоко|овсянка|каша|суп|мясо|курица|говядина|свинина|рыба|овощи|фрукты|ягоды|молочка|молоко|сыр|творог|кефир|сметана|масло|хлеб|булка|печенье|конфеты|шоколад|мороженое|пицца|бургер|суши|роллы|паста|спагетти|макароны|рис|гречка|овсянка|манка|пшено|перловка|яйца|омлет|яичница|блины|оладьи|вареники|пельмени|котлеты|шашлык|шаурма|салат|цезарь|оливье|винегрет|борщ|щи|солянка|рассольник|уха|суп|борщ|хлеб|батон|булка|круассан|булочка|пирог|торт|пирожное|кекс|печенье|вафли|блины|оладьи|вареники|пельмени|котлеты|шашлык|шаурма|салат|цезарь|оливье|винегрет|борщ|щи|солянка|рассольник|уха|суп)\b',
        r'\b(капучино|латте|эспрессо|американо|раф|гляссе|мокко|фраппе)\b',
    ]
    
    food_pattern = '|'.join(food_keywords)
    if re.search(food_pattern, text_lower, re.IGNORECASE):
        logging.info(f"Определён food интент для текста: '{text[:100]}...'")
        return 'food'
    
    # 3. По умолчанию - календарь (как сейчас)
    logging.info(f"Неопределённый интент, по умолчанию календарь для текста: '{text[:100]}...'")
    return 'unknown'

