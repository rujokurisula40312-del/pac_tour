#!/bin/bash
cd "$(dirname "$0")"

echo "================================"
echo "  Бот \"Поиск круизов\""
echo "================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ОШИБКА] Python 3 не найден. Установите Python 3.10+ с python.org"
    read -n 1 -s -r -p "Нажмите любую клавишу..."
    exit 1
fi

if [ ! -d .venv ]; then
    echo "Создаю виртуальное окружение Python..."
    python3 -m venv .venv || { echo "[ОШИБКА] Не создалось .venv"; read -n 1 -s; exit 1; }
fi

echo "Проверяю зависимости..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt || { echo "[ОШИБКА] pip install"; read -n 1 -s; exit 1; }

if [ ! -f .env ]; then
    echo
    echo "=== Первый запуск: нужна настройка ==="
    echo
    read -p "Вставьте BOT_TOKEN от @BotFather: " USER_BOT_TOKEN
    read -p "Ваш Telegram username без @ (напр. anastasia_ukolova): " USER_MANAGER
    cat > .env <<EOF
BOT_TOKEN=$USER_BOT_TOKEN
WEBAPP_URL=https://rujokurisula40312-del.github.io/pac_tour/
MANAGER_USERNAME=$USER_MANAGER
EOF
    echo
    echo "Файл .env создан. В следующий раз запуск будет без вопросов."
    echo
fi

echo
echo "================================"
echo "  Бот запускается..."
echo "  Пока это окно открыто — бот работает."
echo "  Закройте окно, чтобы остановить бота."
echo "================================"
echo

.venv/bin/python bot.py
echo
echo "Бот остановлен."
read -n 1 -s -r -p "Нажмите любую клавишу..."
