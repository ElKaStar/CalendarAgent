# Инструкция по развертыванию на Ubuntu 22.04

## Подготовка сервера

### 1. Установка системных зависимостей

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python 3.10+ и pip
sudo apt install -y python3 python3-pip python3-venv

# Установка ffmpeg (требуется для Whisper)
sudo apt install -y ffmpeg

# Установка Git (если еще не установлен)
sudo apt install -y git
```

### 2. Клонирование репозитория

```bash
cd ~
git clone <ваш_github_repo_url> CalendarAgent
cd CalendarAgent
```

### 3. Создание виртуального окружения

```bash
# Создание виртуального окружения
python3 -m venv venv

# Активация виртуального окружения
source venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

```bash
# Копирование примера конфигурации
cp env.example .env

# Редактирование .env файла
nano .env
```

Заполните все необходимые переменные:
- `TELEGRAM_BOT_TOKEN`
- `GIGACHAT_CLIENT_ID`
- `GIGACHAT_CLIENT_SECRET`
- `GOOGLE_CREDENTIALS_FILE=service-account.json`
- И другие настройки

### 5. Загрузка credentials

```bash
# Загрузите service-account.json в корневую директорию проекта
# (не коммитьте его в Git - он уже в .gitignore)
```

### 6. Создание директорий

```bash
# Создание директории для временных файлов
mkdir -p temp

# Установка прав на скрипт запуска
chmod +x run_bot.sh
```

## Запуск бота

### Ручной запуск (для тестирования)

```bash
source venv/bin/activate
python3 bot.py
```

### Запуск через systemd (рекомендуется для production)

Создайте файл `/etc/systemd/system/calendarbot.service`:

```ini
[Unit]
Description=Calendar Agent Telegram Bot
After=network.target

[Service]
Type=simple
User=ваш_пользователь
WorkingDirectory=/home/ваш_пользователь/CalendarAgent
Environment="PATH=/home/ваш_пользователь/CalendarAgent/venv/bin"
ExecStart=/home/ваш_пользователь/CalendarAgent/venv/bin/python3 /home/ваш_пользователь/CalendarAgent/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активация сервиса:

```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable calendarbot

# Запуск сервиса
sudo systemctl start calendarbot

# Проверка статуса
sudo systemctl status calendarbot

# Просмотр логов
sudo journalctl -u calendarbot -f
```

## Проверка работы

1. Проверьте логи: `sudo journalctl -u calendarbot -n 50`
2. Отправьте тестовое сообщение боту в Telegram
3. Проверьте, что бот отвечает

## Обновление бота

```bash
cd ~/CalendarAgent
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart calendarbot
```

## Решение проблем

### Проблема с правами доступа

```bash
# Убедитесь, что у пользователя есть права на директорию
chown -R ваш_пользователь:ваш_пользователь ~/CalendarAgent
```

### Проблема с ffmpeg

```bash
# Проверка установки
ffmpeg -version

# Если не установлен
sudo apt install -y ffmpeg
```

### Проблема с Whisper (модель не скачивается)

Whisper автоматически скачает модель при первом запуске (~1.5GB для base модели).
Убедитесь, что есть достаточно места на диске и интернет-соединение.

### Проблема с путями

Все пути в коде используют `os.path.join()`, что обеспечивает кроссплатформенность.
Если возникают проблемы, проверьте переменную `TEMP_DIR` в `.env`.

