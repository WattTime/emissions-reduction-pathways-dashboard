import pandas as pd
import io
import streamlit as st
import urllib.parse
import html
import numpy as np
import math
import plotly.graph_objects as go
# import duckdb
# from config import CONFIG

def format_dropdown_options(raw_values, lowercase_words=None):
    if lowercase_words is None:
        lowercase_words = {"and"}

    def format_label(value):
        words = value.replace("-", " ").split()
        return " ".join([
            word.capitalize() if word.lower() not in lowercase_words else word.lower()
            for word in words
        ])

    # generate labels and check for duplicates
    seen = {}
    options = []
    mapping = {}
    for raw in raw_values:
        label = format_label(raw)
        if label in seen:
            label += f" ({raw})"  # Ensure uniqueness
        seen[label] = True
        options.append(label)
        mapping[label] = raw

    return options, mapping


# function finds us the correct column and value to use as a condition based on the dropdown selection
def map_region_condition(region_selection):
    
    list_of_continents = ['Africa',
                          'Antarctica',
                          'Asia',
                          'Europe',
                          'North America',
                          'Oceania',
                          'South America']
    
    region_mapping = {
        'EU': {
            'column_name': 'eu',
            'column_value': True
        },
        'OECD': {
            'column_name': 'oecd',
            'column_value': True
        },
        'Non-OECD': {
            'column_name': 'oecd',
            'column_value': False
        },
        'UNFCCC Annex': {
            'column_name': 'unfccc_annex',
            'column_value': True
        },
        'UNFCCC Non-Annex': {
            'column_name': 'unfccc_annex',
            'column_value': False
        },
        'Global North': {
            'column_name': 'developed_un',
            'column_value': True
        },
        'Global South': {
            'column_name': 'developed_un',
            'column_value': False
        },
        'Developed Markets': {
            'column_name': 'em_finance',
            'column_value': False
        },
        'Emerging Markets': {
            'column_name': 'em_finance',
            'column_value': True
        }
    }

    if region_selection == 'Global':
        return None
    
    elif region_selection in list_of_continents:
        return {
            'column_name': 'continent',
            'column_value': region_selection
        }
    
    elif region_selection in region_mapping:
        return region_mapping[region_selection]
    
    elif region_selection in ["United States", "United States of America"]:
        return {
            'column_name': 'country_name',
            'column_value': ["United States", "United States of America"]
    }

    else:
        return {
            'column_name': 'country_name',
            'column_value': region_selection
        }
    
def relabel_regions(df):
    dict_relabel = {
        'unfccc_annex': {True: 'Annex1', False: 'Non-Annex1'},
        'em_finance': {True: 'Emerging Markets', False: 'Developed Markets'},
        'developed_un': {True: 'Global North', False: 'Global South'},
        'continent': {'Unlisted': 'Unknown/Unlisted'}
    }
    for col, mapping in dict_relabel.items():
        if col in df.columns:
            df[col] = df[col].replace(mapping)
    return df 
    

def format_number_short(n):
    if abs(n) >= 1_000_000_000:
        return f"{n / 1e9:.1f}B"
    elif abs(n) >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    elif abs(n) >= 1_000:
        return f"{n / 1e3:.0f}K"
    else:
        return f"{n:.0f}"
    

def create_excel_file(dataframes_dict):
    
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in dataframes_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    output.seek(0)
    return output

def get_release_version(con, path):
    
    release_version = con.execute(f"SELECT DISTINCT release FROM '{path}'").fetchone()[0]
    con.close()

    return release_version



def bordered_metric(
    label, 
    value, 
    tooltip_enabled=False, 
    total_options_in_scope=None, 
    tooltip_value=None, 
    value_color=None
):
    # Format the display value
    if isinstance(value, list):
        if total_options_in_scope and len(value) == total_options_in_scope:
            display_val = f"All ({len(value)})"
            tooltip = ", ".join(value)
        else:
            tooltip = ", ".join(value)
            total_char_len = sum(len(v) for v in value)
            if total_char_len > 19:
                display_val = value[0] + f" +{len(value) - 1} more"
            else:
                display_val = ", ".join(value[:2])
                if len(value) > 2:
                    display_val += f" +{len(value) - 2} more"
    else:
        display_val = str(value)
        tooltip = tooltip_value if tooltip_value else display_val

    # Escape all text to avoid breaking markup
    display_val = html.escape(display_val)
    tooltip = html.escape(tooltip)
    label = html.escape(label)

    # Build style dynamically
    base_style = (
        "flex-grow: 1; display: flex; align-items: center; justify-content: center; "
        "font-size: 2em; font-weight: bold; text-align: center; padding: 0 4px;"
    )
    if value_color:
        base_style += f" color: {value_color};"

    card_html = f"""
        <div style="
            border: 1px solid #999;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
            min-height: 160px;
            display: flex;
            flex-direction: column;
        ">
            <div style="
                font-weight: 600;
                text-align: left;
                margin-bottom: -18px;
                margin-top: -4px;
                padding: 0;
            ">
                {label}
            </div>
            <div style="{base_style}">
                {display_val}
            </div>
        </div>
    """

    st.markdown(card_html, unsafe_allow_html=True)

