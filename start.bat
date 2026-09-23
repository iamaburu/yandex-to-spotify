@echo off
rem Запуск yandex-to-spotify на Windows: двойной клик по этому файлу.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>nul
if errorlevel 1 (
  echo Не найден Python 3.9 или новее. Установите его с https://www.python.org/downloads/
  echo При установке отметьте галочку "Add python.exe to PATH", затем запустите этот файл снова.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo Первый запуск: устанавливаю необходимые компоненты...
  %PY% -m venv .venv
)
.venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Не удалось установить зависимости. Проверьте интернет и запустите снова.
  pause
  exit /b 1
)

.venv\Scripts\python.exe -W ignore transfer.py %*
pause
