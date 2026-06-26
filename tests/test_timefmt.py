from datetime import datetime, timezone
from app.timefmt import fmt_dt


def test_utc_converted_to_kyiv():
    # 15:00 UTC = 18:00 у Києві влітку (+03:00)
    dt = datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc)
    assert fmt_dt(dt) == "01.07.2026 18:00"


def test_iso_string_with_offset_preserved():
    # вже київський час зі зміщенням +03:00
    assert fmt_dt("2026-05-03T18:00:00+03:00") == "03.05.2026 18:00"


def test_naive_treated_as_utc():
    # naive-час трактуємо як UTC → 00:00 UTC = 03:00 Київ влітку
    dt = datetime(2026, 7, 1, 0, 0)
    assert fmt_dt(dt) == "01.07.2026 03:00"


def test_winter_offset():
    # взимку Київ +02:00: 15:00 UTC = 17:00
    dt = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)
    assert fmt_dt(dt) == "15.01.2026 17:00"


def test_none_fallback():
    assert fmt_dt(None) == "не вказано"
