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

# Pending TaskSpecs awaiting confirmation: {chat_id: TaskSpec}
PENDING: dict[int, dict] = {}

def _allowed(update: Update) -> bool:
    return update.effective_chat and update.effective_chat.id == config.ALLOWED_CHAT_ID

async def voice_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    if update.effective_user.id != config.VITALY_USER_ID:
        # only Victor sets tasks via voice; assistant voice goes to status_handler
        await status_handler(update, ctx)
        return

    file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        text = transcribe_voice(oai, tmp.name)

    spec = parse_task(oai, text, datetime.now(timezone.utc), config.TZ)
    PENDING[update.effective_chat.id] = spec.model_dump(mode="json")

    msg = format_confirmation(spec)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Создать", callback_data="confirm"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
    ]])
    await update.message.reply_text(msg, reply_markup=kb, parse_mode="HTML")

def format_confirmation(spec) -> str:
    lines = [f"<b>Задача:</b> {spec.title}", f"{spec.description}"]
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
        spec = TaskSpec.model_validate(data)
        await _finalize(chat_id, spec, q)

async def _finalize(chat_id: int, spec: TaskSpec, q):
    deadline = spec.deadline or (datetime.now(timezone.utc) + timedelta(days=1))
    event_id = gcal.create_event(
        title=spec.title,
        description=spec.description,
        start=deadline - timedelta(minutes=30),
        end=deadline,
    )
    task_id = db.create_task(
        chat_id=chat_id,
        assistant_user_id=config.ASSISTANT_USER_ID,
        title=spec.title,
        description=spec.description,
        deadline=spec.deadline,
        gcal_event_id=event_id,
    )
    # schedule reminders
    for r in spec.reminders:
        sched.schedule_reminder(task_id, r.when, "reminder")
    if spec.deadline:
        sched.schedule_reminder(task_id, spec.deadline, "deadline")

    await q.edit_message_text(
        f"✅ Создано (#{task_id}). @assistant — задача:\n\n"
        f"<b>{spec.title}</b>\n{spec.description}\n\n"
        f"Дедлайн: {spec.deadline.strftime('%Y-%m-%d %H:%M') if spec.deadline else 'не задан'}",
        parse_mode="HTML",
    )

# tg_bot set in main.py after Application built
tg_bot: Bot | None = None

def on_scheduler_fire(task_id: int, kind: str):
    """Called from APScheduler thread — schedule async send."""
    import asyncio
    asyncio.get_event_loop().create_task(_fire_async(task_id, kind))

async def _fire_async(task_id: int, kind: str):
    task = db.get_task(task_id)
    if not task or task["status"] in ("done", "cancelled"):
        return
    chat_id = task["chat_id"]
    if kind == "reminder":
        text = (f"⏰ @assistant напомнить по задаче #{task_id} "
                f"<b>{task['title']}</b>\nКак статус? (сделал / в работе / застрял)")
        await tg_bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
    elif kind == "deadline":
        if task["status"] != "done":
            db.update_status(task_id, "overdue")
            gcal.update_summary(task["gcal_event_id"], "⚠️ ")
            await tg_bot.send_message(
                chat_id,
                f"⚠️ Просрочка по задаче #{task_id} <b>{task['title']}</b>. "
                f"@vitaly — статус не подтверждён.",
                parse_mode=ParseMode.HTML)

async def status_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    user_id = update.effective_user.id
    if user_id != config.ASSISTANT_USER_ID:
        return  # only assistant statuses tracked here

    # Get text (transcribe if voice)
    if update.message.voice:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            text = transcribe_voice(oai, tmp.name)
    else:
        text = update.message.text or ""

    if not text.strip():
        return

    task = db.find_active_for_assistant(update.effective_chat.id, user_id)
    if not task:
        return  # no active task to bind status to

    res = classify_status(oai, text, task["title"])
    intent = res["intent"]
    note = res.get("note", "")

    if intent == "other":
        return

    db.update_status(task["id"], intent, note=note)
    gcal.append_to_description(
        task["gcal_event_id"],
        f"[{datetime.now(timezone.utc).isoformat()}] {intent}: {note}")

    if intent == "done":
        sched.cancel_task_jobs(task["id"])
        await update.message.reply_text(f"✅ Задача #{task['id']} закрыта.")
    elif intent == "blocked":
        await update.message.reply_text(
            f"⚠️ Задача #{task['id']} в блоке. @vitaly — нужно вмешательство.")
    else:
        await update.message.reply_text(f"📝 Статус #{task['id']}: {intent}")

async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    rows = db.list_active(update.effective_chat.id)
    if not rows:
        await update.message.reply_text("Нет активных задач.")
        return
    lines = []
    for t in rows:
        dl = t["deadline"][:16].replace("T"," ") if t["deadline"] else "—"
        lines.append(f"#{t['id']} [{t['status']}] {t['title']} → {dl}")
    await update.message.reply_text("\n".join(lines))

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update): return
    if update.effective_user.id != config.VITALY_USER_ID: return
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
