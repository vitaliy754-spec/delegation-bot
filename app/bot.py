import json
import tempfile
from datetime import datetime, timezone, timedelta
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from app import config
from app.transcribe import transcribe_voice
from app.parser import parse_task
from app.intent import classify_status
from app.db import Db
from app.gcal import GCalClient
from app.scheduler import Scheduler
from app.schemas import TaskSpec
from app.timefmt import fmt_dt, KYIV_LABEL, KYIV
from app.digest import split_morning, split_evening

# Module-level singletons (init in main.py)
oai: OpenAI | None = None
db: Db | None = None
gcal: GCalClient | None = None
sched: Scheduler | None = None

# Pending tasks awaiting confirmation:
# {chat_id: {"spec": dict, "recipient_uid": int, "recipient_label": str}}
PENDING: dict[int, dict] = {}

def _is_vitaly(update: Update) -> bool:
    return bool(update.effective_user) and update.effective_user.id == config.VITALY_USER_ID

def _is_registered_executor(user_id: int | None) -> bool:
    return bool(user_id) and db.get_executor_by_user_id(user_id) is not None

def clean_command_args(args: list[str] | None) -> list[str]:
    """Tolerate placeholder angle brackets typed by mistake, e.g.
    '/add_executor <1680472982> <Вадім>' → ['1680472982', 'Вадім']."""
    return [a for a in ((x or "").strip().strip("<>").strip() for x in (args or [])) if a]

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id == config.VITALY_USER_ID:
        await update.message.reply_text(
            "Привіт! Надсилай задачу голосом або текстом — я створю її та поставлю.\n"
            "Виконавця вкажи в мові: «…відповідальний — Оля». Без виконавця — задача тобі.\n\n"
            "/tasks — активні задачі\n"
            "/executors — список виконавців\n"
            "/add_executor 1680472982 Вадім — додати виконавця (id та імʼя, без дужок)\n"
            "/cancel <id> — скасувати задачу\n"
            "/morning — показати ранковий список зараз\n"
            "/evening — показати вечірній список зараз"
        )
        return
    if _is_registered_executor(user_id):
        await update.message.reply_text(
            "Привіт! Сюди надходитимуть задачі. Відповідай мені (текстом або голосом), "
            "коли змінюється статус: «роблю», «готово», «застряг»."
        )
        return
    # unregistered → show id so the owner can register them
    await update.message.reply_text(
        f"Привіт! Твій ID: {user_id}\n"
        "Передай його постановнику задач — він додасть тебе як виконавця, "
        "і сюди почнуть надходити задачі."
    )

async def cmd_add_executor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    args = clean_command_args(ctx.args)
    if len(args) < 2 or not args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "Використовуй: /add_executor <telegram_id> <імʼя>\n"
            "Напр.: /add_executor 1680472982 Вадім  (без дужок < >)")
        return
    uid = int(args[0])
    name = " ".join(args[1:]).strip()
    db.add_executor(name, uid)
    await update.message.reply_text(f"✅ Виконавця {name} (id {uid}) додано.")

async def cmd_executors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    rows = db.list_executors()
    if not rows:
        await update.message.reply_text(
            "Виконавців поки немає.\nПопроси виконавця натиснути /start у бота, "
            "хай надішле свій ID — додай його: /add_executor <id> <імʼя>"
        )
        return
    lines = [f"• {r['name']} — id {r['telegram_user_id']}" for r in rows]
    await update.message.reply_text("Виконавці:\n" + "\n".join(lines))

async def _extract_text(update: Update) -> str:
    """Voice → transcript, else plain text."""
    if update.message.voice:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            return transcribe_voice(oai, tmp.name)
    return update.message.text or ""

