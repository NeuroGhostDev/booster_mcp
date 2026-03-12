<#
.SYNOPSIS
Booster MCP Installation Script for Windows.

.DESCRIPTION
Этот скрипт клонирует репозиторий, настраивает виртуальное окружение и устанавливает все зависимости.
#>

$ErrorActionPreference = "Stop"

Write-Host "🚀 Установка Booster MCP..." -ForegroundColor Cyan

# Проверка Git
if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Ошибка: Git не установлен. Скачайте и установите: https://git-scm.com/" -ForegroundColor Red
    exit 1
}

# Проверка Python
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Ошибка: Python не установлен. Скачайте и установите Python 3.11+." -ForegroundColor Red
    exit 1
}

$InstallDir = Join-Path $HOME "booster_mcp"

# Клонирование репозитория
if (Test-Path $InstallDir) {
    Write-Host "🔄 Обновление существующей установки в $InstallDir..." -ForegroundColor Yellow
    Set-Location $InstallDir
    git pull
} else {
    Write-Host "📥 Клонирование репозитория в $InstallDir..." -ForegroundColor Yellow
    git clone https://github.com/NeuroGhostDev/Booster-mcp.git $InstallDir
    Set-Location $InstallDir
}

# Настройка виртуального окружения
Write-Host "📦 Настройка виртуального окружения..." -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

# Активация и установка зависимостей
Write-Host "⚙️ Установка зависимостей..." -ForegroundColor Cyan
# Используем прямой вызов python из .venv чтобы обойти ограничения ExecutionPolicy
$VenvPython = Join-Path ".venv" "Scripts" "python.exe"

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

# Установка скиллов
Write-Host "🧠 Установка встроенных скиллов..." -ForegroundColor Cyan
& $VenvPython skill_installer.py

Write-Host ""
Write-Host "✅ Установка завершена успешно!" -ForegroundColor Green
Write-Host ""
Write-Host "🔥 Для запуска MCP сервера в конфигурации клиента добавьте:" -ForegroundColor Cyan
Write-Host @"
{
  "mcpServers": {
    "Booster": {
      "command": "$($InstallDir.Replace('\', '\\'))\\.venv\\Scripts\\python.exe",
      "args": ["$($InstallDir.Replace('\', '\\'))\\server.py"]
    }
  }
}
"@ -ForegroundColor Gray

Write-Host ""
Write-Host "Для запуска Web UI:" -ForegroundColor Cyan
Write-Host "cd $InstallDir" -ForegroundColor Gray
Write-Host ".\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "python city_server.py --port 8080" -ForegroundColor Gray
