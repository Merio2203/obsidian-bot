# Obsidian AI Assistant — Telegram Bot

Telegram-бот на Python для управления персональной базой знаний в Obsidian с AI-помощником, Google Calendar и синхронизацией через rclone в Dropbox.

## 1. Требования и зависимости

- Docker и Docker Compose
- VPS (рекомендовано Ubuntu 22.04+)
- Настроенный Telegram Bot Token
- Ключ RouterAI
- Доступ к Dropbox (через rclone)
- Google OAuth credentials (для календаря)

Основные Python-зависимости описаны в `requirements.txt`.

## 2. Настройка rclone для Dropbox

1. Установите `rclone` на сервер.
2. Выполните интерактивную настройку:
   - `rclone config`
   - Создайте remote с именем `dropbox`.
3. Проверьте доступ:
   - `rclone lsd dropbox:`
4. Убедитесь, что конфиг доступен контейнеру через volume:
   - `~/.config/rclone:/root/.config/rclone:ro`

Дополнительно: можно использовать скрипт [`scripts/setup_rclone.sh`](scripts/setup_rclone.sh).

## 3. Создание Google OAuth credentials (пошагово)

1. Откройте Google Cloud Console.
2. Создайте проект (или выберите существующий).
3. Включите Google Calendar API.
4. Перейдите в Credentials -> Create Credentials -> OAuth client ID.
5. Тип приложения: Desktop app.
6. Сохраните `client_id` и `client_secret`.
7. Добавьте их в `.env`:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`

## 4. Настройка `.env`

1. Скопируйте шаблон:
   - `cp .env.example .env`
2. Заполните обязательные переменные:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_OWNER_ID`
   - `ROUTERAI_API_KEY`
   - `VAULT_PATH`
  - `DROPBOX_VAULT_PATH`
  - `DROPBOX_DB_BACKUP_PATH` (опционально, по умолчанию `/ObsidianBotBackups`)
  - `TIMEZONE`

Для Obsidian плагина `remotely-save` рекомендуемый путь:
- `DROPBOX_VAULT_PATH=/Приложения/remotely-save/ObsidianVault`

## 5. Запуск через docker-compose

```bash
docker-compose up -d --build
```

Логи:

```bash
docker-compose logs -f bot
```

Остановка:

```bash
docker-compose down
```

## 6. Команды и функции бота

- `/start` — приветствие и главное меню.
- Главное меню:
  - `📁 Проекты`
  - `✅ Задачи`
  - `📓 Дневник`
  - `📚 Библиотека`
  - `📥 Входящие`
  - `📊 Сегодня`
  - `⚙️ Настройки`

На этапе 1 реализованы инфраструктура, меню и базовые сервисы.

## 7. Структура vault

```text
vault/
├── Проекты/
├── Дневник/
├── Библиотека/
└── Входящие/
```

## 8. Логирование

- Логи пишутся в `./data/logs/bot_YYYY-MM-DD.log` (в контейнере: `/app/data/logs/`).
- Ротация выполняется ежедневно в полночь, хранение 30 дней.
- Ошибки уровня `ERROR` и выше дополнительно отправляются владельцу в Telegram.

Просмотр логов контейнера:

```bash
docker-compose logs -f bot
```

Просмотр файла логов:

```bash
tail -f ./data/logs/bot_$(date +%Y-%m-%d).log
```
