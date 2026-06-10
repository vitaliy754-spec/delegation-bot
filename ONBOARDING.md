# 🚀 Гайд для Виталия — от нуля до работающего бота на Railway

Этот документ написан так, как будто ты впервые сел за компьютер. Каждый шаг — команда + что должно произойти + куда смотреть если не получилось. Делай по порядку, не прыгай.

**Что в итоге будет:** Telegram-бот, которому ты шлёшь голосом задачи → он передаёт их сотруднику → напоминает в нужное время → собирает статус → ведёт записи в Google Calendar. Работает 24/7 на Railway (даже когда твой ноут выключен).

**Сколько времени:** ~1.5–2 часа в первый раз. Дальше изменения деплоятся за минуту.

> ⚡ **Проще всего — через ИИ.** Открой проект в Codex/Claude Code и скажи: «разверни бота по `AGENT_SETUP.md`» — он проведёт тебя по шагам сам. Этот документ — для ручного прохождения.
>
> 📅 **Google Calendar НЕ обязателен.** Бот полностью работает без него: задачи хранятся в базе и видны через `/tasks` и утреннюю сводку. Раздел 9 (Google Calendar) — **опциональный**, его можно пропустить. Включай, только если действительно хочешь дублировать задачи в Google-календарь.

---

## 📋 Оглавление

