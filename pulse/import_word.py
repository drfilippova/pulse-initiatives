"""Разовый импорт Word-отчёта Центра «план / факт» (.docx).

Ожидаемая структура документа (как в отчёте Центра):
    1. Наука рядом                                  ← номер списка = инициатива
    КОЛИЧЕСТВО УЧАСТНИКОВ МЕРОПРИЯТИЙ …              ← строка ЗАГЛАВНЫМИ = показатель
    млн человек в период с 2022 по 2026 гг.          ← единица; «нарастающим итогом» = накопительный
    2022                                            ← год
    0,47 / 3,07                                     ← план / факт
    ???                                             ← данных нет
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import BinaryIO

import docx

from .catalog import find_initiative

YEAR_RE = re.compile(r"^(20[23]\d)$")
VALUE_RE = re.compile(r"^([\d\s .,]+)\s*/\s*([\d\s .,]+)$")
NUMBERED_RE = re.compile(r"^\d{1,2}[.)]\s+(.+)$")

UNIT_MAP = [
    ("млн", "млн чел."),
    ("тыс", "тыс. чел."),
    ("единиц", "ед."),
    ("ед.", "ед."),
]

PROPER_FIXES = {
    "российской федерации": "Российской Федерации",
    "десятилетия науки и технологий": "Десятилетия науки и технологий",
}


@dataclass
class ParsedValue:
    initiative_id: str
    initiative_title: str
    indicator: str
    unit: str
    is_cumulative: bool
    year: int
    plan: float
    fact: float


@dataclass
class WordParseResult:
    values: list[ParsedValue] = field(default_factory=list)
    unknown_initiatives: list[str] = field(default_factory=list)
    no_data: dict[str, str] = field(default_factory=dict)  # initiative_id → пояснение
    problems: list[str] = field(default_factory=list)

    @property
    def n_indicators(self) -> int:
        return len({(v.initiative_id, v.indicator) for v in self.values})

    @property
    def n_initiatives(self) -> int:
        return len({v.initiative_id for v in self.values})


def parse_number(text: str) -> float:
    """«11 300» → 11300.0, «0,47» → 0.47, «17» → 17.0."""
    clean = str(text).replace(" ", "").replace(" ", "").replace(",", ".").strip()
    if not clean or clean.count(".") > 1:
        raise ValueError(f"не число: {text!r}")
    return float(clean)


def sentence_case(text: str) -> str:
    low = re.sub(r"\s+", " ", text.strip()).lower()
    for k, v in PROPER_FIXES.items():
        low = low.replace(k, v)
    return low[:1].upper() + low[1:]


def detect_unit(line: str) -> tuple[str, bool]:
    low = line.lower()
    unit = "ед."
    for key, value in UNIT_MAP:
        if low.startswith(key):
            unit = value
            break
    return unit, "нарастающ" in low


def _is_indicator_line(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.8


def _is_numbered(paragraph) -> bool:
    ppr = paragraph._p.pPr
    return ppr is not None and ppr.numPr is not None


def parse_docx(source: str | bytes | BinaryIO) -> WordParseResult:
    if isinstance(source, (bytes, bytearray)):
        source = BytesIO(source)
    document = docx.Document(source)
    res = WordParseResult()
    ini = None
    ini_title = ""
    indicator = None
    unit, cumulative = "ед.", False
    year = None
    got_values_for_ini = False

    def close_initiative():
        if ini is not None and not got_values_for_ini and ini.id not in res.no_data:
            res.no_data[ini.id] = "В отчёте нет значений по этой инициативе"

    for p in document.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        m = NUMBERED_RE.match(text)
        if _is_numbered(p) or (m and not VALUE_RE.match(text)):
            title = m.group(1) if m else text
            close_initiative()
            found = find_initiative(title)
            if found is None:
                res.unknown_initiatives.append(title)
                ini = None
            else:
                ini, ini_title = found, title
            indicator, year, got_values_for_ini = None, None, False
            continue
        if ini is None:
            continue
        if "???" in text or text in {"?", "??", "—", "-"}:
            res.no_data[ini.id] = f"В отчёте вместо значений стоит «{text}» — данные не предоставлены"
            continue
        if _is_indicator_line(text):
            indicator = sentence_case(text)
            unit, cumulative, year = "ед.", False, None
            continue
        if indicator and "в период" in text.lower():
            unit, cumulative = detect_unit(text)
            continue
        ym = YEAR_RE.match(text)
        if ym:
            year = int(ym.group(1))
            continue
        vm = VALUE_RE.match(text)
        if vm and indicator and year:
            try:
                plan, fact = parse_number(vm.group(1)), parse_number(vm.group(2))
            except ValueError as exc:
                res.problems.append(f"{ini.short}, {indicator[:40]}…, {year}: {exc}")
                continue
            res.values.append(ParsedValue(ini.id, ini_title, indicator, unit, cumulative, year, plan, fact))
            got_values_for_ini = True
            res.no_data.pop(ini.id, None)
            year = None
            continue
        if vm and not year:
            res.problems.append(f"{ini.short}: значение «{text}» без года — пропущено")
    close_initiative()
    return res
