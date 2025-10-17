import streamlit as st
import duckdb
import re
import pandas as pd
import geopandas as gpd
import numpy as np
import plotly.express as px
from config import CONFIG
from utils.utils import *
from utils.queries import *


def show_ownership_module():
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
    con = duckdb.connect()
    annual_asset_path = CONFIG['annual_asset_path']
    gadm_0_path = CONFIG['gadm_0_path']
    ownership_path = CONFIG['asset_ownership_path']
    
    ##### IMPORT DATA -------
    
    # import ownership + emissions data
    query_df_ownership = get_ownership_sql(annual_asset_path, ownership_path)
    df_ownership = con.execute(query_df_ownership).df()
    query_ct_emissions = get_gadm_emissions_sql(gadm_0_path)
    df_gadm_emissions = con.execute(query_ct_emissions).df()

    # calculate country-level and gadm-level emissions factors
    df_gadm_emissions = df_gadm_emissions[(df_gadm_emissions['activity'].notna()) & (df_gadm_emissions['emissions_quantity'].notna())]
    df_global_emissions = df_gadm_emissions.groupby(['subsector']).agg(activity=('activity', 'sum'), emissions_quantity=('emissions_quantity', 'sum')).reset_index()
    df_global_emissions['ef_global'] = np.where(df_global_emissions['activity'] != 0, df_global_emissions['emissions_quantity'] / df_global_emissions['activity'], np.nan)
    df_global_emissions['ef_global'] = np.where(df_global_emissions['ef_global'] == 0, np.nan, df_global_emissions['ef_global'])
    df_global_emissions = df_global_emissions[['subsector', 'ef_global']]
    df_gadm_emissions['ef_country'] = np.where(df_gadm_emissions['activity'] != 0, df_gadm_emissions['emissions_quantity'] / df_gadm_emissions['activity'], np.nan)
    df_gadm_emissions['ef_country'] = np.where(np.isclose(df_gadm_emissions['ef_country'], 0, atol=1e-6), np.nan, df_gadm_emissions['ef_country'])
    df_gadm_emissions = df_gadm_emissions[['iso3_country', 'subsector', 'ef_country']]

    # format + clean ownership data
    df_ownership['parent_entity_id'] = df_ownership['parent_entity_id'].fillna('')
    df_ownership['parent_name'] = df_ownership['parent_name'].str.strip()
    df_ownership['parent_name'] = df_ownership['parent_name'].replace('unknown', '').fillna('')
    df_ownership['parent_lei'] = np.where(((df_ownership['parent_lei'] == 'not applicable') & (df_ownership['parent_entity_type'] == 'unknown entity')) |
                                        (df_ownership['parent_lei'] == 'not found'), '', df_ownership['parent_lei'])
    df_ownership['immediate_source_owner'] = df_ownership['immediate_source_owner'].replace('unknown', '').fillna('')
    
    # create keys to search by parent, immediate source, and source operator
    df_ownership['parent'] = np.where(df_ownership['parent_lei'] != '', 
                                      df_ownership['parent_entity_id'] + ': ' + df_ownership['parent_name'] + ' (' + df_ownership['parent_lei'] + ')',
                                      df_ownership['parent_entity_id'] + ': ' + df_ownership['parent_name'])
    df_ownership['parent'] = np.where(df_ownership['parent'] == ': ', 'Unknown parent', df_ownership['parent'])
    df_ownership['immediate source'] = df_ownership['immediate_source_owner_entity_id'] + ': ' + df_ownership['immediate_source_owner']
    df_ownership['immediate source'] = np.where(df_ownership['immediate source'] == ': ', 'Unknown immediate source', df_ownership['immediate source'])
    df_ownership['source operator'] = df_ownership['source_operator_id'] + ': ' + df_ownership['source_operator']
    df_ownership['source operator'] = np.where(df_ownership['source operator'] == ': ', 'Unknown source operator', df_ownership['source operator'])
    
    # calculate ownership emissions factors
    df_ownership['activity'] = df_ownership['activity'].astype(float)
    df_ownership['ef_asset'] = df_ownership['emissions_quantity'].div(df_ownership['activity'].where(df_ownership['activity'] != 0, np.nan))

    ##### DROPDOWN MENU: KEYS FOR SEARCHING -------

    ownership_list = {'parent': df_ownership['parent'].drop_duplicates().sort_values().tolist(),
                      'immediate source': df_ownership['immediate source'].drop_duplicates().sort_values().tolist(),
                      'source operator': df_ownership['source operator'].drop_duplicates().sort_values().tolist()}

    # by default, show all assets
    selected_key_default = 'parent'

    key_col = st.columns(1)
    with key_col[0]:
        key_options = ownership_list.keys()
        selected_key_user= st.selectbox(
            "Select owner type",
            options=key_options)

    if not selected_key_user:
        selected_key = selected_key_default
    else:
        selected_key = selected_key_user

    owners_options = [
        owner
        for owner in ownership_list[selected_key]]

    # select relevant owners
    selected_owners_default = owners_options

    with st.expander("Select owner"):
        selected_owners_user = st.multiselect(
            "Owner Entity ID: Owner Name (Owner LEI, if applicable)",
            options=owners_options,
            default=[]
        )

        # select relevant locations
        loc_options = df_ownership[df_ownership[selected_key].isin(selected_owners_user)]['iso3_country'].drop_duplicates().sort_values()
        selected_location_user = st.multiselect(
            "Locations",
            options=loc_options,
            default=loc_options
        )

    # filter based on selection
    if not selected_owners_user:
        selected_owners = selected_owners_default
        df_selected = df_ownership.sort_values('emissions_quantity', ascending=False).reset_index().copy()
    else:
        selected_owners = selected_owners_user
        df_selected = df_ownership[(df_ownership[selected_key].isin(selected_owners)) & (df_ownership['iso3_country'].isin(selected_location_user))].copy()
        df_selected = df_selected.sort_values('emissions_quantity', ascending=False).reset_index()
    
    ##### SUMMARY INFO -------
    st.markdown("### Ownership Analysis")
    st.markdown(
    f"""
    <div style="text-align:left; font-size:24px; margin-top:5px;">
        <b>Emissions (t CO2e):</b> {df_selected.drop_duplicates('asset_id')['emissions_quantity'].sum():,.0f} <br> 
        <b>Sectors:</b> {df_selected['subsector'].nunique()} <br> 
        <b>Assets:</b> {df_selected['asset_id'].nunique():,.0f} <br> 
    </div>
    """,
    unsafe_allow_html=True)

    ##### CREATE ASSET MAP -------

    # get country information
    df_map = df_selected.groupby(['iso3_country']).agg(num_assets=('asset_id', 'size')).reset_index()
    
    # get asset information --- REPLACE WITH REAL ASSETS
    asset_data = {
        "lat": [37.77, 45.42, 19.43],
        "lon": [-122.42, -75.69, -99.13],
        "asset_id": ["San Francisco", "Ottawa", "Mexico City"]}
    df_assets = pd.DataFrame(asset_data)

    # map countries
    fig = px.choropleth(df_map,
                        locations="iso3_country",
                        hover_name="iso3_country",
                        hover_data={"num_assets": True, "iso3_country": False},
                        labels={"num_assets": "Number of Assets"},
                        color='num_assets',
                        color_continuous_scale=px.colors.sequential.Teal)

    # map assets
    fig.add_scattergeo(
        lat=df_assets["lat"],
        lon=df_assets["lon"],
        text=df_assets["asset_id"],
        mode="markers",
        marker=dict(size=8, color="#EFA282"),
        textposition="top center",
        name="Asset",
        hovertemplate="<b>%{text}</b>"
    )

    fig.update_layout(width=1000, height=700)
    st.plotly_chart(fig, use_container_width=True)

    ##### VISUALIZATIONS -------
    sector_col, country_col = st.columns(2)

    # create pie chart based off sector breakdown
    with sector_col:
        fig_pie = px.pie(
            df_selected,
            values='emissions_quantity',
            names='subsector',
            title='Sector View<br><i>Emissions in CO2e</i>',
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # create bar chart based off country breakdown
    with country_col:
        bar_data = df_selected.groupby('iso3_country', as_index=False)['emissions_quantity'].sum()
        # add row for sum of all countries
        total_row = pd.DataFrame({"iso3_country": ['Total'], "emissions_quantity": [bar_data['emissions_quantity'].sum()]})
        bar_data = pd.concat([bar_data, total_row])
        bar_data['color_group'] = bar_data['iso3_country'].apply(lambda x: 'Total' if x == 'Total' else 'Country')
        color_map = {'Country': '#3B7A72', 'Total': 'grey'}
        fig_bar = px.bar(
            bar_data,
            x='iso3_country',
            y='emissions_quantity',
            title='Country View<br><i>Emissions in CO2e</i>',
            color='color_group',
            color_discrete_map=color_map,
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    
    ##### DATA TABLE -------

    st.markdown("###")
    st.markdown("### Asset Information")
    # add caveat
    st.markdown(
    """
    <div style="text-align:left; font-size:16px; margin-top:10px;">
        <i>Note: selected sectors have null activity value due to data license agreement (e.g. oil-and-gas-production/transport)</i>
    </div>
    """,
    unsafe_allow_html=True)

    # create table
    df_table = df_selected[['asset_id', 'asset_name', 'subsector', 'asset_type', 'iso3_country', 'activity_units', 'activity', 'emissions_quantity', 'ef_asset']].drop_duplicates().head(1000)
    df_table = df_table.merge(df_gadm_emissions, how='left', on=['iso3_country', 'subsector']).merge(df_global_emissions, how='left', on=['subsector'])
    st.dataframe(
        df_table,
        use_container_width=True,
        height=600,
        column_config={"activity": st.column_config.NumberColumn(format="localized"),
                       "emissions_quantity": st.column_config.NumberColumn(format="localized"),
                       "ef_asset": st.column_config.NumberColumn(format="localized"),
                       "ef_country": st.column_config.NumberColumn(format="localized"),
                       "ef_global": st.column_config.NumberColumn(format="localized")}
    )