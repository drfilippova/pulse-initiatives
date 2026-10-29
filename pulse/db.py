"""Хранение данных в SQLite: справочники, значения план/факт, журнал загрузок, настройки.

Вся база — один файл `data/pulse.db` (путь можно поменять переменной окружения PULSE_DB).
Резервная копия — просто копия этого файла.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

from .catalog import INITIATIVES

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "pulse.db"

DEFAULT_SETTINGS = {
    "thr_crit": "80",       # критично, если прогноз < 80 % плана
    "thr_risk": "95",       # риск, если 80 ≤ прогноз < 95
    "thr_high": "150",      # «план занижен», если прогноз ≥ 150
    "current_year": "2026",
    "current_month": "6",   # данные текущего года — на 30.06 (допущение, см. README)
    "mode": "empty",        # empty | report | demo
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS initiatives (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    short_name   TEXT NOT NULL,
    is_irregular INTEGER NOT NULL DEFAULT 0,
    note         TEXT,
    sort_order   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS indicators (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    initiative_id TEXT NOT NULL REFERENCES initiatives(id),
    name          TEXT NOT NULL,
    unit          TEXT NOT NULL DEFAULT 'ед.',
    is_cumulative INTEGER NOT NULL DEFAULT 0,
    UNIQUE (initiative_id, name)
);
CREATE TABLE IF NOT EXISTS plan_fact (
    indicator_id INTEGER NOT NULL REFERENCES indicators(id) ON DELETE CASCADE,
    year         INTEGER NOT NULL CHECK (year BETWEEN 2022 AND 2031),
    plan         REAL CHECK (plan IS NULL OR plan >= 0),
    fact         REAL CHECK (fact IS NULL OR fact >= 0),
    as_of_month  INTEGER NOT NULL DEFAULT 12 CHECK (as_of_month BETWEEN 1 AND 12),
    confirmed    INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'excel',
    comment      TEXT,
    loaded_at    TEXT NOT NULL,
    PRIMARY KEY (indicator_id, year)
);
CREATE TABLE IF NOT EXISTS uploads (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name     TEXT NOT NULL,
    loaded_at     TEXT NOT NULL,
    rows_ok       INTEGER NOT NULL DEFAULT 0,
    rows_rejected INTEGER NOT NULL DEFAULT 0,
    rows_warned   INTEGER NOT NULL DEFAULT 0,
    rows_replaced INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.environ.get("PULSE_DB", DEFAULT_DB))


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Открывает базу; всё внутри блока — одна транзакция (либо всё, либо ничего)."""
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db(path: Path | None = None) -> None:
    """Создаёт таблицы, справочник инициатив и настройки по умолчанию (если их ещё нет)."""
    with connect(path) as con:
        con.executescript(SCHEMA)
        for order, ini in enumerate(INITIATIVES):
            con.execute(
                "INSERT OR IGNORE INTO initiatives (id, name, short_name, sort_order) VALUES (?, ?, ?, ?)",
                (ini.id, ini.name, ini.short, order),
            )
        for key, value in DEFAULT_SETTINGS.items():
            con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ---------- настройки ----------

def get_settings(path: Path | None = None) -> dict[str, str]:
    with connect(path) as con:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
    out = dict(DEFAULT_SETTINGS)
    out.update({r["key"]: r["value"] for r in rows})
    return out


def set_settings(values: dict[str, object], path: Path | None = None) -> None:
    with connect(path) as con:
        for key, value in values.items():
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )


# ---------- справочники ----------

def initiatives_frame(path: Path | None = None) -> pd.DataFrame:
    with connect(path) as con:
        rows = con.execute("SELECT * FROM initiatives ORDER BY sort_order").fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def indicators_frame(path: Path | None = None) -> pd.DataFrame:
    with connect(path) as con:
        rows = con.execute(
            "SELECT ind.*, ini.short_name AS initiative FROM indicators ind "
            "JOIN initiatives ini ON ini.id = ind.initiative_id ORDER BY ini.sort_order, ind.id"
        ).fetchall()
    cols = ["id", "initiative_id", "name", "unit", "is_cumulative", "initiative"]
    return pd.DataFrame([dict(r) for r in rows], columns=cols)


def get_or_create_indicator(
    con: sqlite3.Connection, initiative_id: str, name: str, unit: str = "ед.", is_cumulative: bool = False
) -> int:
    row = con.execute(
        "SELECT id FROM indicators WHERE initiative_id = ? AND name = ?", (initiative_id, name)
    ).fetchone()
    if row:
        return int(row["id"])
    cur = con.execute(
        "INSERT INTO indicators (initiative_id, name, unit, is_cumulative) VALUES (?, ?, ?, ?)",
        (initiative_id, name, unit, int(bool(is_cumulative))),
    )
    return int(cur.lastrowid)


def set_cumulative(indicator_id: int, value: bool, path: Path | None = None) -> None:
    with connect(path) as con:
        con.execute("UPDATE indicators SET is_cumulative = ? WHERE id = ?", (int(value), indicator_id))


def set_irregular(initiative_id: str, value: bool, path: Path | None = None) -> None:
    with connect(path) as con:
        con.execute("UPDATE initiatives SET is_irregular = ? WHERE id = ?", (int(value), initiative_id))


