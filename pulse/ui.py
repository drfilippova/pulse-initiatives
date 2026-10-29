"""Общие элементы интерфейса: стили, загрузка состояния, HTML-блоки в фирменном стиле.

HTML собирается строками и выводится через st.markdown(..., unsafe_allow_html=True).
Функции, которые возвращают строку, не вызывают Streamlit — их легко проверить отдельно.
"""

from __future__ import annotations

import base64
import html as _html
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import db
from .calc import (
    STATUS_ICONS, STATUS_LABELS, InitiativeSummary, Thresholds, YearSummary, conclusion, fmt_num, fmt_pct,
    plural, year_summary,
)
from .catalog import INITIATIVES

ASSETS = db.ROOT / "assets"
YEARS = list(range(2022, 2027))
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
              "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

PALETTE = {
    "blue": "#1E4FC2", "electric": "#2F6BFF", "sky": "#6495ED", "ice": "#BFD6FF", "navy": "#0B1E5B",
    "ink": "#0A1024", "ink2": "#4A5878", "ink3": "#7C8AA8", "grid": "rgba(30,79,194,0.10)",
}


def esc(text) -> str:
    return _html.escape(str(text), quote=True)


def compact(markup: str) -> str:
    """Убирает отступы и пустые строки: иначе Markdown примет HTML за блок кода."""
    return "".join(line.strip() for line in markup.splitlines() if line.strip())


@lru_cache(maxsize=8)
def asset_b64(name: str) -> str:
    return base64.b64encode((ASSETS / name).read_bytes()).decode()


def asset_uri(name: str) -> str:
    return f"data:image/png;base64,{asset_b64(name)}"


FONTS_URL = ("https://fonts.googleapis.com/css2?family=Unbounded:wght@500;600;700&"
             "family=Mulish:wght@400;600;700;800;900&display=swap")


def css() -> str:
    """Стили одной строкой, начиная с <style>.

    Markdown в Streamlit обрывает HTML-блок на пустой строке, и остаток CSS выводится как текст.
    Поэтому убираем комментарии и переводы строк, а шрифты подключаем через @import.
    """
    raw = (ASSETS / "style.css").read_text(encoding="utf-8")
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    one_line = " ".join(line.strip() for line in raw.splitlines() if line.strip())
    return f"<style>@import url('{FONTS_URL}'); {one_line}</style>"


def today_ru(d: date | None = None) -> tuple[str, str]:
    d = d or date.today()
    return f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year}", WEEKDAYS[d.weekday()]


def as_of_text(year: int, month: int) -> str:
    """«30.06.2026» — последний день месяца, на который даны данные."""
    last = (pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)).day
    return f"{last:02d}.{month:02d}.{year}"


# ---------- состояние ----------

@dataclass
class AppState:
    settings: dict
    thr: Thresholds
    current_year: int
    current_month: int
    values: pd.DataFrame
    initiatives: pd.DataFrame
    mode: str

    def summary(self, year: int) -> YearSummary:
        return year_summary(self.values, year, self.thr, self.current_year, self.initiatives)

    @property
    def years(self) -> list[int]:
        have = sorted(set(int(y) for y in self.values["year"])) if not self.values.empty else []
        return have or YEARS

    @property
    def as_of(self) -> str:
        return as_of_text(self.current_year, self.current_month)


def load_state() -> AppState:
    db.init_db()
    s = db.get_settings()
    return AppState(
        settings=s, thr=Thresholds.from_settings(s), current_year=int(s["current_year"]),
        current_month=int(s["current_month"]), values=db.values_frame(), initiatives=db.initiatives_frame(),
        mode=s.get("mode", "empty"),
    )


# ---------- HTML-блоки ----------

def chip(st: str) -> str:
    return f'<span class="chip s-{st}"><b>{STATUS_ICONS[st]}</b>{STATUS_LABELS[st]}</span>'


def mini(st: str) -> str:
    return f'<i class="mini s-{st}" title="{STATUS_LABELS[st]}">{STATUS_ICONS[st]}</i>'


def legend() -> str:
    return '<div class="legend-st">' + "".join(chip(s) for s in ["crit", "risk", "ok", "high", "nodata"]) + "</div>"


