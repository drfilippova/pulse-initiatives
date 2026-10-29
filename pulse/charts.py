"""Графики plotly в фирменных цветах."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .calc import fmt_num, fmt_pct
from .ui import PALETTE


def plan_fact_figure(history: pd.DataFrame, unit: str, current_year: int, as_of: str) -> go.Figure:
    """Столбцы «план» и «факт» по годам; для текущего года — пунктир прогноза до конца года.

    history: строки indicator_rows за все годы для одного показателя (year, plan, fact, fc, pct, fc_pct).
    """
    h = history.sort_values("year")
    years = [str(y) + ("*" if y == current_year else "") for y in h["year"]]
    fig = go.Figure()
    fig.add_bar(
        name="План", x=years, y=h["plan"], marker_color=PALETTE["ice"], marker_line_width=0,
        hovertemplate="План %{x}: %{y:,.2f} " + unit + "<extra></extra>",
    )
    fig.add_bar(
        name="Факт", x=years, y=h["fact"], marker_color=PALETTE["blue"], marker_line_width=0,
        text=[fmt_pct(p) for p in h["pct"]], textposition="outside", textfont={"color": PALETTE["ink"], "size": 12},
        cliponaxis=False,
        hovertemplate="Факт %{x}: %{y:,.2f} " + unit + "<extra></extra>",
    )
    cur = h[h["year"] == current_year]
    if len(cur) and cur.iloc[0]["fc"] is not None and not pd.isna(cur.iloc[0]["fc"]):
        r = cur.iloc[0]
        fig.add_scatter(
            name=f"Прогноз на конец {current_year}", x=[years[-1]], y=[r["fc"]], mode="markers+text",
            marker={"symbol": "line-ew-open", "size": 30, "color": PALETTE["electric"],
                    "line": {"width": 3, "color": PALETTE["electric"]}},
            text=[f"прогноз {fmt_num(r['fc'])}"], textposition="top left", cliponaxis=False,
            textfont={"color": PALETTE["electric"], "size": 12},
            hovertemplate="Прогноз на конец года: %{y:,.2f} " + unit + "<extra></extra>",
        )
    fig.update_layout(
        template="plotly_white", barmode="group", bargap=0.35, bargroupgap=0.08, height=360,
        margin={"l": 10, "r": 20, "t": 40, "b": 10}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Mulish, sans-serif", "color": PALETTE["ink2"], "size": 13},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        yaxis={"title": unit, "gridcolor": PALETTE["grid"], "zeroline": False, "separatethousands": True},
        xaxis={"title": {"text": f"* {current_year} — данные на {as_of}", "font": {"size": 11, "color": PALETTE["ink3"]}}},
        separators=", ",
    )
    return fig
