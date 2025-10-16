import streamlit as st
import streamlit.components.v1 as components
import duckdb
import json
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from matplotlib.colors import LinearSegmentedColormap
import base64
from calendar import month_name
import calendar
from collections import defaultdict
from config import CONFIG
from utils.utils import *
from utils.queries import *
import logging


def show_reduction_heatmap():

    logging.getLogger("streamlit.dataframe_util").setLevel(logging.ERROR)

    st.markdown(
        """
        <style>
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

    # configure data paths and region options for querying
    annual_asset_path = CONFIG['annual_asset_path']
    city_path = CONFIG['city_path']
    gadm_0_path = CONFIG['gadm_0_path']
    gadm_1_path = CONFIG['gadm_1_path']
    gadm_2_path = CONFIG['gadm_2_path']
    country_subsector_totals_path = CONFIG['country_subsector_totals_path']
    percentile_path = CONFIG['percentile_path']
    region_options = CONFIG['region_options']
    gadm_0_path = CONFIG['gadm_0_path']

    con = duckdb.connect()

    country_rows = con.execute(
            f"SELECT DISTINCT country_name, iso3_country FROM '{gadm_0_path}' WHERE country_name IS NOT NULL order by country_name"
        ).fetchall()

    country_map = {row[0]: row[1] for row in country_rows}
    
    unique_countries = list(country_map.keys())

    st.markdown("<br>", unsafe_allow_html=True)


    country_dropdown, view_by_dropdown  = st.columns([2,2])

    with country_dropdown:
        
        selected_region = st.selectbox(
            "Country", 
            ["Global"] + unique_countries, 
            key="selected_region_HM",
            #on_change=mark_hm_recompute
        )

        region_condition = map_region_condition(selected_region, country_map)

    country_selected_bool = selected_region != "Global"

    state_selected_bool = False
    with view_by_dropdown:
        if not country_selected_bool:
            state_province_options = ['Select a Country to Enable']
            selected_state_province = st.selectbox(
                "State / Province",
                state_province_options,
                disabled=True,
                key="state_province_selector_HM",
                index=0,
                #on_change=mark_hm_recompute
            )

            state_selected_bool = False

        else:
            col_value = region_condition['column_value']

            state_province_options = ['-- Select State / Province --'] + sorted(
                row[0] for row in con.execute(
                    f"SELECT DISTINCT gadm_1_corrected_name FROM '{gadm_1_path}' WHERE iso3_country = '{col_value}' and gadm_1_name is not null"
                ).fetchall()
            )

            selected_state_province = st.selectbox(
                "State / Province",
                state_province_options,
                disabled=False,
                key="state_province_selector_HM",
                index=0,
                # on_change=reset_city
            )

    if selected_state_province not in ['-- Select State / Province --', 'Select a Country to Enable']:
        state_selected_bool = True


    heatmap_sql = create_heatmap_sql(country_selected_bool=country_selected_bool,
                                     state_selected_bool=state_selected_bool,
                                     region_condition=region_condition,
                                     selected_state_province=selected_state_province,
                                     annual_asset_path=annual_asset_path,
                                     gadm_1_path=gadm_1_path,
                                     gadm_2_path=gadm_2_path)
    
    print(heatmap_sql['sector_summary'])
    
    sector_df = con.execute(heatmap_sql['sector_summary']).df()
    table_df = con.execute(heatmap_sql['table_summary']).df()

    sector_df = sector_df.loc[:, ~sector_df.columns.duplicated()].copy()
    table_df  = table_df.loc[:, ~table_df.columns.duplicated()].copy()

    sector_df = sector_df.reset_index(drop=True)
    table_df = table_df.reset_index(drop=True)

    sector_df.insert(0, "Region", ["Total"])
    if "country_name" in table_df.columns:
        table_df.rename(columns={"country_name": "Region"}, inplace=True)

    # --- Add one empty spacer row between them ---
    spacer = pd.DataFrame(columns=sector_df.columns)
    for col in sector_df.columns:
        if np.issubdtype(sector_df[col].dtype, np.number):
            spacer.at[0, col] = np.nan
        else:
            spacer.at[0, col] = ""

    # --- Combine everything ---
    combined_df = pd.concat([sector_df, spacer, table_df], ignore_index=True)
    combined_df = combined_df.loc[:, ~combined_df.columns.duplicated()].copy()

    combined_df = combined_df.drop(columns=[col for col in combined_df.columns if str(col).strip() == ""], errors="ignore")

    


    # --- Define excluded and numeric columns ---
    excluded_cols = [
        "Region",
        "total_exc_forestry",
        "forestry_and_land_use",
        "total_reduction_potential",
        "asset_count"
    ]
    numeric_cols = [c for c in combined_df.select_dtypes(include=["number"]).columns if c not in excluded_cols]

    # --- Colormap ---
    universal_red_cmap = LinearSegmentedColormap.from_list(
        "universal_red",
        [
            (0.0, "#D3D3D3"),  # neutral low
            (0.3, "#E57373"),  # soft red
            (0.6, "#E53935"),  # medium red
            (1.0, "#B71C1C")   # deep red
        ]
    )

    # --- Custom color function ---
    def mixed_gradient(df):
        colors = pd.DataFrame("", index=df.index, columns=df.columns)

        # find spacer index (where Region is blank)
        spacer_idx = df.index[df["Region"] == ""].tolist()
        spacer_idx = spacer_idx[0] if spacer_idx else None

        # top = horizontal gradient (row 0)
        top = df.loc[0, color_cols]
        top_scaled = (top - top.min()) / (top.max() - top.min() + 1e-9)
        for col in color_cols:
            rgba = universal_red_cmap(top_scaled[col])
            colors.at[0, col] = f"background-color: rgba({int(rgba[0]*255)}, {int(rgba[1]*255)}, {int(rgba[2]*255)}, {rgba[3]})"


        # spacer = light gray filler row (text hidden by matching color)
        if spacer_idx is not None:
            gray_hex = "#E0E0E0"  # same as your background
            for col in df.columns:
                colors.at[spacer_idx, col] = (
                    f"background-color: {gray_hex}; "
                    f"color: {gray_hex}; "           # make text fully blend in
                )

        # lower = vertical gradient (below spacer)
        start_row = spacer_idx + 1 if spacer_idx is not None else 1
        lower = df.loc[start_row:, color_cols]
        lower_scaled = (lower - lower.min()) / (lower.max() - lower.min() + 1e-9)
        for col in color_cols:
            for idx in lower_scaled.index:
                rgba = universal_red_cmap(lower_scaled.loc[idx, col])
                colors.at[idx, col] = f"background-color: rgba({int(rgba[0]*255)}, {int(rgba[1]*255)}, {int(rgba[2]*255)}, {rgba[3]})"

        return colors

    # --- Apply highlight and gradient ---
    def highlight_total_row(row):
        return ['background-color: #303030; color: white;' if row.name == 0 else '' for _ in row]


    # --- Convert to numeric for all non-Region columns ---
    for col in combined_df.columns:
        if col != "Region":
            combined_df[col] = pd.to_numeric(combined_df[col], errors="coerce")

    # --- Define which columns get color vs only formatting ---
    color_cols = [
        "agriculture",
        "buildings",
        "fluorinated_gases",
        "fossil_fuel_operations",
        "manufacturing",
        "mineral_extraction",
        "power",
        "transportation",
        "waste"
    ]

    # --- Identify numeric columns for formatting ---
    numeric_cols = [
        c for c in combined_df.columns
        if c != "Region" and np.issubdtype(combined_df[c].dtype, np.number)
    ]

    # --- Blank out the spacer row properly ---
    spacer_idx = combined_df.index[combined_df["Region"] == ""].tolist()
    if spacer_idx:
        r = spacer_idx[0]
        for c in combined_df.columns:
            combined_df.loc[r, c] = "" if c != "Region" else ""  # all blanks

    # --- Define a safe formatter function ---
    def safe_format(x):
        # Handle missing or None/NaN explicitly
        if x is None or x == "None" or (isinstance(x, float) and np.isnan(x)):
            return ""
        try:
            return f"{float(x):,.0f}"
        except (ValueError, TypeError):
            return ""

    # --- Create the Styler first ---
    combined_styled = (
        combined_df
        .style
        .apply(highlight_total_row, axis=1)
        .apply(lambda df: mixed_gradient(df), axis=None)
    )

    # --- Then apply number formatting ---
    combined_styled = combined_styled.format(
        subset=numeric_cols,
        formatter=safe_format
    )


    # --- Display ---
    st.markdown("### Emissions Reduction Potential by Sector")
    st.dataframe(
        combined_styled, 
        use_container_width=True, 
        hide_index=True,
        height=800
    )
