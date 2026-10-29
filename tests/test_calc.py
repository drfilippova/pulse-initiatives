"""Тесты формул и статусов (T-01…T-09 из документа проектирования)."""

import pandas as pd
import pytest

from pulse.calc import (
    Thresholds, conclusion, fmt_num, fmt_pct, forecast, indicator_rows, initiative_summaries, pct, status,
    year_summary,
)

THR = Thresholds()


def values(rows):
    base = {"confirmed": 0, "source": "test", "comment": None, "loaded_at": "", "unit": "ед.",
            "is_cumulative": 0, "initiative_id": "INI-09", "initiative": "Третий семестр", "is_irregular": 0,
            "as_of_month": 12}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_t01_pct():
    assert pct(29, 20) == pytest.approx(145.0)


def test_t02_forecast_regular():
    fc = forecast(29, 9)
    assert fc == pytest.approx(38.67, abs=0.01)
    assert pct(fc, 20) == pytest.approx(193.3, abs=0.1)


def test_t03_forecast_cumulative():
    fc = forecast(95, 9, is_cumulative=True, prev_fact=78)
    assert fc == pytest.approx(100.67, abs=0.01)
    assert pct(fc, 50) == pytest.approx(201.3, abs=0.1)


def test_forecast_cumulative_half_year():
    # Детские площадки 2026 на 30.06: 78 + (95 − 78) / 6 × 12 = 112
    assert forecast(95, 6, True, 78) == pytest.approx(112.0)


def test_t04_closed_year():
    assert forecast(47, 12) == 47


@pytest.mark.parametrize("value,expected", [
    (79.9, "crit"), (80, "risk"), (94.9, "risk"), (95, "ok"), (149.9, "ok"), (150, "high"), (None, "nodata"),
])
def test_t05_status_borders(value, expected):
    assert status(value, THR) == expected


def test_t06_zero_plan():
    assert pct(10, 0) is None
    rows = indicator_rows(values([{"indicator_id": 1, "indicator": "x", "year": 2025, "plan": 0, "fact": 10}]),
                          2025, THR, 2026)
    assert rows.iloc[0]["status"] == "nodata"


def test_t07_too_early_for_forecast():
    assert forecast(10, 2) is None
    rows = indicator_rows(values([{"indicator_id": 1, "indicator": "x", "year": 2026, "plan": 20, "fact": 5,
                                   "as_of_month": 2}]), 2026, THR, 2026)
    assert rows.iloc[0]["status"] == "na"


def test_irregular_initiative_has_no_forecast():
    rows = indicator_rows(values([{"indicator_id": 1, "indicator": "x", "year": 2026, "plan": 4, "fact": 7,
                                   "as_of_month": 6, "is_irregular": 1}]), 2026, THR, 2026)
    assert rows.iloc[0]["status"] == "na"
    assert rows.iloc[0]["fc"] is None


def test_t08_median_status():
    rows = indicator_rows(values([
        {"indicator_id": 1, "indicator": "a", "year": 2025, "plan": 100, "fact": 100},
        {"indicator_id": 2, "indicator": "b", "year": 2025, "plan": 100, "fact": 120},
        {"indicator_id": 3, "indicator": "c", "year": 2025, "plan": 100, "fact": 1177},
    ]), 2025, THR, 2026)
    ini = [i for i in initiative_summaries(rows, THR) if i.id == "INI-09"][0]
    assert ini.median_fc_pct == pytest.approx(120)
    assert ini.status == "ok"


def test_t09_flag_fact_equals_plan():
    rows = indicator_rows(values([{"indicator_id": 1, "indicator": "x", "year": 2026, "plan": 60, "fact": 60,
                                   "as_of_month": 6}]), 2026, THR, 2026)
    assert "Q-1" in rows.iloc[0]["flags"]
    confirmed = values([{"indicator_id": 1, "indicator": "x", "year": 2026, "plan": 60, "fact": 60,
                         "as_of_month": 6, "confirmed": 1}])
    assert "Q-1" not in indicator_rows(confirmed, 2026, THR, 2026).iloc[0]["flags"]


def test_t11_flag_jump():
    v = values([
        {"indicator_id": 1, "indicator": "x", "year": 2025, "plan": 21, "fact": 42},
        {"indicator_id": 1, "indicator": "x", "year": 2026, "plan": 23, "fact": 150, "as_of_month": 6},
    ])
    assert "Q-4" not in indicator_rows(v, 2026, THR, 2026).iloc[0]["flags"]
    v.loc[v["year"] == 2026, "fact"] = 250
    assert "Q-4" in indicator_rows(v, 2026, THR, 2026).iloc[0]["flags"]


def test_thresholds_validation():
    assert Thresholds(80, 95, 150).validate() is None
    assert Thresholds(95, 80, 150).validate() is not None
    assert Thresholds(0, 95, 150).validate() is not None


def test_conclusion_text():
    v = values([{"indicator_id": 1, "indicator": "x", "year": 2026, "plan": 20, "fact": 29, "as_of_month": 6}])
    s = year_summary(v, 2026, THR, 2026)
    text = conclusion(s, THR)
    assert text.startswith("Отставаний нет")
    assert "у 1 показателя" in text


def test_formatting():
    assert fmt_num(11300) == "11 300"
    assert fmt_num(0.47) == "0,47"
    assert fmt_num(38.666) == "38,7"
    assert fmt_pct(193.33) == "193 %"
    assert fmt_pct(None) == "—"
