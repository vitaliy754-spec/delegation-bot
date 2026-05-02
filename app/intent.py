import json

INTENT_PROMPT = """Классифицируй ответ исполнителя по задаче "{title}":
- done: завершено ("сделал", "готово", "закрыл")
- in_progress: в работе ("делаю", "к вечеру", "почти")
- blocked: затык ("застрял", "не могу", "нужна инфа")
- other: не статус (мелкий вопрос, болтовня)

Верни JSON: {{"intent": "...", "note": "краткая суть ответа"}}"""

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
