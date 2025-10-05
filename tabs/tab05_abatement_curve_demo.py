import streamlit as st
import duckdb
import re
import pandas as pd
from config import CONFIG
from utils.utils_demo import *
from utils.queries_demo import *

def show_abatement_curve():

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


    ##### SET UP -------
    # set up data pathways
    annual_asset_path = CONFIG['annual_asset_path']
    gadm_0_path = CONFIG['gadm_0_path']
    gadm_1_path = CONFIG['gadm_1_path']
    gadm_2_path = CONFIG['gadm_2_path']

    ##### DROPDOWN MENU: SECTOR, SUBSECTOR, GAS, YEAR -------
    # add drop-down options for filtering data
    #sector_col, subsector_col, gas_col, year_col = st.columns(4)
    all_sectors = list(abatement_subsector_options.keys())

    selected_sector_default = all_sectors

    with st.expander("Sector"):
        selected_sector_user = st.multiselect(
            "Sector",
            options=all_sectors,
            default=[]
        )

    if not selected_sector_user:
        selected_sector = selected_sector_default
    else:
        selected_sector = selected_sector_user
    subsector_options = [
        subsector
        for sector in selected_sector
        for subsector in abatement_subsector_options[sector]]

    selected_subsector_default = subsector_options

    with st.expander("Subsector"):
        selected_subsector_user = st.multiselect(
            "Subsector",
            options=subsector_options,
            default=[]
        )

    if not selected_subsector_user:
        selected_subsector = selected_subsector_default
    else:
        selected_subsector = selected_subsector_user

    selected_year = 2024

    ##### QUERY DATA -------
    con = duckdb.connect()

    # determine sector type
    # sector_type = return_sector_type(selected_sector)

    # find asset information for highlighting
    query_assets_filter = create_assets_filter_sql(annual_asset_path, selected_subsector, selected_year)
    df_assets_filter = con.execute(query_assets_filter).df()
    
    # query all assets using selected info and add gadm information
    print("getting asset and country-subsector data")
    country_sector_sql = query_country_sector(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year)
    top_1000_assets_sql = query_top_1000_assets(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year)
    
    # country-subsector data
    df_country_subsector = con.execute(country_sector_sql).df()
    df_country_subsector =  relabel_regions(df_country_subsector)

    # top 1000 asset data
    df_top_1000_assets = con.execute(top_1000_assets_sql).df()
    df_top_1000_assets =  relabel_regions(df_top_1000_assets)

    ##### SUMMARIZE KEY METRICS -------
    # activity_unit = df_assets['activity_units'][0]
    print("aggregating totals...")
    total_ers = df_country_subsector['strategy_name'].nunique()
    total_emissions = df_country_subsector['emissions_quantity'].sum()
    total_reductions = df_country_subsector['net_reduction_potential'].sum()
    
    # changing this to sum asset count
    total_assets = df_country_subsector['asset_count'].sum()
    total_countries = df_country_subsector['iso3_country'].nunique()
    total_ba = df_country_subsector['balancing_authority_region'].nunique()

    ##### DROPDOWN MENU: METRIC, GROUP, COLOR, HIGHLIGHT -------
    metric_col, group_col, color_col, asset_col = st.columns(4)

    with metric_col:
        metric_options = ['Version 1', 'Version 2']
        # if total_ers > 0:
        #     metric_options = ['emissions_factor', 'asset_reduction_potential', 'net_reduction_potential']
        # else:
        #     metric_options = ['emissions_factor']
        selected_version= st.selectbox(
            "Version",
            options=metric_options)
    
    if selected_version == 'Version 1':
        selected_metric = 'net_reduction_potential'
    else:
        selected_metric = 'emissions_quantity'

    with group_col:
        selected_group = st.selectbox(
            "Group type",
            options=['asset', 'country'])

    with color_col:
        selected_color = st.selectbox(
            "Color group",
            options=['sector', 'continent', 'unfccc_annex'])

    with asset_col:
        if selected_group == 'asset':
            asset_options = df_assets_filter.sort_values('net_reduction_potential', ascending=False).head(1000)['selected_asset_list'].unique()
        elif selected_group == 'country':
            asset_options = df_assets_filter['country_name'].unique()
        selected_assets = st.multiselect(
            "Assets to highlight",
            options=asset_options,
            default=[])
        if selected_group == 'asset':
            selected_assets_list = [int(re.search(r'\((\d+)\)', asset).group(1)) for asset in selected_assets]
        else:
            selected_assets_list = selected_assets

    ##### ADD DESCRIPTIONS FOR SECTORS -------
    
    summary_text = (f"<b>Total Emissions:</b> {round(total_emissions / 1000000000, 1)} billion tons of CO₂ <br>"
                        f"<b>Total Net Reduction Potential:</b> {round(total_reductions / 1000000000, 1)} billion tons of CO₂ ")

    # display text
    st.markdown(
        f"""
        <div style="margin-top: 8px; font-size: 25px; line-height: 1.5;">
            {summary_text}
        </div>
        """,
        unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    ##### PLOT FIGURE -------
    st.markdown("<br>", unsafe_allow_html=True)
    # define variables
    print("plotting abatement curve")
    dict_color, dict_lines = define_color_lines(selected_metric)
    if selected_group == 'asset':
        df_plot = df_top_1000_assets.sort_values(selected_metric, ascending=False).head(1000).copy()
    else:
        df_plot = df_country_subsector.sort_values(selected_metric, ascending=False)
    fig = plot_abatement_curve(df_plot, selected_group, selected_color, dict_color, dict_lines, selected_assets_list, selected_metric)

    if selected_group == 'asset':
        total_units = total_assets
        total_units_desc = 'total assets'
    elif selected_group == 'country':
        total_units = total_countries
        total_units_desc = 'countries'
    elif selected_group == 'balancing_authority_region':
        total_units = total_ba
        total_units_desc = 'balancing authority regions'

    if selected_group == 'asset':
        chart_title = (f"<b>By Top {min(total_assets, 1000)} Assets ({selected_year})</b> - <i>{total_units:,} {total_units_desc}</i>")
    else:
        chart_title = (f"<b>By Country ({selected_year})</b> - <i>{total_units:,} {total_units_desc}</i>")
    # noteee: to fix
    st.markdown(
        f"""
        <div style="text-align:left; font-size:24px; margin-top:10px;">
            {chart_title}
        </div>
        """,
        unsafe_allow_html=True)

    # st.markdown(
    #     f"""
    #     <div style="text-align:left; font-size:24px; margin-top:10px;">
    #         <b>{selected_subsector} ({selected_year})</b> {metric_unit} - <i>{total_units:,} {total_units_desc}</i>
    #     </div>
    #     """,
    #     unsafe_allow_html=True)

    st.plotly_chart(fig, use_container_width=True)

    ##### EMISSIONS REDUCING SOLUTIONS -------
    st.markdown(f"### {total_ers} emissions-reducing solutions")

    # create a table to summarize ers for sector
    query_ers = summarize_ers_sql(annual_asset_path, selected_subsector, selected_year)
    ers_table = con.execute(query_ers).df()

    st.dataframe(
        ers_table,
        use_container_width=True,
        row_height=80,
        column_config={
            "strategy_description": st.column_config.Column(width="large"),
            "assets_impacted": st.column_config.NumberColumn(format="localized"),
            "total_asset_reduction_potential": st.column_config.NumberColumn(format="localized"),
            "total_net_reduction_potential": st.column_config.NumberColumn(format="localized")})

    # create a table with all assets + ERS info
    query_table = create_table_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year)
    df_table = con.execute(query_table).df()

    # create urls to link info to climate trace website
    df_table['asset_url'] = df_table.apply(make_asset_url, axis=1)
    df_table['country_url'] = df_table.apply(make_country_url, axis=1)
    df_table['gadm_1_url'] = df_table.apply(make_state_url, axis=1)
    df_table['gadm_1_url'].fillna('', inplace=True)
    df_table['gadm_2_url'] = df_table.apply(make_county_url, axis=1)
    df_table['gadm_2_url'].fillna('', inplace=True)

    # filter + format table
    df_table = df_table[['subsector', 'asset_url', 'country_url', 'gadm_1_url', 'gadm_2_url', 'strategy_name', 'emissions_quantity (t CO2e)', 'emissions_factor', 'asset_reduction_potential (t CO2e)', 'net_reduction_potential (t CO2e)']]

    # NOTEEEE: TO FIX
    # st.markdown(f"### top emitting {selected_subsector} assets")
    st.markdown(f"### top emitting 200 reduction opportunities")

    # display table
    st.dataframe(
        df_table,
        use_container_width=True,
        height=600,
        column_config={
            "asset_url": st.column_config.LinkColumn("asset_name", display_text=r"admin=([^&]+)"),
            "country_url": st.column_config.LinkColumn("country", display_text=r'admin=([^:]+)'),
            "gadm_1_url": st.column_config.LinkColumn("state / province", display_text=r'admin=(.+?)--'),
            "gadm_2_url": st.column_config.LinkColumn("county / municipality / district", display_text=r'admin=(.+?)--'),
            "emissions_quantity (t CO2e)": st.column_config.NumberColumn(format="localized"),
            "asset_reduction_potential (t CO2e)": st.column_config.NumberColumn(format="localized"),
            "net_reduction_potential (t CO2e)": st.column_config.NumberColumn(format="localized")}
    )

