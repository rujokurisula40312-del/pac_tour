@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================
echo   Бот "Поиск круизов"
echo ================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+ с python.org
    echo и поставьте галочку "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Создаю виртуальное окружение Python...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать .venv.
        pause
        exit /b 1
    )
)

echo Проверяю зависимости...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)

if not exist ".env" (
    echo.
    echo === Первый запуск: нужна настройка ===
    echo.
    set /p USER_BOT_TOKEN=Вставьте BOT_TOKEN от @BotFather:
    set /p USER_MANAGER=Ваш Telegram username без @ (напр. anastasia_ukolova):
    (
        echo BOT_TOKEN=!USER_BOT_TOKEN!
        echo WEBAPP_URL=https://rujokurisula40312-del.github.io/pac_tour/
        echo MANAGER_USERNAME=!USER_MANAGER!
    )> .env
    echo.
    echo Файл .env создан. В следующий раз запуск будет без вопросов.
    echo.
)

echo.
echo ================================
echo   Бот запускается...
echo   Пока это окно открыто — бот работает.
echo   Закройте окно, чтобы остановить бота.
echo ================================
echo.

".venv\Scripts\python.exe" bot.py
echo.
echo Бот остановлен.
pause
