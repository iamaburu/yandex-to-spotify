#!/bin/bash
# Запуск на Linux (или из терминала на macOS). Вся логика — в start.command.
exec bash "$(dirname "$0")/start.command" "$@"
