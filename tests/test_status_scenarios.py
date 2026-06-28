"""Scenario-based probe of status_handler (executor -> status collection).
Not part of the permanent suite — ad-hoc check, run and report findings."""
import json
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone
import pytest

from app import bot


def make_update(user_id, text, voice=None):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.voice = voice
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 999
    return update


def make_ctx():
    return MagicMock()


def llm_response(intent, note=""):
    return MagicMock(
        choices=[MagicMock(message=MagicMock(
            content=json.dumps({"intent": intent, "note": note})))]
    )


@pytest.fixture(autouse=True)
def setup_module_state(monkeypatch):
    bot.config.VITALY_USER_ID = 1
    bot.db = MagicMock()
    bot.gcal = MagicMock()
    bot.sched = MagicMock()
    bot.oai = MagicMock()
    bot.tg_bot = MagicMock()
    bot.tg_bot.send_message = AsyncMock()
    yield


# Scenario 1: registered executor says "done" -> task closed, owner notified
@pytest.mark.asyncio
async def test_scenario_done():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 5, "title": "Лендинг", "gcal_event_id": "evt1"}
    bot.oai.chat.completions.create.return_value = llm_response("done", "готово")
    update = make_update(2, "Зробив, готово")
    await bot.status_handler(update, make_ctx())
    bot.db.update_status.assert_called_with(5, "done", note="готово")
    bot.sched.cancel_task_jobs.assert_called_with(5)
    update.message.reply_text.assert_called_once()
    bot.tg_bot.send_message.assert_called_once()
    print("Scenario 1 (done): OK")


# Scenario 2: registered executor says "in_progress"
@pytest.mark.asyncio
async def test_scenario_in_progress():
    bot.db.get_executor_by_user_id.return_value = {"name": "Петя", "telegram_user_id": 3}
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 6, "title": "Звіт", "gcal_event_id": None}
    bot.oai.chat.completions.create.return_value = llm_response("in_progress", "роблю")
    update = make_update(3, "Роблю, до вечора")
    await bot.status_handler(update, make_ctx())
    bot.db.update_status.assert_called_with(6, "in_progress", note="роблю")
    print("Scenario 2 (in_progress): OK")


# Scenario 3: registered executor says "blocked"
@pytest.mark.asyncio
async def test_scenario_blocked():
    bot.db.get_executor_by_user_id.return_value = {"name": "Вадім", "telegram_user_id": 4}
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 7, "title": "Афіша", "gcal_event_id": None}
    bot.oai.chat.completions.create.return_value = llm_response("blocked", "нема макета")
    update = make_update(4, "Застряг, немає макету")
    await bot.status_handler(update, make_ctx())
    bot.db.update_status.assert_called_with(7, "blocked", note="нема макета")
    print("Scenario 3 (blocked): OK")


# Scenario 4: message classified as "other" -> nothing happens
@pytest.mark.asyncio
async def test_scenario_other_ignored():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 5, "title": "Лендинг", "gcal_event_id": None}
    bot.oai.chat.completions.create.return_value = llm_response("other", "")
    update = make_update(2, "А скільки часу ще є?")
    await bot.status_handler(update, make_ctx())
    bot.db.update_status.assert_not_called()
    update.message.reply_text.assert_not_awaited()
    print("Scenario 4 (other -> ignored): OK")


# Scenario 5: unregistered/unknown sender -> ignored, no LLM call
@pytest.mark.asyncio
async def test_scenario_unknown_sender_ignored():
    bot.db.get_executor_by_user_id.return_value = None
    update = make_update(999, "Зробив")
    await bot.status_handler(update, make_ctx())
    bot.oai.chat.completions.create.assert_not_called()
    print("Scenario 5 (unknown sender -> ignored, no LLM call): OK")


# Scenario 6: owner's own message in executor flow -> ignored (handled elsewhere)
@pytest.mark.asyncio
async def test_scenario_owner_message_ignored_here():
    update = make_update(1, "Зробив")  # user_id == VITALY_USER_ID
    await bot.status_handler(update, make_ctx())
    bot.oai.chat.completions.create.assert_not_called()
    print("Scenario 6 (owner message -> ignored in this handler): OK")


# Scenario 7: registered executor but NO active task -> executor gets feedback (FIXED)
@pytest.mark.asyncio
async def test_scenario_no_active_task_feedback():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    bot.db.find_active_for_assistant_any_chat.return_value = None
    update = make_update(2, "Готово")
    await bot.status_handler(update, make_ctx())
    bot.oai.chat.completions.create.assert_not_called()
    update.message.reply_text.assert_awaited_once()
    print("Scenario 7 (no active task -> executor now gets feedback): FIXED")


