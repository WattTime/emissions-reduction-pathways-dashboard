import streamlit as st
import base64

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.markdown("<br>", unsafe_allow_html=True)

# Tag added to avoid search engines
st.markdown("""
<meta name="robots" content="noindex,nofollow">
""", unsafe_allow_html=True)

# --- Style cleanup ---
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
    }
    section[data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        height: 100vh !important;
    }

    .tool-card {
        background-color: #262730;
        border: 1px solid #444;
        border-radius: 12px;
        padding: 16px 14px;
        text-align: center;
        transition: all 0.2s ease-in-out;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        color: inherit;
        height: 300px;
        width: 100%;
        box-sizing: border-box;
        position: relative;
    }
    .tool-card:hover {
        border-color: #ff4b4b;
        transform: translateY(-4px);
    }
    /* Static tools (not refreshed monthly): a slightly lighter, cooler slate-teal card */
    .tool-card.static {
        background-color: #29475a;
        border: 1px solid #4f7a8f;
    }
    .tool-card.static:hover {
        border-color: #6cc4e0;
    }
    .card-badge {
        position: absolute;
        top: 10px;
        right: 12px;
        font-size: 0.65rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #bbb;
        border: 1px solid #666;
        border-radius: 999px;
        padding: 1px 8px;
    }
    .tool-card.static .card-badge {
        color: #9fd3e6;
        border-color: #6cc4e0;
    }
    .tool-icon {
        font-size: 4.2rem;
    }
    .tool-title {
        font-size: 1.05rem;
        font-weight: 600;
        margin-top: 6px;
        color: #1f77ff;
        line-height: 1.2;
    }
    .tool-desc {
        font-size: 0.78rem;
        color: #bbb;
        margin-top: 5px;
        line-height: 1.3;
    }
    .tool-card.static .tool-title { color: #6cc4e0; }
    </style>
    """,
    unsafe_allow_html=True
)

# ---- Load logo ----
def get_base64_logo():
    with open("Climate TRACE Logo.png", "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_base64 = get_base64_logo()

# ---- Header ----
st.markdown(
    f"""
    <div style='display: flex; align-items: center; justify-content: center;'>
        <img src="data:image/png;base64,{logo_base64}" width="70" style="margin-right: 15px;" />
        <h1 style="margin: 0; font-size: 2.8em;">Climate TRACE Sandbox</h1>
    </div>
    """,
    unsafe_allow_html=True
)


st.markdown("<br>", unsafe_allow_html=True)

# ---- Tool cards: 2 rows x 4 ----
# (href, icon, title, description, static) -- static=True marks tools built on a frozen
# dataset that is NOT regenerated each month (shown with a different card background).
TOOLS = [
    ("/Sector_Reduction_Pathways", "🧭", "Sector Reduction Pathways",
     "Top-down reduction opportunities by sector and region.", False),
    ("/Abatement_Curve", "📉", "Abatement Curve",
     "Bottom-up reduction potential comparing ERS by difficulty and scale.", False),
    ("/Heat_Map", "🌡️", "Heat Map",
     "Geographic hotspots of reduction potential across sectors and regions.", False),
    ("/Global_Trends", "🌍", "Global Trends",
     "Explore emissions change drivers by geography and sector.", False),
    ("/Ownership", "🗂️", "Ownership",
     "Identify owners and evaluate their asset portfolios.", False),
    ("/Country_Trends", "🌐", "Country Trends",
     "Analyze a country's emissions profile and see how it compares globally.", False),
    ("/ERS_Cost_Analysis", "💰", "ERS Cost Analysis",
     "Cost-effectiveness and marginal cost abatement of ERS, with a cash-flow simulator.", True),
    ("/Electrification", "⚡", "Electrification Scenarios",
     "Scenarios for reaching 35% electrification of global final energy demand.", True),
]


def render_card(href, icon, title, desc, static):
    cls = "tool-card static" if static else "tool-card"
    badge = f'<div class="card-badge">{"Static" if static else "Monthly"}</div>'
    # Keep the original markup shape: the inner lines MUST be indented, or Streamlit's Markdown parser turns the
    # <a> into an empty paragraph and re-wraps every text node in its own link (losing the card text colours).
    # Also never emit a blank line (e.g. from an empty badge) - that ends the HTML block.
    lines = [
        f'<a href="{href}" target="_self" style="text-decoration: none; display: block;">',
        f'    <div class="{cls}">',
    ]
    lines.append(f'        {badge}')
    lines += [
        f'        <div class="tool-icon">{icon}</div>',
        f'        <div class="tool-title">{title}</div>',
        f'        <div class="tool-desc">{desc}</div>',
        '    </div>',
        '</a>',
    ]
    st.markdown("\n".join(lines), unsafe_allow_html=True)


for row_start in range(0, len(TOOLS), 4):
    cols = st.columns(4, gap="medium")
    for col, tool in zip(cols, TOOLS[row_start:row_start + 4]):
        with col:
            render_card(*tool)
    st.markdown("<br>", unsafe_allow_html=True)

# ---- Footer ----
# st.markdown(
#     """
#     <div style='text-align: center; margin-top: 3rem;'>
#         <a href='https://climatetrace.org' target='_blank'
#            style='text-decoration: none; font-size: 1.5rem; color: #1f77ff;'>
#            🌍 Visit the <span style='font-weight:600;'>Climate TRACE</span> website!
#         </a>
#     </div>
#     """,
#     unsafe_allow_html=True
# )
