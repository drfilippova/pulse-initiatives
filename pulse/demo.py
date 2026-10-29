"""Синтетические демо-данные (выдуманные!) — чтобы показать все статусы светофора.

Реальный отчёт Центра почти целиком в статусе «план занижен», поэтому для демонстрации
отставаний, риска и флагов качества используется этот набор. Значения детерминированные.
"""

from __future__ import annotations

from .catalog import INITIATIVES

YEARS = [2022, 2023, 2024, 2025, 2026]

# Целевой прогноз выполнения 2026 года (% плана) по каждой инициативе: два показателя.
TARGETS_2026 = {
    "INI-01": (104, 112),   # в норме
    "INI-02": (86, 91),     # риск
    "INI-03": (171, 160),   # план занижен (нарастающий итог)
    "INI-04": (66, 74),     # критично
    "INI-05": (99, 128),    # в норме
    "INI-06": None,         # нет данных
    "INI-07": (93, 84),     # риск
    "INI-08": (118, 125),   # в норме
    "INI-09": (240, 190),   # план занижен
    "INI-10": (101, 200),   # второй показатель — факт = план (флаг Q-1)
    "INI-11": (77, 109),    # критично по первому показателю
    "INI-12": (135, 96),    # в норме
}
BASE_PLAN = {
    "INI-01": (900, 120), "INI-02": (40, 18), "INI-03": (10, 6), "INI-04": (20, 9),
    "INI-05": (35, 12), "INI-07": (15, 30), "INI-08": (5, 6), "INI-09": (14, 20),
    "INI-10": (25, 8), "INI-11": (12, 11), "INI-12": (10, 4),
}


def _indicators(ini_id: str) -> list[tuple[str, str, bool]]:
    if ini_id == "INI-03":
        return [("Количество площадок (демо)", "ед.", True), ("Количество городов с площадками (демо)", "ед.", True)]
    return [("Количество мероприятий (демо)", "ед.", False), ("Количество участников (демо)", "тыс. чел.", False)]


def demo_values(current_month: int = 6) -> tuple[list[dict], dict[str, str]]:
    """Возвращает (строки для загрузки, пояснения для инициатив без данных)."""
    rows: list[dict] = []
    notes: dict[str, str] = {}
    for i, ini in enumerate(INITIATIVES):
        if TARGETS_2026.get(ini.id) is None:
            notes[ini.id] = "Демо: куратор не предоставил данные"
            continue
        for j, (name, unit, cumulative) in enumerate(_indicators(ini.id)):
            base = BASE_PLAN[ini.id][j]
            prev_fact = 0.0
            for k, year in enumerate(YEARS):
                plan = round(base * (1.12 ** k), 1)
                if cumulative:
                    plan = round(base * (1 + 0.6 * k), 1)
                if year < 2026:
                    ratio = 1.0 + ((i * 7 + j * 3 + k * 5) % 9) * 0.06   # 100…148 % — закрытые годы
                    fact = round(plan * ratio, 1)
                    if ini.id == "INI-12" and j == 0 and year == 2025:
                        fact = round(prev_fact * 6.5, 1)                  # флаг Q-4: резкий рост
                    month = 12
                else:
                    target = TARGETS_2026[ini.id][j] / 100
                    year_end = plan * target
                    if cumulative:
                        fact = round(prev_fact + (year_end - prev_fact) * current_month / 12, 1)
                    else:
                        fact = round(year_end * current_month / 12, 1)
                    if ini.id == "INI-10" and j == 1:
                        fact = plan                                       # флаг Q-1: факт = план
                    month = current_month
                rows.append({
                    "initiative_id": ini.id, "indicator": name, "unit": unit, "is_cumulative": cumulative,
                    "year": year, "plan": plan, "fact": fact, "as_of_month": month,
                })
                prev_fact = fact
    return rows, notes
