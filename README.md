# delegation-bot

Telegram-бот задач и делегирования с трекингом через Google Calendar. Владелец ставит
задачу голосом или текстом; бот раздаёт её исполнителям, напоминает, собирает статус и
каждое утро присылает сводку дня.

## Возможности

- **Голос или текст** → задача (Whisper + LLM-разбор), подтверждение кнопками.
- **Несколько исполнителей**: в речи указываешь имя («…ответственный — Оля») — задача уходит ему.
  Без имени — задача себе, с напоминаниями владельцу (за 2ч/1ч/15м до дедлайна).
- **Делегирование**: исполнителю приходит задача в личку; через сутки бот спрашивает статус,
  если напоминания не заданы голосом (`FOLLOWUP_DELAY_HOURS`).
- **Статус** от исполнителя («делаю/готово/застрял») зеркалится владельцу; «готово» закрывает задачу.
- **Просрочка** на дедлайне → алерт владельцу + пометка ⚠️ в Google Calendar.
- **Утренняя сводка** активных задач владельцу в `MORNING_DIGEST_HOUR`.

## Команды (владелец)

- `/tasks` — активные задачи
- `/executors` — список исполнителей
- `/add_executor <telegram_id> <имя>` — добавить исполнителя
- `/cancel <id>` — отменить задачу

Исполнитель: жмёт `/start`, бот показывает его ID — передать владельцу для `/add_executor`.

## Как развернуть (проще всего — через ИИ)

Открой проект в **Codex / Claude Code** и скажи: «разверни бота по `AGENT_SETUP.md`».
ИИ проведёт по шагам: создать бота, получить ключи, заполнить `.env`, запустить, задеплоить на Railway.

**Google Calendar НЕ требуется** — основной режим работает без него (задачи хранятся в базе, видны через `/tasks` и утреннюю сводку). Google Calendar — опционально, только если нужен, и требует более сложной настройки (см. `ONBOARDING.md`, раздел 9).

Ручной онбординг для человека — в `ONBOARDING.md`.

## Quick start (prototype mode — without Google Calendar)

Минимум для теста: только Telegram + OpenAI.

1. Создать бота через @BotFather → токен
2. Получить OpenAI API key
3. Узнать ID чата и user_id через @RawDataBot
4. Скопировать `.env.example` → `.env`, заполнить:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `ALLOWED_CHAT_ID`
   - `VITALY_USER_ID`
   - `ASSISTANT_USER_ID`
   - GCal-переменные оставить пустыми
5. `python -m app.main`
6. В чат шлёшь voice → бот парсит → подтверждаешь → задача в SQLite, напоминания работают через APScheduler. Календарь добавишь позже.

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