async def owner_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Owner sets a task (voice or text). Parses, resolves assignee, asks to confirm."""
    if not _is_vitaly(update):
        return
    text = await _extract_text(update)
    if not text.strip():
        return

    known = [e["name"] for e in db.list_executors()]
    # Anchor relative times ("через 2 хвилини", "сьогодні о 18:00") to the owner's
    # local Kyiv wall-clock — the digits and the offset must match the declared
    # timezone, otherwise the model shifts everything by the Kyiv offset.
    spec = parse_task(oai, text, datetime.now(KYIV), config.TZ, known_executors=known)

    # resolve assignee → recipient (default: the owner = task for self)
    recipient_uid = config.VITALY_USER_ID
    recipient_label = "тобі"
    if spec.assignee:
        matches = db.get_executors_by_name(spec.assignee)
        if len(matches) == 1:
            recipient_uid = matches[0]["telegram_user_id"]
            recipient_label = matches[0]["name"]
        elif len(matches) > 1:
            recipient_uid = matches[0]["telegram_user_id"]
            recipient_label = f"{matches[0]['name']} (перший зі збігів)"
        else:
            recipient_label = f"«{spec.assignee}» не знайдено — поставлю тобі"

    PENDING[update.effective_chat.id] = {
        "spec": spec.model_dump(mode="json"),
        "recipient_uid": recipient_uid,
        "recipient_label": recipient_label,
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Створити", callback_data="confirm"),
        InlineKeyboardButton("❌ Скасувати", callback_data="cancel"),
    ]])
    await update.message.reply_text(
        format_confirmation(spec, recipient_label), reply_markup=kb, parse_mode="HTML")

def _task_kb(task_id: int, status: str) -> InlineKeyboardMarkup:
    """Inline keyboard for a task message. Shows 'Взяв в роботу' only while
    the task is still pending; 'Виконано' is always offered until closed."""
    buttons = []
    if status == "pending":
        buttons.append(InlineKeyboardButton("🟢 Взяв в роботу", callback_data=f"started:{task_id}"))
    buttons.append(InlineKeyboardButton("✅ Виконано", callback_data=f"done:{task_id}"))
    return InlineKeyboardMarkup([buttons])

def format_confirmation(spec, recipient_label: str = "тобі") -> str:
    lines = [f"<b>Задача:</b> {spec.title}", f"{spec.description}",
             f"<b>Виконавець:</b> {recipient_label}"]
    if spec.deadline:
        lines.append(f"<b>Дедлайн:</b> {fmt_dt(spec.deadline)}")
    else:
        lines.append("<b>Дедлайн:</b> не вказано")
    if spec.reminders:
        lines.append("<b>Нагадати:</b>")
        for r in spec.reminders:
            lines.append(f"  • {fmt_dt(r.when)}")
    if spec.deadline or spec.reminders:
        lines.append(f"\n🕒 Час вказано {KYIV_LABEL}")
    return "\n".join(lines)

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    if q.data and q.data.startswith("started:"):
        tid = int(q.data.split(":", 1)[1])
        task = db.get_task(tid)
        if not task or task["status"] in ("done", "cancelled"):
            await q.edit_message_text("Задачу вже закрито.")
            return
        db.update_status(tid, "in_progress")
        await q.edit_message_reply_markup(reply_markup=_task_kb(tid, "in_progress"))
        return
    if q.data and q.data.startswith("done:"):
        tid = int(q.data.split(":", 1)[1])
        task = db.get_task(tid)
        if not task or task["status"] in ("done", "cancelled"):
            await q.edit_message_text("Задачу вже закрито.")
            return
        db.update_status(tid, "done")
        sched.cancel_task_jobs(tid)
        if task.get("gcal_event_id"):
            gcal.update_summary(task["gcal_event_id"], "✅ ")
        await q.edit_message_text(
            f"✅ Задачу #{tid} «{task['title']}» виконано. Молодець!",
            parse_mode="HTML",
        )
        return
    if q.data == "cancel":
        PENDING.pop(chat_id, None)
        await q.edit_message_text("Скасовано.")
        return
    if q.data == "confirm":
        data = PENDING.pop(chat_id, None)
        if not data:
            await q.edit_message_text("Термін дії вичерпано. Продиктуй задачу заново.")
            return
        spec = TaskSpec.model_validate(data["spec"])
        await _finalize(chat_id, spec, data["recipient_uid"], data["recipient_label"], q)

async def _finalize(chat_id: int, spec: TaskSpec, recipient_uid: int, recipient_label: str, q):
    deadline = spec.deadline or (datetime.now(timezone.utc) + timedelta(days=1))
    event_id = gcal.create_event(
        title=spec.title,
        description=spec.description,
        start=deadline - timedelta(minutes=30),
        end=deadline,
    )
    task_id = db.create_task(
        chat_id=chat_id,
        assistant_user_id=recipient_uid,
        title=spec.title,
        description=spec.description,
        deadline=spec.deadline,
        gcal_event_id=event_id,
    )

    to_self = recipient_uid == config.VITALY_USER_ID
    now = datetime.now(timezone.utc)

    # nag if still not picked up within NOT_STARTED_REMINDER_MINUTES, regardless
    # of deadline/dictated reminders — this guards the "nobody started it" case
    sched.schedule_reminder(
        task_id,
        now + timedelta(minutes=config.NOT_STARTED_REMINDER_MINUTES),
        "not_started")

    # explicit reminders dictated in the voice/text, if any
    dictated = [r.when for r in spec.reminders]
    for when in dictated:
        if when > now:
            sched.schedule_reminder(task_id, when, "reminder")

    if spec.deadline:
        if to_self:
            # personal task: default offset reminders (2h/1h/15m) when none dictated
            if not dictated:
                for when in default_reminder_times(spec.deadline, to_self=True):
                    sched.schedule_reminder(task_id, when, "reminder")
        else:
            # delegated task: remind the executor at the midpoint, and ask status
            # when ~20% of the time is left
            mid, status = delegated_tracking_times(spec.deadline, now)
            if mid > now:
                sched.schedule_reminder(task_id, mid, "mid")
            if status > now:
                sched.schedule_reminder(task_id, status, "status_check")
        sched.schedule_reminder(task_id, spec.deadline, "deadline")
        sched.schedule_interval(task_id, "overdue_repeat", spec.deadline, config.OVERDUE_REPEAT_HOURS)
    elif not to_self and not dictated:
        # delegated task without a deadline: a single follow-up status request
        sched.schedule_reminder(
            task_id, now + timedelta(hours=config.FOLLOWUP_DELAY_HOURS), "status_check")

    deadline_str = fmt_dt(spec.deadline, fallback="не задано")
    deadline_suffix = f" ({KYIV_LABEL})" if spec.deadline else ""

    await q.edit_message_text(
        f"✅ Задачу #{task_id} створено.\n\n<b>{spec.title}</b>\n"
        f"Дедлайн: {deadline_str}{deadline_suffix}\n\n"
        + ("Це твоя задача." if to_self else f"Надіслано виконавцю: {recipient_label}."),
        parse_mode="HTML",
        reply_markup=_task_kb(task_id, "pending") if to_self else None,
    )

    if not to_self:
        try:
            await tg_bot.send_message(
                recipient_uid,
                f"📌 <b>Нова задача #{task_id}</b>\n\n"
                f"<b>{spec.title}</b>\n{spec.description}\n\n"
                f"⏰ Дедлайн: {deadline_str}{deadline_suffix}\n\n"
                f"Коли візьмеш у роботу / завершиш / застрягнеш — напиши мені сюди (текстом або голосом).",
                parse_mode="HTML",
                reply_markup=_task_kb(task_id, "pending"),
            )
        except Exception as e:
            await tg_bot.send_message(
                config.VITALY_USER_ID,
                f"⚠️ Не вдалося надіслати задачу виконавцю ({recipient_label}): {e}\n"
                f"Попроси його написати боту /start, щоб відкрити діалог.",
            )

def default_reminder_times(deadline: datetime, to_self: bool) -> list[datetime]:
    """Default reminders when none were dictated.

    For personal tasks: offsets before the deadline (2h/1h/15m) — like the
    calendar bot. For delegated tasks: a single follow-up after FOLLOWUP_DELAY_HOURS.
    Only future times are kept.
    """
    now = datetime.now(timezone.utc)
    if to_self:
        candidates = [deadline - timedelta(minutes=m) for m in (120, 60, 15)]
    else:
        candidates = [now + timedelta(hours=config.FOLLOWUP_DELAY_HOURS)]
    return [t for t in candidates if t > now]

def delegated_tracking_times(deadline: datetime, now: datetime | None = None):
    """For a delegated task, return (midpoint, status_check) times within the
    creation→deadline window:
    - midpoint     = now + 50% of the remaining time (remind the executor);
    - status_check = now + 80% of the remaining time (ask: in progress / done?).
    Times may land in the past for very short windows — the caller filters them.
    """
    now = now or datetime.now(timezone.utc)
    span = deadline - now
    return now + span / 2, now + span * 0.8

# tg_bot set in main.py after Application built
tg_bot: Bot | None = None

def on_scheduler_fire(task_id: int, kind: str):
    """Called from APScheduler — schedule async send on the running loop."""
    import asyncio
    asyncio.get_event_loop().create_task(_fire_async(task_id, kind))

async def _fire_async(task_id: int, kind: str):
    task = db.get_task(task_id)
    if not task or task["status"] in ("done", "cancelled"):
        return
    recipient = task["assistant_user_id"]
    to_self = recipient == config.VITALY_USER_ID
    if kind == "reminder":
        if to_self:
            text = (f"⏰ Нагадування: <b>{task['title']}</b>\n{task['description']}")
            await tg_bot.send_message(
                recipient, text, parse_mode=ParseMode.HTML,
                reply_markup=_task_kb(task_id, task["status"]))
        else:
            text = (f"⏰ Нагадай щодо задачі #{task_id} <b>{task['title']}</b>\n"
                    f"Який статус? (зробив / у роботі / застряг)")
            await tg_bot.send_message(recipient, text, parse_mode=ParseMode.HTML)
    elif kind == "not_started":
        if task["status"] != "pending":
            return
        if to_self:
            await tg_bot.send_message(
                recipient,
                f"⏰ Нагадування: ти ще не взяв задачу #{task_id} <b>{task['title']}</b> в роботу.",
                parse_mode=ParseMode.HTML,
                reply_markup=_task_kb(task_id, "pending"))
        else:
            await tg_bot.send_message(
                recipient,
                f"⏰ Нагадування: ти ще не взяв в роботу задачу #{task_id} <b>{task['title']}</b>.\n"
                f"Напиши мені (текстом або голосом), коли почнеш.",
                parse_mode=ParseMode.HTML)
    elif kind == "mid":
        if to_self:
            return
        dl = fmt_dt(task["deadline"], fallback="без дедлайну")
        await tg_bot.send_message(
            recipient,
            f"⏰ Нагадування по задачі #{task_id}: <b>{task['title']}</b>\n"
            f"Дедлайн: {dl} ({KYIV_LABEL}). Це приблизно середина терміну — як просувається?",
            parse_mode=ParseMode.HTML)
    elif kind == "status_check":
        if to_self:
            return
        dl = fmt_dt(task["deadline"], fallback="скоро")
        await tg_bot.send_message(
            recipient,
            f"⏳ До дедлайну задачі #{task_id} <b>{task['title']}</b> лишилось ~20% часу "
            f"(дедлайн {dl}, {KYIV_LABEL}).\n"
            f"Який статус — <b>виконується</b> чи <b>виконано</b>?",
            parse_mode=ParseMode.HTML)
    elif kind == "deadline":
        if task["status"] != "done":
            db.update_status(task_id, "overdue")
            if task.get("gcal_event_id"):
                gcal.update_summary(task["gcal_event_id"], "⚠️ ")
            await tg_bot.send_message(
                config.VITALY_USER_ID,
                f"⚠️ Прострочення задачі #{task_id} <b>{task['title']}</b>. "
                f"Виконавець не підтвердив виконання.",
                parse_mode=ParseMode.HTML,
            )
    elif kind == "overdue_repeat":
        if task["status"] in ("done", "cancelled"):
            return
        dl = fmt_dt(task["deadline"], fallback="—")
        text = (f"⚠️ Задача #{task_id} <b>{task['title']}</b> досі не виконана "
                f"(дедлайн {dl}, {KYIV_LABEL}).")
        await tg_bot.send_message(recipient, text, parse_mode=ParseMode.HTML)
        if not to_self:
            await tg_bot.send_message(config.VITALY_USER_ID, text, parse_mode=ParseMode.HTML)

def on_daily_digest(which: str = "morning"):
    """Called from APScheduler — schedule the morning/evening digest send."""
    import asyncio
    if which == "evening":
        asyncio.get_event_loop().create_task(_send_evening_digest())
    else:
        asyncio.get_event_loop().create_task(_send_morning_digest())

def _fmt_task_line(t) -> str:
    dl = fmt_dt(t["deadline"], fallback="—")
    return f"#{t['id']} [{t['status']}] {t['title']} → {dl}"

async def _send_morning_digest():
    today = datetime.now(KYIV).date()
    tasks = db.list_active_for_vitaly(config.VITALY_USER_ID)
    todays, overdue = split_morning(tasks, today)
    lines = [f"☀️ <b>Доброго ранку!</b> {today.strftime('%d.%m.%Y')}", ""]
    lines.append("📌 <b>Задачі на сьогодні:</b>")
    if todays:
        lines += [_fmt_task_line(t) for t in todays]
    else:
        lines.append("— на сьогодні задач немає")
    if overdue:
        lines.append("")
        lines.append("⚠️ <b>Невиконані (прострочені):</b>")
        lines += [_fmt_task_line(t) for t in overdue]
    lines.append(f"\n🕒 Час {KYIV_LABEL}")
    await tg_bot.send_message(
        config.VITALY_USER_ID, "\n".join(lines), parse_mode=ParseMode.HTML)

async def _send_evening_digest():
    today = datetime.now(KYIV).date()
    tomorrow = today + timedelta(days=1)
    tasks = db.list_all_for_owner(config.VITALY_USER_ID)
    done_today, tomorrow_tasks = split_evening(tasks, today, tomorrow)
    lines = [f"🌙 <b>Вечірній підсумок</b> {today.strftime('%d.%m.%Y')}", ""]
    lines.append("✅ <b>Виконано сьогодні:</b>")
    if done_today:
        lines += [f"#{t['id']} {t['title']}" for t in done_today]
    else:
        lines.append("— сьогодні нічого не закрито")
    lines.append("")
    lines.append(f"📋 <b>Задачі на завтра ({tomorrow.strftime('%d.%m.%Y')}):</b>")
    if tomorrow_tasks:
        lines += [_fmt_task_line(t) for t in tomorrow_tasks]
    else:
        lines.append("— на завтра задач немає")
    lines.append(f"\n🕒 Час {KYIV_LABEL}")
    await tg_bot.send_message(
        config.VITALY_USER_ID, "\n".join(lines), parse_mode=ParseMode.HTML)

async def status_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Status reply from a registered executor (text or voice)."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id == config.VITALY_USER_ID:
        return  # owner intake handled elsewhere
    if not _is_registered_executor(user_id):
        return  # unknown sender

    text = await _extract_text(update)
    if not text.strip():
        return

    task = db.find_active_for_assistant_any_chat(user_id)
    if not task:
        await update.message.reply_text(
            "У тебе немає активної задачі — нема що оновлювати.")
        return

    try:
        res = classify_status(oai, text, task["title"])
        intent = res["intent"]
        note = res.get("note", "")
    except Exception:
        await update.message.reply_text(
            "Не вдалося розпізнати статус, спробуй написати ще раз.")
        return

    if intent == "other":
        return

    db.update_status(task["id"], intent, note=note)
    if task.get("gcal_event_id"):
        try:
            gcal.append_to_description(
                task["gcal_event_id"],
                f"[{datetime.now(timezone.utc).isoformat()}] {intent}: {note}")
        except Exception:
            pass  # status is already saved in db; calendar mirror is best-effort

    # confirm to executor
    if intent == "done":
        sched.cancel_task_jobs(task["id"])
        await update.message.reply_text(f"✅ Задачу #{task['id']} закрито.")
    elif intent == "blocked":
        await update.message.reply_text("⚠️ Записав статус: застряг. Повідомив постановника.")
    else:
        await update.message.reply_text(f"📝 Записав статус: {intent}")

    # mirror to owner
    executor = db.get_executor_by_user_id(user_id)
    who = executor["name"] if executor else str(user_id)
    icon = {"done": "✅", "in_progress": "🟡", "blocked": "⚠️"}.get(intent, "📝")
    await tg_bot.send_message(
        config.VITALY_USER_ID,
        f"{icon} <b>#{task['id']} {task['title']}</b> ({who}): {intent}\n{note or ''}",
        parse_mode=ParseMode.HTML,
    )

async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    rows = db.list_active_for_vitaly(config.VITALY_USER_ID)
    if not rows:
        await update.message.reply_text("Активних задач немає.")
        return
    lines = []
    for t in rows:
        dl = fmt_dt(t["deadline"], fallback="—")
        lines.append(f"#{t['id']} [{t['status']}] {t['title']} → {dl}")
    lines.append(f"\n🕒 Час {KYIV_LABEL}")
    await update.message.reply_text("\n".join(lines))

async def cmd_morning(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    await _send_morning_digest()

async def cmd_evening(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    await _send_evening_digest()

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Використовуй: /cancel <id>")
        return
    tid = int(args[0])
    task = db.get_task(tid)
    if not task:
        await update.message.reply_text("Не знайдено.")
        return
    db.update_status(tid, "cancelled")
    sched.cancel_task_jobs(tid)
    await update.message.reply_text(f"❌ Задачу #{tid} скасовано.")
