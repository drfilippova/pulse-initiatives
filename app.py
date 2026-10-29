"""«Пульс инициатив» — точка входа. Запуск: streamlit run app.py"""

import streamlit as st

from pulse import ui

st.set_page_config(
    page_title="Пульс инициатив",
    page_icon=str(ui.ASSETS / "favicon.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(ui.css(), unsafe_allow_html=True)
st.logo(str(ui.ASSETS / "logo_horizontal_color.png"), size="large")

state = ui.load_state()

pages = [
    st.Page("views/dashboard.py", title="Дашборд", icon=":material/dashboard:", default=True),
    st.Page("views/upload.py", title="Загрузка отчётов", icon=":material/upload:", url_path="upload"),
    st.Page("views/initiative.py", title="Инициатива", icon=":material/bar_chart:", url_path="initiative"),
    st.Page("views/quality.py", title="Качество данных", icon=":material/warning:", url_path="quality"),
    st.Page("views/export.py", title="Выгрузка", icon=":material/download:", url_path="export"),
    st.Page("views/settings.py", title="Настройки", icon=":material/tune:", url_path="settings"),
]
nav = st.navigation(pages)

with st.sidebar:
    st.markdown(ui.sidebar_html(state), unsafe_allow_html=True)

nav.run()
