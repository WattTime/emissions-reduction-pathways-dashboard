import streamlit as st
import duckdb
import pandas as pd
from config import CONFIG
from utils.utils import (relabel_regions, bordered_metric_abatement,
                         define_color_lines, plot_abatement_curve,
                         make_asset_url, make_country_url, make_state_url, make_county_url)

def show_abatement_curve():

    ##### SET UP -------
    # set up data pathways
    annual_asset_path = CONFIG['annual_asset_path']
    gadm_0_path = CONFIG['gadm_0_path']
    gadm_1_path = CONFIG['gadm_1_path']
    gadm_2_path = CONFIG['gadm_2_path']

    # define variables
    dict_color, dict_lines = define_color_lines()

    ##### DROPDOWN MENU: SECTOR, SUBSECTOR, GAS, YEAR -------
    # add drop-down options for filtering data
    sector_col, subsector_col, gas_col, year_col = st.columns(4)

    with sector_col:
        selected_sector= st.selectbox(
            "Sector",
            options=['manufacturing', 'power', 'waste'])

    with subsector_col:
        subsector_options = {
            'manufacturing': ['aluminum', 'cement', 'chemicals', 'food-beverage-tobacco', 'glass', 'iron-and-steel', 
                              'lime', 'other-chemicals', 'other-manufacturing', 'other-metals', 'petrochemical-steam-cracking', 
                              'pulp-and-paper', 'textiles-leather-apparel'],
            'power': ['electricity-generation'],
            'waste': ['solid-waste-disposal']
        }
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

    # find information for highlighting
    query_assets_filter = f'''
        SELECT 
            ae.asset_id,
            ae.asset_name,
            ae.iso3_country,
            ae.country_name,
            ae.balancing_authority_region,
        FROM '{annual_asset_path}' ae
        WHERE 
            subsector = '{selected_subsector}'
            AND year = {selected_year}
    '''
    df_assets_filter = con.execute(query_assets_filter).df()
    df_assets_filter = df_assets_filter.drop_duplicates('asset_id')

    # query all assets using selected info
    query_assets = f'''
        SELECT 
            ae.year,
            ae.asset_id,
            ae.asset_name,
            ae.iso3_country,
            ae.country_name,
            ae.balancing_authority_region,
            ae.continent,
            ae.eu,
            ae.oecd,
            ae.unfccc_annex,
            ae.developed_un,
            ae.em_finance,
            ae.sector,
            ae.subsector,
            ae.gadm_1,
            ae.gadm_2,
            ae.activity_units,
            ae.strategy_name,
            ae.strategy_description,
            ae.mechanism,
            SUM(ae.activity) AS activity,
            SUM(ae.capacity) AS capacity,
            SUM(ae.emissions_quantity) AS emissions_quantity,
            ae.emissions_reduced_at_asset,
            ae.total_emissions_reduced_per_year
        FROM '{annual_asset_path}' ae
        WHERE 
            subsector = '{selected_subsector}'
            AND year = {selected_year}
        GROUP BY
            ae.year,
            ae.asset_id,
            ae.asset_name,
            ae.iso3_country,
            ae.country_name,
            ae.balancing_authority_region,
            ae.continent,
            ae.eu,
            ae.oecd,
            ae.unfccc_annex,
            ae.developed_un,
            ae.em_finance,
            ae.sector,
            ae.subsector,
            ae.gadm_1,
            ae.gadm_2,
            ae.activity_units,
            ae.strategy_name,
            ae.strategy_description,
            ae.mechanism,
            ae.emissions_reduced_at_asset,
            ae.total_emissions_reduced_per_year
    '''
    df_assets = con.execute(query_assets).df()
    df_assets = pd.DataFrame(df_assets)
    df_assets['emissions_factor'] = df_assets['emissions_quantity'] / df_assets['activity']
    df_assets =  relabel_regions(df_assets)

    # add gadm information
    query_gadm_0 = f'''
        SELECT DISTINCT
            gid AS gid_0,
            iso3_country
        FROM '{gadm_0_path}'
        '''
    df_gadm_0 = con.execute(query_gadm_0).df()

    query_gadm_1 = f'''
        SELECT DISTINCT
            gid AS gid_1,
            gadm_id AS gadm_1,
            gadm_1_corrected_name AS gadm_1_name
        FROM '{gadm_1_path}'
        '''
    df_gadm_1 = con.execute(query_gadm_1).df()

    query_gadm_2 = f'''
        SELECT DISTINCT
            gid AS gid_2,
            gadm_2_id AS gadm_2,
            gadm_2_corrected_name AS gadm_2_name
        FROM '{gadm_2_path}'
        '''
    df_gadm_2 = con.execute(query_gadm_2).df()

    df_assets = df_assets.merge(df_gadm_0, how='left', on='iso3_country').merge(df_gadm_1, how='left', on='gadm_1').merge(df_gadm_2, how='left', on='gadm_2')

    ##### SUMMARIZE KEY METRICS -------
    activity_unit = df_assets['activity_units'][0]
    total_emissions = df_assets['emissions_quantity'].sum()
    total_assets = df_assets['asset_id'].nunique()

    ##### DROPDOWN MENU: METRIC, GROUP, COLOR, HIGHLIGHT -------
    metric_col, group_col, color_col, asset_col = st.columns(4)

    with metric_col:
        selected_metric= st.selectbox(
            "Metric",
            options=['emissions_factor'],
            disabled=True)

    with group_col:
        if selected_subsector == 'electricity-generation':
            group_options = ["country", "balancing_authority_region"]
        else:
            group_options= ["asset", "country"]
        selected_group = st.selectbox(
            "Group type",
            options=group_options)

    with color_col:
        selected_color = st.selectbox(
            "Color group",
            options=['unfccc_annex', 'em_finance', 'continent', 'developed_un', 'sector'])

    with asset_col:
        if selected_group == 'asset':
            asset_options = 'asset_name'
        elif selected_group == 'country':
            asset_options = 'country_name'
        else:
            asset_options = 'balancing_authority_region'
        selected_assets = st.multiselect(
            "Assets to highlight",
            options=df_assets_filter[asset_options].unique(),
            default=[])

    ##### ADD DESCRIPTIONS FOR SECTORS -------
    
    iron_and_steel = (
        f"The iron and steel sector emits approximately {round(total_emissions / 1000000000, 1)} billion tons of CO₂ equivalent worldwide "
        f"each year. One of the most effective strategies to reduce these emissions is upgrading steel plants with greener technologies "
        f"such as Direct Reduced Iron–Electric Arc Furnace (DRI-EAF). <br><br> While greener steel technologies almost always lower "
        f"emissions, their impact is greatest when applied to mills with higher-emitting existing technology types, strong suitability "
        f"for conversion to low-emission options like DRI-EAF, and access to cleaner electricity sources in the local grid. "
        f"Climate TRACE analyzed the world's largest {total_assets} steel mills to determine which facilities combine "
        f"these factors most effectively. The chart below shows the impact of all opportunities, ranked by "
        f"the emissions reduction potential per ton of steel produced using cleaner technology.")

    aluminum = (
        f"The aluminum sector emits approximately {round(total_emissions / 1000000, 1)} billion tons of CO₂ equivalent worldwide "
        f"each year. One of the most effective strategies to _____. <br><br>____ "
        f"Climate TRACE analyzed the world's largest {total_assets} ____ to determine which facilities combine "
        f"these factors most effectively. The chart below shows the impact of all opportunities, ranked by "
        f"the emissions reduction potential per ton of aluminum produced using cleaner technology.")
    
    solid_waste_disposal = (
        f"The solid waste sector emits million tons of methane "
        f"(equivalent to  {round(total_emissions / 1000000000, 1)} billion tons of CO₂) worldwide each year. "
        f"One of the most effective strategies for reducing landfill emissions "
        f"is to cover them, particularly at unmanaged dumpsites in emerging economies "
        f"across the global south. <br><br> While covering landfills almost always reduces emissions, "
        f"the impact is greatest for sites with poorer existing coverage and higher organic waste content. "
        f"Drawing on best practices from developed nations, covering landfills with materials such as "
        f"sand and clay can significantly cut methane emissions. Climate TRACE analyzed these characteristics "
        f"across {total_assets} of the world’s largest landfills to identify where covering landfills would likely "
        f"offer the greatest emissions reductions per ton of waste covered.")
    
    electricity_generation = (
        f"The electricity sector emits approximately {round(total_emissions / 1000000000, 1)} billion tons of CO₂ worldwide each year. "
        f"One of the most effective strategies for reducing emissions in this sector is to build renewable "
        f"energy capacity. Because power grids constantly balance supply and demand, adding renewable energy "
        f"anywhere always displaces generation at nearby 'marginal' power plants on the same grid. <br><br>"
        f"While renewable energy projects almost always cut emissions, their impact is greatest in grids where "
        f"marginal plants rely on fossil fuels—especially highly emissions-intensive fuels such as anthracite coal—"
        f"and operate with low energy efficiency. Climate TRACE analyzed all {total_assets} power grids worldwide to pinpoint "
        f"where building renewable energy would achieve the greatest emissions reductions per kilowatt-hour generated. "
        f"The chart below shows the potential impact of all opportunities, ranked by emissions reductions per "
        f"kilowatt-hour of renewable energy produced.")

    summary_solution = {
        'iron-and-steel': iron_and_steel,
        'aluminum': aluminum, 
        'solid-waste-disposal': solid_waste_disposal, 
        'electricity-generation': electricity_generation}
    
    if selected_subsector not in ['iron-and-steel', 'solid-waste-disposal', 'electricity-generation']:
        summary_text = ('Description coming soon')
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

    # define assets using id + country
    df_assets['id_str'] = df_assets['asset_name'] + " (" + df_assets['iso3_country'] + ")"

    # calculate emissions factors (max, min, avg)
    ef_max = df_assets['emissions_factor'].max()
    ef_max_asset = df_assets[df_assets['emissions_factor'] == ef_max]['id_str'].unique()
    if len(ef_max_asset) > 2:
        ef_max_asset = ef_max_asset[:2]
        ef_max_asset = ', '.join(map(str, ef_max_asset)) + ', etc.'
    else:
        ef_max_asset = ', '.join(map(str, ef_max_asset))  
    ef_max = round(ef_max, 3)

    ef_min = df_assets['emissions_factor'].min()
    ef_min_asset = df_assets[df_assets['emissions_factor'] == ef_min]['id_str'].unique()
    if len(ef_min_asset) > 2:
        ef_min_asset = ef_min_asset[:2]
        ef_min_asset = ', '.join(map(str, ef_min_asset)) + ', etc.'
    else:
        ef_min_asset = ', '.join(map(str, ef_min_asset))
    ef_min = round(ef_min, 3)

    ef_avg = round(df_assets['emissions_factor'].median(), 3)

    # create columns
    select_subsector_col, select_group_col, select_ef_avg_col, select_ef_min_col, select_ef_max_col = st.columns(5)

    with select_subsector_col:
        bordered_metric_abatement("Selected Subsector", selected_subsector)
    with select_group_col:
        bordered_metric_abatement("Selected Group", selected_group)
    with select_ef_avg_col:
        bordered_metric_abatement("Average Emissions Factor", f"{ef_avg}t of CO<sub>2</sub>e<br><span style='font-size:0.6em;'>per {activity_unit}</span>")
    with select_ef_min_col:
        bordered_metric_abatement("Lowest Emissions Factor", f"{ef_min}<br><span style='font-size:0.6em;'>{ef_min_asset}</span>", value_color='green')
    with select_ef_max_col:
        bordered_metric_abatement("Highest Emissions Factor", f"{ef_max}<br><span style='font-size:0.6em;'>{ef_max_asset}</span>", value_color='red')

    ##### PLOT FIGURE -------
    st.markdown("<br>", unsafe_allow_html=True)
    fig = plot_abatement_curve(df_assets, selected_group, selected_color, dict_color, dict_lines, selected_assets)
    
    st.markdown(
        f"""
        <div style="text-align:left; font-size:24px; margin-top:10px;">
            <b>{selected_subsector} ({selected_year})</b> emissions factors - <i>{round(len(df_assets)):,} total assets</i>
        </div>
        """,
        unsafe_allow_html=True)

    st.plotly_chart(fig, use_container_width=True)

    ##### EMISSIONS REDUCING SOLUTIONS -------
    st.markdown("### emissions-reducing solutions")

    # create a table to summarize ers for sector
    ers_table = df_assets.copy()
    ers_table = ers_table.groupby(['strategy_name', 'strategy_description', 'mechanism']).agg(
        assets_impacted=('asset_id', 'count'),
        total_reduced_emissions=('emissions_reduced_at_asset', 'sum')).reset_index()
    ers_table = ers_table.sort_values(['total_reduced_emissions'], ascending=False)
    ers_table['total_reduced_emissions'] = ers_table['total_reduced_emissions'].round()

    st.dataframe(
        ers_table,
        use_container_width=True,
        row_height=80,
        column_config={
            "strategy_description": st.column_config.Column(width="large"),
            "total_reduced_emissions": st.column_config.NumberColumn(format="localized")})

    # create a table with all assets + ERS info
    df_table = df_assets.copy()
    # create urls to link info to climate trace website
    df_table['asset_url'] = df_table.apply(make_asset_url, axis=1)
    df_table['country_url'] = df_table.apply(make_country_url, axis=1)
    df_table['gadm_1_url'] = df_table.apply(make_state_url, axis=1)
    df_table['gadm_2_url'] = df_table.apply(make_county_url, axis=1)
    df_table['gadm_1_url'].fillna('', inplace=True)
    df_table['gadm_2_url'].fillna('', inplace=True)
    # filter + format table
    df_table = df_table[['asset_url', 'country_url', 'gadm_1_url', 'gadm_2_url', 'strategy_name', 'emissions_quantity', 'emissions_factor', 'emissions_reduced_at_asset']]
    df_table = df_table.sort_values('emissions_quantity', ascending=False).reset_index(drop=True)
    df_table['emissions_quantity'] = df_table['emissions_quantity'].round()
    df_table['emissions_reduced_at_asset'] = df_table['emissions_reduced_at_asset'].fillna(0)
    df_table['emissions_reduced_at_asset'] = df_table['emissions_reduced_at_asset'].round()
    
    st.markdown(f"### {selected_subsector} assets")

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
            "emissions_quantity": st.column_config.NumberColumn(format="localized"),
            "emissions_reduced_at_asset": st.column_config.NumberColumn(format="localized")}
    )


    