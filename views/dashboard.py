"""Дашборд: главная синяя карточка, статусы, светофор инициатив, рейтинг и динамика."""

import streamlit as st

from pulse import loaders, ui
from pulse.charts import plan_fact_figure

state = ui.load_state()
html = lambda markup: st.markdown(markup, unsafe_allow_html=True)  # noqa: E731

html(ui.demo_banner(state))

if state.values.empty:
    html(ui.topbar_html("Пульс", "инициатив", "Мониторинг выполнения плана Десятилетия науки и технологий"))
    html(ui.empty_state_html())
    c1, c2, c3 = st.columns([1.2, 1, 1])
    if c1.button("Загрузить отчёт Центра 2022–2026", type="primary", use_container_width=True):
        rep = loaders.load_center_report()
        st.toast(f"Загружено {rep.added} значений по {rep.indicators} показателям")
        st.rerun()
    if c2.button("Загрузить демо-данные", use_container_width=True):
        loaders.load_demo()
        st.rerun()
    c3.page_link("views/upload.py", label="Загрузить свой файл", icon=":material/upload:")
    st.stop()

years = state.years
default_year = state.current_year if state.current_year in years else years[-1]
if st.session_state.get("year") not in years:
    st.session_state["year"] = default_year

top_l, top_r = st.columns([3, 2], vertical_alignment="bottom")
with top_l:
    html(ui.topbar_html("Пульс", "инициатив",
                        f"Выполнение плана Десятилетия науки и технологий · данные {state.current_year} года "
                        f"на {state.as_of}"))
with top_r:
    picked = st.segmented_control("Отчётный год", options=years, key="year", label_visibility="collapsed")
year = picked or default_year
s = state.summary(year)

left, right = st.columns([2.3, 1], gap="medium")
with left:
    html(ui.hero_html(s, state))
    note = (f"Текущий год: прогноз на конец года по данным на {state.as_of} (M = {state.current_month})."
            if s.is_current else "Закрытый год: прогноз равен факту.")
    html(f'<p class="muted note">{note}</p>' + ui.callout_html(s, state))
with right:
    html(ui.side_cards_html(s, state))

with st.container(key="card_tiles"):
    html(ui.tiles_html(s))

c1, c2 = st.columns([1, 1.15], gap="medium")
with c1:
    with st.container(key="card_rating"):
        html(ui.rating_html(s, state.thr))
with c2:
    with st.container(key="card_dyn"):
        html('<div class="card-h"><h3>Динамика план / факт по годам</h3></div>')
        v = state.values
        ini_ids = list(dict.fromkeys(v["initiative_id"]))
        short = dict(zip(v["initiative_id"], v["initiative"]))
        a, b = st.columns([1, 1.6])
        ini_id = a.selectbox("Инициатива", ini_ids, format_func=lambda i: short.get(i, i), key="dyn_ini")
        inds = v[v["initiative_id"] == ini_id].drop_duplicates("indicator_id")
        names = dict(zip(inds["indicator_id"], inds["indicator"]))
        ind_id = b.selectbox("Показатель", list(names), format_func=lambda i: names[i], key=f"dyn_ind_{ini_id}")
        hist = ui.indicator_history(state, ind_id)
        unit = inds.set_index("indicator_id").loc[ind_id, "unit"]
        st.plotly_chart(plan_fact_figure(hist, unit, state.current_year, state.as_of), use_container_width=True,
                        config={"displayModeBar": False})