def bordered_metric_abatement(
    label, 
    value, 
    tooltip_enabled=False, 
    total_options_in_scope=None, 
    tooltip_value=None, 
    value_color=None
):
    # Format the display value
    if isinstance(value, list):
        if total_options_in_scope and len(value) == total_options_in_scope:
            display_val = f"All ({len(value)})"
            tooltip = ", ".join(value)
        else:
            tooltip = ", ".join(value)
            total_char_len = sum(len(v) for v in value)
            if total_char_len > 19:
                display_val = value[0] + f" +{len(value) - 1} more"
            else:
                display_val = ", ".join(value[:2])
                if len(value) > 2:
                    display_val += f" +{len(value) - 2} more"
    else:
        display_val = str(value)
        tooltip = tooltip_value if tooltip_value else display_val

    # Build style dynamically
    base_style = (
        "flex-grow: 1; "
        "font-size: 2em; font-weight: bold; padding: 0 4px; "
        "display: flex; flex-direction: column; align-items: center; justify-content: center; "
        "line-height: 0.7;"
    )

    if value_color:
        base_style += f" color: {value_color};"

    card_html = f"""
        <div style="
            border: 1px solid #999;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 12px;
            min-height: 160px;
            display: flex;
            flex-direction: column;
        ">
            <div style="
                font-weight: 600;
                text-align: left;
                margin-bottom: -18px;
                margin-top: -4px;
                padding: 0;
            ">
                {label}
            </div>
            <div style="{base_style}">
                <div style="text-align: center; white-space: normal; overflow-wrap: anywhere;">
                    {display_val}
                </div>
            </div>
        </div>
    """

    st.markdown(card_html, unsafe_allow_html=True)


def map_percentile_col(selected_percentile):

    percentile_dict = {
        # "0th": "percentile_0",
        "10th": "percentile_avg_0_to_10",
        "20th": "percentile_avg_10_to_20",
        "30th": "percentile_avg_20_to_30",
        "40th": "percentile_avg_30_to_40",
        "50th": "percentile_avg_40_to_50",
        "60th": "percentile_avg_50_to_60",
        "70th": "percentile_avg_60_to_70",
        "80th": "percentile_avg_70_to_80",
        "90th": "percentile_avg_80_to_90",
        "100th": "percentile_avg_90_to_100"
    }

    return percentile_dict[selected_percentile]


