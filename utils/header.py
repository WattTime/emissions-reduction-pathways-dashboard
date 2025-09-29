import streamlit as st
import base64
import duckdb
from config import CONFIG
from utils.utils import get_release_version

def render_static_header():
    def get_base64_logo():
        with open("Climate TRACE Logo.png", "rb") as f:
            return base64.b64encode(f.read()).decode()

    logo_base64 = get_base64_logo()
    con = duckdb.connect()
    asset_path = CONFIG["asset_path"]
    release_version = get_release_version(con,asset_path)

    st.markdown(
        f"""
        <div style='display: flex; align-items: center;'>
            <img src="data:image/png;base64,{logo_base64}" width="50" style="margin-right: 10px;" />
            <h1 style="margin: 0; font-size: 2.8em;">Climate TRACE Emissions Reduction Pathways (Beta)</h1>
        </div>
        <p style="margin-top: 2px; font-size: 1em; font-style: italic;">
            The data in this dashboard is from Climate TRACE release <span style='color: red;'><strong>{release_version}</strong></span> (excluding forestry), covering 660 million assets globally.
        </p>
        <p style="margin-top: 2px; font-size: 1em; font-style: italic;">
            This web application is for the internal use of Climate TRACE and its partners only. The data displayed may be revised, updated, rearranged, or deleted without prior communication to users, and is not warranted to be error free.
        </p>
        """,
        unsafe_allow_html=True
    )
