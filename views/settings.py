"""Настройки: пороги светофора, месяц данных текущего года, справочники, управление данными."""

import streamlit as st

from pulse import db, loaders, ui
from pulse.calc import Thresholds

state = ui.load_state()
html = lambda markup: st.markdown(markup, unsafe_allow_html=True)  # noqa: E731

html(ui.demo_banner(state))
html(ui.banner_html("Настройки", "Изменения сразу пересчитывают дашборд, страницы инициатив и выгрузку."))

with st.container(key="card_thr"):
    html('<div class="card-h"><h3>Пороги светофора (прогноз, % плана)</h3></div>')
    with st.form("thresholds"):
        c1, c2, c3, c4 = st.columns(4)
        crit = c1.number_input("«Критично», если меньше", 1.0, 1000.0, state.thr.crit, step=5.0)
        risk = c2.number_input("«Риск», если меньше", 1.0, 1000.0, state.thr.risk, step=5.0)
        high = c3.number_input("«План занижен», если от", 1.0, 1000.0, state.thr.high, step=10.0)
        month = c4.number_input(f"Данные {state.current_year} года на месяц", 1, 12, state.current_month, step=1)
        saved = st.form_submit_button("Сохранить")
    if saved:
        thr = Thresholds(crit, risk, high)
        problem = thr.validate()
        if problem:
            st.error(problem)
        else:
            db.set_settings({"thr_crit": crit, "thr_risk": risk, "thr_high": high})
            if int(month) != state.current_month:
                db.set_current_month(state.current_year, int(month))
            st.success("Сохранено. Статусы пересчитаны.")
            st.rerun()
    html(ui.compact(f"""<div class="legend-st">{ui.chip('crit')} <span class="muted">&lt; {state.thr.crit:g} %</span>
      {ui.chip('risk')} <span class="muted">{state.thr.crit:g}–{state.thr.risk:g} %</span>
      {ui.chip('ok')} <span class="muted">{state.thr.risk:g}–{state.thr.high:g} %</span>
      {ui.chip('high')} <span class="muted">≥ {state.thr.high:g} %</span></div>"""))
    st.caption("Месяц данных: при 6 (30.06) прогноз 2026 года больше факта 2025-го у всех показателей отчёта Центра. "
               "Прогноз не считается, если данных меньше чем за 3 месяца.")

with st.container(key="card_dirs"):
    html('<div class="card-h"><h3>Справочник показателей</h3></div>')
    ind = db.indicators_frame()
    if ind.empty:
        st.caption("Показателей пока нет — они появятся после загрузки отчёта.")
    else:
        edited = st.data_editor(
            ind[["id", "initiative", "name", "unit", "is_cumulative"]].assign(is_cumulative=ind["is_cumulative"].astype(bool)),
            hide_index=True, use_container_width=True, disabled=["id", "initiative", "name", "unit"],
            column_config={
                "id": None,
                "initiative": st.column_config.TextColumn("Инициатива"),
                "name": st.column_config.TextColumn("Показатель", width="large"),
                "unit": st.column_config.TextColumn("Ед."),
                "is_cumulative": st.column_config.CheckboxColumn("Нарастающим итогом"),
            },
            key="ind_editor",
        )
        changed = edited[edited["is_cumulative"] != ind["is_cumulative"].astype(bool)]
        if len(changed):
            for r in changed.itertuples():
                db.set_cumulative(int(r.id), bool(r.is_cumulative))
            st.rerun()

    html('<div class="card-h"><h3>Разовые события</h3></div>')
    st.caption("Для отмеченных инициатив прогноз в текущем году не считается: событие проходит один раз в год "
               "(например, Конгресс молодых учёных).")
    inis = db.initiatives_frame()
    edited_i = st.data_editor(
        inis[["id", "name", "is_irregular"]].assign(is_irregular=inis["is_irregular"].astype(bool)),
        hide_index=True, use_container_width=True, disabled=["id", "name"],
        column_config={"id": st.column_config.TextColumn("Код"), "name": st.column_config.TextColumn("Инициатива"),
                       "is_irregular": st.column_config.CheckboxColumn("Разовое событие")},
        key="ini_editor",
    )
    changed_i = edited_i[edited_i["is_irregular"] != inis["is_irregular"].astype(bool)]
    if len(changed_i):
        for r in changed_i.itertuples():
            db.set_irregular(r.id, bool(r.is_irregular))
        st.rerun()

with st.container(key="card_data"):
    html('<div class="card-h"><h3>Данные</h3></div>')
    mode = {"demo": "демо-данные (синтетика)", "report": "отчёт Центра", "empty": "пусто"}.get(state.mode, state.mode)
    st.markdown(f"Сейчас в базе: **{mode}**, {len(state.values)} значений. Файл базы: `{db.db_path().name}`.")
    c1, c2, c3 = st.columns(3)
    if c1.button("Загрузить отчёт Центра 2022–2026", type="primary", use_container_width=True):
        rep = loaders.load_center_report()
        st.success(f"Загружено {rep.added} значений. Совпадения «факт = план» 2026 года отмечены как подтверждённые.")
        st.rerun()
    if c2.button("Загрузить демо-данные", use_container_width=True):
        loaders.load_demo()
        st.rerun()
    sure = c3.checkbox("Да, удалить все данные", key="sure_reset")
    if c3.button("Очистить базу", use_container_width=True, disabled=not sure):
        db.reset_all()
        db.set_settings({"mode": "empty"})
        st.rerun()
    st.caption("Загрузка отчёта или демо заменяет текущие данные. Резервная копия — копия файла data/pulse.db.")
