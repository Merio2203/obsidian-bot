#!/bin/bash
set -e

reset_db() {
    echo "⚠️  Сброс базы данных..."
    docker compose stop bot || true
    rm -f ./data/bot.db
    docker compose up -d --build
    echo "✅ БД сброшена и бот пересоздан"
    exit 0
}

if [[ "$1" == "--reset-db" ]]; then
    cd ~/apps/obsidian-bot
    reset_db
fi

echo "⏳ Обновление бота..."
cd ~/apps/obsidian-bot

git pull
docker compose down
docker compose up -d --build

echo "Синхронизация БД с vault..."
docker compose exec -T bot python -c "import asyncio; from bot.services.obsidian_service import sync_db_with_vault; asyncio.run(sync_db_with_vault())"
echo "✅ БД синхронизирована"

echo "✅ Бот обновлён и запущен"
docker compose logs --tail=20 bot
