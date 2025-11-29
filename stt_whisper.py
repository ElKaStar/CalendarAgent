"""
Модуль для распознавания речи через локальную модель Whisper.

Использует модель 'base' для распознавания голосовых сообщений.
Модель загружается один раз при первом использовании и кэшируется.
"""
import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# Глобальная переменная для кэширования модели
_whisper_model = None


def get_whisper_model(model_name: str = "base"):
    """
    Загружает модель Whisper один раз и кэширует её.
    
    Args:
        model_name: Название модели ('tiny', 'base', 'small', 'medium', 'large')
                   По умолчанию 'base' - оптимальный баланс скорости и качества
    
    Returns:
        whisper.Model: Загруженная модель Whisper
        
    Raises:
        ImportError: Если библиотека whisper не установлена
        Exception: При ошибках загрузки модели
    """
    global _whisper_model
    
    # Если модель уже загружена и это та же модель, возвращаем её
    if _whisper_model is not None:
        # Проверяем, что это та же модель (упрощённая проверка)
        return _whisper_model
    
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "Библиотека openai-whisper не установлена. "
            "Установите: pip install openai-whisper"
        )
    
    logging.info(f"Загружаем модель Whisper '{model_name}' (первый запуск, это может занять время)...")
    try:
        _whisper_model = whisper.load_model(model_name)
        logging.info(f"Модель Whisper '{model_name}' успешно загружена и кэширована")
        return _whisper_model
    except Exception as e:
        logging.error(f"Ошибка загрузки модели Whisper: {e}")
        raise Exception(f"Не удалось загрузить модель Whisper: {e}")


def check_ffmpeg() -> bool:
    """
    Проверяет, установлен ли ffmpeg в системе.
    
    Returns:
        bool: True если ffmpeg доступен, False иначе
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def convert_audio_to_wav(input_path: str, output_path: Optional[str] = None) -> str:
    """
    Конвертирует аудиофайл в формат WAV с помощью ffmpeg.
    
    Args:
        input_path: Путь к исходному аудиофайлу
        output_path: Путь к выходному файлу (если None, создаётся временный файл)
        
    Returns:
        str: Путь к конвертированному WAV файлу
        
    Raises:
        RuntimeError: Если ffmpeg не установлен или произошла ошибка конвертации
    """
    if not check_ffmpeg():
        raise RuntimeError(
            "ffmpeg не установлен. "
            "Установите ffmpeg: "
            "Windows: https://ffmpeg.org/download.html "
            "Linux: sudo apt-get install ffmpeg "
            "macOS: brew install ffmpeg"
        )
    
    if output_path is None:
        # Создаём временный файл
        output_fd, output_path = tempfile.mkstemp(suffix='.wav')
        os.close(output_fd)
    
    logging.info(f"Конвертируем {input_path} в {output_path} через ffmpeg...")
    
    try:
        # Конвертируем в WAV, моно, 16kHz (оптимально для Whisper)
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,
                "-ar", "16000",  # Sample rate 16kHz
                "-ac", "1",      # Mono
                "-y",            # Overwrite output file
                output_path
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True
        )
        logging.info(f"Конвертация завершена успешно: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        error_msg = f"Ошибка конвертации через ffmpeg: {e.stderr}"
        logging.error(error_msg)
        raise RuntimeError(error_msg)
    except subprocess.TimeoutExpired:
        error_msg = "Конвертация через ffmpeg превысила таймаут (30 секунд)"
        logging.error(error_msg)
        raise RuntimeError(error_msg)
    except Exception as e:
        error_msg = f"Неожиданная ошибка при конвертации: {e}"
        logging.error(error_msg)
        raise RuntimeError(error_msg)


def transcribe_audio(file_path: str, model_name: str = "base", initial_prompt: Optional[str] = None) -> str:
    """
    Принимает путь к аудиофайлу, прогоняет его через модель Whisper
    и возвращает распознанный текст.
    
    Args:
        file_path: Путь к аудиофайлу (поддерживаются различные форматы, но рекомендуется WAV)
        model_name: Название модели ('tiny', 'base', 'small', 'medium', 'large')
                   По умолчанию 'base'
        initial_prompt: Начальный промпт для улучшения распознавания (опционально)
                       Помогает модели лучше распознавать специфические слова
        
    Returns:
        str: Распознанный текст (пустая строка, если распознавание не удалось)
        
    Raises:
        ImportError: Если библиотека whisper не установлена
        FileNotFoundError: Если файл не найден
        Exception: При других ошибках распознавания
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Аудиофайл не найден: {file_path}")
    
    logging.info(f"Начинаем распознавание речи через Whisper для файла: {file_path}")
    
    try:
        model = get_whisper_model(model_name)
        
        # Запускаем распознавание
        import time
        start_time = time.time()
        
        # Параметры для улучшения распознавания русского языка и еды
        transcribe_options = {
            "language": "ru",
            "temperature": 0.0,  # Детерминированное распознавание (более стабильно)
            "beam_size": 5,      # Больше вариантов для лучшей точности
            "best_of": 5,        # Выбираем лучший из нескольких вариантов
            "fp16": False,       # Используем float32 для лучшей точности на CPU
        }
        
        # Добавляем промпт, если он указан
        # Промпт помогает модели лучше распознавать специфические слова
        if initial_prompt:
            transcribe_options["initial_prompt"] = initial_prompt
            logging.info(f"Используется промпт для улучшения распознавания: {initial_prompt[:100]}...")
        
        result = model.transcribe(file_path, **transcribe_options)
        
        elapsed_time = time.time() - start_time
        text = result["text"].strip()
        
        logging.info(f"Распознавание завершено за {elapsed_time:.2f} секунд. Текст: {text[:100]}...")
        
        return text
        
    except ImportError as e:
        logging.error(f"Ошибка импорта Whisper: {e}")
        raise
    except Exception as e:
        logging.error(f"Ошибка распознавания через Whisper: {e}", exc_info=True)
        raise Exception(f"Не удалось распознать речь через Whisper: {e}")


def download_and_convert_voice(telegram_file_path: str, output_dir: str) -> str:
    """
    Скачивает voice-файл из Telegram (уже скачанный во временную директорию),
    конвертирует его через ffmpeg в подходящий формат (WAV) для Whisper,
    возвращает путь к конечному аудиофайлу.
    
    Args:
        telegram_file_path: Путь к уже скачанному файлу от Telegram (обычно .ogg)
        output_dir: Директория для сохранения конвертированного файла
        
    Returns:
        str: Путь к конвертированному WAV файлу
        
    Raises:
        RuntimeError: При ошибках конвертации
    """
    if not os.path.exists(telegram_file_path):
        raise FileNotFoundError(f"Файл не найден: {telegram_file_path}")
    
    # Создаём выходную директорию, если её нет
    os.makedirs(output_dir, exist_ok=True)
    
    # Генерируем имя выходного файла
    input_stem = Path(telegram_file_path).stem
    output_path = os.path.join(output_dir, f"{input_stem}_converted.wav")
    
    logging.info(f"Конвертируем голосовое сообщение: {telegram_file_path} -> {output_path}")
    
    # Конвертируем через ffmpeg
    converted_path = convert_audio_to_wav(telegram_file_path, output_path)
    
    return converted_path

