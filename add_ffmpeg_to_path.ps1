# Скрипт для добавления ffmpeg в PATH на Windows
# Запустите от имени администратора: PowerShell -ExecutionPolicy Bypass -File add_ffmpeg_to_path.ps1

Write-Host "========================================"
Write-Host "FFmpeg PATH Setup Script"
Write-Host "========================================"
Write-Host ""

# Ищем ffmpeg.exe в стандартных местах
$searchPaths = @(
    "C:\ffmpeg\bin",
    "C:\Program Files\ffmpeg\bin",
    "C:\Program Files (x86)\ffmpeg\bin",
    "$env:USERPROFILE\Downloads\ffmpeg*\bin",
    "$env:USERPROFILE\Desktop\ffmpeg*\bin"
)

$ffmpegPath = $null

Write-Host "Ищем ffmpeg.exe..."
foreach ($path in $searchPaths) {
    $found = Get-ChildItem $path -ErrorAction SilentlyContinue | 
             Where-Object { $_.Name -eq "ffmpeg.exe" } | 
             Select-Object -First 1
    
    if ($found) {
        $ffmpegPath = $found.DirectoryName
        Write-Host "  Найден: $ffmpegPath" -ForegroundColor Green
        break
    }
}

# Если не найден, просим указать путь вручную
if (-not $ffmpegPath) {
    Write-Host ""
    Write-Host "ffmpeg.exe не найден автоматически." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "ВАЖНО: У вас исходный код ffmpeg, а не готовая версия!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Скачайте готовую версию:"
    Write-Host "  1. https://www.gyan.dev/ffmpeg/builds/" -ForegroundColor Cyan
    Write-Host "  2. Скачайте: ffmpeg-release-essentials.zip"
    Write-Host "  3. Распакуйте (например, в C:\ffmpeg)"
    Write-Host "  4. Запустите этот скрипт снова"
    Write-Host ""
    
    $manualPath = Read-Host "Или введите путь к папке bin вручную (например, C:\ffmpeg\bin)"
    if ($manualPath -and (Test-Path "$manualPath\ffmpeg.exe")) {
        $ffmpegPath = $manualPath
        Write-Host "  Используем: $ffmpegPath" -ForegroundColor Green
    } else {
        Write-Host "  Путь неверный или ffmpeg.exe не найден" -ForegroundColor Red
        exit 1
    }
}

# Добавляем в PATH
Write-Host ""
Write-Host "Добавляем в PATH..."

try {
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    
    if ($currentPath -like "*$ffmpegPath*") {
        Write-Host "  ffmpeg уже в PATH" -ForegroundColor Yellow
    } else {
        $newPath = "$currentPath;$ffmpegPath"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "  ✓ Добавлено в PATH: $ffmpegPath" -ForegroundColor Green
        
        # Обновляем PATH в текущей сессии
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path','User') + ';' + [System.Environment]::GetEnvironmentVariable('Path','Machine')
    }
    
    Write-Host ""
    Write-Host "Проверяем установку..."
    $ffmpegCheck = & ffmpeg -version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ ffmpeg работает!" -ForegroundColor Green
        Write-Host ""
        Write-Host "ВАЖНО: Перезапустите терминал/PowerShell для применения изменений!" -ForegroundColor Yellow
    } else {
        Write-Host "  ⚠ ffmpeg не найден в текущей сессии" -ForegroundColor Yellow
        Write-Host "  Перезапустите терминал и выполните: ffmpeg -version" -ForegroundColor Yellow
    }
    
} catch {
    Write-Host "  ✗ Ошибка: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Попробуйте запустить скрипт от имени администратора" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================"
Write-Host "Готово!"
Write-Host "========================================"