# import os, psutil, time, sys, traceback
# print("=== DEBUG: Starting tab02_abatement_curve_tab.py ===", flush=True)

# try:
#     print("Importing libraries...", flush=True)
#     import streamlit as st
#     import duckdb
#     import re
#     import pandas as pd
#     from config import CONFIG
#     from utils.utils_demo import *
#     from utils.queries_demo import *
#     print("✅ All imports successful", flush=True)

#     def show_abatement_curve():
#         print("=== show_abatement_curve() called ===", flush=True)

#         st.markdown(
#             """
#             <style>
#             /* Hide the sidebar completely */
#             section[data-testid="stSidebar"] {
#                 display: none;
#             }
#             /* Hide the sidebar collapse/expand arrow */
#             [data-testid="collapsedControl"] {
#                 display: none;
#             }
#             </style>
#             """,
#             unsafe_allow_html=True
#         )

#         ##### SET UP -------
#         print("Setting up CONFIG paths...", flush=True)
#         annual_asset_path = CONFIG['annual_asset_path']
#         gadm_0_path = CONFIG['gadm_0_path']
#         gadm_1_path = CONFIG['gadm_1_path']
#         gadm_2_path = CONFIG['gadm_2_path']
#         print(f"✅ Loaded paths: {annual_asset_path}, {gadm_0_path}", flush=True)