1. [Что нужно подготовить](#1-что-нужно-подготовить)
2. [Установка инструментов на компьютер](#2-установка-инструментов-на-компьютер)
3. [Получение проекта от Виктора](#3-получение-проекта-от-виктора)
4. [Создание Telegram-бота](#4-создание-telegram-бота)
5. [Получение OpenAI API key](#5-получение-openai-api-key)
6. [Узнать свой Telegram user ID + ID сотрудника](#6-узнать-свой-telegram-user-id--id-сотрудника)
7. [Заполнить файл .env](#7-заполнить-файл-env)
8. [Первый локальный запуск (без Google Calendar)](#8-первый-локальный-запуск-без-google-calendar)
9. [Подключение Google Calendar](#9-подключение-google-calendar)
10. [Залить проект на GitHub](#10-залить-проект-на-github)
11. [Деплой на Railway](#11-деплой-на-railway)
12. [Что делать если что-то сломалось](#12-что-делать-если-что-то-сломалось)

---

## 1. Что нужно подготовить

Тебе понадобятся аккаунты:

- ✅ **Telegram** — у тебя уже есть
- ✅ **Claude Code** — у тебя уже установлен
- ⬜ **GitHub** — бесплатно, [github.com/signup](https://github.com/signup)
- ⬜ **OpenAI** — платный, [platform.openai.com/signup](https://platform.openai.com/signup), нужно будет пополнить минимум $5
- ⬜ **Google аккаунт** — для календаря (можно тот что уже есть)
- ⬜ **Railway** — бесплатный план есть, [railway.app](https://railway.app) (логин через GitHub)

**Действие:** зарегистрируйся в GitHub, OpenAI и Railway сейчас. На Google и Telegram уже всё есть.

---

## 2. Установка инструментов на компьютер

Тебе нужны 3 программы:

### 2.1. Python 3.11 (язык на котором написан бот)

1. Зайди на [python.org/downloads](https://python.org/downloads)
2. Скачай Python 3.11 или новее (3.12, 3.13 ОК)
3. Запусти установщик
4. **ВАЖНО:** на первом экране поставь галочку **«Add Python to PATH»** (внизу окна). Без неё ничего не заработает.
5. Жми «Install Now», жди до конца

**Проверка:** открой PowerShell (нажми Win → набери `powershell` → Enter) и набери:
```powershell
python --version
```
Должно вывести `Python 3.11.x` (или новее). Если пишет «команда не найдена» — переустанови с галочкой PATH.

### 2.2. Git (для работы с GitHub)

1. Зайди на [git-scm.com/download/win](https://git-scm.com/download/win)
2. Скачай и установи. На всех экранах жми «Next» — настройки по умолчанию подходят.

**Проверка:**
```powershell
git --version
```
Должно вывести `git version 2.x.x`.

### 2.3. Node.js (нужен для Railway CLI)

1. Зайди на [nodejs.org](https://nodejs.org)
2. Скачай LTS-версию (зелёная кнопка слева)
3. Установи, везде «Next»

**Проверка:**
```powershell
node --version
npm --version
```
Должно вывести версии.

### 2.4. (Готово автоматически) Claude Code

У тебя уже стоит. Если нет — [claude.ai/code](https://claude.ai/code).

---

## 3. Получение проекта от Виктора

Виктор пришлёт тебе папку `delegation-bot` (через архив или GitHub-ссылку). У тебя должна получиться папка примерно по такому пути:

```
C:\AI-projects\delegation-bot\
```

Открой её — внутри должны быть папки `app/`, `tests/`, `scripts/`, и файлы `pyproject.toml`, `.env.example`, `README.md`, и этот гайд `ONBOARDING.md`.

### 3.1. Открыть проект в Claude Code

1. Запусти Claude Code
2. Жми «Open Folder» (или эквивалент)
3. Выбери `C:\AI-projects\delegation-bot`
4. Дальше Claude Code сможет помогать тебе с этим проектом голосом

### 3.2. Установить зависимости (библиотеки Python)

В Claude Code открой встроенный терминал (или открой обычный PowerShell и `cd` в папку проекта):

```powershell
cd C:\AI-projects\delegation-bot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Что это делает:
- `python -m venv .venv` — создаёт изолированное окружение для проекта (чтобы библиотеки не путались с системными)
- `.venv\Scripts\activate` — заходим в это окружение (увидишь `(.venv)` слева в командной строке)
- `pip install -e ".[dev]"` — ставит все библиотеки из `pyproject.toml` (telegram, openai, google, и т.д.)

**Проверка:** в конце должно быть `Successfully installed ...` со списком пакетов. Если красная ошибка — скопируй её и спроси Claude Code «помоги исправить».

---

## 4. Создание Telegram-бота

### 4.1. Создать бота

1. Открой Telegram, найди в поиске **@BotFather** (синяя галка верификации)
2. Нажми «Start»
3. Отправь команду `/newbot`
4. Введи имя бота (любое, например «Мой делегатор»)
5. Введи username бота — должен заканчиваться на `bot`, например `vitaly_delegator_bot`. Если занят — придумай другой.
6. BotFather пришлёт сообщение с **токеном** — длинная строка вида `<10 цифр>:<35 символов букв-цифр>` (через двоеточие, всего ~46 символов)
7. **Скопируй токен** в блокнот — он понадобится в шаге 7

### 4.2. Отключить privacy mode (важно для DM-режима, можно пропустить если только DM)

Не нужно для нашего случая (мы в DM). Пропускай.

---

## 5. Получение OpenAI API key

1. Зайди на [platform.openai.com](https://platform.openai.com)
2. Залогинься (или зарегистрируйся если ещё не сделал)
3. Слева в меню → **Billing** → **Add payment method** → привяжи карту
4. **Пополни баланс минимум $5** (расход на бота копеечный — Whisper $0.006/мин, GPT-4o-mini $0.15/1M токенов; $5 хватит надолго)
5. Слева в меню → **API keys** → **Create new secret key**
6. Дай ключу имя, например `delegation-bot`
7. Permissions: **All** (или Restricted с минимумом — но для простоты All)
8. Жми **Create**
9. **Скопируй ключ** (показывается ОДИН РАЗ, начинается с `sk-proj-...`) в блокнот

⚠️ Никому не показывай этот ключ. Если случайно опубликовал — заходи на ту же страницу и удаляй (Revoke), создавай новый.

---

## 6. Узнать свой Telegram user ID + ID сотрудника

### 6.1. Свой ID

1. В Telegram найди **@RawDataBot** или **@userinfobot**
2. Напиши ему `/start`
3. Бот пришлёт твой `Chat ID` — это число из 9–10 цифр. **Запиши его**.

### 6.2. ID сотрудника

Сотрудник делает то же самое (находит @userinfobot, шлёт `/start`, получает свой ID и присылает тебе).

Альтернатива: попроси сотрудника написать твоему боту любое сообщение (например `/start`). Потом открой в браузере:
```
https://api.telegram.org/bot<ТВОЙ_ТОКЕН>/getUpdates
```
(подставь свой токен). В ответе найди блок `"from":{"id": <число>, ...}` — это его ID.

---

## 7. Заполнить файл .env

В папке проекта найди файл **`.env.example`** — скопируй его и переименуй копию в **`.env`** (без `.example`).

Открой `.env` в любом редакторе (Notepad, VS Code, Claude Code) и заполни:

```
TELEGRAM_BOT_TOKEN=ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER
OPENAI_API_KEY=ВСТАВЬ_СЮДА_КЛЮЧ_OPENAI
VITALY_USER_ID=ТВОЙ_ID_ИЗ_ШАГА_6.1
ASSISTANT_USER_ID=ID_СОТРУДНИКА_ИЗ_ШАГА_6.2
DB_PATH=./data/bot.db
TZ=Europe/Kyiv

# Google Calendar пока пустой — заполним в шаге 9
GOOGLE_CALENDAR_ID=
GOOGLE_CREDENTIALS_PATH=
GOOGLE_TOKEN_PATH=
```

Сохрани.

⚠️ **Никогда не показывай содержимое `.env` никому и не заливай его на GitHub.** Файл `.gitignore` уже настроен, чтобы `.env` не попадал в коммиты — но всё равно проверяй.

---

## 8. Первый локальный запуск (без Google Calendar)

Сейчас попробуем что бот вообще оживает.

### 8.1. Запустить бота

В терминале (с активированным venv):
```powershell
python -m app.main
```

Должны появиться строки:
```
... main: Google Calendar DISABLED (prototype mode) — events will be logged only
... apscheduler.scheduler: Scheduler started
... main: healthcheck on :8080/health
... main: bot started
```

Если видишь это — бот живой. Не закрывай терминал, оставь его работать.

### 8.2. Тестировать в Telegram

1. Открой Telegram, найди своего бота (по username)
2. Нажми **Start**
3. Бот должен ответить «Привет! Шли голосом задачу...»
4. **Попроси сотрудника тоже найти бота и нажать Start.** Без этого бот не сможет ему писать.
5. Запиши себе **голосовое** примерно так: _«Сделай тестовый отчёт. Напомни через 2 минуты»_
6. Бот должен:
   - Прислать «Задача: Тестовый отчёт... Подтвердить? [✅/❌]»
   - При нажатии ✅ — задача создаётся, сотруднику в его DM прилетает «📌 Новая задача»
7. Через 2 минуты сотрудник получит «⏰ Напомнить по задаче ... Как статус?»
8. Сотрудник пишет «делаю» → ему ответ «Записал статус: in_progress», тебе в DM прилетает «🟡 in_progress»

**Если работает — поздравляю, прототип живой.** Закрой бота `Ctrl+C` в терминале, идём подключать Google Calendar.

**Если не работает** — пиши Виктору лог из терминала + что произошло.

---

## 8a. Несколько исполнителей

Бот умеет раздавать задачи нескольким исполнителям по имени. `ASSISTANT_USER_ID` в `.env` теперь **необязателен** — если задан, этот человек становится исполнителем «по умолчанию»; остальных добавляешь прямо в боте.

Как добавить исполнителя:

1. Попроси человека открыть твоего бота и нажать **`/start`** — бот пришлёт ему его **ID** (число).
2. Он присылает этот ID тебе.
3. Ты пишешь боту: **`/add_executor <его_ID> <имя>`** — например `/add_executor 123456789 Оля`.
4. Проверь список: **`/executors`**.

Теперь, когда ставишь задачу, называй исполнителя голосом: _«Сделать афишу к пятнице, ответственный — Оля»_ — задача уйдёт именно Оле. Если имя не назвать — задача останется на тебе (и напоминания придут тебе).

---

## 9. Подключение Google Calendar (опционально — можно пропустить)

> Этот раздел нужен, только если хочешь видеть задачи в Google Calendar. Для работы бота он НЕ требуется — без него задачи и так хранятся в базе и видны через `/tasks` и утреннюю сводку. Если не нужно — переходи к разделу 10.

### 9.1. Создать проект в Google Cloud

1. Зайди на [console.cloud.google.com](https://console.cloud.google.com)
2. Залогинься тем Google-аккаунтом, к чьему календарю хочешь подключиться
3. Сверху рядом с логотипом Google Cloud — выпадающий список проектов → **New Project**
4. Имя: `delegation-bot` → **Create**
5. Жди ~10 секунд, выбери созданный проект в выпадающем списке

### 9.2. Включить Google Calendar API

1. В строке поиска сверху набери **«Google Calendar API»** → жми по результату
2. Кнопка **Enable** → жди

### 9.3. Создать OAuth credentials

1. Слева в меню → **APIs & Services** → **OAuth consent screen**
2. User Type: **External** → Create
3. Заполни обязательные поля:
   - App name: `delegation-bot`
   - User support email: твой email
   - Developer contact: твой email
   - Остальное можно пропустить → **Save and Continue**
4. На шаге Scopes — пропускай (Save and Continue)
5. На шаге Test users → **Add Users** → введи свой Google email → Save and Continue
6. **Back to Dashboard**

7. Слева → **APIs & Services** → **Credentials**
8. **Create Credentials** → **OAuth client ID**
9. Application type: **Desktop app**
10. Name: `delegation-bot-desktop` → **Create**
11. Появится окно с Client ID и Client secret → жми **Download JSON** (иконка справа)
12. Скачается файл вида `client_secret_xxx.json`
13. **Положи его в `C:\AI-projects\delegation-bot\data\credentials.json`** (создай папку `data` если нет, переименуй файл в `credentials.json`)

### 9.4. Получить token.json (один раз через браузер)

В терминале (с venv):
```powershell
python scripts/gcal_oauth.py
```

Откроется браузер → выбери свой Google аккаунт → разрешения → жми «Allow».

Может появиться предупреждение «Google hasn't verified this app» → жми **Advanced** → **Go to delegation-bot (unsafe)** → Continue. Это нормально для своего приложения.

В терминале появится `Saved token to data/token.json`.

### 9.5. Создать общий календарь

1. Открой [calendar.google.com](https://calendar.google.com)
2. Слева внизу «Other calendars» → **+** → **Create new calendar**
3. Имя: `Делегированные задачи` → **Create calendar**
4. После создания → нажми на нём → **Settings and sharing**
5. Прокрути до **Integrate calendar** → скопируй **Calendar ID** (выглядит как `abc123...@group.calendar.google.com`)
6. (Опционально) Чтобы сотрудник тоже видел — в разделе **Share with specific people** добавь его email с правами «See all event details»

### 9.6. Дописать .env

Открой `.env` и заполни последние 3 строки:
```
GOOGLE_CALENDAR_ID=abc123...@group.calendar.google.com
GOOGLE_CREDENTIALS_PATH=./data/credentials.json
GOOGLE_TOKEN_PATH=./data/token.json
```

### 9.7. Перезапустить бота

```powershell
python -m app.main
```

Должно появиться `Google Calendar enabled` (вместо DISABLED). Тестируй: создай задачу голосом → проверь что в календаре появилось событие на дедлайн.

---

## 10. Залить проект на GitHub

GitHub — это место где будет лежать код. Railway будет качать код оттуда автоматически.

### 10.1. Создать репозиторий

1. Зайди на [github.com](https://github.com), залогинься
2. Справа сверху **+** → **New repository**
3. Repository name: `delegation-bot`
4. **Private** (важно — там твои настройки)
5. **Create repository**
6. На следующей странице ничего не трогай, она сама подскажет команды

### 10.2. Привязать локальную папку к GitHub

В терминале:
```powershell
cd C:\AI-projects\delegation-bot
git remote add origin https://github.com/ТВОЙ_USERNAME/delegation-bot.git
git branch -M main
git push -u origin main
```

При первом push спросит логин/пароль:
- Username: твой GitHub username
- Password: **НЕ обычный пароль**, а **Personal Access Token**:
  1. На github.com → справа сверху твоя аватарка → **Settings**
  2. Слева внизу → **Developer settings**
  3. **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**
  4. Note: `delegation-bot-push`, expiration: 90 days
  5. Галочка **`repo`** (полный доступ к репозиториям)
  6. **Generate token** → скопируй и используй как пароль

⚠️ **Проверь что `.env` НЕ залился:** зайди на репозиторий на github.com, в списке файлов не должно быть `.env` (должен быть только `.env.example`). Если есть — это утечка ключей, удаляй репо и переделывай.

### 10.3. Дальнейшие изменения

Каждый раз когда меняешь код:
```powershell
git add .
git commit -m "что изменил"
git push
```

Railway сам подхватит и передеплоит (мы это настроим в шаге 11).

---

## 11. Деплой на Railway

Railway — сервис который запустит твоего бота на своих серверах 24/7. Бесплатно даёт $5 в месяц (хватит на маленького бота).

### 11.1. Регистрация и проект

1. Зайди на [railway.app](https://railway.app) → **Login with GitHub** → разреши доступ
2. На главной → **New Project** → **Deploy from GitHub repo**
3. Выбери `delegation-bot` (если не видишь — Railway попросит расширить доступ к репо, разреши)
4. Railway начнёт билд автоматически

### 11.2. Добавить переменные окружения

1. В проекте Railway → твой сервис (один прямоугольник) → клик
2. Вкладка **Variables**
3. Добавляй по одной (Add variable) — те же что в твоём локальном `.env`:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `VITALY_USER_ID`
   - `ASSISTANT_USER_ID`
   - `DB_PATH=/data/bot.db` ⚠️ обрати внимание — на Railway путь `/data/`, не `./data/`
   - `TZ=Europe/Kyiv`
   - `GOOGLE_CALENDAR_ID` (если уже подключал)
   - `GOOGLE_CREDENTIALS_PATH=/data/credentials.json`
   - `GOOGLE_TOKEN_PATH=/data/token.json`

### 11.3. Создать Volume (постоянное хранилище для базы и токена)

1. В проекте Railway → твой сервис → вкладка **Settings**
2. Прокрути до **Volumes** → **+ New Volume**
3. Mount path: `/data`
4. Size: 1 GB
5. **Add**

Volume сохраняет файлы между перезапусками контейнера. Без него SQLite база и Google token обнулятся каждый деплой.

### 11.4. Установить Railway CLI (чтобы залить файлы Google в volume)

В терминале:
```powershell
npm install -g @railway/cli
railway login
```

Откроется браузер → подтверди → возвращайся в терминал.

```powershell
cd C:\AI-projects\delegation-bot
railway link
```

Выбери свой проект из списка.

### 11.5. Залить credentials.json и token.json в volume

⚠️ Это самый муторный шаг. Railway не позволяет напрямую копировать файлы в volume. Самый простой способ:

**Способ A — через переменные окружения (proще):**

1. Открой `data/credentials.json` в блокноте, скопируй ВЕСЬ JSON в одну строку (можно через [jsonformatter.org](https://jsonformatter.org) → Compact)
2. В Railway Variables добавь `GOOGLE_CREDENTIALS_JSON=ВСТАВЬ_JSON`
3. То же для `data/token.json` → `GOOGLE_TOKEN_JSON=ВСТАВЬ_JSON`
4. Попроси Виктора (или Claude Code) добавить в `app/main.py` код, который при старте записывает эти переменные в `/data/credentials.json` и `/data/token.json` если их там нет.

**Способ B — через railway run (тоже рабочий):**

1. В корне проекта временно положи `data/credentials.json` и `data/token.json`
2. Залей в репо как часть коммита (НО ПОТОМ УДАЛИ!) → Railway скопирует
3. После первого деплоя удали из репо: `git rm data/credentials.json data/token.json && git commit -m "remove secrets" && git push`

Способ A надёжнее. Попроси Виктора прислать код для способа A когда будешь на этом шаге.

### 11.6. Перезапустить и проверить

1. В Railway → твой сервис → справа сверху **⋮** → **Restart**
2. Вкладка **Deployments** → последний деплой → **View logs**
3. Должны появиться те же строки что локально: `Google Calendar enabled`, `bot started`

### 11.7. Healthcheck (чтобы Railway не усыплял)

В Settings → **Healthcheck Path**: `/health` (если уже не стоит). Это говорит Railway что бот живой.

### 11.8. Дальше — автодеплой

Каждый `git push` будет автоматически передеплоивать бота на Railway. Никаких ручных действий.

---

## 12. Что делать если что-то сломалось

### Бот молчит на сообщения

1. Проверь что бот запущен (Railway Logs или локальный терминал)
2. Проверь что писал именно ему (а не другому боту)
3. Проверь что нажал `/start` хоть раз
4. Проверь `VITALY_USER_ID` в `.env` — точно твой ID? (через @userinfobot)

### Сотрудник не получает задачи

- Сотрудник нажимал `/start` у бота? Если нет — Telegram блокирует первое сообщение от бота.
- `ASSISTANT_USER_ID` в `.env` правильный?

### Напоминания не приходят

- Бот запущен 24/7? (если локально — комп должен быть включён)
- Время напоминания в правильной таймзоне? (`TZ=Europe/Kyiv`)
- Посмотри логи Railway — должна быть строчка о fire job

### Google Calendar события не создаются

- В логах есть `Google Calendar enabled` или `DISABLED`?
- Если DISABLED — пустой `GOOGLE_CALENDAR_ID` или `GOOGLE_TOKEN_PATH` в env
- Если Enabled но событий нет — проверь что `credentials.json` и `token.json` доехали до volume (логи будут писать про FileNotFoundError)

### Railway бот падает после старта

- Логи смотри через Deployments → View logs
- Чаще всего — забыл переменную в Variables. Сравни со своим `.env`.

### Куда писать если не разбираешься

Просто скинь Виктору:
1. Что хотел сделать
2. На каком шаге застрял
3. Скриншот ошибки или логов

Виктор → Claude Code → починим.

---

## 🎉 После всего этого

У тебя:
- ✅ Бот в Telegram, работает 24/7 на Railway
- ✅ Голос → задача → Google Calendar event
- ✅ Напоминания сотруднику в DM
- ✅ Статус-апдейты дублируются тебе
- ✅ `/tasks` показывает активные, `/cancel <id>` отменяет
- ✅ Каждый `git push` обновляет бота на проде

**Дальше — пользуйся. Если хочешь добавить фичу — попроси Claude Code в этом проекте: «добавь команду чтобы видеть задачи на завтра» — и он добавит, прогонит тесты, ты `git push`, и через минуту это уже на Railway.**

Удачи!
