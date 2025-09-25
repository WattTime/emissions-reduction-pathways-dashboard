import streamlit as st
import base64

st.set_page_config(layout="wide")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    """
    <style>
    /* Remove default top padding */
    .block-container {
        padding-top: 1rem; /* adjust this number (default ~6rem) */
    }
    /* Hide the sidebar completely */
    section[data-testid="stSidebar"] {
        display: none;
    }
    /* Hide the sidebar collapse/expand arrow */
    [data-testid="collapsedControl"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# disable scrolling
st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        height: 100vh !important;
        overflow: hidden !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ---- Load logo ----
def get_base64_logo():
    with open("Climate TRACE Logo.png", "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_base64 = get_base64_logo()

# ---- Hub Header ----
st.markdown(
    f"""
    <div style='display: flex; align-items: center; justify-content: center;'>
        <img src="data:image/png;base64,{logo_base64}" width="70" style="margin-right: 15px;" />
        <h1 style="margin: 0; font-size: 2.8em;">Climate TRACE Toolkit</h1>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)

# ---- Card Styling ----
st.markdown(
    """
    <style>
    .tool-card {
        background-color: #262730;
        border: 1px solid #444;
        border-radius: 12px;
        padding: 25px;
        text-align: center;
        transition: all 0.2s ease-in-out;
        cursor: pointer;
        display: block;
        color: inherit;
    }
    .tool-card:hover {
        border-color: #ff4b4b;
        transform: translateY(-4px);
    }
    .tool-icon {
        font-size: 2.5rem;
    }
    .tool-title {
        font-size: 1.4rem;
        font-weight: 600;
        margin-top: 10px;
        color: #1f77ff; /* make titles stand out like links */
    }
    .tool-desc {
        font-size: 1rem;
        color: #bbb;
        margin-top: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ---- Tool Cards ----
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <a href="/Emissions_Reduction_Pathways" target="_self" style="text-decoration: none;">
            <div class="tool-card">
                <div class="tool-icon">📉</div>
                <div class="tool-title">Emissions Reduction Pathways</div>
                <div class="tool-desc">Discover reduction opportunities across sectors, regions, and assets.</div>
            </div>
        </a>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        """
        <a href="/Inventory_Comparison" target="_self" style="text-decoration: none;">
            <div class="tool-card">
                <div class="tool-icon">📒</div>
                <div class="tool-title">Inventory Comparison</div>
                <div class="tool-desc">Compare Climate TRACE data with organizational inventories such as EDGAR or UNFCCC.</div>
            </div>
        </a>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        """
        <a href="https://climatetrace.org/explore#admin=&gas=co2e&year=2024&timeframe=100&sector=&asset=" target="_blank" style="text-decoration: none;">
            <div class="tool-card">
                <div class="tool-icon">🗺️</div>
                <div class="tool-title">Map Explorer</div>
                <div class="tool-desc">Browse global emissions data interactively on the Climate TRACE world map.</div>
            </div>
        </a>
        """,
        unsafe_allow_html=True
    )

with col2:
    st.markdown(
        """
        <a href="/Monthly_Trends" target="_self" style="text-decoration: none;">
            <div class="tool-card">
                <div class="tool-icon">📊</div>
                <div class="tool-title">Monthly Trends</div>
                <div class="tool-desc">Track month-over-month emissions patterns and sector activity worldwide.</div>
            </div>
        </a>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        """
        <a href="/Asset_Finder" target="_self" style="text-decoration: none;">
            <div class="tool-card">
                <div class="tool-icon">📍</div>
                <div class="tool-title">Asset Finder</div>
                <div class="tool-desc">Find assets within a specified kilometer radius.</div>
            </div>
        </a>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        """
        <a href="https://climatetrace.org/air-pollution" target="_blank" style="text-decoration: none;">
            <div class="tool-card">
                <div class="tool-icon">🏭</div>
                <div class="tool-title">Air Pollution Explorer</div>
                <div class="tool-desc">Visualize air pollution in your city and how emitters expose you to harmful particles.</div>
            </div>
        </a>
        """,
        unsafe_allow_html=True
    )

# ---- Footer link ----
st.markdown(
    """
    <div style='text-align: center; margin-top: 3rem;'>
        <a href='https://climatetrace.org' target='_blank'
           style='text-decoration: none; font-size: 1.5rem; color: #1f77ff;'>
           🌍 Visit the <span style='font-weight:600;'>Climate TRACE</span> website!
        </a>
    </div>
    """,
    unsafe_allow_html=True
)
