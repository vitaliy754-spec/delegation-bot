# Design: "не взяв в роботу" / повторні нагадування після дедлайну / авто-реєстрація виконавця

Repo: delegation-bot (https://github.com/vitaliy754-spec/delegation-bot)

## Контекст

Бот делегування задач (Telegram, python-telegram-bot + APScheduler + sqlite) вже вміє:
- створювати задачу (собі або делегувати виконавцю), планувати нагадування й дедлайн (`app/bot.py::_finalize`, `app/scheduler.py`);
- приймати статус від виконавця текстом/голосом (`status_handler` → `pending` → `in_progress`/`blocked`/`done`);
- для власних задач Віталія — лише кнопку «✅ Виконано» (без проміжного статусу).

Потрібно додати три можливості:
1. Нагадування, якщо виконавець/Віталій не взяв задачу в роботу протягом 30 хв.
2. Повторне (щогодинне) нагадування після дедлайну, поки задача не `done`/`cancelled`.
3. Автоматична реєстрація виконавця через посилання-інвайт замість ручного вводу Telegram ID.

## 1. Кнопка "Взяв в роботу" + нагадування 30 хв

- При створенні будь-якої задачі (делегованої або власної):
  - Делегована: повідомлення виконавцю `📌 Нова задача #...` отримує inline-кнопку **«🟢 Взяв в роботу»** (`callback_data=f"started:{task_id}"`).
  - Власна (Віталію): підтвердження створення задачі отримує дві кнопки — **«🟢 Взяв в роботу»** і **«✅ Виконано»**.
- Натискання «Взяв в роботу» → `db.update_status(task_id, "in_progress")`, повідомлення оновлюється — кнопка «Взяв в роботу» зникає, лишається тільки «✅ Виконано» (для делегованих кнопок взагалі не було — додається тільки «in_progress» статус-лог).
- Підстраховка: одразу при створенні задачі планується одноразове нагадування `kind="not_started"` через `NOT_STARTED_REMINDER_MINUTES` (дефолт 30) хвилин.
  - На спрацюванні: якщо `task.status == "pending"` ще:
    - делегована → повідомлення виконавцю: «ти ще не взяв задачу в роботу»;
    - власна → повідомлення Віталію з тими ж двома кнопками (Почав / Виконано).
  - Якщо статус уже змінився (`in_progress`/`done`/...) — нічого не робити.

## 2. Повторне нагадування після дедлайну (раз на годину)

- Як і зараз: при спрацюванні `kind="deadline"`, якщо `task.status != "done"` → статус стає `overdue`, Віталію летить одне повідомлення про прострочення.
- Додатково в цей момент планується **повторюваний** job `kind="overdue_repeat"` (APScheduler `IntervalTrigger`, `start_date=deadline`, `hours=OVERDUE_REPEAT_HOURS`, дефолт 1) з `job_id=f"task{id}-overdue_repeat"`.
- На кожному спрацюванні `overdue_repeat`: якщо `task.status not in ("done", "cancelled")` → шле нагадування:
  - делегована задача → і виконавцю, і Віталію;
  - власна задача → тільки Віталію.
- Завершення задачі (`done`) уже викликає `sched.cancel_task_jobs(task_id)`, який видаляє всі job'и з префіксом `task{id}-` (включно з `overdue_repeat`) — додаткового коду для зупинки повторів не потрібно.

## 3. Авто-реєстрація виконавця через інвайт-посилання

- Нова таблиця `invites(id, token TEXT UNIQUE, name TEXT, created_at TEXT, used_at TEXT NULL)`.
- `/add_executor <ім'я>` (без ID, одне чи кілька слів імені):
  - генерує токен (`secrets.token_urlsafe(6)`), зберігає інвайт, повертає Віталію посилання `https://t.me/<bot_username>?start=invite_<token>`.
- Виконавець відкриває посилання → Telegram шле `/start invite_<token>`.
- `cmd_start`: якщо `ctx.args` містить payload, що починається з `invite_` →
  - знайти інвайт за токеном; якщо не знайдено або `used_at` вже стоїть — звичайна поведінка незареєстрованого користувача (показати його ID);
  - якщо знайдено й не використано → `db.add_executor(invite.name, user_id)`, позначити `used_at`, відповісти виконавцю підтвердженням і Віталію — повідомлення «✅ Виконавець {name} (id {uid}) зареєстрований за посиланням».
- Старий ручний спосіб `/add_executor <telegram_id> <ім'я>` залишається як fallback: розпізнається тим, що перший аргумент — число (як і зараз у `cmd_add_executor`); якщо перший аргумент не число — трактується як режим генерації інвайта (ім'я = всі аргументи разом).
- Токен без явного TTL (YAGNI) — одноразовий (`used_at`), не protected секрет (random 8-symbol url-safe токен достатньо для цього use-case, не security-critical).

## Технічні зміни (файли)

- `app/db.py`: таблиця `invites` у `SCHEMA`; методи `create_invite(token, name)`, `get_invite_by_token(token)`, `mark_invite_used(token)`.
- `app/scheduler.py`: новий метод `schedule_interval(task_id, kind, start, hours)` (IntervalTrigger), id `f"task{task_id}-{kind}"` — підхоплюється існуючим `list_jobs_for_task`/`cancel_task_jobs` (вони матчать за префіксом `task{id}-`).
- `app/config.py`: `NOT_STARTED_REMINDER_MINUTES` (дефолт 30), `OVERDUE_REPEAT_HOURS` (дефолт 1).
- `app/bot.py`:
  - `_finalize`: планування `not_started` (завжди, +30 хв); якщо є дедлайн — додатково `schedule_interval(..., "overdue_repeat", start=deadline, hours=...)`; додавання кнопки «Взяв в роботу» в обидва типи повідомлень про нову задачу.
  - `_fire_async`: нові гілки `kind == "not_started"` і `kind == "overdue_repeat"`.
  - `callback_handler`: новий case `started:{id}` → `update_status(in_progress)` + редагування клавіатури повідомлення.
  - `_done_kb` → узагальнити (наприклад `_task_kb(task_id, status, to_self)`), що повертає правильний набір кнопок залежно від поточного статусу.
  - `cmd_add_executor`: розгалуження manual-id / generate-invite режимів.
  - `cmd_start`: обробка `invite_<token>` payload.

## Тестування

- `tests/test_scheduler.py`: тест на `schedule_interval` + що `cancel_task_jobs` видаляє і його.
- `tests/test_status_scenarios.py` (або новий файл `tests/test_reminders.py`): сценарії — задача не взята в роботу за 30 хв (delegated/self), повторне нагадування після дедлайну (раз на годину, зупиняється на done).
- `tests/test_bot.py`: `cmd_add_executor` генерує інвайт-посилання; `cmd_start` з валідним/невалідним/уже використаним токеном реєструє виконавця.
- `tests/test_db.py`: CRUD для `invites`.

## Поза скоупом

- TTL/прострочення інвайт-токенів.
- Підтвердження виконавцем "Почав" окремим текстовим повідомленням (тільки кнопка/мовчазний статус-апдейт через `status_handler`, як і зараз).
