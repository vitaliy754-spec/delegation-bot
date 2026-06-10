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

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id == config.VITALY_USER_ID:
        await update.message.reply_text(
            "Привет! Шли задачу голосом или текстом — я создам её и поставлю.\n"
            "Укажи исполнителя в речи: «…ответственный — Оля». Без исполнителя — задача тебе.\n\n"
            "/tasks — активные задачи\n"
            "/executors — список исполнителей\n"
            "/add_executor <id> <имя> — добавить исполнителя\n"
            "/cancel <id> — отменить задачу"
        )
        return
    if _is_registered_executor(user_id):
        await update.message.reply_text(
            "Привет! Сюда будут приходить задачи. Отвечай мне (текстом или голосом), "
            "когда меняется статус: «делаю», «готово», «застрял»."
        )
        return
    # unregistered → show id so the owner can register them
    await update.message.reply_text(
        f"Привет! Твой ID: {user_id}\n"
        "Передай его постановщику задач — он добавит тебя как исполнителя, "
        "и сюда начнут приходить задачи."
    )

async def cmd_add_executor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    args = ctx.args or []
    if len(args) < 2 or not args[0].lstrip("-").isdigit():
        await update.message.reply_text("Используй: /add_executor <telegram_id> <имя>")
        return
    uid = int(args[0])
    name = " ".join(args[1:]).strip()
    db.add_executor(name, uid)
    await update.message.reply_text(f"✅ Исполнитель {name} (id {uid}) добавлен.")

async def cmd_executors(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    rows = db.list_executors()
    if not rows:
        await update.message.reply_text(
            "Исполнителей пока нет.\nПопроси исполнителя нажать /start у бота, "
            "пусть пришлёт свой ID — добавь его: /add_executor <id> <имя>"
        )
        return
    lines = [f"• {r['name']} — id {r['telegram_user_id']}" for r in rows]
    await update.message.reply_text("Исполнители:\n" + "\n".join(lines))

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
    spec = parse_task(oai, text, datetime.now(timezone.utc), config.TZ, known_executors=known)

    # resolve assignee → recipient (default: the owner = task for self)
    recipient_uid = config.VITALY_USER_ID
    recipient_label = "тебе"
    if spec.assignee:
        matches = db.get_executors_by_name(spec.assignee)
        if len(matches) == 1:
            recipient_uid = matches[0]["telegram_user_id"]
            recipient_label = matches[0]["name"]
        elif len(matches) > 1:
            recipient_uid = matches[0]["telegram_user_id"]
            recipient_label = f"{matches[0]['name']} (первый из совпавших)"
        else:
            recipient_label = f"«{spec.assignee}» не найден — поставлю тебе"

    PENDING[update.effective_chat.id] = {
        "spec": spec.model_dump(mode="json"),
        "recipient_uid": recipient_uid,
        "recipient_label": recipient_label,
    }

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Создать", callback_data="confirm"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
    ]])
    await update.message.reply_text(
        format_confirmation(spec, recipient_label), reply_markup=kb, parse_mode="HTML")