def spark(points: list[tuple[int, float | None]], selected: int, w: int, h: int, dark: bool) -> str:
    """Небольшой график-площадь: медиана % выполнения по годам."""
    vals = [v or 0 for _, v in points]
    if len(points) < 2 or max(vals) <= 0:
        return ""
    top = max(vals) * 1.15
    pad_x, pad_b, pad_t = (4, 4, 6) if dark else (14, 20, 34)
    x = lambda i: pad_x + i * (w - 2 * pad_x) / (len(points) - 1)  # noqa: E731
    y = lambda v: pad_t + (h - pad_t - pad_b) * (1 - (v or 0) / top)  # noqa: E731
    line = "".join(f"{'L' if i else 'M'}{x(i):.1f} {y(v):.1f}" for i, (_, v) in enumerate(points))
    area = f"{line}L{x(len(points) - 1):.1f} {h - pad_b}L{x(0):.1f} {h - pad_b}Z"
    color = "#FFFFFF" if dark else PALETTE["electric"]
    gid = "spd" if dark else "spl"
    out = [f'<svg class="spark" viewBox="0 0 {w} {h}" role="img" aria-label="Медиана % выполнения по годам">'
           f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" '
           f'stop-opacity=".45"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
           f'<path d="{area}" fill="url(#{gid})"/><path d="{line}" fill="none" stroke="{color}" stroke-width="2.2" '
           f'stroke-linejoin="round" stroke-linecap="round"/>']
    for i, (yr, v) in enumerate(points):
        if yr == selected:
            cx, cy = x(i), y(v)
            out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{cy:.1f}" y2="{h - pad_b}" stroke="{color}" '
                       f'stroke-opacity=".5" stroke-dasharray="3 3"/><circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" '
                       f'fill="{"#2F6BFF" if dark else "#fff"}" stroke="{color}" stroke-width="2.5"/>')
            if not dark:
                label = fmt_pct(v)
                bw = len(label) * 7.6 + 18
                bx = min(max(cx - bw / 2, 0), w - bw)
                by = max(cy - 32, 0)
                out.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="22" rx="11" fill="#0A0F1F"/>'
                           f'<text x="{bx + bw / 2:.1f}" y="{by + 15:.1f}" text-anchor="middle" font-size="12" '
                           f'font-weight="800" fill="#fff" font-family="Mulish,sans-serif">{label}</text>')
        if not dark:
            fill = PALETTE["blue"] if yr == selected else PALETTE["ink3"]
            out.append(f'<text x="{x(i):.1f}" y="{h - 4}" text-anchor="middle" font-size="11" font-weight="700" '
                       f'fill="{fill}" font-family="Mulish,sans-serif">{yr}</text>')
    out.append("</svg>")
    return "".join(out)


def sidebar_html(state: AppState) -> str:
    day, weekday = today_ru()
    mode = {"demo": "Демо-данные (синтетика)", "report": "Отчёт Центра план/факт", "empty": "Данных пока нет"}
    return compact(f"""
    <div class="today"><b>{day}</b><span>{weekday}</span></div>
    <div class="side-card">
      <b>Центр сопровождения инициатив</b>
      <span>Данные {state.current_year} года на {state.as_of}</span>
      <small>{mode.get(state.mode, state.mode)}</small>
    </div>""")


def topbar_html(title_a: str, title_b: str, subtitle: str) -> str:
    return compact(f"""<div class="topbar"><h1 class="greet">{esc(title_a)} <span>{esc(title_b)}</span></h1>
    <p class="muted">{subtitle}</p></div>""")


def demo_banner(state: AppState) -> str:
    if state.mode != "demo":
        return ""
    return ('<div class="demo-banner"><b>ДЕМО</b>Сейчас показаны синтетические данные. Реальный отчёт Центра '
            'загружается в «Настройках».</div>')


def hero_html(s: YearSummary, state: AppState) -> str:
    n = len(s.rows)
    total = len(INITIATIVES)
    leader = max((i for i in s.initiatives if i.median_fc_pct is not None), key=lambda i: i.median_fc_pct,
                 default=None)
    history = [(y, state.summary(y).median_pct) for y in state.years]
    fact_tag = f"факт на {state.as_of}" if s.is_current else "закрытый год"
    leader_card = (f'<div class="gcard g3"><span class="gdot">↑</span><span><span class="gk">Лидер</span><br>'
                   f'<b class="sm">{esc(leader.short)} · {fmt_pct(leader.median_fc_pct)}</b></span></div>'
                   if leader else "")
    check = s.q1_flags if s.is_current else "—"
    check_text = ("значения факт = план" if s.q1_flags else "всё подтверждено") if s.is_current else "только текущий год"
    return compact(f"""
    <div class="bal">
      <img class="bal-orbit" src="{asset_uri('logo_orbit_white.png')}" alt="">
      <div class="bal-l">
        <div class="bal-k">Медиана выполнения плана · {s.year}</div>
        <div class="bal-v">{fmt_pct(s.median_pct)}</div>
        <div class="bal-tags"><span class="gtag">{fact_tag}</span><span class="gtag o">прогноз {fmt_pct(s.median_fc_pct)}</span></div>
        <div class="bal-prog"><i style="width:{s.with_data / total * 100:.0f}%"></i></div>
        <div class="bal-pr"><span>Отчитались инициативы</span><b>{s.with_data} из {total}</b></div>
        <p class="bal-c">{esc(conclusion(s, state.thr))}</p>
      </div>
      <div class="bal-art">
        <div class="gcard g1"><span class="gk">Отставаний</span><b>{s.lagging}</b><span class="gs">инициатив в «риске» или «критично»</span></div>
        <div class="gcard g2"><span class="gk">План занижен</span><b>{s.counts['high']}<small> / {n}</small></b>
          <span class="gs">показателей, прогноз ≥ {state.thr.high:g} %</span>{spark(history, s.year, 150, 40, True)}</div>
        {leader_card}
        <div class="gcard g4"><span class="gdot">{check}</span><span><span class="gk">Проверить</span><br><b class="sm">{check_text}</b></span></div>
      </div>
      <div class="bal-actions">
        <a class="act" href="upload" target="_self"><i>+</i>Загрузить отчёт</a>
        <a class="act" href="initiative" target="_self"><i>▦</i>Инициативы</a>
        <a class="act" href="quality" target="_self"><i>!</i>Качество данных</a>
        <a class="act" href="export" target="_self"><i>⤓</i>Выгрузка в Excel</a>
      </div>
    </div>""")