#         ##### DROPDOWN MENU -------
#         print("Building dropdowns...", flush=True)
#         all_sectors = list(abatement_subsector_options.keys())
#         selected_sector_default = all_sectors

#         with st.expander("Sector"):
#             selected_sector_user = st.multiselect(
#                 "Sector",
#                 options=all_sectors,
#                 default=[]
#             )

#         if not selected_sector_user:
#             selected_sector = selected_sector_default
#         else:
#             selected_sector = selected_sector_user

#         subsector_options = [
#             subsector
#             for sector in selected_sector
#             for subsector in abatement_subsector_options[sector]]

#         selected_subsector_default = subsector_options

#         with st.expander("Subsector"):
#             selected_subsector_user = st.multiselect(
#                 "Subsector",
#                 options=subsector_options,
#                 default=[]
#             )

#         if not selected_subsector_user:
#             selected_subsector = selected_subsector_default
#         else:
#             selected_subsector = selected_subsector_user

#         selected_year = 2024
#         print(f"✅ Selected subsectors: {selected_subsector[:5]}...", flush=True)

#         ##### QUERY DATA -------
#         print("Connecting to DuckDB...", flush=True)
#         con = duckdb.connect()
#         print("✅ DuckDB connected", flush=True)

#         print("Creating asset filter query...", flush=True)
#         query_assets_filter = create_assets_filter_sql(annual_asset_path, selected_subsector, selected_year)
#         print(f"Asset filter SQL:\n{query_assets_filter[:200]}...", flush=True)
#         df_assets_filter = con.execute(query_assets_filter).df()
#         print(f"✅ df_assets_filter loaded ({len(df_assets_filter):,} rows)", flush=True)
        
#         print("Preparing queries for country/subsector and top assets...", flush=True)
#         country_sector_sql = query_country_sector(
#             annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path,
#             selected_subsector, selected_year)
#         top_1000_assets_sql = query_top_1000_assets(
#             annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path,
#             selected_subsector, selected_year)

#         print("Executing country/subsector query...", flush=True)
#         df_country_subsector = con.execute(country_sector_sql).df()
#         print(f"✅ df_country_subsector loaded ({len(df_country_subsector):,} rows)", flush=True)
#         df_country_subsector = relabel_regions(df_country_subsector)

#         print("Executing top_1000_assets query...", flush=True)
#         df_top_1000_assets = con.execute(top_1000_assets_sql).df()
#         print(f"✅ df_top_1000_assets loaded ({len(df_top_1000_assets):,} rows)", flush=True)
#         df_top_1000_assets = relabel_regions(df_top_1000_assets)

#         ##### SUMMARIZE -------
#         print("Aggregating totals...", flush=True)
#         total_ers = df_country_subsector['strategy_name'].nunique()
#         total_emissions = df_country_subsector['emissions_quantity'].sum()
#         total_reductions = df_country_subsector['net_reduction_potential'].sum()
#         total_assets = df_country_subsector['asset_count'].sum()
#         total_countries = df_country_subsector['iso3_country'].nunique()
#         total_ba = df_country_subsector['balancing_authority_region'].nunique()
#         print(f"✅ Totals aggregated (ERS={total_ers}, assets={total_assets:,})", flush=True)