# Scenario 8: executor has TWO active tasks, replies about the OLDER one ->
# bot always picks the most recently updated task (potential mis-attribution)
@pytest.mark.asyncio
async def test_scenario_multiple_active_tasks_picks_latest_only():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    # simulate DB behaviour: query always returns most recently updated task
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 11, "title": "Задача Б (новіша)", "gcal_event_id": None}
    bot.oai.chat.completions.create.return_value = llm_response("done", "перша готова")
    update = make_update(2, "Перша задача готова")  # talking about an OLDER task
    await bot.status_handler(update, make_ctx())
    args, kwargs = bot.db.update_status.call_args
    print(f"Scenario 8 (2+ active tasks, ambiguous reference): bot updated task "
          f"id={args[0]} ('Задача Б (новіша)') regardless of which task the "
          f"executor meant — LOGIC GAP: no disambiguation, always picks latest "
          f"updated task.")


# Scenario 9: LLM call raises an exception (network/timeout/bad response)
@pytest.mark.asyncio
async def test_scenario_llm_failure_unhandled():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 5, "title": "Лендинг", "gcal_event_id": None}
    bot.oai.chat.completions.create.side_effect = TimeoutError("OpenAI timeout")
    update = make_update(2, "Готово")
    try:
        await bot.status_handler(update, make_ctx())
        print("Scenario 9 (LLM failure): handled gracefully")
    except TimeoutError:
        print("Scenario 9 (LLM failure): UNHANDLED EXCEPTION propagates — "
              "no try/except around classify_status() — LOGIC GAP")


# Scenario 10: LLM returns malformed JSON
@pytest.mark.asyncio
async def test_scenario_llm_malformed_json():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 5, "title": "Лендинг", "gcal_event_id": None}
    bot.oai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="not valid json"))])
    update = make_update(2, "Готово")
    try:
        await bot.status_handler(update, make_ctx())
        print("Scenario 10 (malformed JSON): handled gracefully")
    except json.JSONDecodeError:
        print("Scenario 10 (malformed JSON): UNHANDLED JSONDecodeError — LOGIC GAP")


# Scenario 11: empty/whitespace-only message -> ignored early
@pytest.mark.asyncio
async def test_scenario_empty_message_ignored():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    update = make_update(2, "   ")
    await bot.status_handler(update, make_ctx())
    bot.oai.chat.completions.create.assert_not_called()
    print("Scenario 11 (empty message -> ignored): OK")


# Scenario 12: gcal.append_to_description fails (network/credentials issue)
@pytest.mark.asyncio
async def test_scenario_gcal_failure_unhandled():
    bot.db.get_executor_by_user_id.return_value = {"name": "Оля", "telegram_user_id": 2}
    bot.db.find_active_for_assistant_any_chat.return_value = {
        "id": 5, "title": "Лендинг", "gcal_event_id": "evt1"}
    bot.oai.chat.completions.create.return_value = llm_response("done", "готово")
    bot.gcal.append_to_description.side_effect = ConnectionError("Calendar API down")
    update = make_update(2, "Готово")
    try:
        await bot.status_handler(update, make_ctx())
        print("Scenario 12 (gcal failure): handled gracefully")
    except ConnectionError:
        print("Scenario 12 (gcal failure): UNHANDLED ConnectionError — task status "
              "stays unsaved in this code path (gcal called BEFORE db.update_status "
              "completes its visible effect to user) — LOGIC GAP")


def make_callback_update(user_id, data):
    update = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.data = data
    update.callback_query.message.chat_id = 999
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_started_callback_marks_in_progress():
    bot.db.get_task.return_value = {"id": 8, "title": "Афіша", "status": "pending"}
    update = make_callback_update(2, "started:8")
    await bot.callback_handler(update, make_ctx())
    bot.db.update_status.assert_called_with(8, "in_progress")
    update.callback_query.edit_message_reply_markup.assert_called_once()


@pytest.mark.asyncio
async def test_started_callback_on_closed_task_is_noop():
    bot.db.get_task.return_value = {"id": 9, "title": "Афіша", "status": "done"}
    update = make_callback_update(2, "started:9")
    await bot.callback_handler(update, make_ctx())
    bot.db.update_status.assert_not_called()
    update.callback_query.edit_message_text.assert_called_once_with("Задачу вже закрито.")
