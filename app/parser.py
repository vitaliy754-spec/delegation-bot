import json
from datetime import datetime
from app.schemas import TaskSpec

SYSTEM_PROMPT = """Ти — парсер голосових і текстових задач. З тексту витягни:
- title: коротка назва задачі (3-7 слів, без крапки), УКРАЇНСЬКОЮ мовою
- description: повний опис, що треба зробити, УКРАЇНСЬКОЮ мовою
- assignee: імʼя виконавця, якому доручають задачу (з фраз «відповідальний — Оля»,
  «доручи Петі», «скажи Маші зробити»). Якщо виконавця не названо або задача для себе
  («мені», «собі», «нагадай мені») — assignee=null. Поверни лише імʼя, без слова «відповідальний».
- deadline: ISO 8601 datetime з таймзоною, або null якщо не вказано
- reminders: список {when: ISO datetime, text: null} — час, коли нагадати
- expected_result: що буде підтвердженням виконання, якщо це названо у мові
  (напр. «результат — фото квитанції», «підтвердження — посилання»). Поверни короткий
  опис українською. Якщо про результат не сказано — expected_result=null

current_time подано ВЖЕ у таймзоні користувача (з її зміщенням, напр. +03:00).
Усі відносні фрази ("через 2 хвилини", "сьогодні о 20:00", "завтра") рахуй від
current_time. deadline і when ОБОВʼЯЗКОВО повертай у ТІЙ САМІЙ таймзоні, що й
current_time (з тим самим зміщенням).
"Сьогодні о 20:00" = сьогоднішня дата + 20:00 у таймзоні користувача.
"Завтра до 18:00" = deadline = завтра 18:00.
"До кінця дня" = 23:59 вказаного дня.
Якщо в тексті немає дедлайну — deadline=null.
Якщо немає явних нагадувань — reminders=[].
Якщо є список відомих виконавців — зістав імʼя з мови саме з ним.
title та description ЗАВЖДИ повертай українською, навіть якщо ввід іншою мовою.

Поверни ТІЛЬКИ JSON без markdown."""

def parse_task(client, transcript: str, now: datetime, tz: str,
               known_executors: list[str] | None = None) -> TaskSpec:
    user_msg = f"current_time={now.isoformat()}\ntimezone={tz}\ntranscript=\"{transcript}\""
    if known_executors:
        user_msg += f"\nknown_executors={known_executors}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    data = json.loads(resp.choices[0].message.content)
    return TaskSpec.model_validate(data)

DEADLINE_PROMPT = """Користувач уточнює дедлайн задачі. З тексту визнач дату й час.
current_time подано ВЖЕ у таймзоні користувача (зі зміщенням). Рахуй відносно нього
й повертай у ТІЙ САМІЙ таймзоні.
Поверни ТІЛЬКИ JSON: {"deadline": "ISO 8601 з таймзоною" або null}.
Якщо дати немає або сказано «без дедлайну»/«не треба» — deadline=null."""

def parse_deadline(client, text: str, now: datetime, tz: str) -> datetime | None:
    """Parse a free-form deadline answer ('завтра до 18:00') into a datetime."""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": DEADLINE_PROMPT},
            {"role": "user", "content": f"current_time={now.isoformat()}\ntimezone={tz}\ntext=\"{text}\""},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    dl = json.loads(resp.choices[0].message.content).get("deadline")
    return datetime.fromisoformat(dl) if dl else None