def data_add_moer(df, cond={}):
    """
    Adding MOER data to the analysis (temporary: monthly 2023 only)
    df:  straightly from ct.get_data_asset()
    """

    cond0 = {'moer': False}
    for k,v in cond0.items():
        if k not in cond:
            cond[k] = v

    #Get MOER data (ask Zoheyr)  --  *** ADD codes to check every asset is covered ***
    fpath = 'data/static/asset_moer_2023.parquet'
    df_moer = pd.read_parquet(fpath)
    df_moer['ef_moer'] = df_moer['moer_avg']*0.4536/1000 #Convert lbs to tons

    #Map MOER to assets using asset_id
    df = pd.merge(
        df,
        df_moer[['asset_id', 'original_inventory_sector', 'ef_moer']],
        left_on=['asset_id', 'subsector'],
        right_on=['asset_id', 'original_inventory_sector'],
        how='left'
    )  

    df = df.drop(columns=['original_inventory_sector'])

    #Customize MOER data based on subsectors:
    df[['other1', 'other2', 'other3', 'other4', 'other5', 'other7', 'other9']] = df[['other1', 'other2', 'other3', 'other4', 'other5', 'other7', 'other9']].apply(pd.to_numeric, errors='coerce')

    df['eq_12'] = df['emissions_quantity']
    df['ef_12'] = df['average_emissions_factor']
    df['eq_12_moer'] = np.nan
    df['ef_12_moer'] = np.nan

    if cond['moer']:
        for sec in df.subsector.unique():
            mask_sec = df['subsector']==sec
            df_sec = df.loc[mask_sec, :].copy()

            if sec == 'electricity-generation':
                mask = df_sec['asset_type']=='biomass'
                df_sec.loc[mask,'eq_12_moer'] = df_sec.loc[mask,'other4']
                df_sec.loc[~mask,'eq_12_moer'] = df_sec.loc[~mask,'activity']*(df_sec.loc[~mask,'other7'].fillna(df_sec.loc[~mask,'average_emissions_factor']))            

                df_sec['ef_12_moer'] = df_sec['eq_12_moer']/df_sec['activity']
                
            elif sec == 'iron-and-steel':
                df_sec['eq_12'] = df_sec['other2']
                df_sec['ef_12'] = df_sec['other1']

                # df_sec['eq_12_moer'] = df_sec['other2'] + df_sec['activity']*df_sec['other3']*(df_sec['other7']-df_sec['other5'])
                df_sec['eq_12_moer'] = df_sec['other2']
                df_sec['ef_12_moer'] = df_sec['eq_12_moer']/df_sec['activity']

            # elif sec == 'aluminum':
            #     df_sec['eq_12'] = df_sec['other2']
            #     df_sec['ef_12'] = df_sec['other1']

            #     df_sec['eq_12_moer'] = df_sec['other2'] + df_sec['activity'] * df_sec['other3'] * ((df_sec['ef_moer'].fillna(df_sec['other5'])) - df_sec['other5'])
            #     df_sec['ef_12_moer'] = df_sec['eq_12_moer']/df_sec['activity']

            elif sec == 'cement':
                df_sec['eq_12'] = df_sec['other2']
                df_sec['ef_12'] = df_sec['other1']

                df_sec['eq_12_moer'] = df_sec['other2'] + df_sec['activity'] * df_sec['other7'] * ((df_sec['ef_moer'].fillna(df_sec['other9'])) - df_sec['other9'])
                df_sec['ef_12_moer'] = df_sec['eq_12_moer']/df_sec['activity']

            # elif sec == 'road-transportation':
            #     df_sec['ef_12_moer'] = df_sec['ef_moer']*35/1.6093/100/1000  #35 refers to distrance travelled to kWh based on EPA study among average car (high is 48, low is 24)
            #     df_sec['eq_12_moer'] = df_sec['activity']*df_sec['ef_12_moer'] #

            df.loc[mask_sec, ['eq_12','ef_12','eq_12_moer','ef_12_moer']] = df_sec[['eq_12','ef_12','eq_12_moer','ef_12_moer']]
    return df

def is_country(region_selection):
    if region_selection in [
        'Global',
        'Africa',
        'Antarctica',
        'Asia',
        'Europe',
        'North America',
        'Oceania',
        'South America',
        'EU',
        'OECD',
        'Non-OECD',
        'UNFCCC Annex',
        'UNFCCC Non-Annex',
        'Global North',
        'Global South',
        'Developed Markets',
        'Emerging Markets'
    ]:
        return False
    
    else:
        return True
    
def reset_city():
    st.session_state["city_selector"] = "-- Select City --"
    st.session_state.needs_recompute_RO = True

def reset_state_and_county():
    st.session_state["state_province_selector"] = "-- Select State / Province --"
    st.session_state["county_district_selector"] = "-- Select County / District --"
    st.session_state.needs_recompute_RO = True


abatement_subsector_options = {
    'agriculture': [
        'crop-residues',
        'cropland-fires',
        'enteric-fermentation-cattle-operation',
        'enteric-fermentation-cattle-pasture',
        'manure-applied-to-soils',
        'manure-left-on-pasture-cattle',
        'manure-management-cattle-operation',
        'rice-cultivation',
        'synthetic-fertilizer-application',
    ],
    'buildings': [
        'non-residential-onsite-fuel-usage',
        'residential-onsite-fuel-usage',
    ],
    'forestry-and-land-use': [
        'forest-land-clearing',
        'forest-land-degradation',
        'forest-land-fires',
        'net-forest-land',
        'net-shrubgrass',
        'net-wetland',
        'removals',
        'shrubgrass-fires',
        'water-reservoirs',
        'wetland-fires',
    ],
    'fossil-fuel-operations': [
        'coal-mining',
        'oil-and-gas-production',
        'oil-and-gas-refining',
        'oil-and-gas-transport',
    ],
    'manufacturing': [
        'aluminum',
        'cement',
        'chemicals',
        'food-beverage-tobacco',
        'glass',
        'iron-and-steel',
        'lime',
        'other-chemicals',
        'other-manufacturing',
        'other-metals',
        'petrochemical-steam-cracking',
        'pulp-and-paper',
        'textiles-leather-apparel',
    ],
    'mineral-extraction': [
        'bauxite-mining',
        'copper-mining',
        'iron-mining',
    ],
    'power': [
        'electricity-generation',
    ],
    'transportation': [
        'domestic-aviation',
        'domestic-shipping',
        'international-aviation',
        'international-shipping',
        'road-transportation',
    ],
    'waste': [
        #'domestic-wastewater-treatment-and-discharge',
        #'industrial-wastewater-treatment-and-discharge',
        'solid-waste-disposal',
    ],
}

