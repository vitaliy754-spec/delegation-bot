from datetime import datetime
from pydantic import BaseModel, Field

class Reminder(BaseModel):
    when: datetime
    text: str | None = None

class TaskSpec(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str
    assignee: str | None = None  # имя исполнителя из речи; None = задача себе
    deadline: datetime | None = None
    reminders: list[Reminder] = []
