"""Загрузка отчётов: Excel/CSV по шаблону с проверкой и разовый импорт Word-отчёта."""

import streamlit as st

from pulse import db, loaders, ui
from pulse.calc import plural
from pulse.export import protocol_xlsx
from pulse.import_excel import FileReadError, build_template, read_table
from pulse.import_word import parse_docx
from pulse.validation import RULES, validate

state = ui.load_state()
html = lambda markup: st.markdown(markup, unsafe_allow_html=True)  # noqa: E731

html(ui.banner_html("Загрузка отчётов",
                    "Файл проверяется до записи в базу: строки с ошибками не попадут в свод, "
                    "а протокол подскажет куратору, что исправить."))
html(ui.compact("""<div class="steps">
  <div class="step"><span class="step-n">1</span><b>Скачайте шаблон</b><p>Лист «Данные» с выпадающими списками инициатив и показателей.</p></div>
  <div class="step"><span class="step-n">2</span><b>Загрузите файлы</b><p>.xlsx или .csv до 5 МБ, можно несколько сразу.</p></div>
  <div class="step"><span class="step-n">3</span><b>Проверьте протокол</b><p>Загрузите корректные строки, протокол отправьте куратору.</p></div>
</div>"""))

tab_excel, tab_word, tab_log = st.tabs(["Excel / CSV по шаблону", "Word-отчёт Центра", "Журнал загрузок"])

with tab_excel:
    indicators = db.indicators_frame()
    if indicators.empty:
        st.warning("Справочник показателей пуст. Сначала импортируйте Word-отчёт (вкладка рядом) или загрузите "
                   "отчёт Центра в «Настройках» — из него появятся показатели для шаблона.")
    else:
        st.download_button(
            "Скачать шаблон .xlsx", build_template(indicators, state.current_year, state.current_month),
            file_name="shablon_puls_iniciativ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    files = st.file_uploader("Заполненные файлы", type=["xlsx", "csv"], accept_multiple_files=True,
                             key="excel_files")
    for f in files or []:
        with st.container(key=f"card_file_{f.file_id}"):
            st.markdown(f"**{f.name}**")
            try:
                df = read_table(f.getvalue(), f.name)
            except FileReadError as exc:
                st.error(str(exc))
                continue
            res = validate(df, indicators, db.existing_keys(), state.current_year)
            n_err, n_warn = len(res.errors), len(res.warnings)
            html(ui.compact(f"""<div class="sum-chips">
                {ui.chip('ok').replace('В норме', f'{len(res.rows)} {plural(len(res.rows), "строка готова", "строки готовы", "строк готово")}')}
                {ui.chip('crit').replace('Критично', f'{n_err} {plural(n_err, "ошибка", "ошибки", "ошибок")}')}
                {ui.chip('risk').replace('Риск', f'{n_warn} {plural(n_warn, "предупреждение", "предупреждения", "предупреждений")}')}
            </div>"""))
            protocol = res.as_frame()
            if not protocol.empty:
                st.dataframe(protocol, hide_index=True, use_container_width=True)
                st.download_button("Скачать протокол для куратора", protocol_xlsx(protocol),
                                   file_name=f"protokol_{f.name.rsplit('.', 1)[0]}.xlsx", key=f"proto_{f.file_id}")
            if res.file_error or not res.rows:
                st.info("Загружать нечего: исправьте файл по протоколу и загрузите снова.")
                continue
            on_dup = "replace"
            if any(w.rule == "V-09" for w in res.warnings):
                choice = st.radio("Записи, которые уже есть в базе", ["Заменить новыми значениями", "Пропустить"],
                                  horizontal=True, key=f"dup_{f.file_id}")
                on_dup = "replace" if choice.startswith("Заменить") else "skip"
            if st.button(f"Загрузить корректные строки ({len(res.rows)})", type="primary", key=f"save_{f.file_id}"):
                rep = loaders.load_validated(res, f.name, on_dup)
                st.success(f"Готово: добавлено {rep.added}, заменено {rep.replaced}, пропущено {rep.skipped}, "
                           f"отклонено с ошибками {rep.rejected}. Дашборд обновлён.")
    with st.expander("Какие проверки выполняются"):
        st.table({"Правило": list(RULES), "Что проверяется": list(RULES.values())})

with tab_word:
    st.markdown("Разовый перенос итогового отчёта «план / факт» из Word. Структура как в отчёте Центра: "
                "нумерованный заголовок инициативы, название показателя заглавными, строка с единицей, "
                "затем пары «год — план / факт».")
    if state.mode == "demo":
        st.warning("Сейчас в базе демо-данные. Чтобы не смешать их с реальными, очистите базу в «Настройках» "
                   "перед импортом.")
    doc =st.file_uploader("Word-отчёт .docx", type=["docx"], key="word_file")
    if doc is not None:
        try:
            parsed = parse_docx(doc.getvalue())
        except Exception as exc:  # повреждённый или не тот файл
            st.error(f"Не удалось прочитать документ ({exc.__class__.__name__}). Проверьте, что это .docx.")
            parsed = None
        if parsed is not None:
            c1, c2, c3 = st.columns(3)
            c1.metric("Значений", len(parsed.values))
            c2.metric("Показателей", parsed.n_indicators)
            c3.metric("Инициатив с данными", parsed.n_initiatives)
            for ini_id, note in parsed.no_data.items():
                st.warning(f"{ini_id}: {note}")
            for title in parsed.unknown_initiatives:
                st.error(f"Инициатива «{title}» не найдена в справочнике — её значения не будут загружены.")
            for p in parsed.problems:
                st.error(p)
            equal = [v for v in parsed.values if v.year == state.current_year and v.plan == v.fact]
            confirm = False
            if equal:
                confirm = st.checkbox(
                    f"В {state.current_year} году у {len(equal)} показателей факт равен плану — это подтверждённые "
                    f"реальные значения", value=False, key="word_confirm")
            st.caption(f"Значения {state.current_year} года будут сохранены как данные на {state.as_of} "
                       f"(месяц меняется в «Настройках»).")
            if parsed.values and st.button("Импортировать в базу", type="primary", key="word_save"):
                rep = loaders.load_word(doc.getvalue(), doc.name, state.current_year, state.current_month,
                                        confirm_equal_current=confirm)
                if state.mode in ("empty", "demo"):
                    db.set_settings({"mode": "report"})
                st.success(f"Импортировано: добавлено {rep.added}, заменено {rep.replaced}.")

with tab_log:
    log = db.uploads_frame()
    if log.empty:
        st.caption("Загрузок пока не было.")
    else:
        st.dataframe(
            log.rename(columns={"file_name": "Файл", "loaded_at": "Когда", "rows_ok": "Принято",
                                "rows_rejected": "Отклонено", "rows_warned": "Предупреждений",
                                "rows_replaced": "Заменено"}).drop(columns=["id"]),
            hide_index=True, use_container_width=True,
        )
