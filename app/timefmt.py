"""Відображення часу в локальній (київській) таймзоні власника.

Усі дати в застосунку зберігаються/парсяться як timezone-aware (зазвичай зі
зміщенням Києва з парсера, або UTC для внутрішньо згенерованих часів). Для показу
ми завжди конвертуємо у Europe/Kyiv, щоб власник бачив київський час за стінним
годинником, і явно це підписуємо.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ_NAME = os.environ.get("TZ", "Europe/Kyiv")
KYIV = ZoneInfo(TZ_NAME)
KYIV_LABEL = "за київським часом"


def to_kyiv(dt: datetime | str | None) -> datetime | None:
    """Нормалізує datetime або ISO-рядок у київський aware-datetime."""
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KYIV)


def fmt_dt(dt: datetime | str | None, fallback: str = "не вказано") -> str:
    """Форматує datetime/ISO-рядок як 'ДД.ММ.РРРР ГГ:ХХ' у київському часі."""
    local = to_kyiv(dt)
    if local is None:
        return fallback
    return local.strftime("%d.%m.%Y %H:%M")