def define_color_lines(metric):

    # dictionary for asset colors
    dict_color = {}
    dict_color['unfccc_annex'] = {
        'Annex1': '#407076',
        'Non-Annex1': '#FBBA1A'
    }
    dict_color['em_finance'] = {
        'Developed Markets': '#407076',
        'Emerging Markets': '#FBBA1A'
    }
    dict_color['developed_un'] = {
        'Global North': '#407076',
        'Global South': '#FBBA1A'
    }
    dict_color['asset_type'] = {
        'Smelting': '#407076',
        'Refinery': '#FBBA1A'
    }
    dict_color['continent'] = {
        'Europe': '#4878A8',
        'North America': '#6D4DA8',
        'Asia': '#FBBA1A',
        'Africa': '#C75B39',
        'South America': '#4C956C',
        'Oceania': '#91643A',
        'Antarctica': '#D3D3D3',
        'Unknown/Unlisted': '#9E9C9C'
    }
    dict_color['sector'] = {
        'forestry': '#E8516C',
        'manufacturing': '#9554FF',
        'fossil-fuel-operation': '#FF6F42',
        'waste': '#BBD421',
        'transportation': '#FBBA1A',
        'agriculture':  '#0BCF42',
        'buildings':  '#03A0E3',
        'fluorinated-gas': '#B6B4B4',
        'mineral': '#4380F5',
        'power': '#407076'
    }
    dict_color['background'] = {
        'background0': '#EBE6E6',
        'background1': '#D9D4D4',
        'background2': '#556063',
        'background3': '#444546',
    }

    if metric == 'emissions_factor':
        outlier_values = {
        'solid-waste-disposal': {'more landfills above': 1},
        'food-beverage-tobacco': {'more facilities above': 0.0000814059958583646}}
        dict_lines = {
            subsector: outlier_values.get(subsector, {})
            for subsector, sublist in abatement_subsector_options.items()
            for subsector in sublist}  
        
    elif metric == 'asset_reduction_potential':
        outlier_values = {}
        dict_lines = {
            subsector: outlier_values.get(subsector, {})
            for subsector, sublist in abatement_subsector_options.items()
            for subsector in sublist}
        
    elif metric == 'net_reduction_potential':
        outlier_values = {}
        dict_lines = {
            subsector: outlier_values.get(subsector, {})
            for subsector, sublist in abatement_subsector_options.items()
            for subsector in sublist}

    return dict_color, dict_lines


