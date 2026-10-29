"""Расчёты: % выполнения, прогноз на конец года, статусы светофора, флаги качества данных.

Обозначения (как в документе проектирования):
    P — план на год, F — факт на дату, M — месяц, на который даны данные (закрытый год: M = 12),
    F_prev — факт прошлого года.
Прогноз:
    обычный показатель            Fc = F / M × 12
    показатель нарастающим итогом Fc = F_prev + (F − F_prev) / M × 12
    закрытый год (M = 12)         Fc = F
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

import pandas as pd

from .catalog import INITIATIVES

MIN_MONTHS_FOR_FORECAST = 3
JUMP_RATIO = 5.0  # флаг Q-4: факт вырос больше чем в 5 раз к прошлому году

STATUS_LABELS = {
    "crit": "Критично",
    "risk": "Риск",
    "ok": "В норме",
    "high": "План занижен",
    "nodata": "Нет данных",
    "na": "Прогноз н/п",
}
STATUS_ICONS = {"crit": "✕", "risk": "!", "ok": "✓", "high": "↑", "nodata": "—", "na": "…"}
STATUS_ORDER = ["crit", "risk", "ok", "high", "na", "nodata"]


@dataclass(frozen=True)
class Thresholds:
    crit: float = 80.0   # ниже — «критично»
    risk: float = 95.0   # ниже — «риск»
    high: float = 150.0  # от этого значения — «план занижен»

    def validate(self) -> str | None:
        """Возвращает текст ошибки или None, если пороги корректны."""
        if not (0 < self.crit < self.risk < self.high <= 1000):
            return "Пороги должны возрастать: 0 < «критично» < «риск» < «план занижен» ≤ 1000."
        return None

    @classmethod
    def from_settings(cls, s: dict) -> "Thresholds":
        return cls(float(s["thr_crit"]), float(s["thr_risk"]), float(s["thr_high"]))


def _num(x) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def pct(fact, plan) -> float | None:
    """% выполнения = F / P × 100. При пустом или нулевом плане — None («нет данных»)."""
    f, p = _num(fact), _num(plan)
    if f is None or p is None or p <= 0:
        return None
    return f / p * 100


def forecast(fact, month: int, is_cumulative: bool = False, prev_fact=None) -> float | None:
    """Прогноз на конец года линейной экстраполяцией."""
    f = _num(fact)
    if f is None:
        return None
    month = int(month)
    if month >= 12:
        return f
    if month < MIN_MONTHS_FOR_FORECAST:
        return None
    if is_cumulative:
        prev = _num(prev_fact) or 0.0
        return prev + (f - prev) / month * 12
    return f / month * 12


def status(fc_pct: float | None, thr: Thresholds) -> str:
    """Статус по прогнозу выполнения (% плана)."""
    if fc_pct is None:
        return "nodata"
    if fc_pct < thr.crit:
        return "crit"
    if fc_pct < thr.risk:
        return "risk"
    if fc_pct < thr.high:
        return "ok"
    return "high"


def indicator_rows(values: pd.DataFrame, year: int, thr: Thresholds, current_year: int) -> pd.DataFrame:
    """Расчёт по каждому показателю за выбранный год: %, прогноз, статус, флаги."""
    cols = [
        "initiative_id", "initiative", "indicator_id", "indicator", "unit", "is_cumulative", "year",
        "plan", "fact", "as_of_month", "pct", "fc", "fc_pct", "status", "flags", "confirmed",
    ]
    if values.empty:
        return pd.DataFrame(columns=cols)
    prev = values[values["year"] == year - 1].set_index("indicator_id")["fact"].to_dict()
    out = []
    for r in values[values["year"] == year].itertuples(index=False):
        month = int(r.as_of_month)
        closed = month >= 12
        p = pct(r.fact, r.plan)
        if not closed and (bool(r.is_irregular) or month < MIN_MONTHS_FOR_FORECAST):
            fc = None
            st = "na" if p is not None else "nodata"
        else:
            fc = forecast(r.fact, month, bool(r.is_cumulative), prev.get(r.indicator_id))
            fc_p = pct(fc, r.plan)
            st = status(fc_p, thr)
        fc_p = pct(fc, r.plan)
        out.append({
            "initiative_id": r.initiative_id, "initiative": r.initiative, "indicator_id": r.indicator_id,
            "indicator": r.indicator, "unit": r.unit, "is_cumulative": bool(r.is_cumulative), "year": year,
            "plan": _num(r.plan), "fact": _num(r.fact), "as_of_month": month, "pct": p, "fc": fc,
            "fc_pct": fc_p, "status": st,
            "flags": row_flags(r, prev.get(r.indicator_id), year, current_year),
            "confirmed": bool(r.confirmed),
        })
    return pd.DataFrame(out, columns=cols)


def row_flags(r, prev_fact, year: int, current_year: int) -> list[str]:
    """Флаги качества для одной записи (не меняют статус)."""
    flags = []
    f, p, prev = _num(r.fact), _num(r.plan), _num(prev_fact)
    if f is None or p is None:
        flags.append("Q-2")
    if year == current_year and f is not None and p is not None and f == p and not bool(r.confirmed):
        flags.append("Q-1")
    if f is not None and prev and prev > 0 and f / prev > JUMP_RATIO:
        flags.append("Q-4")
    if bool(r.is_cumulative) and f is not None and prev is not None and f < prev:
        flags.append("Q-5")
    return flags


@dataclass
class InitiativeSummary:
    id: str
    short: str
    name: str
    median_fc_pct: float | None
    median_pct: float | None
    status: str
    n_indicators: int
    has_crit: bool
    n_flags: int
    note: str | None


def initiative_summaries(
    rows: pd.DataFrame, thr: Thresholds, initiatives: pd.DataFrame | None = None
) -> list[InitiativeSummary]:
    """Статус инициативы — по медиане прогноза её показателей. Без данных — «нет данных»."""
    notes = {}
    names = {i.id: (i.short, i.name) for i in INITIATIVES}
    order = [i.id for i in INITIATIVES]
    if initiatives is not None and not initiatives.empty:
        notes = dict(zip(initiatives["id"], initiatives["note"]))
        names = {r.id: (r.short_name, r.name) for r in initiatives.itertuples()}
        order = list(initiatives["id"])
    out = []
    for ini_id in order:
        sub = rows[rows["initiative_id"] == ini_id] if not rows.empty else rows
        fcs = [v for v in sub["fc_pct"].tolist() if v is not None and not pd.isna(v)] if len(sub) else []
        pcs = [v for v in sub["pct"].tolist() if v is not None and not pd.isna(v)] if len(sub) else []
        m_fc = median(fcs) if fcs else None
        if len(sub) == 0:
            st = "nodata"
        elif m_fc is None:
            st = "na" if pcs else "nodata"
        else:
            st = status(m_fc, thr)
        short, name = names.get(ini_id, (ini_id, ini_id))
        out.append(InitiativeSummary(
            id=ini_id, short=short, name=name, median_fc_pct=m_fc, median_pct=median(pcs) if pcs else None,
            status=st, n_indicators=len(sub), has_crit=bool(len(sub) and (sub["status"] == "crit").any()),
            n_flags=int(sum("Q-1" in f for f in sub["flags"])) if len(sub) else 0,
            note=notes.get(ini_id),
        ))
    return out


@dataclass
class YearSummary:
    year: int
    rows: pd.DataFrame
    initiatives: list[InitiativeSummary]
    counts: dict[str, int]
    lagging: int
    with_data: int
    q1_flags: int
    median_pct: float | None
    median_fc_pct: float | None
    is_current: bool
    as_of_month: int | None


def year_summary(
    values: pd.DataFrame, year: int, thr: Thresholds, current_year: int, initiatives: pd.DataFrame | None = None
) -> YearSummary:
    rows = indicator_rows(values, year, thr, current_year)
    inis = initiative_summaries(rows, thr, initiatives)
    counts = {k: 0 for k in STATUS_ORDER}
    for s in rows["status"]:
        counts[s] += 1
    pcs = [v for v in rows["pct"] if v is not None and not pd.isna(v)]
    fcs = [v for v in rows["fc_pct"] if v is not None and not pd.isna(v)]
    months = rows["as_of_month"].tolist()
    return YearSummary(
        year=year, rows=rows, initiatives=inis, counts=counts,
        lagging=sum(i.status in ("crit", "risk") for i in inis),
        with_data=sum(i.n_indicators > 0 for i in inis),
        q1_flags=int(sum("Q-1" in f for f in rows["flags"])),
        median_pct=median(pcs) if pcs else None, median_fc_pct=median(fcs) if fcs else None,
        is_current=year == current_year, as_of_month=min(months) if months else None,
    )


def conclusion(s: YearSummary, thr: Thresholds) -> str:
    """Вывод одной фразой для руководства."""
    if s.rows.empty:
        return f"{s.year}: данных за этот год нет."
    parts = []
    if s.lagging == 0:
        parts.append("Отставаний нет")
    else:
        parts.append(f"Отставание у {s.lagging} {plural(s.lagging, 'инициативы', 'инициатив', 'инициатив')}")
    h = s.counts["high"]
    if h:
        parts.append(
            f"у {h} {plural(h, 'показателя', 'показателей', 'показателей')} прогноз — "
            f"{thr.high:g} % плана и выше, планы стоит пересмотреть"
        )
    if s.is_current:
        q = s.q1_flags
        parts.append(f"{q} {plural(q, 'значение требует', 'значения требуют', 'значений требуют')} проверки"
                     if q else "значений для проверки нет")
    return "; ".join(parts) + "."


def quality_flags(
    values: pd.DataFrame, current_year: int, initiatives: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Все флаги качества по всем годам: Q-1…Q-5 плюс инициативы без данных."""
    out = []
    if not values.empty:
        prev_map = values.set_index(["indicator_id", "year"])["fact"].to_dict()
        for r in values.itertuples(index=False):
            flags = row_flags(r, prev_map.get((r.indicator_id, r.year - 1)), r.year, current_year)
            confirmed_eq = (r.year == current_year and r.confirmed and _num(r.fact) is not None
                            and _num(r.fact) == _num(r.plan))
            for code in flags:
                out.append(_flag_row(code, r, prev_map.get((r.indicator_id, r.year - 1))))
            if confirmed_eq:
                out.append(_flag_row("Q-1✓", r, None))
    have = set(values["initiative_id"]) if not values.empty else set()
    ini_iter = (
        initiatives.itertuples() if initiatives is not None and not initiatives.empty else
        [type("I", (), {"id": i.id, "short_name": i.short, "note": None})() for i in INITIATIVES]
    )
    for ini in ini_iter:
        if ini.id not in have:
            note = getattr(ini, "note", None)
            out.append({
                "code": "Q-2" if note else "Q-3", "initiative_id": ini.id, "initiative": ini.short_name,
                "indicator_id": None, "indicator": "—", "year": None, "plan": None, "fact": None,
                "detail": note or "Инициатива есть в справочнике, но в данных её нет",
            })
    cols = ["code", "initiative_id", "initiative", "indicator_id", "indicator", "year", "plan", "fact", "detail"]
    return pd.DataFrame(out, columns=cols)


