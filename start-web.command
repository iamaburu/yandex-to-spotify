#!/bin/bash
# Запуск веб-интерфейса yandex-to-spotify: двойной клик (macOS) или ./start-web.command
# Откроет браузер; окно терминала не закрывайте, пока работаете.
exec bash "$(dirname "$0")/start.command" web "$@"
