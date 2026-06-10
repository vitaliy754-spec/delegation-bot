import asyncio
import logging
import os
from openai import OpenAI
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler,
    CommandHandler, filters,
)

from app import config, bot
from app.db import Db
from app.scheduler import Scheduler
from app.health import make_app

logging.basicConfig(level=logging.INFO,
                   format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("main")

async def run():
    # init singletons
    bot.oai = OpenAI(api_key=config.OPENAI_API_KEY)
    bot.db = Db(config.DB_PATH)
    bot.db.init_schema()
    # back-compat: seed the single env executor into the registry, if provided
    if config.ASSISTANT_USER_ID:
        bot.db.add_executor("Исполнитель", config.ASSISTANT_USER_ID)
    if config.GCAL_ENABLED:
        from app.gcal import GCalClient
        bot.gcal = GCalClient(
            calendar_id=config.GOOGLE_CALENDAR_ID,
            token_path=config.GOOGLE_TOKEN_PATH,
            credentials_path=config.GOOGLE_CREDENTIALS_PATH,
        )
        log.info("Google Calendar enabled")
    else:
        from app.gcal import NullGCalClient
        bot.gcal = NullGCalClient()
        log.info("Google Calendar DISABLED (prototype mode) — events will be logged only")
    bot.sched = Scheduler(
        db_url=f"sqlite:///{config.DB_PATH}",
        tz=config.TZ,
    )
    bot.sched.set_callback(bot.on_scheduler_fire)
    bot.sched.set_daily_callback(bot.on_daily_digest)
    bot.sched.start()
    bot.sched.schedule_daily(config.MORNING_DIGEST_HOUR)

    # telegram app
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    bot.tg_bot = app.bot

    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("tasks", bot.cmd_tasks))
    app.add_handler(CommandHandler("cancel", bot.cmd_cancel))
    app.add_handler(CommandHandler("add_executor", bot.cmd_add_executor))
    app.add_handler(CommandHandler("executors", bot.cmd_executors))
    # owner intake: voice or text from the owner
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.VOICE) & ~filters.COMMAND & filters.User(user_id=config.VITALY_USER_ID),
        bot.owner_handler))
    # executor status: voice or text from anyone else (registry checked in handler)
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.VOICE) & ~filters.COMMAND & ~filters.User(user_id=config.VITALY_USER_ID),
        bot.status_handler))
    app.add_handler(CallbackQueryHandler(bot.callback_handler))

    # healthcheck server
    health_app = make_app()
    runner = web.AppRunner(health_app)
    await runner.setup()
    # Railway assigns the public/healthcheck port via $PORT; fall back to 8080 locally.
    port = int(os.environ.get("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("healthcheck on :%s/health", port)

    # run telegram polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    log.info("bot started")

    # keep alive
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        bot.sched.shutdown()

if __name__ == "__main__":
    asyncio.run(run())
