import streamlit as st
import duckdb
import re
import pandas as pd
from config import CONFIG
from utils.utils import *
from utils.queries import *

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
    sector_col, subsector_col, gas_col, year_col = st.columns(4)

    with sector_col:
        selected_sector= st.selectbox(
            "Sector",
            options=abatement_subsector_options.keys())

    with subsector_col:
        subsector_options = abatement_subsector_options
        selected_subsector = st.selectbox(
            "Subsector",
            options=subsector_options[selected_sector])

    with gas_col:
        selected_gas = st.selectbox(
            "Gas",
            options=['co2e_100yr', 'ch4'],
            disabled=True)

    with year_col:
        selected_year = st.selectbox(
            "Year",
            options=[2024],
            disabled=True)

    ##### QUERY DATA -------
    con = duckdb.connect()

    # determine sector type
    sector_type = return_sector_type(selected_sector)

    # find asset information for highlighting
    query_assets_filter = create_assets_filter_sql(annual_asset_path, selected_subsector, selected_year)
    df_assets_filter = con.execute(query_assets_filter).df()
    
    # query all assets using selected info and add gadm information
    query_assets = find_sector_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year)
    df_assets = con.execute(query_assets).df()
    df_assets =  relabel_regions(df_assets)

    ##### SUMMARIZE KEY METRICS -------
    activity_unit = df_assets['activity_units'][0]
    total_ers = df_assets['strategy_name'].nunique()
    total_emissions = df_assets['emissions_quantity'].sum()
    total_assets = df_assets['asset_id'].nunique()
    total_countries = df_assets['iso3_country'].nunique()
    total_ba = df_assets['balancing_authority_region'].nunique()

    ##### DROPDOWN MENU: METRIC, GROUP, COLOR, HIGHLIGHT -------
    metric_col, group_col, color_col, asset_col = st.columns(4)

    with metric_col:
        if total_ers > 0:
            metric_options = ['emissions_factor', 'emissions_quantity', 'asset_reduction_potential', 'net_reduction_potential']
        else:
            metric_options = ['emissions_factor', 'emissions_quantity']
        selected_metric= st.selectbox(
            "Metric",
            options=metric_options)
        
    with group_col:
        if selected_subsector == 'electricity-generation':
            group_options = ['balancing_authority_region', 'country']
        elif sector_type == 'asset':
            group_options=['asset', 'country']
        else:
            group_options= ['country']
        selected_group = st.selectbox(
            "Group type",
            options=group_options)

    with color_col:
        selected_color = st.selectbox(
            "Color group",
            options=['unfccc_annex', 'em_finance', 'continent', 'developed_un', 'sector'])

    with asset_col:
        if selected_group == 'asset':
            asset_options = 'selected_asset_list'
        elif selected_group == 'country':
            asset_options = 'country_name'
        else:
            asset_options = 'balancing_authority_region'
        selected_assets = st.multiselect(
            "Assets to highlight",
            options=df_assets_filter[asset_options].unique(),
            default=[])
        if selected_group == 'asset':
            selected_assets_list = [int(re.search(r'\((\d+)\)', asset).group(1)) for asset in selected_assets]
        else:
            selected_assets_list = selected_assets

    ##### ADD DESCRIPTIONS FOR SECTORS -------
    
    iron_and_steel = (
        f"The iron and steel sector emits approximately <b>{round(total_emissions / 1000000000, 1)} billion tons of CO₂</b> equivalent worldwide "
        f"each year. One of the most effective strategies to reduce these emissions is upgrading steel plants with greener technologies "
        f"such as Direct Reduced Iron–Electric Arc Furnace (DRI-EAF). <br><br> While greener steel technologies almost always lower "
        f"emissions, their impact is greatest when applied to mills with higher-emitting existing technology types, strong suitability "
        f"for conversion to low-emission options like DRI-EAF, and access to cleaner electricity sources in the local grid. "
        f"Climate TRACE analyzed the world's largest {total_assets:,} steel mills to determine which facilities combine "
        f"these factors most effectively. The chart below shows the impact of all opportunities, ranked by "
        f"the emissions reduction potential per ton of steel produced using cleaner technology.")
    
    solid_waste_disposal = (
        f"The solid waste sector emits million tons of methane "
        f"(equivalent to  <b>{round(total_emissions / 1000000000, 1)} billion tons of CO₂)</b> worldwide each year. "
        f"One of the most effective strategies for reducing landfill emissions "
        f"is to cover them, particularly at unmanaged dumpsites in emerging economies "
        f"across the global south. <br><br> While covering landfills almost always reduces emissions, "
        f"the impact is greatest for sites with poorer existing coverage and higher organic waste content. "
        f"Drawing on best practices from developed nations, covering landfills with materials such as "
        f"sand and clay can significantly cut methane emissions. Climate TRACE analyzed these characteristics "
        f"across {total_assets:,} of the world’s largest landfills to identify where covering landfills would likely "
        f"offer the greatest emissions reductions per ton of waste covered.")
    
    electricity_generation = (
        f"The electricity sector emits approximately <b>{round(total_emissions / 1000000000, 1)} billion tons of CO₂</b> worldwide each year. "
        f"One of the most effective strategies for reducing emissions in this sector is to build renewable "
        f"energy capacity. Because power grids constantly balance supply and demand, adding renewable energy "
        f"anywhere always displaces generation at nearby 'marginal' power plants on the same grid. <br><br>"
        f"While renewable energy projects almost always cut emissions, their impact is greatest in grids where "
        f"marginal plants rely on fossil fuels—especially highly emissions-intensive fuels such as anthracite coal—"
        f"and operate with low energy efficiency. Climate TRACE analyzed all {total_assets:,} power grids worldwide to pinpoint "
        f"where building renewable energy would achieve the greatest emissions reductions per kilowatt-hour generated. "
        f"The chart below shows the potential impact of all opportunities, ranked by emissions reductions per "
        f"kilowatt-hour of renewable energy produced.")

    summary_solution = {
        'iron-and-steel': iron_and_steel,
        'solid-waste-disposal': solid_waste_disposal, 
        'electricity-generation': electricity_generation}
    
    if selected_subsector not in ['iron-and-steel', 'solid-waste-disposal', 'electricity-generation']:
        summary_text = (f"The {selected_subsector} emits approximately <b>{round(total_emissions / 1000000000, 1)} billion tons of CO₂</b> worldwide each year. "
                        f"More details on effective strategies to reduce emissions in this sector will be available soon.<br><br>"
                        f"Climate TRACE analyzed {total_assets:,} assets worldwide and identified emissions reducing solutions for each asset.")
    else:
        summary_text = (f"{summary_solution[selected_subsector]}")

    # display text
    st.markdown(
        f"""
        <div style="margin-top: 8px; font-size: 17px; line-height: 1.5;">
            {summary_text}
        </div>
        """,
        unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    #### ADD METRICS INFO -------

    df_metrics = df_assets.copy()
    if selected_group == 'asset':
        # define assets using id + country
        df_metrics['id_str'] = df_metrics['asset_name'] + " (" + df_metrics['iso3_country'] + ")"
    elif selected_group == 'country':
        df_metrics['id_str'] = df_metrics['iso3_country'] + ' Average'
    else:
        df_metrics['id_str'] = df_metrics['balancing_authority_region']

    df_metrics = df_metrics.groupby('id_str')[selected_metric].median().reset_index()

    # calculate emissions factors (max, min, avg)
    ef_max = df_metrics[selected_metric].max()
    ef_max_asset = df_metrics[df_metrics[selected_metric] == ef_max]['id_str'].unique()

    ef_min = df_metrics[selected_metric].min()
    ef_min_asset = df_metrics[df_metrics[selected_metric] == ef_min]['id_str'].unique()
    
    ef_avg = df_metrics[selected_metric].median()

    if selected_metric == 'emissions_factor':
        metric_unit = 'emissions factors'
        if len(ef_max_asset) > 2:
            ef_max_asset = ef_max_asset[:2]
            ef_max_asset = ', '.join(map(str, ef_max_asset)) + ', etc.'
        else:
            ef_max_asset = ', '.join(map(str, ef_max_asset))  
        if len(ef_min_asset) > 2:
            ef_min_asset = ef_min_asset[:2]
            ef_min_asset = ', '.join(map(str, ef_min_asset)) + ', etc.'
        else:
            ef_min_asset = ', '.join(map(str, ef_min_asset))
        ef_max = round(ef_max, 3)
        ef_max_title = 'Highest Emissions Factor'
        ef_max_text = f"{ef_max}<br><span style='font-size:0.6em;'>{ef_max_asset}</span>"
        ef_max_color = 'red'
        ef_min = round(ef_min, 3)
        ef_min_title = 'Lowest Emissions Factor'
        ef_min_text = f"{ef_min}<br><span style='font-size:0.6em;'>{ef_min_asset}</span>"
        ef_min_color = 'green'
        ef_avg = round(ef_avg, 3)
        ef_avg_title = 'Average Emissions Factor'
        ef_avg_text = f"{ef_avg}t of CO<sub>2</sub>e<br><span style='font-size:0.6em;'>per {activity_unit}</span>"
    
    elif selected_metric == 'asset_reduction_potential':
        metric_unit = 'emissions reduction potential'
        if len(ef_max_asset) > 1:
            ef_max_asset = ef_max_asset[:1]
            ef_max_asset = ', '.join(map(str, ef_max_asset)) + ', etc.'
        else:
            ef_max_asset = ', '.join(map(str, ef_max_asset))  
        if len(ef_min_asset) > 1:
            ef_min_asset = ef_min_asset[:1]
            ef_min_asset = ', '.join(map(str, ef_min_asset)) + ', etc.'
        else:
            ef_min_asset = ', '.join(map(str, ef_min_asset))
        ef_max = round(ef_max / 1000000, 2)
        ef_max_title = 'Highest Reduction Potential'
        ef_max_text = f"{ef_max} mil tonnes <br><span style='font-size:0.6em;'>{ef_max_asset}</span>"
        ef_max_color = 'teal'
        ef_min = round(ef_min / 1000000, 2)
        ef_min_title = 'Lowest Reduction Potential'
        ef_min_text = f"{ef_min} mil tonnes <br><span style='font-size:0.6em;'>{ef_min_asset}</span>"
        ef_min_color = 'grey'
        ef_avg = round(ef_avg / 1000000, 2)
        ef_avg_title = 'Avg Reduction Potential'
        ef_avg_text = f"{ef_avg} million tonnes of CO<sub>2</sub>e<br><span style='font-size:0.6em;'>per asset</span>"
    
    elif selected_metric == 'net_reduction_potential':
        metric_unit = 'net emissions reduction potential'
        if len(ef_max_asset) > 1:
            ef_max_asset = ef_max_asset[:1]
            ef_max_asset = ', '.join(map(str, ef_max_asset)) + ', etc.'
        else:
            ef_max_asset = ', '.join(map(str, ef_max_asset))  
        if len(ef_min_asset) > 1:
            ef_min_asset = ef_min_asset[:1]
            ef_min_asset = ', '.join(map(str, ef_min_asset)) + ', etc.'
        else:
            ef_min_asset = ', '.join(map(str, ef_min_asset))
        ef_max = round(ef_max / 1000000, 2)
        ef_max_title = 'Highest Total Emissions'
        ef_max_text = f"{ef_max} mil tonnes<br><span style='font-size:0.6em;'>{ef_max_asset}</span>"
        ef_max_color = 'teal'
        ef_min = round(ef_min / 1000000, 2)
        ef_min_title = 'Lowest Total Emissions'
        ef_min_text = f"{ef_min} mil tonnes <br><span style='font-size:0.6em;'>{ef_min_asset}</span>"
        ef_min_color = 'grey'
        ef_avg = round(ef_avg / 1000000, 2)
        ef_avg_title = 'Avg Emissions'
        ef_avg_text = f"{ef_avg} million tonnes of CO<sub>2</sub>e<br><span style='font-size:0.6em;'>per asset</span>"

    elif selected_metric == 'emissions_quantity':
        metric_unit = 'total emissions'
        if len(ef_max_asset) > 1:
            ef_max_asset = ef_max_asset[:1]
            ef_max_asset = ', '.join(map(str, ef_max_asset)) + ', etc.'
        else:
            ef_max_asset = ', '.join(map(str, ef_max_asset))  
        if len(ef_min_asset) > 1:
            ef_min_asset = ef_min_asset[:1]
            ef_min_asset = ', '.join(map(str, ef_min_asset)) + ', etc.'
        else:
            ef_min_asset = ', '.join(map(str, ef_min_asset))
        ef_max = round(ef_max / 1000000, 2)
        ef_max_title = 'Highest Net Reduction Potential'
        ef_max_text = f"{ef_max} mil tonnes<br><span style='font-size:0.6em;'>{ef_max_asset}</span>"
        ef_max_color = 'teal'
        ef_min = round(ef_min / 1000000, 2)
        ef_min_title = 'Lowest Net Reduction Potential'
        ef_min_text = f"{ef_min} mil tonnes <br><span style='font-size:0.6em;'>{ef_min_asset}</span>"
        ef_min_color = 'grey'
        ef_avg = round(ef_avg / 1000000, 2)
        ef_avg_title = 'Avg Net Reduction Potential'
        ef_avg_text = f"{ef_avg} million tonnes of CO<sub>2</sub>e<br><span style='font-size:0.6em;'>per asset</span>"

    # create columns
    select_subsector_col, select_group_col, select_ef_avg_col, select_ef_min_col, select_ef_max_col = st.columns(5)

    with select_subsector_col:
        bordered_metric_abatement("Selected Subsector", selected_subsector)
    with select_group_col:
        bordered_metric_abatement("Selected Group", selected_group)
    with select_ef_avg_col:
        bordered_metric_abatement(ef_avg_title, ef_avg_text)
    with select_ef_min_col:
        bordered_metric_abatement(ef_min_title, ef_min_text, value_color=ef_min_color)
    with select_ef_max_col:
        bordered_metric_abatement(ef_max_title, ef_max_text, value_color=ef_max_color)

    ##### PLOT FIGURE -------
    st.markdown("<br>", unsafe_allow_html=True)
    # define variables
    dict_color, dict_lines = define_color_lines(selected_metric)
    fig = plot_abatement_curve(df_assets, selected_group, selected_color, dict_color, dict_lines, selected_assets_list, selected_metric)

    if selected_group == 'asset':
        total_units = total_assets
        total_units_desc = 'total assets'
    elif selected_group == 'country':
        total_units = total_countries
        total_units_desc = 'countries'
    elif selected_group == 'balancing_authority_region':
        total_units = total_ba
        total_units_desc = 'balancing authority regions'

    st.markdown(
        f"""
        <div style="text-align:left; font-size:24px; margin-top:10px;">
            <b>{selected_subsector} ({selected_year})</b> {metric_unit} - <i>{total_units:,} {total_units_desc}</i>
        </div>
        """,
        unsafe_allow_html=True)

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
    df_table = df_table[['asset_url', 'country_url', 'gadm_1_url', 'gadm_2_url', 'strategy_name', 'emissions_quantity (t CO2e)', 'emissions_factor', 'asset_reduction_potential (t CO2e)', 'net_reduction_potential (t CO2e)']]

    st.markdown(f"### top emitting {selected_subsector} assets")

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