def plot_abatement_curve(gdf_asset, choice_group, choice_color, dict_color, dict_lines, selected_assets, selected_metric, cond={}):

    # set up conditions
    cond0 = {
        'label': True,
        'label_distance': 0.003,
        'label_distance_scalar': 20,
        'label_limit': 0.2,
        'sort_order': [False,True],
        'xaxis': ['activity'],  #not sured as yet
        'yaxis': [selected_metric],   #not used as yet
    }
    for k,v in cond0.items():
        if k not in cond: cond[k] = v

    # identify key information
    df = gdf_asset.copy()
    activity_unit = df['activity_units'][0]
    sector1 = df.subsector.unique()[0]

    # update chart based off asset/country/BA - cumulative sum activity
    if choice_group == 'asset':
        hover_id = 'asset_id'
        hover_name = 'asset_name'
        df = df.sort_values([selected_metric, 'activity'], ascending=cond['sort_order'])
        df = df.reset_index(drop=True)
        df['activity_cum'] = df['activity'].cumsum()
        df[choice_color] = df[choice_color].apply(lambda x: False if pd.isna(x)==True else x)
        df['color'] = df[choice_color].map(dict_color[choice_color])

    elif choice_group in ['country', 'balancing_authority_region']:
        if choice_group == 'country':
            hover_id = 'country_name'
            hover_name = 'country_name'
            if choice_color == 'sector':
                fds_key = ['iso3_country','country_name','sector','subsector']
            else:
                fds_key = [choice_color] + ['iso3_country', 'country_name', 'sector', 'subsector']
        else:
            hover_name = 'balancing_authority_region'
            hover_id = 'balancing_authority_region'
            if choice_color == 'sector':
                fds_key = ['iso3_country','country_name', choice_group, 'sector', 'subsector']
            else:
                fds_key = [choice_color] + ['iso3_country', 'country_name', choice_group, 'sector', 'subsector']

        df = df.pivot_table(index=fds_key, values=['activity','emissions_quantity', 'asset_reduction_potential', 'net_reduction_potential'], aggfunc='sum')
        df['emissions_factor'] = df['emissions_quantity']/df['activity']

        df = df.sort_values([selected_metric, 'activity'], ascending=cond['sort_order'])
        df = df.reset_index()
        df['activity_cum'] = df['activity'].cumsum()
        df['color'] = df[choice_color].map(dict_color[choice_color])

    new_row = []
    for col in df.columns:
        if col == 'color':
            new_row.append(df.loc[0,'color'])
        else:
            if pd.api.types.is_numeric_dtype(df[col]):
                new_row.append(0)  # For numeric columns, use 0
            else:
                new_row.append(np.nan)  # For non-numeric columns, use NaN

    df = pd.concat([pd.DataFrame([new_row], columns=df.columns), df], ignore_index=True)

    # create the fig
    fig = go.Figure()

    # calculate metrics for formatting
    x_min, x_max = min(df['activity_cum']), max(df['activity_cum'])
    y_min = df[selected_metric].min()
    y_max = df[selected_metric].max()
    y_offset = (y_max - y_min) * 0.03
    if dict_lines[sector1]:
        y_range_quantile = 0.95
    else:
        y_range_quantile = 1

    # create abatement curve, filling in area underneath for each asset iteratively
    if selected_metric == 'emissions_factor':
        y_axis_title = f'emissions factor (t of CO2e per {activity_unit if 'yaxis_title' not in cond else cond['yaxis_title']})'
        hover_text_1 = f'{df['country_name'][0]}<br><i>{df[hover_id][0]}</i><br>Activity: {round(df['activity'][0], 2)}<br>EF: {round(df[selected_metric][0], 3)}',
    elif selected_metric == 'asset_reduction_potential':
        y_axis_title = 'asset emissions reduction potential (t of CO2e)'
        hover_text_1 = f'{df['country_name'][0]}<br><i>{df[hover_id][0]}</i><br>Activity: {round(df['activity'][0], 2)}<br>Reduction Potential: {round(df[selected_metric][0], 0)}',
    elif selected_metric == 'net_reduction_potential':
        y_axis_title = 'net emissions reduction potential (t of CO2e)'
        hover_text_1 = f'{df['country_name'][0]}<br><i>{df[hover_id][0]}</i><br>Activity: {round(df['activity'][0], 2)}<br>Net Reduction Potential: {round(df[selected_metric][0], 0)}',
    
    fig.add_trace(go.Scatter(
        x=[0, df['activity_cum'][1]],
        y=[df[selected_metric][1], df[selected_metric][1]], 
        fill='tozeroy',
        fillcolor=f'{df['color'][1]}',
        line=dict(color=f'{df['color'][1]}', width=0),
        mode='lines',
        name=f'{df['iso3_country'][1]}',
        line_shape='hv',
        legendgroup=f'{df['color'][1]}',
        showlegend=False,
        hoverinfo='text',
        hovertext=hover_text_1,
        hoverlabel=dict(
            bgcolor='white',
            font=dict(color=df['color'][1], size=14))))
    
    for i in range(2,len(df)):
        if selected_metric == 'emissions_factor':
            hover_text = f'{df['country_name'][i]}<br><i>{df[hover_id][i]}</i><br>Activity: {round(df['activity'][i], 2)}<br>EF: {round(df[selected_metric][i], 3)}'
        else:
            hover_text = f'{df['country_name'][i]}<br><i>{df[hover_id][i]}</i><br>Activity: {round(df['activity'][i], 2)}<br>Reduction Potential: {round(df[selected_metric][i], 0)}'
        
        color_value = df['color'][i] 
        fig.add_trace(go.Scatter(
            x=[df['activity_cum'][i-1], df['activity_cum'][i]],
            y=[df[selected_metric][i-1], df[selected_metric][i]], 
            fill='tozeroy', 
            fillcolor=f'{color_value}',
            line=dict(color=f'{color_value}', width=2),
            mode='lines',
            name=f'{df['iso3_country'][i]}',
            line_shape='hv',
            legendgroup=f'{color_value}',
            showlegend=False,
            hoverinfo='text',
            hovertext=hover_text,
            hoverlabel=dict(
                bgcolor='white',
                font=dict(color=color_value, size=14))))

    # add selected assets to the chart
    selected_df = df[df[hover_id].isin(selected_assets)].copy()
    
    if choice_group == 'asset':
        highlight_hover_text = [
            f"{country}<br>{hover_val}<br><i>{hover_val2}</i><br>Activity: {activity:,.1f}<br>EF: {ef:.3f}"
            for country, hover_val, hover_val2, activity, ef in zip(
                selected_df['country_name'], 
                selected_df[hover_id], 
                selected_df[hover_name],
                selected_df['activity'], 
                selected_df[selected_metric]
                )
            ]
    else:
        highlight_hover_text = [
        f"{country}<br><i>{hover_val}</i><br>Activity: {activity:,.1f}<br>EF: {ef:.3f}"
        for country, hover_val, activity, ef in zip(
            selected_df['iso3_country'], 
            selected_df[hover_name],
            selected_df['activity'], 
            selected_df[selected_metric]
            )
        ]
    
    fig.add_trace(go.Scatter(
        x=selected_df['activity_cum'] - selected_df['activity'] / 2,
        y=selected_df[selected_metric] + y_offset,
        mode='markers',
        marker=dict(size=12, color='#A94442', symbol='triangle-down'),
        name="Selected Assets",
        hoverinfo='text',
        hovertext=highlight_hover_text,
        hoverlabel=dict(
            bgcolor="white",
            font=dict(color='#A94442', size=14))))
    
    fig.add_trace(go.Scatter(
        x=selected_df['activity_cum'] - selected_df['activity'] / 2,
        y=selected_df[selected_metric] + y_offset * 1.5,
        mode='text',
        hoverinfo=None,
        text=selected_df[hover_name],
        textposition="top center",
        textfont=dict(size=14, color="#A94442"),
        showlegend=False))
    
    # add custom legend items
    for color_label, color_value in dict_color[choice_color].items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode='markers',
            marker=dict(color=color_value, size=10),
            name=f'{color_label}', 
            showlegend=True
        ))

    # format plot layout
    fig.update_layout(
        xaxis_title=f'activity ({activity_unit if 'xaxis_title' not in cond else cond['xaxis_title']})',
        yaxis_title=y_axis_title,
        showlegend=True,
        legend=dict(x=1.08, y=0.97, xanchor='right', yanchor='top'),
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=50, r=50, t=20, b=50),
        xaxis=dict(
            showgrid=True,
            zeroline=True,
            zerolinecolor='lightgrey',
            gridcolor='lightgrey',
            range=[0, math.ceil(max(df['activity_cum']))*1.1]),
        yaxis=dict(
            showgrid=True,
            zeroline=True,
            zerolinecolor='lightgrey',
            gridcolor='lightgrey',
            range=[0, df[selected_metric].quantile(y_range_quantile)]),
        height=700
    
    )
    # add line to the plot if overflowing information
    for line_name, line_y in dict_lines[sector1].items():
        fig.add_shape(
            type='line',
            x0=x_min, x1=x_max,
            y0=line_y, y1=line_y,
            line=dict(color='#444546', width=1, dash='dash'),
        )
        ax_y_max = max(df[selected_metric])
        text_y = line_y
        if line_y + 0.015 * ax_y_max > ax_y_max:
            text_y = line_y - 0.015 * ax_y_max
        elif line_y - 0.015 * ax_y_max < 0:
            text_y = line_y + 0.015 * ax_y_max
        fig.add_annotation(
            x=x_max + 1, 
            y=text_y,
            text=line_name,
            showarrow=False,
            font=dict(size=12, color='#444546'),
            align='left',
            xanchor='left',
            yanchor='middle',
            xref='x',
            yref='y'
        )

    return fig

