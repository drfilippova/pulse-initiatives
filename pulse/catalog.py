"""Справочник 12 инициатив Десятилетия науки и технологий (перечень с сайта наука.рф).

Коды INI-01…INI-12 введены в проекте для удобства, это не официальные коды.
`aliases` — другие написания, которые встречаются в отчётах (нужны при импорте).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Initiative:
    id: str
    name: str
    short: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


INITIATIVES: list[Initiative] = [
    Initiative("INI-01", "Наука рядом", "Наука рядом"),
    Initiative("INI-02", "Научно-популярный туризм", "Научно-популярный туризм", ("Научный туризм",)),
    Initiative("INI-03", "Научные детские площадки", "Научные детские площадки", ("Детские площадки",)),
    Initiative("INI-04", "Наука как искусство", "Наука как искусство"),
    Initiative("INI-05", "Научное волонтёрство", "Научное волонтёрство"),
    Initiative("INI-06", "Наука побеждать", "Наука побеждать"),
    Initiative(
        "INI-07",
        "Тематические инициативы по приоритетам научно-технологического развития",
        "Тематические инициативы",
        ("Тематические инициативы по приоритетам НТР",),
    ),
    Initiative(
        "INI-08",
        "Конгресс молодых учёных и мероприятия-спутники Конгресса",
        "КМУ",
        ("КМУ", "Конгресс молодых учёных", "Конгресс молодых ученых и мероприятия-спутники"),
    ),
    Initiative("INI-09", "Третий семестр", "Третий семестр"),
    Initiative("INI-10", "Наука и бизнес", "Наука и бизнес"),
    Initiative(
        "INI-11", "Работа с опытом и проектирование будущего", "Работа с опытом", ("Работа с опытом",)
    ),
    Initiative(
        "INI-12",
        "Решения и сервисы для профессионального сообщества",
        "Решения и сервисы",
        ("Решения и сервисы",),
    ),
]

BY_ID: dict[str, Initiative] = {i.id: i for i in INITIATIVES}


def normalize(text: str) -> str:
    """Приводит название к виду для сравнения: нижний регистр, ё→е, без лишних знаков и пробелов."""
    text = str(text).lower().replace("ё", "е")
    text = re.sub(r"[«»\"'.,:;()\-–—]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_initiative(text: str) -> Initiative | None:
    """Ищет инициативу по названию, короткому названию, коду или одному из вариантов написания."""
    key = normalize(text)
    if not key:
        return None
    for ini in INITIATIVES:
        if key == normalize(ini.id):
            return ini
        names = [ini.name, ini.short, *ini.aliases]
        if any(key == normalize(n) for n in names):
            return ini
    # Длинное название в отчёте может начинаться с короткого (например, «Работа с опытом …»).
    for ini in INITIATIVES:
        names = [ini.name, ini.short, *ini.aliases]
        if any(key.startswith(normalize(n)) and len(normalize(n)) >= 8 for n in names):
            return ini
    return None