def side_cards_html(s: YearSummary, state: AppState) -> str:
    history = [(y, state.summary(y).median_pct) for y in state.years]
    n = len(s.rows)
    no_data = sum(1 for i in s.initiatives if i.n_indicators == 0)
    rows = "".join(
        f'<div class="st-row s-{st}">{mini(st)}<span>{STATUS_LABELS[st]}</span><b>{s.counts[st]}</b></div>'
        for st in ["crit", "risk", "ok", "high"]
    )
    if s.counts.get("na"):
        rows += f'<div class="st-row s-na">{mini("na")}<span>Прогноз пока неприменим</span><b>{s.counts["na"]}</b></div>'
    rows += f'<div class="st-row s-nodata">{mini("nodata")}<span>Инициатив без данных</span><b>{no_data}</b></div>'
    return compact(f"""
    <div class="scard"><div class="scard-h"><div><h3>Медиана по годам</h3><small>% выполнения плана</small></div></div>
      <div class="mini-chart">{spark(history, s.year, 260, 120, False)}</div></div>
    <div class="scard"><div class="scard-h"><div><h3>Статусы показателей</h3><small>{s.year}, всего {n}</small></div></div>
      <div class="st-list">{rows}</div></div>""")


def callout_html(s: YearSummary, state: AppState) -> str:
    n, h = len(s.rows), s.counts["high"]
    if s.lagging:
        title, text = "Есть отставания", (
            f"У {s.lagging} {plural(s.lagging, 'инициативы', 'инициатив', 'инициатив')} прогноз ниже "
            f"{state.thr.risk:g} % плана. Обсудите их с кураторами до конца года.")
    elif h:
        title, text = "Планы пора пересмотреть?", (
            f"У {h} из {n} показателей прогноз — {state.thr.high:g} % плана и выше. "
            f"Это аргумент обновить планы на следующий год.")
    else:
        return ""
    return compact(f"""<div class="scard callout callout-row"><div><h3>{title}</h3><p>{text}</p></div>
      <a class="btn pillc" href="#rating" target="_self">Рейтинг <i>›››</i></a></div>""")


def tiles_html(s: YearSummary) -> str:
    tiles = []
    for ini in s.initiatives:
        value = f'<span class="v">{fmt_pct(ini.median_fc_pct)}</span>' if ini.median_fc_pct is not None else ""
        flag = '<span class="flag" title="Есть значения для проверки">⚠</span>' if ini.n_flags else ""
        tip = esc(ini.name + (f" — {ini.note}" if ini.note else ""))
        tiles.append(f"""<a class="tile s-{ini.status}" href="initiative?ini={ini.id}" target="_self" title="{tip}">
          <span class="tile-top"><span class="tile-ico">{STATUS_ICONS[ini.status]}</span>{flag}</span>
          <span class="tile-name">{esc(ini.short)}</span>
          <span class="tile-meta"><b>{STATUS_LABELS[ini.status]}</b>{value}</span></a>""")
    return compact(f"""<div class="card-h"><h3>Светофор инициатив</h3>{legend()}</div>
      <div class="tiles">{''.join(tiles)}</div>
      <p class="hint">Статус инициативы — по медиане прогноза (% плана) её показателей. Нажмите на плашку, чтобы открыть инициативу.</p>""")


