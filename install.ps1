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

# Проверка uv или Python Launcher
if (-not (Get-Command "uv" -ErrorAction SilentlyContinue) -and
    -not (Get-Command "py" -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Ошибка: установите uv или Python 3.11-3.13 с Python Launcher." -ForegroundColor Red
    exit 1
}

$InstallDir = Join-Path $HOME "booster_mcp"

# Клонирование репозитория
if (Test-Path $InstallDir) {
    Write-Host "🔄 Обновление существующей установки в $InstallDir..." -ForegroundColor Yellow
    Set-Location $InstallDir
    git pull
}
else {
    Write-Host "📥 Клонирование репозитория в $InstallDir..." -ForegroundColor Yellow
    git clone https://github.com/NeuroGhostDev/Booster-mcp.git $InstallDir
    Set-Location $InstallDir
}

# Настройка виртуального окружения и зависимостей
Write-Host "📦 Настройка виртуального окружения..." -ForegroundColor Cyan
$VenvPython = Join-Path ".venv" "Scripts" "python.exe"

if (Get-Command "uv" -ErrorAction SilentlyContinue) {
    Write-Host "⚡ Синхронизация зависимостей через uv.lock..." -ForegroundColor Cyan
    uv sync --no-dev
}
else {
    $PythonSelector = $null
    foreach ($Candidate in @("-3.12", "-3.13", "-3.11")) {
        & py $Candidate -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonSelector = $Candidate
            break
        }
    }

    if (-not $PythonSelector) {
        Write-Host "❌ Ошибка: не найден совместимый Python 3.11-3.13." -ForegroundColor Red
        exit 1
    }

    if (Test-Path ".venv") {
        Remove-Item ".venv" -Recurse -Force
    }

    Write-Host "⚙️ Установка зависимостей через pip..." -ForegroundColor Cyan
    & py $PythonSelector -m venv .venv
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install .
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "❌ Ошибка: виртуальное окружение не было создано." -ForegroundColor Red
    exit 1
}

# Установка скиллов
Write-Host "🧠 Установка встроенных скиллов..." -ForegroundColor Cyan
& $VenvPython -c "from skill_installer import install_bundled_skills; install_bundled_skills()"

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
