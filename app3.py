import streamlit as st
from utils.header import render_static_header
from tabs.tab01_emissions_reduction_tab import show_emissions_reduction_plan
from tabs.tab02_abatement_curve_tab import show_abatement_curve
from tabs.tab03_monthly_dashboard_tab import show_monthly_dashboard

# ---------- page config ----------
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# ---------- static header ----------
render_static_header()
st.markdown("<br>", unsafe_allow_html=True)

# ---------- tabs config ----------
TABS = ["Reduction Opportunities", "Abatement Curve", "Monthly Trends"]

# ---- Inject CSS to hide default radio buttons ----
st.markdown(
    """
    <style>
    div[role="radiogroup"] {
        display: flex;
        gap: 2rem;
        margin-bottom: 1.25rem;
    }
    div[role="radiogroup"] > label {
        font-size: 1.1rem;
        font-weight: 500;
        cursor: pointer;
        color: #aaaaaa;
        border-bottom: 2px solid transparent;
        padding-bottom: 0.25rem;
    }
    div[role="radiogroup"] > label[data-selected="true"] {
        color: #ffffff;
        border-bottom: 2px solid #ff4b4b;
    }
    /* hide the native radio circle */
    div[role="radiogroup"] input {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---- Render "fake tabs" with radio ----
active_tab = st.radio("Navigation", TABS, horizontal=True, label_visibility="collapsed")

# ---- Line separator under tabs ----
st.markdown("<hr style='margin:0.5rem 0 1.5rem 0; border:1px solid #444;' />", unsafe_allow_html=True)

# ---------- render selected tab ----------
if active_tab == "Reduction Opportunities":
    show_emissions_reduction_plan()
elif active_tab == "Abatement Curve":
    show_abatement_curve()
elif active_tab == "Monthly Trends":
    show_monthly_dashboard()
