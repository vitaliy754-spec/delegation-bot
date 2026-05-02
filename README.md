# delegation-bot

Telegram-бот для делегирования задач с трекингом через Google Calendar.

## Google Calendar setup
1. Создать OAuth client (Desktop app) в Google Cloud Console
2. Скачать credentials.json в `data/credentials.json`
3. Запустить `python scripts/gcal_oauth.py` — откроется браузер
4. Залогиниться, разрешить доступ → создастся `data/token.json`
5. Загрузить `data/token.json` и `data/credentials.json` в Railway volume `/data`
