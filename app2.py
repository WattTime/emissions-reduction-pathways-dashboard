import streamlit as st
from urllib.parse import quote
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

# read active tab from URL (?tab=...)
qp = st.query_params
raw = qp.get("tab", None)
if isinstance(raw, list) and raw:        # in case your Streamlit returns list
    active_tab = raw[0]
elif isinstance(raw, str) and raw:
    active_tab = raw
else:
    active_tab = TABS[0]                 # default

# ensure active_tab is valid
if active_tab not in TABS:
    active_tab = TABS[0]

# ---------- build horizontal nav ----------
parts = []
parts.append("<div style='display:flex;gap:2rem;margin-bottom:1.25rem;'>")
for tab in TABS:
    is_active = (tab == active_tab)
    style = (
        "border-bottom:2px solid #ff4b4b;color:#ffffff;"
        if is_active else
        "color:#aaaaaa;"
    )
    # add target="_self" to force same window
    parts.append(
        f"<a href='?tab={quote(tab)}' target='_self' "
        f"style='text-decoration:none;{style}font-size:1.1rem;font-weight:500;cursor:pointer;'>{tab}</a>"
    )
parts.append("</div>")
nav_html = "".join(parts)

st.markdown(nav_html, unsafe_allow_html=True)

# ---- LINE SEPARATOR ----
st.markdown("<hr style='margin:0.5rem 0 1.5rem 0; border:1px solid #444;' />", unsafe_allow_html=True)


# ---------- render selected tab ----------
if active_tab == "Reduction Opportunities":
    show_emissions_reduction_plan()
elif active_tab == "Abatement Curve":
    show_abatement_curve()
elif active_tab == "Monthly Trends":
    show_monthly_dashboard()
