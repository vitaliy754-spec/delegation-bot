import json
from datetime import datetime
from app.schemas import TaskSpec

SYSTEM_PROMPT = """Ты парсер голосовых задач. Из транскрипта вытащи:
- title: короткое название задачи (3-7 слов, без точки)
- description: полное описание что нужно сделать
- deadline: ISO 8601 datetime с таймзоной, или null если не указан
- reminders: список {when: ISO datetime, text: null} — времена когда напомнить исполнителю

Все даты интерпретируй относительно current_time и пользовательской таймзоны.
"Сегодня в 20:00" = сегодняшняя дата + 20:00 в таймзоне пользователя.
"Завтра до 18:00" = deadline = завтра 18:00.
"К концу дня" = 23:59 указанного дня.
Если в речи нет дедлайна — deadline=null.
Если в речи нет явных напоминаний — reminders=[].

Верни ТОЛЬКО JSON без markdown."""

def parse_task(client, transcript: str, now: datetime, tz: str) -> TaskSpec:
    user_msg = f"current_time={now.isoformat()}\ntimezone={tz}\ntranscript=\"{transcript}\""
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
