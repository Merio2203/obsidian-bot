#!/usr/bin/env bash
set -euo pipefail

echo "Запуск настройки rclone для Dropbox..."
rclone config
echo "Проверка remote 'dropbox'..."
rclone lsd dropbox:
echo "Готово. Теперь можно запускать docker-compose."