def make_asset_url(row):
    url_root = 'https://climatetrace.org/explore/#'
    admin_value = f"{row['asset_name']}"
    params = {
        'admin': admin_value,
        'gas': 'co2e',
        'year': '2024',
        'timeframe': '100',
        'sector': '',
        'asset': str(row['asset_id'])
    }
    encoded = urllib.parse.urlencode(params, safe=':,._()-')
    full_url = f"{url_root}{encoded}"
    return full_url

def make_country_url(row):
    url_root = 'https://climatetrace.org/explore/#'
    admin_value = f"{row['country_name']} ({row['iso3_country']}):1:{row['iso3_country']}:country"
    params = {
        'admin': admin_value,
        'gas': 'co2e',
        'year': '2024',
        'timeframe': '100',
        'sector': '',
        'asset': ''
    }
    encoded = urllib.parse.urlencode(params, safe=':,._()-')
    full_url = f"{url_root}{encoded}"

    return full_url

def make_state_url(row):
    url_root = 'https://climatetrace.org/explore/#'
    if pd.isna(row['gadm_1']):
        return np.nan
    admin_value = f"{row['gadm_1_name']}-- {row['iso3_country']}:{row['gid_1']}:{row['gadm_1']}:state"
    params = {
        'admin': admin_value,
        'gas': 'co2e',
        'year': '2024',
        'timeframe': '100',
        'sector': '',
        'asset': ''
    }
    encoded = urllib.parse.urlencode(params, safe=':,._()-')
    full_url = f"{url_root}{encoded}"
    return full_url

