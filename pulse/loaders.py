"""Сценарии загрузки данных в базу: Word-отчёт, Excel/CSV по шаблону, демо-набор."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import db
from .demo import demo_values
from .import_word import parse_docx
from .validation import ValidationResult

CENTER_REPORT = db.ROOT / "sample_data" / "otchet_plan_fakt_2022-2026.docx"
CONFIRM_NOTE = "Совпадение «факт = план» подтверждено куратором 29.10.2026"


@dataclass
class LoadReport:
    added: int = 0
    replaced: int = 0
    skipped: int = 0
    rejected: int = 0
    warned: int = 0
    indicators: int = 0
    initiatives: int = 0
    no_data: dict | None = None
    problems: list | None = None
    unknown: list | None = None


def load_word(
    data: bytes | str | Path,
    file_name: str,
    current_year: int,
    current_month: int,
    confirm_equal_current: bool = False,
    on_duplicate: str = "replace",
    path: Path | None = None,
) -> LoadReport:
    """Импорт Word-отчёта. Для текущего года факт считается «на месяц current_month»."""
    if isinstance(data, Path):
        data = str(data)
    parsed = parse_docx(data)
    rows = []
    with db.connect(path) as con:
        for v in parsed.values:
            ind_id = db.get_or_create_indicator(con, v.initiative_id, v.indicator, v.unit, v.is_cumulative)
            is_current = v.year == current_year
            equal = is_current and v.plan == v.fact
            rows.append({
                "indicator_id": ind_id, "year": v.year, "plan": v.plan, "fact": v.fact,
                "as_of_month": current_month if is_current else 12,
                "confirmed": int(bool(confirm_equal_current and equal)),
                "source": "word_import",
                "comment": CONFIRM_NOTE if (confirm_equal_current and equal) else None,
            })
        added, replaced, skipped = db.save_values(con, rows, on_duplicate)
        for ini_id, note in parsed.no_data.items():
            db.set_initiative_note(con, ini_id, note)
        db.log_upload(con, file_name, added + replaced, len(parsed.problems), 0, replaced)
    return LoadReport(
        added=added, replaced=replaced, skipped=skipped, rejected=len(parsed.problems),
        indicators=parsed.n_indicators, initiatives=parsed.n_initiatives,
        no_data=parsed.no_data, problems=parsed.problems, unknown=parsed.unknown_initiatives,
    )


def load_center_report(path: Path | None = None) -> LoadReport:
    """Загружает отчёт Центра из sample_data (данные открытые) вместо текущих данных."""
    s = db.get_settings(path)
    db.reset_all(path)
    rep = load_word(
        CENTER_REPORT, CENTER_REPORT.name, int(s["current_year"]), int(s["current_month"]),
        confirm_equal_current=True, path=path,
    )
    db.set_settings({"mode": "report"}, path)
    return rep


def load_demo(path: Path | None = None) -> LoadReport:
    """Заменяет данные синтетическим демо-набором."""
    s = db.get_settings(path)
    db.reset_all(path)
    rows, notes = demo_values(int(s["current_month"]))
    to_save = []
    with db.connect(path) as con:
        for r in rows:
            ind_id = db.get_or_create_indicator(con, r["initiative_id"], r["indicator"], r["unit"], r["is_cumulative"])
            to_save.append({
                "indicator_id": ind_id, "year": r["year"], "plan": r["plan"], "fact": r["fact"],
                "as_of_month": r["as_of_month"], "source": "demo",
            })
        added, replaced, skipped = db.save_values(con, to_save)
        for ini_id, note in notes.items():
            db.set_initiative_note(con, ini_id, note)
        db.log_upload(con, "демо-данные (синтетика)", added, 0, 0, 0)
    db.set_settings({"mode": "demo"}, path)
    return LoadReport(added=added, indicators=len({r["indicator"] + r["initiative_id"] for r in rows}))


def load_validated(
    result: ValidationResult, file_name: str, on_duplicate: str = "replace", path: Path | None = None
) -> LoadReport:
    """Записывает строки, прошедшие проверку. Всё в одной транзакции."""
    with db.connect(path) as con:
        added, replaced, skipped = db.save_values(con, result.rows, on_duplicate)
        db.log_upload(con, file_name, added + replaced, result.rejected, len(result.warnings), replaced)
    s = db.get_settings(path)
    if s.get("mode") == "empty":
        db.set_settings({"mode": "report"}, path)
    return LoadReport(added=added, replaced=replaced, skipped=skipped, rejected=result.rejected,
                      warned=len(result.warnings))