#         ##### DROPDOWNS -------
#         print("Building metrics dropdowns...", flush=True)
#         metric_col, group_col, color_col, asset_col = st.columns(4)
#         with metric_col:
#             metric_options = ['Version 1', 'Version 2']
#             selected_version= st.selectbox("Version", options=metric_options)
#         selected_metric = 'net_reduction_potential' if selected_version == 'Version 1' else 'emissions_quantity'

#         with group_col:
#             selected_group = st.selectbox("Group type", options=['asset', 'country'])

#         with color_col:
#             selected_color = st.selectbox("Color group", options=['sector', 'continent', 'unfccc_annex'])

#         with asset_col:
#             if selected_group == 'asset':
#                 asset_options = df_assets_filter.sort_values(
#                     'net_reduction_potential', ascending=False
#                 ).head(1000)['selected_asset_list'].unique()
#             elif selected_group == 'country':
#                 asset_options = df_assets_filter['country_name'].unique()
#             selected_assets = st.multiselect("Assets to highlight", options=asset_options, default=[])
#             if selected_group == 'asset':
#                 selected_assets_list = [int(re.search(r'\((\d+)\)', asset).group(1)) for asset in selected_assets]
#             else:
#                 selected_assets_list = selected_assets
#         print("✅ Dropdowns ready", flush=True)

#         ##### SUMMARY TEXT -------
#         summary_text = (
#             f"<b>Total Emissions:</b> {round(total_emissions / 1e9, 1)} billion tons of CO₂ <br>"
#             f"<b>Total Net Reduction Potential:</b> {round(total_reductions / 1e9, 1)} billion tons of CO₂ "
#         )
#         st.markdown(
#             f"""
#             <div style="margin-top: 8px; font-size: 25px; line-height: 1.5;">
#                 {summary_text}
#             </div>
#             """,
#             unsafe_allow_html=True
#         )
#         st.markdown("<br>", unsafe_allow_html=True)
#         print("✅ Summary section rendered", flush=True)

#         ##### PLOT FIGURE -------
#         print("Plotting abatement curve...", flush=True)
#         dict_color, dict_lines = define_color_lines(selected_metric)
#         if selected_group == 'asset':
#             df_plot = df_top_1000_assets.sort_values(selected_metric, ascending=False).head(1000).copy()
#         else:
#             df_plot = df_country_subsector.sort_values(selected_metric, ascending=False)

#         fig = plot_abatement_curve(
#             df_plot, selected_group, selected_color, dict_color, dict_lines,
#             selected_assets_list, selected_metric
#         )
#         print("✅ Plot generated", flush=True)

#         st.plotly_chart(fig, use_container_width=True)
#         print("✅ Chart rendered", flush=True)

#         ##### TABLES -------
#         print("Summarizing ERS...", flush=True)
#         query_ers = summarize_ers_sql(annual_asset_path, selected_subsector, selected_year)
#         ers_table = con.execute(query_ers).df()
#         print(f"✅ ERS table loaded ({len(ers_table):,} rows)", flush=True)
#         st.dataframe(ers_table, use_container_width=True, row_height=80)

#         print("Building final table...", flush=True)
#         query_table = create_table_assets_sql(
#             annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year
#         )
#         df_table = con.execute(query_table).df()
#         print(f"✅ df_table loaded ({len(df_table):,} rows)", flush=True)

#         df_table['asset_url'] = df_table.apply(make_asset_url, axis=1)
#         df_table['country_url'] = df_table.apply(make_country_url, axis=1)
#         df_table['gadm_1_url'] = df_table.apply(make_state_url, axis=1)
#         df_table['gadm_1_url'].fillna('', inplace=True)
#         df_table['gadm_2_url'] = df_table.apply(make_county_url, axis=1)
#         df_table['gadm_2_url'].fillna('', inplace=True)
#         print("✅ URL columns created", flush=True)

#         df_table = df_table[['subsector', 'asset_url', 'country_url', 'gadm_1_url',
#                             'gadm_2_url', 'strategy_name', 'emissions_quantity (t CO2e)',
#                             'emissions_factor', 'asset_reduction_potential (t CO2e)',
#                             'net_reduction_potential (t CO2e)']]

#         st.markdown(f"### top emitting 200 reduction opportunities")
#         st.dataframe(df_table, use_container_width=True, height=600)
#         print("✅ Final table rendered", flush=True)

#         print("=== show_abatement_curve() finished successfully ===", flush=True)

# except Exception as e:
#     print("💥 ERROR in tab02_abatement_curve_tab.py!", flush=True)
#     traceback.print_exc()
#     st.error(f"App crashed: {e}")
