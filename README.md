# delegation-bot

Telegram-бот для делегирования задач с трекингом через Google Calendar.

## Google Calendar setup
1. Создать OAuth client (Desktop app) в Google Cloud Console
2. Скачать credentials.json в `data/credentials.json`
3. Запустить `python scripts/gcal_oauth.py` — откроется браузер
4. Залогиниться, разрешить доступ → создастся `data/token.json`
5. Загрузить `data/token.json` и `data/credentials.json` в Railway volume `/data`

## Railway deploy
1. `railway init` (или через UI)
2. Добавить volume `/data` (1GB)
3. Залить `data/credentials.json` и `data/token.json` через `railway run` или scp
4. Установить env vars из `.env.example`
5. `railway up`
6. Проверить `https://<service>.up.railway.app/health` → `ok`
