import streamlit as st

st.set_page_config(layout="wide")

# Place the logo at the top
st.sidebar.image("assets/pngimg.com - beaver_PNG35.png")

about_page = st.Page(
    page="pages/about_lab.py",
    title="About the Tool",
    icon=":material/account_circle:",
    default=True,
)

project_1_page = st.Page(
    page="pages/analyze_impacts.py",
    title="Analyze Impacts!",
    icon=":material/bar_chart:",
)

pg = st.navigation(pages=[about_page, project_1_page])
pg.run()
