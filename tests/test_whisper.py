"""
Тест для проверки работы модуля stt_whisper.py.

Запуск:
    python -m pytest tests/test_whisper.py -v
    или
    python tests/test_whisper.py
"""
import os
import sys
import unittest
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from stt_whisper import (
        get_whisper_model,
        check_ffmpeg,
        convert_audio_to_wav,
        transcribe_audio,
        download_and_convert_voice
    )
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что установлены зависимости: pip install openai-whisper")
    sys.exit(1)


class TestWhisperSTT(unittest.TestCase):
    """Тесты для модуля распознавания речи через Whisper"""
    
    def setUp(self):
        """Подготовка к тестам"""
        self.test_resources_dir = Path(__file__).parent / "resources"
        self.test_resources_dir.mkdir(exist_ok=True)
    
    def test_check_ffmpeg(self):
        """Тест проверки наличия ffmpeg"""
        has_ffmpeg = check_ffmpeg()
        print(f"\nffmpeg установлен: {has_ffmpeg}")
        if not has_ffmpeg:
            print("⚠️  ВНИМАНИЕ: ffmpeg не установлен!")
            print("   Установите ffmpeg для работы с голосовыми сообщениями")
        # Не делаем assert, так как это информационный тест
    
    def test_get_whisper_model(self):
        """Тест загрузки модели Whisper"""
        print("\nТестируем загрузку модели Whisper...")
        try:
            model = get_whisper_model()
            self.assertIsNotNone(model, "Модель должна быть загружена")
            print("✅ Модель Whisper успешно загружена")
            
            # Проверяем кэширование - вторая загрузка должна быть быстрой
            import time
            start = time.time()
            model2 = get_whisper_model()
            elapsed = time.time() - start
            self.assertIs(model, model2, "Модель должна быть закэширована")
            print(f"✅ Модель закэширована (повторная загрузка заняла {elapsed:.3f} сек)")
        except ImportError as e:
            self.fail(f"Библиотека whisper не установлена: {e}")
        except Exception as e:
            self.fail(f"Ошибка загрузки модели: {e}")
    
    def test_transcribe_audio(self):
        """Тест распознавания речи из аудиофайла"""
        print("\nТестируем распознавание речи...")
        
        # Ищем тестовый аудиофайл
        test_audio_files = list(self.test_resources_dir.glob("*.wav")) + \
                          list(self.test_resources_dir.glob("*.mp3")) + \
                          list(self.test_resources_dir.glob("*.ogg"))
        
        if not test_audio_files:
            print("⚠️  Тестовый аудиофайл не найден в tests/resources/")
            print("   Создайте файл test_audio.wav для полного теста")
            print("   Пропускаем тест распознавания...")
            return
        
        test_file = test_audio_files[0]
        print(f"Используем тестовый файл: {test_file}")
        
        try:
            text = transcribe_audio(str(test_file))
            print(f"✅ Распознанный текст: '{text}'")
            self.assertIsInstance(text, str, "Результат должен быть строкой")
        except FileNotFoundError:
            self.fail(f"Тестовый файл не найден: {test_file}")
        except Exception as e:
            self.fail(f"Ошибка распознавания: {e}")


def run_manual_test():
    """
    Ручной тест для быстрой проверки работы Whisper.
    Запуск: python tests/test_whisper.py
    """
    import sys
    import io
    # Устанавливаем UTF-8 для вывода
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    print("=" * 60)
    print("Manual test of stt_whisper.py module")
    print("=" * 60)
    
    # Проверка ffmpeg
    print("\n1. Checking ffmpeg...")
    has_ffmpeg = check_ffmpeg()
    if has_ffmpeg:
        print("   OK: ffmpeg is installed")
    else:
        print("   ERROR: ffmpeg is not installed")
        print("   Install ffmpeg for voice message processing")
        return
    
    # Проверка модели
    print("\n2. Loading Whisper model...")
    try:
        model = get_whisper_model()
        print("   OK: Whisper model loaded")
    except Exception as e:
        print(f"   ERROR: Model loading failed: {e}")
        return
    
    # Проверка распознавания (если есть тестовый файл)
    test_resources = Path(__file__).parent / "resources"
    test_resources.mkdir(exist_ok=True)
    
    test_files = list(test_resources.glob("*.wav")) + \
                 list(test_resources.glob("*.mp3")) + \
                 list(test_resources.glob("*.ogg"))
    
    if test_files:
        test_file = test_files[0]
        print(f"\n3. Testing transcription from file: {test_file.name}...")
        try:
            text = transcribe_audio(str(test_file))
            print(f"   OK: Recognized text: '{text}'")
        except Exception as e:
            print(f"   ERROR: Transcription failed: {e}")
    else:
        print("\n3. Test audio file not found")
        print("   Place .wav, .mp3 or .ogg file in tests/resources/ for testing")
    
    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--unittest":
        # Запуск через unittest
        unittest.main()
    else:
        # Ручной тест
        run_manual_test()

