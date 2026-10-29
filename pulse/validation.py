"""Проверка загружаемых строк по правилам V-01…V-10.

Ошибка — строка не загружается. Предупреждение — строка загружается, но аналитик видит замечание.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .catalog import find_initiative, normalize

REQUIRED = ["Инициатива", "Показатель", "Год", "План", "Факт", "Данные на месяц"]
OPTIONAL = ["Комментарий"]
YEAR_MIN, YEAR_MAX = 2022, 2031

RULES = {
    "V-01": "Есть все обязательные колонки",
    "V-02": "Обязательные поля заполнены",
    "V-03": "План, факт, год и месяц — числа",
    "V-04": "План и факт не отрицательные",
    "V-05": "Год 2022–2031, месяц 1–12",
    "V-06": "Инициатива есть в справочнике",
    "V-07": "Показатель есть у этой инициативы",
    "V-08": "Показатель за год не повторяется в файле",
    "V-09": "Запись уже есть в базе",
    "V-10": "Прошедший год — данные на месяц 12",
}


@dataclass
class Issue:
    level: str        # "error" | "warning"
    rule: str         # V-01…V-10
    row: int | None   # номер строки в файле (как в Excel, с учётом заголовка)
    column: str
    message: str
    fix: str


@dataclass
class ValidationResult:
    rows: list[dict] = field(default_factory=list)       # строки, готовые к записи
    issues: list[Issue] = field(default_factory=list)
    file_error: bool = False
    total: int = 0

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def rejected(self) -> int:
        return self.total - len(self.rows)

    def as_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"Уровень": "Ошибка" if i.level == "error" else "Предупреждение", "Правило": i.rule,
              "Строка": i.row, "Колонка": i.column, "Что не так": i.message, "Как исправить": i.fix}
             for i in self.issues],
            columns=["Уровень", "Правило", "Строка", "Колонка", "Что не так", "Как исправить"],
        )


def to_number(value) -> float | None:
    """Число из ячейки: допускаются пробелы-разделители тысяч и запятая. Пусто → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if pd.isna(value) else float(value)
    s = str(value).replace(" ", "").replace(" ", "").replace(",", ".").strip()
    if s == "" or s.lower() == "nan":
        return None
    return float(s)  # ValueError, если не число


def _empty(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def validate(
    df: pd.DataFrame,
    indicators: pd.DataFrame,
    existing: dict[tuple[int, int], str],
    current_year: int,
) -> ValidationResult:
    """indicators — справочник показателей (id, initiative_id, name); existing — ключи из базы."""
    res = ValidationResult(total=len(df))
    df = df.rename(columns=lambda c: str(c).strip())
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        res.file_error = True
        res.issues.append(Issue("error", "V-01", None, ", ".join(missing),
                                f"Нет обязательных колонок: {', '.join(missing)}",
                                "Скачайте шаблон и перенесите данные в него, не меняя названия колонок"))
        return res

    ind_lookup = {
        (r.initiative_id, normalize(r.name)): int(r.id) for r in indicators.itertuples()
    } if not indicators.empty else {}
    seen: dict[tuple[int, int], int] = {}
    candidates: list[tuple[int, dict]] = []
    bad_rows: set[int] = set()

    for idx, rec in enumerate(df.to_dict("records")):
        line = idx + 2  # строка 1 — заголовок
        errs_before = len(res.errors)

        def err(rule, col, msg, fix):
            res.issues.append(Issue("error", rule, line, col, msg, fix))

        for col in REQUIRED:
            if _empty(rec.get(col)):
                err("V-02", col, f"Пустое поле «{col}»", "Заполните поле или удалите строку")
        if len(res.errors) > errs_before:
            bad_rows.add(line)
            continue

        nums = {}
        for col in ["Год", "План", "Факт", "Данные на месяц"]:
            try:
                nums[col] = to_number(rec[col])
            except ValueError:
                err("V-03", col, f"«{rec[col]}» — не число", "Укажите число без текста и знаков, например 12500")
        if len(res.errors) > errs_before:
            bad_rows.add(line)
            continue

        year, month = nums["Год"], nums["Данные на месяц"]
        for col in ["План", "Факт"]:
            if nums[col] < 0:
                err("V-04", col, f"Отрицательное значение ({rec[col]})", "План и факт не могут быть меньше нуля")
        if year != int(year) or not YEAR_MIN <= year <= YEAR_MAX:
            err("V-05", "Год", f"Год {rec['Год']} вне периода Десятилетия", f"Укажите год от {YEAR_MIN} до {YEAR_MAX}")
        if month != int(month) or not 1 <= month <= 12:
            err("V-05", "Данные на месяц", f"Месяц {rec['Данные на месяц']} вне диапазона",
                "Укажите целое число от 1 до 12")

        ini = find_initiative(rec["Инициатива"])
        if ini is None:
            err("V-06", "Инициатива", f"Инициатива «{rec['Инициатива']}» не найдена",
                "Выберите название из выпадающего списка шаблона")
        ind_id = None
        if ini is not None:
            ind_id = ind_lookup.get((ini.id, normalize(rec["Показатель"])))
            if ind_id is None:
                err("V-07", "Показатель", f"У инициативы «{ini.short}» нет показателя «{rec['Показатель']}»",
                    "Выберите показатель из справочника этой инициативы или добавьте его в настройках")
        if len(res.errors) > errs_before:
            bad_rows.add(line)
            continue

        key = (ind_id, int(year))
        if key in seen:
            err("V-08", "Показатель", f"Повторяет строку {seen[key]} (тот же показатель и год)",
                "Оставьте одну строку на показатель за год")
            bad_rows.update({line, seen[key]})
            continue
        seen[key] = line

        if key in existing:
            res.issues.append(Issue("warning", "V-09", line, "Год",
                                    f"Запись уже загружена {existing[key]}",
                                    "Выберите ниже: заменить старые значения или пропустить"))
        if int(year) < current_year and int(month) != 12:
            res.issues.append(Issue("warning", "V-10", line, "Данные на месяц",
                                    f"{int(year)} год уже прошёл, а данные на месяц {int(month)}",
                                    "Для закрытого года обычно указывают 12"))
        candidates.append((line, {
            "indicator_id": ind_id, "year": int(year), "plan": nums["План"], "fact": nums["Факт"],
            "as_of_month": int(month), "source": "excel",
            "comment": None if _empty(rec.get("Комментарий")) else str(rec.get("Комментарий"))[:500],
        }))

    res.rows = [row for line, row in candidates if line not in bad_rows]
    return res
