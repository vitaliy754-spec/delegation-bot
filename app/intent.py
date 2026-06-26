import json

INTENT_PROMPT = """Класифікуй відповідь виконавця щодо задачі "{title}":
- done: завершено ("зробив", "готово", "закрив")
- in_progress: у роботі ("роблю", "до вечора", "майже")
- blocked: затик ("застряг", "не можу", "потрібна інформація")
- other: не статус (дрібне питання, балачка)

Поверни JSON: {{"intent": "...", "note": "коротка суть відповіді українською"}}"""

def classify_status(client, message: str, task_title: str) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":INTENT_PROMPT.format(title=task_title)},
            {"role":"user","content":message},
        ],
        response_format={"type":"json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)