FLAG_TITLES = {
    "Q-1": "Факт = план",
    "Q-1✓": "Факт = план, подтверждено",
    "Q-2": "Нет данных",
    "Q-3": "Нет в отчёте",
    "Q-4": "Резкий рост",
    "Q-5": "Нарастающий итог уменьшился",
}


def _flag_row(code: str, r, prev) -> dict:
    detail = {
        "Q-1": "В текущем году факт в точности равен плану — подтвердите у куратора",
        "Q-1✓": "Совпадение подтверждено: это реальные значения",
        "Q-2": "Нет значения плана или факта",
        "Q-4": f"Факт вырос больше чем в {JUMP_RATIO:g} раз к прошлому году ({fmt_num(prev)} → {fmt_num(r.fact)})",
        "Q-5": f"Показатель нарастающим итогом уменьшился ({fmt_num(prev)} → {fmt_num(r.fact)})",
    }[code]
    return {
        "code": code, "initiative_id": r.initiative_id, "initiative": r.initiative, "indicator_id": r.indicator_id,
        "indicator": r.indicator, "year": int(r.year), "plan": _num(r.plan), "fact": _num(r.fact), "detail": detail,
    }


# ---------- форматирование ----------

def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def fmt_num(v) -> str:
    v = _num(v)
    if v is None:
        return "—"
    a = abs(v)
    digits = 2 if a < 10 else 1 if a < 100 else 0
    s = f"{v:,.{digits}f}".replace(",", " ").replace(".", ",")
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def fmt_pct(v) -> str:
    v = _num(v)
    if v is None:
        return "—"
    return f"{round(v):,}".replace(",", " ") + " %"
