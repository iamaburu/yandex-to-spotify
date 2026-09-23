#!/bin/bash
# Запуск yandex-to-spotify на macOS и Linux: двойной клик (macOS) или ./start.command
# При первом запуске создаёт окружение Python и ставит зависимости, затем запускает мастер.
cd "$(dirname "$0")" || exit 1

pause() { [ -t 0 ] && read -r -p "Нажмите Enter, чтобы закрыть окно…" _; }

PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Не найден Python 3.9 или новее."
  if [ "$(uname)" = "Darwin" ]; then
    echo "На macOS выполните в Терминале: xcode-select --install"
    echo "(установятся инструменты разработчика Apple вместе с Python), затем запустите этот файл снова."
  else
    echo "Установите Python 3 через менеджер пакетов вашей системы и запустите этот файл снова."
  fi
  pause; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Первый запуск: устанавливаю необходимые компоненты (около минуты)…"
  "$PY" -m venv .venv || { echo "Не удалось создать окружение Python."; pause; exit 1; }
fi
if ! .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt; then
  echo "Не удалось установить зависимости. Проверьте интернет и запустите снова."
  pause; exit 1
fi

.venv/bin/python -W ignore transfer.py "$@"
pause
