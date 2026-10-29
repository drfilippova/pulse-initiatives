"""Выгрузка сводного отчёта в Excel для руководства и Координационного комитета."""

import streamlit as st

from pulse import ui
from pulse.calc import STATUS_LABELS, conclusion, fmt_pct, quality_flags
from pulse.export import build_report

state = ui.load_state()
html = lambda markup: st.markdown(markup, unsafe_allow_html=True)  # noqa: E731

html(ui.demo_banner(state))
html(ui.banner_html("Выгрузка в Excel",
                    "Сводка, детализация по показателям, флаги качества, исходные данные и параметры расчёта — "
                    "в одном файле. Цифры совпадают с дашбордом."))

if state.values.empty:
    st.info("Данных пока нет — загрузите отчёт на странице «Загрузка отчётов» или в «Настройках».")
    st.stop()

years = state.years
year = st.selectbox("Отчётный год", years, index=years.index(state.current_year) if state.current_year in years
                    else len(years) - 1)
s = state.summary(year)

with st.container(key="card_export"):
    html(f'<div class="card-h"><h3>Что попадёт в отчёт за {year} год</h3></div>')
    st.markdown(f"**Вывод:** {conclusion(s, state.thr)}")
    preview = [
        {"Инициатива": i.short, "Медиана прогноза": fmt_pct(i.median_fc_pct), "Статус": STATUS_LABELS[i.status],
         "Показателей": i.n_indicators}
        for i in sorted(s.initiatives, key=lambda i: -(i.median_fc_pct or -1))
    ]
    st.dataframe(preview, hide_index=True, use_container_width=True)
    data = build_report(s, quality_flags(state.values, state.current_year, state.initiatives), state.values,
                        state.thr, state.mode)
    suffix = "_DEMO" if state.mode == "demo" else ""
    st.download_button(
        "Сформировать и скачать Excel", data, file_name=f"puls_iniciativ_{year}{suffix}.xlsx", type="primary",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption("Листы: «Сводка», «Детализация», «Флаги качества», «Данные», «Параметры».")
