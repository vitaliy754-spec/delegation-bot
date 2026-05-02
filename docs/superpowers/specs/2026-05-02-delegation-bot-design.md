# Delegation Bot — Design Spec

**Date:** 2026-05-02
**Owner:** Виталий

## Goal

Telegram-бот для делегирования задач одному постоянному исполнителю. Виталий голосом ставит задачу с дедлайном и расписанием напоминаний → бот создаёт событие в Google Calendar → ведёт исполнителя в общем чате → шлёт напоминания → отслеживает статус → алертит при просрочке.

## User flow

1. В общем чате (Виталий + Исполнитель + Бот) Виталий шлёт voice: «Сделай лендинг до завтра 18:00, напомни ему сегодня в 20:00 и завтра в 12:00»
2. Бот транскрибирует (Whisper) → парсит LLM в структуру `{task, deadline, reminders[]}`
3. Бот в чат: «Понял: <задача>, дедлайн <дата>, напоминания <список>. Подтвердить? [✅/✏️]»
4. Виталий жмёт ✅ → бот создаёт событие в Google Calendar, тегает исполнителя в чате
5. По расписанию бот пингует в чат: «@assistant как дела по "лендинг"?»
6. Исполнитель отвечает голосом или текстом → бот классифицирует intent (`in_progress` / `done` / `blocked` / `other`) → пишет в description события и подтверждает
7. На дедлайне если статус ≠ `done` → бот пингует Виталийа: «⚠️ Просрочка: <задача>»

## Architecture

Single Python service на Railway. Long-polling Telegram (без webhook — проще). APScheduler с SQLite jobstore для напоминаний.

```
[Telegram chat] ⇄ [bot.py handlers]
                      ↓
              [voice → Whisper → text]
                      ↓
              [LLM parser → TaskSpec]
                      ↓
        [SQLite] ←→ [GCal API client]
                      ↓
              [APScheduler jobs]
                      ↓
              [reminder sender]
```

## Components

| File | Responsibility |
|---|---|
| `app/bot.py` | Telegram handlers: voice, text, callback (confirm/cancel), `/tasks` |
| `app/transcribe.py` | OpenAI Whisper wrapper (voice file → text) |
| `app/parser.py` | LLM (GPT-4o-mini) с Pydantic structured output → `TaskSpec` |
| `app/gcal.py` | Google Calendar: OAuth, create/update/get event |
| `app/db.py` | SQLite (sqlite3 + сырые SQL): schema, task CRUD, mapping task↔event↔chat |
| `app/scheduler.py` | APScheduler init с SQLAlchemyJobStore, schedule reminders |
| `app/intent.py` | LLM intent classifier (status reply → enum) |
| `app/config.py` | env vars, paths |
| `app/main.py` | entry point: init scheduler, register handlers, run polling |

## Data model

**SQLite `tasks`:**
- `id` PK
- `chat_id` (Telegram)
- `assistant_user_id` (Telegram user id of executor)
- `title` text
- `description` text
- `deadline` datetime UTC
- `gcal_event_id` text
- `status` enum: `pending|in_progress|done|blocked|overdue`
- `created_at`, `updated_at`

**SQLite `status_log`:** task_id, status, note, ts.

## External integrations

- **Telegram Bot API** — `python-telegram-bot==21.x`, voice download via `bot.get_file()`
- **OpenAI** — `openai>=1.50`, Whisper-1 для транскрипции, gpt-4o-mini для парсинга и intent. Cache не нужен (объём низкий).
- **Google Calendar** — `google-api-python-client`, OAuth flow один раз локально → сохранить `token.json` в Railway volume. Один общий календарь «Задачи».

## Config (env)

```
TELEGRAM_BOT_TOKEN
OPENAI_API_KEY
GOOGLE_CALENDAR_ID         # email общего календаря
GOOGLE_CREDENTIALS_PATH    # /data/credentials.json (Railway volume)
GOOGLE_TOKEN_PATH          # /data/token.json
ALLOWED_CHAT_ID            # ID общего чата (whitelist)
VITALY_USER_ID             # Виталий — алерты о просрочке
ASSISTANT_USER_ID          # для @mention
DB_PATH                    # /data/bot.db
TZ                         # Europe/Kyiv
```

## TaskSpec schema (Pydantic)

```python
class Reminder(BaseModel):
    when: datetime  # absolute UTC
    text: str | None = None  # custom reminder text

class TaskSpec(BaseModel):
    title: str           # короткое название (3-7 слов)
    description: str     # развёрнутое описание из voice
    deadline: datetime   # UTC
    reminders: list[Reminder]  # explicit times from voice
```

LLM prompt принимает текущее время + транскрипт, возвращает JSON. При неоднозначности (нет дедлайна) — возвращает `null` в deadline, бот переспрашивает.

## Reminder logic

- Виталий задаёт времена голосом → парсер кладёт в `reminders[]`
- На confirm бот регистрирует APScheduler job на каждое время + один автоматический job на `deadline` (overdue check)
- Если воз reminders пустой и срок > 24ч → бот предлагает дефолт «напомнить за 50% и за 2ч до» (одно сообщение с кнопкой ✅)

## Status classification

Intent classifier (LLM) на reply исполнителя в треде задачи:
- `in_progress` («в работе», «делаю», «к вечеру будет»)
- `done` («сделал», «готово», «закрыл»)
- `blocked` («застрял», «не могу», «нужна инфа»)
- `other` (просто сообщение, не статус) — игнор

Бинд reply→task: ищем последний активный task в чате с упоминанием исполнителя ИЛИ reply на сообщение бота с task_id в metadata.

## Deployment

- Railway project, 1 service, 512 MB RAM
- Persistent volume `/data` для SQLite + Google token
- Healthcheck: HTTP `/health` на 8080 (минимальный aiohttp endpoint, для Railway sleep prevention)
- Логи stdout

## Out of scope (v1)

- Несколько исполнителей
- Webhook вместо polling (если нагрузка вырастет — мигрируем)
- Web-дашборд (Google Calendar и есть дашборд)
- Файл-вложения к задачам
- Forward сообщений как задач

## Open questions

- [ ] Реальный TZ Виталийа (Europe/Kyiv?) — подтвердить
- [ ] Нужна ли кнопка «отмена задачи» в чате — да, добавляем `/cancel <id>`
- [ ] Что делать если исполнитель не в чате когда бот пингует — игнорируем, пинг останется в истории
