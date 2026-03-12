#!/usr/bin/env bash
# Booster MCP Installation Script for Unix-like systems (Debian, Ubuntu, macOS, iOS/a-shell)

set -e

echo "🚀 Установка Booster MCP..."

# Проверка наличия Git
if ! command -v git &> /dev/null; then
    echo "❌ Ошибка: Git не установлен. Пожалуйста, установите Git перед продолжением."
    exit 1
fi

# Проверка наличия Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Ошибка: Python 3 не установлен."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "💡 Для Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "💡 Для macOS: brew install python3"
    fi
    exit 1
fi

INSTALL_DIR="$HOME/booster_mcp"

# Клонирование репозитория
if [ -d "$INSTALL_DIR" ]; then
    echo "🔄 Обновление существующей установки в $INSTALL_DIR..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "📥 Клонирование репозитория в $INSTALL_DIR..."
    git clone https://github.com/NeuroGhostDev/Booster-mcp.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Проверка на наличие модуля venv
if ! python3 -c "import venv" &> /dev/null; then
    echo "❌ Ошибка: Модуль python3-venv не установлен."
    echo "💡 На Ubuntu/Debian выполните: sudo apt install python3.11-venv (или версию вашего Python)"
    exit 1
fi

# Создание и активация виртуального окружения
echo "📦 Настройка виртуального окружения..."
python3 -m venv .venv

# Активация
source .venv/bin/activate

# Установка зависимостей
echo "⚙️ Установка зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt

# Установка встроенных скиллов 
echo "🧠 Установка скиллов агента..."
python skill_installer.py

echo ""
echo "✅ Установка завершена успешно!"
echo ""
echo "🔥 Для запуска MCP сервера интегрируйте его с вашим клиентом."
echo ""
echo "Пример конфигурации для Claude Desktop / Glama / Smithery:"
echo "{"
echo "  \"mcpServers\": {"
echo "    \"Booster\": {"
echo "      \"command\": \"$INSTALL_DIR/.venv/bin/python\","
echo "      \"args\": [\"$INSTALL_DIR/server.py\"]"
echo "    }"
echo "  }"
echo "}"
echo ""
echo "Для запуска Web UI:"
echo "cd $INSTALL_DIR && source .venv/bin/activate && python city_server.py --port 8080"
