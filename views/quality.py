"""Качество данных: что проверить до того, как цифры уйдут руководству."""

import streamlit as st

from pulse import db, ui
from pulse.calc import FLAG_TITLES, fmt_num, quality_flags

state = ui.load_state()
html = lambda markup: st.markdown(markup, unsafe_allow_html=True)  # noqa: E731

html(ui.demo_banner(state))
html(ui.banner_html("Качество данных",
                    "Флаги не меняют статусы светофора — они подсказывают, какие значения уточнить у кураторов."))

flags = quality_flags(state.values, state.current_year, state.initiatives)
open_q1 = flags[flags["code"] == "Q-1"]
done_q1 = flags[flags["code"] == "Q-1✓"]
no_data = flags[flags["code"].isin(["Q-2", "Q-3"])]
jumps = flags[flags["code"].isin(["Q-4", "Q-5"])]

html(ui.compact(f"""<div class="kpis">
  <div class="kpi {'t-risk' if len(open_q1) else 't-ok'}"><div class="kpi-v">{len(open_q1)}</div><div class="kpi-l">«Факт = план» ждут подтверждения</div></div>
  <div class="kpi t-ok"><div class="kpi-v">{len(done_q1)}</div><div class="kpi-l">«Факт = план» подтверждено</div></div>
  <div class="kpi t-nodata"><div class="kpi-v">{len(no_data)}</div><div class="kpi-l">Инициатив без данных</div></div>
  <div class="kpi t-high"><div class="kpi-v">{len(jumps)}</div><div class="kpi-l">Резких изменений к прошлому году</div></div>
</div>"""))


def item(badge_cls: str, code: str, r) -> str:
    where = f"{int(r.year)} · план {fmt_num(r.plan)} / факт {fmt_num(r.fact)}" if r.year == r.year and r.year else ""
    return ui.compact(f"""<div class="qitem"><div><span class="qbadge {badge_cls}">{FLAG_TITLES.get(code, code)}</span></div>
      <div><b>{ui.esc(r.initiative)}</b><span>{ui.esc(r.indicator)}</span><br><span>{where}</span></div>
      <div><span>{ui.esc(r.detail)}</span></div></div>""")


with st.container(key="card_q1"):
    html('<div class="card-h"><h3>Факт в точности равен плану (текущий год)</h3></div>')
    if open_q1.empty:
        st.caption("Неподтверждённых совпадений нет.")
    for r in open_q1.itertuples():
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.markdown(item("q-warn", "Q-1", r), unsafe_allow_html=True)
        if c2.button("Подтвердить", key=f"confirm_{r.indicator_id}_{r.year}"):
            db.confirm_value(int(r.indicator_id), int(r.year))
            st.rerun()
    if not done_q1.empty:
        with st.expander(f"Подтверждено: {len(done_q1)}"):
            html("".join(item("q-ok", "Q-1✓", r) for r in done_q1.itertuples()))

with st.container(key="card_nodata"):
    html('<div class="card-h"><h3>Инициативы без данных</h3></div>')
    if no_data.empty:
        st.caption("По всем инициативам есть данные.")
    html("".join(item("q-nd", r.code, r) for r in no_data.itertuples()))

with st.container(key="card_jumps"):
    html('<div class="card-h"><h3>Резкие изменения к прошлому году</h3></div>')
    if jumps.empty:
        st.caption("Резких изменений нет.")
    html("".join(item("q-info", r.code, r) for r in jumps.sort_values("year").itertuples()))
    st.caption("Рост больше чем в 5 раз — не ошибка сам по себе, но стоит уточнить методику подсчёта.")
