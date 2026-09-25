#!/bin/bash
# Запуск веб-интерфейса на Linux (или из терминала на macOS).
exec bash "$(dirname "$0")/start.command" web "$@"
