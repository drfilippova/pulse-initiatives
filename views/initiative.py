"""Страница инициативы: показатели за выбранный год и график по годам."""

import streamlit as st

from pulse import ui
from pulse.catalog import BY_ID, INITIATIVES
from pulse.charts import plan_fact_figure

state = ui.load_state()
html = lambda markup: st.markdown(markup, unsafe_allow_html=True)  # noqa: E731

html(ui.demo_banner(state))
html(ui.banner_html("Инициатива", "Показатели инициативы: план, факт, прогноз на конец года и статус. "
                                  "Σ — показатель считается нарастающим итогом."))

ids = [i.id for i in INITIATIVES]
from_link = st.query_params.get("ini")
if from_link in ids:
    st.session_state["ini_sel"] = from_link
    st.query_params.clear()
if st.session_state.get("ini_sel") not in ids:
    st.session_state["ini_sel"] = ids[0]

years = state.years
if st.session_state.get("ini_year") not in years:
    st.session_state["ini_year"] = state.current_year if state.current_year in years else years[-1]

c1, c2 = st.columns([3, 1])
ini_id = c1.selectbox("Инициатива", ids, format_func=lambda i: BY_ID[i].name, key="ini_sel")
year = c2.selectbox("Год", years, key="ini_year")

s = state.summary(year)
ini = next(i for i in s.initiatives if i.id == ini_id)
rows = s.rows[s.rows["initiative_id"] == ini_id]

with st.container(key="card_ini"):
    html(ui.initiative_head_html(ini))
    if rows.empty:
        reason = ini.note or "За этот год данных по инициативе нет."
        st.info(f"{reason} Запросите отчёт у куратора — инициатива отмечена на странице «Качество данных».")
    else:
        html(ui.indicator_table_html(rows, s.is_current, state.as_of))
        if s.is_current:
            html(f'<p class="hint">Прогноз: обычный показатель — F / M × 12; нарастающим итогом — '
                 f'F<sub>{year - 1}</sub> + (F − F<sub>{year - 1}</sub>) / M × 12; M = {state.current_month}.</p>')

if not rows.empty:
    with st.container(key="card_ini_chart"):
        names = dict(zip(rows["indicator_id"], rows["indicator"]))
        units = dict(zip(rows["indicator_id"], rows["unit"]))
        ind_id = st.selectbox("Показатель на графике", list(names), format_func=lambda i: names[i],
                              key=f"ini_chart_{ini_id}")
        hist = ui.indicator_history(state, ind_id)
        st.plotly_chart(plan_fact_figure(hist, units[ind_id], state.current_year, state.as_of),
                        use_container_width=True, config={"displayModeBar": False})