def format_confirmation(spec, recipient_label: str = "тебе") -> str:
    lines = [f"<b>Задача:</b> {spec.title}", f"{spec.description}",
             f"<b>Исполнитель:</b> {recipient_label}"]
    if spec.deadline:
        lines.append(f"<b>Дедлайн:</b> {spec.deadline.strftime('%Y-%m-%d %H:%M')}")
    else:
        lines.append("<b>Дедлайн:</b> не указан")
    if spec.reminders:
        lines.append("<b>Напомнить:</b>")
        for r in spec.reminders:
            lines.append(f"  • {r.when.strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    if q.data == "cancel":
        PENDING.pop(chat_id, None)
        await q.edit_message_text("Отменено.")
        return
    if q.data == "confirm":
        data = PENDING.pop(chat_id, None)
        if not data:
            await q.edit_message_text("Срок действия истёк. Продиктуй задачу заново.")
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

    # schedule reminders from voice; if none and there is a deadline, apply defaults
    reminder_times = [r.when for r in spec.reminders]
    if not reminder_times and spec.deadline:
        reminder_times = default_reminder_times(spec.deadline, to_self)
    for when in reminder_times:
        sched.schedule_reminder(task_id, when, "reminder")
    if spec.deadline:
        sched.schedule_reminder(task_id, spec.deadline, "deadline")

    deadline_str = spec.deadline.strftime('%Y-%m-%d %H:%M') if spec.deadline else 'не задан'

    await q.edit_message_text(
        f"✅ Задача #{task_id} создана.\n\n<b>{spec.title}</b>\nДедлайн: {deadline_str}\n\n"
        + ("Это твоя задача." if to_self else f"Отправлено исполнителю: {recipient_label}."),
        parse_mode="HTML",
    )

    if not to_self:
        try:
            await tg_bot.send_message(
                recipient_uid,
                f"📌 <b>Новая задача #{task_id}</b>\n\n"
                f"<b>{spec.title}</b>\n{spec.description}\n\n"
                f"⏰ Дедлайн: {deadline_str}\n\n"
                f"Когда возьмёшь в работу/закончишь/застрянешь — напиши мне сюда (текстом или голосом).",
                parse_mode="HTML",
            )
        except Exception as e:
            await tg_bot.send_message(
                config.VITALY_USER_ID,
                f"⚠️ Не получилось отправить задачу исполнителю ({recipient_label}): {e}\n"
                f"Попроси его написать боту /start, чтобы открыть диалог.",
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
            text = (f"⏰ Напоминание: <b>{task['title']}</b>\n{task['description']}")
        else:
            text = (f"⏰ Напомнить по задаче #{task_id} <b>{task['title']}</b>\n"
                    f"Как статус? (сделал / в работе / застрял)")
        await tg_bot.send_message(recipient, text, parse_mode=ParseMode.HTML)
    elif kind == "deadline":
        if task["status"] != "done":
            db.update_status(task_id, "overdue")
            if task.get("gcal_event_id"):
                gcal.update_summary(task["gcal_event_id"], "⚠️ ")
            await tg_bot.send_message(
                config.VITALY_USER_ID,
                f"⚠️ Просрочка по задаче #{task_id} <b>{task['title']}</b>. "
                f"Исполнитель не подтвердил выполнение.",
                parse_mode=ParseMode.HTML,
            )

def on_daily_digest():
    """Called from APScheduler — schedule the morning digest send."""
    import asyncio
    asyncio.get_event_loop().create_task(_send_morning_digest())

async def _send_morning_digest():
    rows = db.list_active_for_vitaly(config.VITALY_USER_ID)
    if not rows:
        await tg_bot.send_message(
            config.VITALY_USER_ID, "☀️ Доброе утро! Активных задач нет.")
        return
    lines = ["☀️ <b>Доброе утро! Твои активные задачи:</b>"]
    for t in rows:
        dl = t["deadline"][:16].replace("T", " ") if t["deadline"] else "—"
        lines.append(f"#{t['id']} [{t['status']}] {t['title']} → {dl}")
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
        return

    res = classify_status(oai, text, task["title"])
    intent = res["intent"]
    note = res.get("note", "")

    if intent == "other":
        return

    db.update_status(task["id"], intent, note=note)
    if task.get("gcal_event_id"):
        gcal.append_to_description(
            task["gcal_event_id"],
            f"[{datetime.now(timezone.utc).isoformat()}] {intent}: {note}")

    # confirm to executor
    if intent == "done":
        sched.cancel_task_jobs(task["id"])
        await update.message.reply_text(f"✅ Задача #{task['id']} закрыта.")
    elif intent == "blocked":
        await update.message.reply_text("⚠️ Записал статус: застрял. Сообщил постановщику.")
    else:
        await update.message.reply_text(f"📝 Записал статус: {intent}")

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
        await update.message.reply_text("Нет активных задач.")
        return
    lines = []
    for t in rows:
        dl = t["deadline"][:16].replace("T", " ") if t["deadline"] else "—"
        lines.append(f"#{t['id']} [{t['status']}] {t['title']} → {dl}")
    await update.message.reply_text("\n".join(lines))

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_vitaly(update):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Используй: /cancel <id>")
        return
    tid = int(args[0])
    task = db.get_task(tid)
    if not task:
        await update.message.reply_text("Не найдено.")
        return
    db.update_status(tid, "cancelled")
    sched.cancel_task_jobs(tid)
    await update.message.reply_text(f"❌ Задача #{tid} отменена.")
