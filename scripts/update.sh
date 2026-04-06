#!/bin/bash
set -e

echo "⏳ Обновление бота..."
cd ~/apps/obsidian-bot

git pull
docker compose down
docker compose up -d --build

echo "✅ Бот обновлён и запущен"
docker compose logs --tail=20 bot
