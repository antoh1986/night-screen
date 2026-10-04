#!/bin/sh
# Запуск приложения «Экран: температура и яркость».
cd "$(dirname "$(readlink -f "$0")")" || exit 1
exec /usr/bin/python3 night_screen.py "$@"
