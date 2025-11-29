# Инструкция по установке ffmpeg на Windows

## Шаг 1: Скачать готовую версию ffmpeg

1. Перейдите на https://www.gyan.dev/ffmpeg/builds/ (рекомендуется)
   ИЛИ
   https://github.com/BtbN/FFmpeg-Builds/releases

2. Скачайте **ffmpeg-release-essentials.zip** (не исходный код!)

3. Распакуйте архив (например, в `C:\ffmpeg`)

## Шаг 2: Найти путь к ffmpeg.exe

После распаковки должна быть структура:
```
C:\ffmpeg\
  └── bin\
      ├── ffmpeg.exe
      ├── ffplay.exe
      └── ffprobe.exe
```

Путь к папке `bin` - это то, что нужно добавить в PATH.

## Шаг 3: Добавить в PATH (способ 1 - через PowerShell)

Откройте PowerShell **от имени администратора** и выполните:

```powershell
# Замените путь на ваш реальный путь к папке bin
$ffmpegBinPath = "C:\ffmpeg\bin"

# Добавляем в PATH для текущего пользователя
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$ffmpegBinPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$ffmpegBinPath", "User")
    Write-Host "ffmpeg добавлен в PATH!"
} else {
    Write-Host "ffmpeg уже в PATH"
}

# Обновляем PATH в текущей сессии
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','User') + ';' + [System.Environment]::GetEnvironmentVariable('Path','Machine')
```

## Шаг 3: Добавить в PATH (способ 2 - через GUI)

1. Нажмите `Win + R`, введите `sysdm.cpl` и нажмите Enter
2. Перейдите на вкладку **"Дополнительно"**
3. Нажмите **"Переменные среды"**
4. В разделе **"Переменные пользователя"** найдите переменную `Path`
5. Нажмите **"Изменить"**
6. Нажмите **"Создать"**
7. Введите путь к папке `bin` (например: `C:\ffmpeg\bin`)
8. Нажмите **"OK"** во всех окнах
9. **Перезапустите терминал/PowerShell**

## Шаг 4: Проверить установку

Откройте **новый** PowerShell и выполните:

```powershell
ffmpeg -version
```

Должна появиться информация о версии ffmpeg.

## Быстрая установка (если уже распаковано)

Если вы уже распаковали ffmpeg, выполните в PowerShell (от имени администратора):

```powershell
# УКАЖИТЕ ПРАВИЛЬНЫЙ ПУТЬ К ВАШЕЙ ПАПКЕ BIN
$ffmpegBinPath = "C:\Users\licos\Downloads\ffmpeg-8.0.1\bin"  # ИЗМЕНИТЕ НА ВАШ ПУТЬ

# Проверяем, существует ли ffmpeg.exe
if (Test-Path "$ffmpegBinPath\ffmpeg.exe") {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$ffmpegBinPath*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$ffmpegBinPath", "User")
        Write-Host "✓ ffmpeg добавлен в PATH: $ffmpegBinPath"
        Write-Host "Перезапустите терминал и выполните: ffmpeg -version"
    } else {
        Write-Host "✓ ffmpeg уже в PATH"
    }
} else {
    Write-Host "✗ ffmpeg.exe не найден по пути: $ffmpegBinPath"
    Write-Host "Проверьте путь или скачайте готовую версию с https://www.gyan.dev/ffmpeg/builds/"
}
```

