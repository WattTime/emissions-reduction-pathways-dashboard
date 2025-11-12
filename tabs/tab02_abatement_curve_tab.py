import os, psutil, time, sys, traceback
import streamlit as st
import duckdb
import re
import pandas as pd
import os
import sys
import sys
import os
from config import CONFIG
from utils.utils import *
from utils.queries import *


def show_abatement_curve():

    print("=== DEBUG: Starting tab02_abatement_curve_tab.py ===", flush=True)

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

    con = duckdb.connect()

    ##### DROPDOWN MENU: SECTOR, SUBSECTOR -------
    # add drop-down options for filtering data

    all_sectors = list(abatement_subsector_options.keys())

    with st.expander("Sector & Subsector", expanded=True):
        selected_sector_user = st.multiselect(
            "Sector",
            options=all_sectors,
            default=['manufacturing']
        )
        if not selected_sector_user:
            selected_sector = all_sectors
        else:
            selected_sector = selected_sector_user

        subsector_options = [
            subsector
            for sector in selected_sector
            for subsector in abatement_subsector_options[sector]
        ]
        subsector_options.sort()

        selected_subsector_user = st.multiselect(
            "Subsector",
            options=subsector_options,
            default=subsector_options[0]
        )
        if not selected_subsector_user:
            selected_subsector = subsector_options
        else:
            selected_subsector = selected_subsector_user

    selected_year = 2024


    ##### DROPDOWN FOR COUNTRY -------
    # add drop-down options for geography

    country_rows = con.execute(
        f"SELECT DISTINCT iso3_country, country_name FROM '{annual_asset_path}' WHERE country_name IS NOT NULL order by iso3_country"
    ).fetchall()

    country_map = {row[0]: row[1] for row in country_rows}
    all_countries = list(country_map.keys())

    with st.expander("Region"):
        selected_country_user = st.multiselect(
            "Country",
            options=all_countries,
            default=[]
        )

    if not selected_country_user:
        selected_country = all_countries
    else:
        selected_country = selected_country_user

    if len(selected_subsector) > 1:
        multisector = True
    else:
        multisector = False
    
    ##### DROPDOWN MENU: AXES, GROUP, COLOR -------
    # set up selections

    #x_axis_col, y_axis_col, group_col, color_col, threshold_col = st.columns(5)
    x_axis_col, y_axis_col, group_col, color_col = st.columns(4)

    with x_axis_col:
        if multisector:
            x_axis_options = ['emissions_quantity', 'net_reduction_potential', 'num_assets']
        else:
            x_axis_options = ['activity', 'emissions_quantity', 'net_reduction_potential', 'num_assets']
        selected_x = st.selectbox(
            "Set x-axis",
            options=x_axis_options)
        
    with y_axis_col:
        if selected_x in ['num_assets', 'activity']:
            y_axis_options = ['emissions_factor', 'asset_difficulty_score', 'emissions_quantity', 'net_reduction_potential']
        else:
            y_axis_options = ['emissions_factor', 'asset_difficulty_score']
        selected_y = st.selectbox(
            "Set y-axis",
            options=y_axis_options
        )

    with group_col:
        selected_group = st.selectbox(
            "Group by",
            # options=['asset', 'country', 'subsector', 'strategy_name'])
            options=['asset'])

    with color_col:
        selected_color = st.selectbox(
            "Color by",
            options=['sector', 'continent', 'unfccc_annex'])
        
    # with threshold_col:
    #     selected_threshold = st.text_input("Add threshold")
    selected_threshold = 0

    ##### QUERY DATA -------

    # query assets based on selection
    query_df_assets = find_sector_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year, selected_country)

    print("Getting asset data")
    df_assets = con.execute(query_df_assets).df()
    df_assets =  relabel_regions(df_assets)
    
    print("✅ Retrieved asset data.", flush=True)

    ##### SUMMARIZE KEY METRICS -------
    # totals for ers, emissions, reduction, assets, countries

    query_totals = summarize_totals_sql(annual_asset_path, selected_subsector, selected_year, selected_country)
    df_totals = con.execute(query_totals).df()
    total_ers = df_totals['total_ers'][0]
    total_emissions = df_totals['total_emissions'][0]
    total_reductions = df_totals['total_reductions'][0]
    # TODO: REMOVE LATER
    if selected_subsector == ['electricity-generation']:
        NUMBER_OF_RENEWABLES = st.number_input('Number of renewable plants', value=1000)
        RENEWABLE_MWH = st.number_input('Renewable Energy (MWh)', value=9000000000)
        total_assets = df_totals['total_assets'][0] + int(NUMBER_OF_RENEWABLES)
    else:
        total_assets = df_totals['total_assets'][0]
    total_countries = df_totals['total_countries'][0]
    print("✅ Aggregated totals...", flush=True)

    if selected_group == 'asset':
        selected_list = 'selected_asset_list'
        highlight_text = "Assets"
        total_units = total_assets
        total_units_desc = 'total assets'
        chart_title = (f"<b>By Assets ({selected_year})</b> - <i>{total_units:,} {total_units_desc}</i>")
    elif selected_group == 'country':
        selected_list = 'selected_country_list'
        highlight_text = "Country-subsectors"
        total_units = total_countries
        total_units_desc = 'countries'
        chart_title = (f"<b>By Country ({selected_year})</b> - <i>{total_units:,} {total_units_desc}</i>")
    elif selected_group == 'subsector':
        # TODO: FIX
        selected_list = 'selected_subsector_list'
        highlight_text = "Subsectors"
        total_units = total_countries
        total_units_desc = 'countries'
        chart_title = (f"<b>By Country ({selected_year})</b> - <i>{total_units:,} {total_units_desc}</i>")
    elif selected_group == 'strategy_name':
        # TODO: FIX
        selected_list = 'selected_strategy_list'
        highlight_text = "Strategies"
        total_units = total_countries
        total_units_desc = 'countries'
        chart_title = (f"<b>By Country ({selected_year})</b> - <i>{total_units:,} {total_units_desc}</i>")

    ##### ADD HIGH-LEVEL EMISSIONS / REDUCTION INFO -------
    # emissions vs. reductions

    summary_text = (
        f"<b>Total Emissions:</b> {round(total_emissions / 1000000000, 1)} billion tons of CO₂ <br>"
        f"<b>Total Net Reduction Potential:</b> {round(total_reductions / 1000000000, 1)} billion tons of CO₂ ({round((total_reductions/total_emissions) * 100, 1)}%)")

    # display text
    st.markdown(
        f"""
        <div style="margin-top: 8px; font-size: 25px; line-height: 1.5;">
            {summary_text}
        </div>
        """,
        unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    ##### ASSET QUERYING -------
    # highlight assets on curve

    if "selected_assets" not in st.session_state:
        st.session_state.selected_assets = []

    # Build your asset options
    asset_options = df_assets[selected_list].unique()

    # Use session_state to store and recall user-selected assets
    selected_assets = st.multiselect(
        highlight_text + " to highlight in curve",
        options=asset_options,
        default=st.session_state.selected_assets,
        key = "selected_assets"
    )

    st.markdown("<br>", unsafe_allow_html=True)


    ##### PLOT FIGURE -------
    # add abatement curve

    # define variables
    dict_color, dict_lines = define_color_lines(selected_y)
    dict_lines={'outlier': {}}
    # TODO: remove later --- electricity generation for COP
    if selected_subsector == ['electricity-generation']:
        columns = ['year', 'asset_id', 'asset_name', 'asset_type', 'iso3_country',
                'country_name', 'balancing_authority_region', 'continent', 'eu', 'oecd',
                'unfccc_annex', 'developed_un', 'em_finance', 'sector', 'subsector',
                'reduction_q_type', 'gid_0', 'gadm_1', 'gid_1', 'gadm_1_name', 'gadm_2',
                'gid_2', 'gadm_2_name', 'activity_units', 'strategy_name', 'activity',
                'capacity', 'emissions_quantity', 'emissions_factor',
                'asset_reduction_potential', 'net_reduction_potential',
                'asset_difficulty_score', 'selected_asset_list',
                'selected_country_list', 'selected_subsector_list',
                'selected_strategy_list']       

        renewables_df = pd.DataFrame(index=range(int(NUMBER_OF_RENEWABLES)))

        # Assign all columns at once
        renewables_df = renewables_df.assign(
            activity = float(RENEWABLE_MWH / NUMBER_OF_RENEWABLES),
            year = 2024,
            asset_id = renewables_df.index,
            asset_name = 'Renewables Dummy',
            asset_type = 'Renewables',
            iso3_country = 'USA',
            country_name = 'TEST',
            balancing_authority_region = 'Test',
            continent = 'North America',
            eu = True,
            oecd = True,
            unfccc_annex = True,
            developed_un = True,
            em_finance = True,
            sector = 'power',
            subsector = 'electricity-generation',
            reduction_q_type = False,
            gid_0 = None,
            gadm_1 = None,
            gid_1 = None,
            gadm_1_name = None,
            gadm_2 = None,
            gid_2 = None,
            gadm_2_name = None,
            activity_units = 'MWh',
            strategy_name = None,
            capacity = None,
            emissions_quantity = 0,
            emissions_factor = 0,
            asset_reduction_potential = 0,
            net_reduction_potential = 0,
            asset_difficulty_score = 0,
            selected_asset_list = None,
            selected_country_list = None,
            selected_subsector_list = None,
            selected_strategy_list = None
        )
        df_assets = pd.concat([df_assets, renewables_df])
    
    fig, df_csv = plot_abatement_curve(df_assets, selected_group, selected_color, dict_color, dict_lines, selected_list, selected_assets, selected_x, selected_y, selected_threshold, fill=True)
    
    st.download_button(
        label="Download data as CSV",
        data=df_csv,
        file_name="abatement_data.csv",
        mime="text/csv"
    )
    print("✅ Plot generated", flush=True)

    st.markdown(
        f"""
        <div style="text-align:left; font-size:24px; margin-top:10px;">
            {chart_title}
        </div>
        """,
        unsafe_allow_html=True)

    st.plotly_chart(fig, use_container_width=True)
    print("✅ Rendered abatement curve chart", flush=True)

    ##### EMISSIONS REDUCING SOLUTIONS -------
    # summarize all ers within selection

    st.markdown(f"### {total_ers} Emissions Reduction Solutions (ERS) Strategies")

    # create a table to summarize ers for sector
    query_ers = summarize_ers_sql(annual_asset_path, selected_subsector, selected_year, selected_country)
    ers_table = con.execute(query_ers).df()

    st.dataframe(
        ers_table,
        use_container_width=True,
        row_height=80,
        column_config={
            "strategy_description": st.column_config.Column(width="large"),
            "assets_impacted": st.column_config.NumberColumn(format="localized"),
            "emissions_quantity": st.column_config.NumberColumn(format="localized"),
            "total_asset_reduction_potential": st.column_config.NumberColumn(format="localized"),
            "total_net_reduction_potential": st.column_config.NumberColumn(format="localized")})
    print(f"✅ ERS table loaded ({len(ers_table):,} rows)", flush=True)

    # create a table with all assets + ERS info
    query_table = create_table_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year, selected_country)
    df_table = con.execute(query_table).df()

    # create urls to link info to climate trace website
    df_table['asset_url'] = df_table.apply(make_asset_url, axis=1)
    df_table['country_url'] = df_table.apply(make_country_url, axis=1)
    df_table['gadm_1_url'] = df_table.apply(make_state_url, axis=1)
    df_table['gadm_1_url'] = df_table['gadm_1_url'].fillna('')
    df_table['gadm_2_url'] = df_table.apply(make_county_url, axis=1)
    df_table['gadm_2_url'] = df_table['gadm_2_url'].fillna('')
    print("✅ URL columns created", flush=True)

    # filter + format table
    df_table = df_table[['subsector', 'asset_url', 'country_url', 'gadm_1_url', 'gadm_2_url', 'strategy_name', 'emissions_quantity (t CO2e)', 'emissions_factor', 'asset_reduction_potential (t CO2e)', 'net_reduction_potential (t CO2e)']]

    st.markdown("### Top 200 Reduction Opportunities")

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
    print("✅ Final table rendered", flush=True)

    con.close()