#!/usr/bin/env bash
# Booster MCP Installation Script for Unix-like systems (Debian, Ubuntu, macOS, iOS/a-shell)

set -e

echo "🚀 Установка Booster MCP..."

# Проверка наличия Git
if ! command -v git &> /dev/null; then
    echo "❌ Ошибка: Git не установлен. Пожалуйста, установите Git перед продолжением."
    exit 1
fi

# Проверка наличия uv или Python 3
if ! command -v uv &> /dev/null && ! command -v python3 &> /dev/null; then
    echo "❌ Ошибка: установите uv или Python 3.11-3.13."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "💡 Для Ubuntu/Debian: sudo apt update && sudo apt install python3.12 python3.12-venv"
    elif [[ "$OSTYPE" == "darwin" ]]; then
        echo "💡 Для macOS: brew install python@3.12"
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

echo "📦 Настройка виртуального окружения..."
VENV_PYTHON=".venv/bin/python"

if command -v uv &> /dev/null; then
    echo "⚡ Синхронизация зависимостей через uv.lock..."
    uv sync --no-dev
else
    PYTHON_BIN=""
    for candidate in python3.12 python3.13 python3.11 python3; do
        if command -v "$candidate" &> /dev/null && "$candidate" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)'; then
            PYTHON_BIN="$candidate"
            break
        fi
    done

    if [ -z "$PYTHON_BIN" ]; then
        echo "❌ Ошибка: не найден совместимый Python 3.11-3.13."
        exit 1
    fi

    rm -rf .venv
    echo "⚙️ Установка зависимостей через pip..."
    "$PYTHON_BIN" -m venv .venv
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install .
fi

if [ ! -x "$VENV_PYTHON" ]; then
    echo "❌ Ошибка: виртуальное окружение не было создано."
    exit 1
fi

# Установка встроенных скиллов 
echo "🧠 Установка скиллов агента..."
"$VENV_PYTHON" -c "from skill_installer import install_bundled_skills; install_bundled_skills()"

echo "🔧 Установка команды booster..."
"$VENV_PYTHON" -m cli control launcher

USER_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$USER_BIN:"* ]]; then
    PROFILE=""
    PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
    case "${SHELL:-}" in
        */zsh) PROFILE="$HOME/.zshrc" ;;
        */bash) PROFILE="$HOME/.bashrc" ;;
        *) PROFILE="$HOME/.profile" ;;
    esac

    if ! grep -Fq "# Added by Booster Control" "$PROFILE" 2>/dev/null; then
        {
            echo ""
            echo "# Added by Booster Control"
            echo "$PATH_LINE"
        } >> "$PROFILE"
        echo "Добавлен $USER_BIN в PATH через $PROFILE."
    fi
    export PATH="$USER_BIN:$PATH"
fi

echo ""
echo "✅ Установка завершена успешно!"
echo "Управление подключениями: booster control"
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
