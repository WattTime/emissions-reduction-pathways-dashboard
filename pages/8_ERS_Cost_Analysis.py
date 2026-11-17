import json
import base64

import streamlit as st

from config import CONFIG
from tabs.tab09_ers_cost import show_ers_cost

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    .block-container { padding-top: 1rem; }
    section[data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    [data-testid="stPageLink-NavLink"],
    [data-testid="stPageLink-NavLink"] span,
    [data-testid="stPageLink-NavLink"] p { color: #ff4b4b !important; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_base64_of_bin_file(bin_file_path):
    with open(bin_file_path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


st.markdown("<br>", unsafe_allow_html=True)

st.page_link("pages/0_Home.py", label="⬅️ Back to Home")

logo_base64 = get_base64_of_bin_file("Climate TRACE Logo.png")

with open(CONFIG['ers_cost_meta_path']) as f:
    _meta = json.load(f)

st.markdown(
    f"""
    <div style='display: flex; align-items: center;'>
        <img src="data:image/png;base64,{logo_base64}" width="50" style="margin-right: 10px;" />
        <h1 style="margin: 0; font-size: 2.8em;">Climate TRACE ERS Cost Analysis (Beta)</h1>
    </div>
    <p style="margin-top: 2px; font-size: 1em; font-style: italic;">
        This is a <strong>static</strong> analysis (not refreshed with the monthly release). Last updated <span style='color: red;'><strong>{_meta['last_updated']}</strong></span>, data version <span style='color: red;'><strong>{_meta['data_version']}</strong></span>.
    </p>
    <p style="margin-top: 2px; font-size: 1em; font-style: italic;">
        This web application is for the internal use of Climate TRACE and its partners only.
        The data displayed may be revised, updated, rearranged, or deleted without prior communication
        to users, and is not warranted to be error free.
    </p>
    """,
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

tab1, = st.tabs(["ERS Cost Analysis"])
with tab1:
    show_ers_cost()
