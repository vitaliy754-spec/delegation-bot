import json
import tempfile
from datetime import datetime, timezone, timedelta
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

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