def make_county_url(row):
    url_root = 'https://climatetrace.org/explore/#'
    if pd.isna(row['gadm_2']):
        return np.nan
    admin_value = f"{row['gadm_2_name']}-- {row['gadm_1_name']}-- {row['iso3_country']}:{row['gid_2']}:{row['gadm_2']}:county"
    params = {
        'admin': admin_value,
        'gas': 'co2e',
        'year': '2024',
        'timeframe': '100',
        'sector': '',
        'asset': ''
    }
    encoded = urllib.parse.urlencode(params, safe=':,._()-')
    full_url = f"{url_root}{encoded}"
    return full_url

def return_sector_type(sector):
    if sector in ['fossil-fuel-operations', 'manufacturing', 'mineral-extraction', 'power', 'waste']:
        sector_type = 'asset'
    elif sector in ['agriculture', 'buildings', 'fluorinated-gases', 'forestry-and-land-use', 'transportation']:
        sector_type = 'raster'
    return sector_type



def get_reduction_induction_json(df_stacked_bar, df_induced):
    def safe_format_number(x):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "0"
        return format_number_short(x)

    summary = []

    for _, row in df_stacked_bar.iterrows():
        sector = row["sector"]

        # gather inductions
        sector_inductions = df_induced[df_induced["receiving_sector"] == sector]
        inductions_list = []
        for _, ind in sector_inductions.iterrows():
            if ind["induced_emissions"] is not None and not math.isnan(ind["induced_emissions"]):
                inductions_list.append({
                    "inducing_sector": ind["inducing_sector"],
                    "induced_emissions": ind["induced_emissions"],
                    "formatted": safe_format_number(ind["induced_emissions"])
                })

        # core values
        asset_reductions = row.get("emissions_reduced_at_asset", 0) or 0
        reduction_potential = row.get("emissions_reduction_potential", 0) or 0
        static_emissions = row.get("static_emissions_q", 0) or 0

        asset_reductions_fmt = safe_format_number(asset_reductions)
        reduction_potential_fmt = safe_format_number(reduction_potential)
        static_emissions_fmt = safe_format_number(static_emissions)

        # total inductions
        total_inductions = sum(
            ind["induced_emissions"] for ind in inductions_list if ind["induced_emissions"] is not None
        )
        total_inductions_fmt = safe_format_number(total_inductions)
        total_inductions_color = "red" if total_inductions >= 0 else "green"

        # build hover text lines
        hover_lines = [f"<b>{sector}</b>"]

        # Asset reductions (moved down with space)
        hover_lines.append("&nbsp;")
        hover_lines.append(
            #f"<span style='color:green; font-size:13px; font-weight:bold'>{asset_reductions_fmt}</span> "
            f"<span style='color:green; font-size:13px; font-weight:bold'>&nbsp;{asset_reductions_fmt}</span>&nbsp;&nbsp;&nbsp;<span style='font-size:13px; font-weight:bold'>Asset Reductions</span>"
        )

        # blank line before inductions
        hover_lines.append("&nbsp;")

        # Inductions
        if inductions_list:
            hover_lines.append(
                f"<span style='color:{total_inductions_color}; font-size:13px; font-weight:bold'>{total_inductions_fmt}</span> "
                f"<span style='font-size:13px; font-weight:bold'>&nbsp;&nbsp;Net Inductions:</span>"
            )
            for ind in inductions_list:
                val = ind["induced_emissions"]
                if val is None or math.isnan(val):
                    continue
                if val >= 0:
                    hover_lines.append(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(<span style='color:red'>{ind['formatted']}</span>) <i>{ind['inducing_sector']}</i>"
                    )
                else:
                    hover_lines.append(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;(<span style='color:green'>{ind['formatted']}</span>) <i>{ind['inducing_sector']}</i>"
                    )
        else:
            hover_lines.append(
                f"<span style='color:green; font-size:13px; font-weight:bold'>&nbsp;0&nbsp;&nbsp;</span> "
                f"<span style='font-size:13px; font-weight:bold'>Net Inductions</span>"
            )

        # formula separator
        hover_lines.append("────────────────────")

        # Net consequential reductions (bigger, bold, first thing your eyes see)
        hover_lines.append(
            f"<span style='color:green; font-size:14px; font-weight:bold'>✅ {reduction_potential_fmt} Net Reduction Opportunity</span>"
        )

        # join with <br>
        hover_text = "<br>".join(hover_lines)

        summary.append({
            "sector": sector,
            "asset_reductions": asset_reductions,
            "asset_reductions_formatted": asset_reductions_fmt,
            "reduction_potential": reduction_potential,
            "reduction_potential_formatted": reduction_potential_fmt,
            "static_emissions": static_emissions,
            "static_emissions_formatted": static_emissions_fmt,
            "inductions": inductions_list,
            "hover_text": hover_text
        })

    return summary