def rating_html(s: YearSummary, thr: Thresholds, cap: float = 300) -> str:
    ranked = sorted(s.initiatives, key=lambda i: -(i.median_fc_pct if i.median_fc_pct is not None else -1))
    lines = [t for t in (thr.crit, thr.risk, thr.high) if t <= cap]
    ticks = "".join(
        f'<span class="rk-tl t{k}" style="left:{t / cap * 100:.2f}%">{t:g}</span>' for k, t in enumerate(lines)
    ) + f'<span class="rk-tl end" style="left:100%">{cap:g} %</span>'
    rules = "".join(f'<span class="rk-line" style="left:{t / cap * 100:.2f}%"></span>' for t in lines)
    rows = [f'<div class="rk-row rk-axis"><span></span><div class="rk-track">{ticks}</div><span></span></div>']
    for ini in ranked:
        v = ini.median_fc_pct
        if v is None:
            bar = '<span class="rk-empty">нет данных</span>'
            val = '<span class="muted">—</span>'
        else:
            width = min(v, cap) / cap * 100
            clipped = " clipped" if v > cap else ""
            bar = f'<span class="rk-bar b-{ini.status}{clipped}" style="width:{width:.1f}%"></span>'
            val = f"<b>{fmt_pct(v)}</b> {mini(ini.status)}"
        rows.append(f'<div class="rk-row" title="{esc(ini.name)}"><span class="rk-name">{esc(ini.short)}</span>'
                    f'<div class="rk-track">{rules}{bar}</div><span class="rk-val">{val}</span></div>')
    return compact(f"""<div class="card-h" id="rating"><h3>Рейтинг: медиана прогноза, % плана</h3></div>
      <div class="rating">{''.join(rows)}</div>
      <p class="rk-note">Шкала обрезана на {cap:g} %: у обрезанного бара «рваный» конец, реальное значение — справа. Пунктир — пороги статусов.</p>""")


def banner_html(title: str, text: str) -> str:
    return compact(f"""<div class="hero"><div><h1>{esc(title)}</h1><p>{text}</p></div></div>""")


def indicator_table_html(rows: pd.DataFrame, is_current: bool, as_of: str) -> str:
    head = ("<tr><th>Показатель</th><th>Ед.</th><th class='num'>План</th>"
            f"<th class='num'>Факт{' на ' + as_of if is_current else ''}</th><th class='num'>% вып.</th>"
            "<th class='num'>Прогноз</th><th class='num'>Прогноз, %</th><th>Статус</th></tr>")
    body = []
    for r in rows.itertuples():
        sigma = ' <span class="tag" title="Нарастающим итогом">Σ</span>' if r.is_cumulative else ""
        flag = ' <span class="flag" title="Факт = план — проверьте">⚠</span>' if "Q-1" in r.flags else ""
        body.append(f"<tr><td class='ind-name'>{esc(r.indicator)}{sigma}</td><td>{esc(r.unit)}</td>"
                    f"<td class='num'>{fmt_num(r.plan)}</td><td class='num'>{fmt_num(r.fact)}{flag}</td>"
                    f"<td class='num'>{fmt_pct(r.pct)}</td><td class='num'>{fmt_num(r.fc)}</td>"
                    f"<td class='num'><b>{fmt_pct(r.fc_pct)}</b></td><td>{chip(r.status)}</td></tr>")
    return compact(f'<div class="table-wrap"><table class="tbl"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>')


def initiative_head_html(ini: InitiativeSummary) -> str:
    sub = (esc(ini.note) if ini.note and ini.n_indicators == 0 else
           f"{ini.n_indicators} {plural(ini.n_indicators, 'показатель', 'показателя', 'показателей')} · "
           f"медиана прогноза {fmt_pct(ini.median_fc_pct)} плана")
    return compact(f"""<div class="init-head"><div><h2>{esc(ini.name)}</h2><p class="muted">{sub}</p></div>
      <div class="init-st">{chip(ini.status)}</div></div>""")


def indicator_history(state: AppState, indicator_id: int) -> pd.DataFrame:
    """Расчётные строки одного показателя за все годы — для графика динамики."""
    from .calc import indicator_rows

    parts = [indicator_rows(state.values, y, state.thr, state.current_year) for y in state.years]
    allr = pd.concat([p for p in parts if not p.empty], ignore_index=True) if parts else pd.DataFrame()
    return allr[allr["indicator_id"] == indicator_id] if not allr.empty else allr


def empty_state_html() -> str:
    return compact("""<div class="hero"><div><h1>Данных пока нет</h1>
      <p>Загрузите отчёт Центра «план / факт» за 2022–2026 годы — он уже лежит в проекте — или синтетические
      демо-данные, где есть все статусы светофора. Свой файл можно загрузить на странице «Загрузка отчётов».</p></div></div>""")


def strip_tags(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)
