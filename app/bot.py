import json
import tempfile
from datetime import datetime, timezone
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