def set_initiative_note(con: sqlite3.Connection, initiative_id: str, note: str | None) -> None:
    con.execute("UPDATE initiatives SET note = ? WHERE id = ?", (note, initiative_id))


# ---------- значения ----------

def existing_keys(path: Path | None = None) -> dict[tuple[int, int], str]:
    """Какие пары (показатель, год) уже есть в базе и когда загружены."""
    with connect(path) as con:
        rows = con.execute("SELECT indicator_id, year, loaded_at FROM plan_fact").fetchall()
    return {(int(r["indicator_id"]), int(r["year"])): r["loaded_at"] for r in rows}


def save_values(
    con: sqlite3.Connection, rows: Iterable[dict], on_duplicate: str = "replace"
) -> tuple[int, int, int]:
    """Сохраняет строки plan_fact. Возвращает (добавлено, заменено, пропущено).

    on_duplicate: "replace" — перезаписать существующую запись, "skip" — оставить старую.
    """
    added = replaced = skipped = 0
    stamp = now()
    for r in rows:
        exists = con.execute(
            "SELECT 1 FROM plan_fact WHERE indicator_id = ? AND year = ?", (r["indicator_id"], r["year"])
        ).fetchone()
        if exists and on_duplicate == "skip":
            skipped += 1
            continue
        con.execute(
            "INSERT INTO plan_fact (indicator_id, year, plan, fact, as_of_month, confirmed, source, comment, loaded_at) "
            "VALUES (:indicator_id, :year, :plan, :fact, :as_of_month, :confirmed, :source, :comment, :loaded_at) "
            "ON CONFLICT(indicator_id, year) DO UPDATE SET plan = excluded.plan, fact = excluded.fact, "
            "as_of_month = excluded.as_of_month, confirmed = excluded.confirmed, source = excluded.source, "
            "comment = excluded.comment, loaded_at = excluded.loaded_at",
            {
                "as_of_month": 12,
                "confirmed": 0,
                "source": "excel",
                "comment": None,
                **r,
                "loaded_at": stamp,
            },
        )
        if exists:
            replaced += 1
        else:
            added += 1
    return added, replaced, skipped


def log_upload(con: sqlite3.Connection, file_name: str, ok: int, rejected: int, warned: int, replaced: int) -> None:
    con.execute(
        "INSERT INTO uploads (file_name, loaded_at, rows_ok, rows_rejected, rows_warned, rows_replaced) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (file_name, now(), ok, rejected, warned, replaced),
    )


def uploads_frame(path: Path | None = None) -> pd.DataFrame:
    with connect(path) as con:
        rows = con.execute("SELECT * FROM uploads ORDER BY id DESC").fetchall()
    cols = ["id", "file_name", "loaded_at", "rows_ok", "rows_rejected", "rows_warned", "rows_replaced"]
    return pd.DataFrame([dict(r) for r in rows], columns=cols)


def values_frame(path: Path | None = None) -> pd.DataFrame:
    """Все значения одной таблицей вместе со справочниками — основа для расчётов."""
    with connect(path) as con:
        rows = con.execute(
            "SELECT pf.indicator_id, pf.year, pf.plan, pf.fact, pf.as_of_month, pf.confirmed, pf.source, "
            "pf.comment, pf.loaded_at, ind.name AS indicator, ind.unit, ind.is_cumulative, "
            "ini.id AS initiative_id, ini.short_name AS initiative, ini.is_irregular "
            "FROM plan_fact pf JOIN indicators ind ON ind.id = pf.indicator_id "
            "JOIN initiatives ini ON ini.id = ind.initiative_id "
            "ORDER BY ini.sort_order, ind.id, pf.year"
        ).fetchall()
    cols = [
        "indicator_id", "year", "plan", "fact", "as_of_month", "confirmed", "source", "comment", "loaded_at",
        "indicator", "unit", "is_cumulative", "initiative_id", "initiative", "is_irregular",
    ]
    return pd.DataFrame([dict(r) for r in rows], columns=cols)


def confirm_value(indicator_id: int, year: int, path: Path | None = None) -> None:
    with connect(path) as con:
        con.execute(
            "UPDATE plan_fact SET confirmed = 1 WHERE indicator_id = ? AND year = ?", (indicator_id, year)
        )


def set_current_month(year: int, month: int, path: Path | None = None) -> None:
    """Меняет «данные на месяц» у всех записей текущего года и сохраняет его в настройках."""
    with connect(path) as con:
        con.execute("UPDATE plan_fact SET as_of_month = ? WHERE year = ?", (month, year))
    set_settings({"current_month": month, "current_year": year}, path)


def delete_values(initiative_id: str | None = None, year: int | None = None, path: Path | None = None) -> int:
    sql = "DELETE FROM plan_fact WHERE indicator_id IN (SELECT id FROM indicators WHERE (? IS NULL OR initiative_id = ?))"
    params: list = [initiative_id, initiative_id]
    if year is not None:
        sql += " AND year = ?"
        params.append(year)
    with connect(path) as con:
        cur = con.execute(sql, params)
        return cur.rowcount


def reset_all(path: Path | None = None) -> None:
    """Полностью очищает данные (справочник инициатив и настройки остаются)."""
    with connect(path) as con:
        con.execute("DELETE FROM plan_fact")
        con.execute("DELETE FROM indicators")
        con.execute("DELETE FROM uploads")
        con.execute("UPDATE initiatives SET note = NULL, is_irregular = 0")
