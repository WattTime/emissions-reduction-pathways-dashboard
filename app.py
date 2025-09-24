import streamlit as st
import base64
import duckdb

from config import CONFIG
from utils.utils import get_release_version
from tabs.tab01_emissions_reduction_tab import show_emissions_reduction_plan
from tabs.tab02_abatement_curve_tab import show_abatement_curve
from tabs.tab03_monthly_dashboard_tab import show_monthly_dashboard

st.set_page_config(layout="wide")

# load CT logo
def get_base64_of_bin_file(bin_file_path):
    with open(bin_file_path, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

logo_base64 = get_base64_of_bin_file("Climate TRACE Logo.png")

asset_path = CONFIG['asset_path']

con = duckdb.connect()

st.markdown(
        f"""
        <div style='display: flex; align-items: center;'>
            <img src="data:image/png;base64,{logo_base64}" width="50" style="margin-right: 10px;" />
            <h1 style="margin: 0; font-size: 2.8em;">Climate TRACE Emissions Reduction Pathways (Beta)</h1>
        </div>
        <p style="margin-top: 2px; font-size: 1em; font-style: italic;">
            The data in this dashboard is from Climate TRACE release <span style='color: red;'><strong>{get_release_version(con, asset_path)}</strong></span> (excluding forestry), covering 660 million assets globally.
        </p>
        <p style="margin-top: 2px; font-size: 1em; font-style: italic;">
            This web application is for the internal use of Climate TRACE and its partners only. The data displayed may be revised, updated, rearranged, or deleted without prior communication to users, and is not warranted to be error free.
        </p>
        """,
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

# def mark_ro_recompute():
#     st.session_state.needs_recompute_reduction_opportunities = True

# def mark_ac_recompute():
#     st.session_state.needs_recompute_abatement_curve = True

# def mark_mt_recompute():
#     st.session_state.needs_recompute_monthly_trends = True

if "needs_recompute_reduction_opportunities" not in st.session_state:
    st.session_state.needs_recompute_reduction_opportunities = True

if "needs_recompute_abatement_curve" not in st.session_state:
    st.session_state.needs_recompute_abatement_curve = True

if "needs_recompute_monthly_trends" not in st.session_state:
    st.session_state.needs_recompute_monthly_trends = True


tab1, tab2, tab3 = st.tabs(["Reduction Opportunities", "Abatement Curve", "Monthly Trends"])
with tab1:
    if st.session_state.needs_recompute_reduction_opportunities:
        show_emissions_reduction_plan()
        st.session_state.needs_recompute_reduction_opportunities = False

with tab2:
    if st.session_state.needs_recompute_abatement_curve:
        show_abatement_curve()
        st.session_state.needs_recompute_abatement_curve = False

with tab3:
    if st.session_state.needs_recompute_monthly_trends:
        show_monthly_dashboard()
        st.session_state.needs_recompute_monthly_trends = False