def get_consequetial_hover_text(df_induced):

    # Format values up front
    df_induced["formatted_asset_reductions"] = df_induced["emissions_reduced_at_asset"].apply(
        lambda x: format_number_short(x) if pd.notnull(x) else None
    )
    df_induced["formatted_reduction_potential"] = df_induced["emissions_reduction_potential"].apply(
        lambda x: format_number_short(x) if pd.notnull(x) else None
    )
    df_induced["formatted_induced_emissions"] = df_induced["induced_emissions"].apply(
        lambda x: format_number_short(x) if pd.notnull(x) else None
    )

    # Build induction lists grouped by receiving sector
    inductions_grouped = (
        df_induced.dropna(subset=["inducing_sector", "induced_emissions"])
        .groupby("receiving_sector")
        .apply(lambda g: [
            {
                "inducing_sector": row["inducing_sector"],
                "induced_emissions": row["formatted_induced_emissions"],
            }
            for _, row in g.iterrows()
        ])
        .to_dict()
    )

    # Attach inductions safely (fallback to empty list)
    df_summary = (
        df_induced.drop_duplicates(subset=["sector"])
        .assign(inductions=lambda d: d["sector"].map(inductions_grouped).apply(lambda x: x if isinstance(x, list) else []))
    )

    hover_texts = []
    for _, row in df_induced.iterrows():
        parts = []
        
        # Asset reductions
        if pd.notnull(row["formatted_asset_reductions"]) and row["formatted_asset_reductions"] not in ["0", None]:
            parts.append(f"+ Asset Reductions: {row['formatted_asset_reductions']} tCO₂e")
        
        # Inductions
        sector_inductions = df_induced[
            (df_induced["receiving_sector"] == row["sector"]) & 
            (df_induced["induced_emissions"].notnull())
        ]
        for _, ind in sector_inductions.iterrows():
            if ind["formatted_induced_emissions"] not in ["0", None]:
                parts.append(f"+ {ind['inducing_sector']}: {ind['formatted_induced_emissions']} tCO₂e")
        
        # Combine into hover text
        formula = "<br>".join(parts)
        text = (
            f"<b>{row['sector']}</b><br>"
            f"{formula}<br>"
            f"= <b style='color:green'>{row['formatted_reduction_potential']} tCO₂e</b>"
        )
        hover_texts.append(text)

    return hover_texts

# ------------- THIS IS TO ISOLATE TABS FROM RECOMPUTE -------------
def mark_ro_recompute():
    st.session_state.needs_recompute_reduction_opportunities = True

def mark_ac_recompute():
    st.session_state.needs_recompute_abatement_curve = True

def mark_mt_recompute():
    st.session_state.needs_recompute_monthly_trends = True