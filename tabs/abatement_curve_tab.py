import streamlit as st
import streamlit.components.v1 as components
import duckdb
import math
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.colors as mcolors
import base64
from calendar import month_name
import calendar
from collections import defaultdict
import sys
import os

# # os.getcwd()
# main_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
# test = pd.read_parquet(main_path + '/emissions_reduction/gadm_2_emissions.parquet')

# utils_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utils'))
# main_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
# if main_path not in sys.path:
#     sys.path.append(main_path)
# if utils_path not in sys.path:
#     sys.path.append(utils_path)

from utils.utils import bordered_metric_2
# from config import CONFIG
# from utils import (format_dropdown_options, 
#                          map_region_condition, 
#                          format_number_short, 
#                          create_excel_file, 
#                          bordered_metric, 
#                          map_percentile_col,
#                          is_country,
#                          reset_city,
#                          reset_state_and_county)

from config import CONFIG
from utils.utils import (relabel_regions)

# Asset Color
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
    'Europe': '#4878A8',  # blue
    'North America': '#6D4DA8',  # purple
    'Asia': '#FBBA1A',  # red
    'Africa': '#C75B39',  # brown
    'South America': '#4C956C',  # green
    'Oceania': '#91643A',  # orange
    # 'Antarctica': '#B6B4B4',  # orange    
    # 'World': '#B6B4B4'  # grey
}
dict_color['sector'] = {
    'forestry': '#E8516C',  #red
    'manufacturing': '#9554FF', #purple
    'fossil-fuel-operation': '#FF6F42',  #orange
    'waste': '#BBD421', #lightgreen
    'transportation': '#FBBA1A',  #lightorange
    'agriculture':  '#0BCF42',  #green
    'buildings':  '#03A0E3',  #ocean blue
    'fluorinated-gas': '#B6B4B4',  #grey
    'mineral': '#4380F5',  #blue
    'power': '#407076'  #turquoise
}
dict_color['background'] = {
    'background0': '#EBE6E6',  #light grey
    'background1': '#D9D4D4',  #medium grey
    'background2': '#556063',  #dark grey (blue)
    'background3': '#444546',  #dark grey (neutral)
}

dict_lines = {}

# power
dict_lines['electricity-generation'] = {}

# waste
dict_lines['solid-waste-disposal'] = {'more landfills above': 3}

# manufacturing
dict_lines['aluminum'] = {}
dict_lines['cement'] = {}
dict_lines['chemicals'] = {}
dict_lines['food-beverage-tobacco'] = {'more facilities above': 0.00021}
dict_lines['glass'] = {}
dict_lines['iron-and-steel'] = {}
dict_lines['lime'] = {}
dict_lines['other-chemicals'] = {}
dict_lines['other-manufacturing'] = {}
dict_lines['other-metals'] = {}
dict_lines['petrochemical-steam-cracking'] = {}
dict_lines['pulp-and-paper'] = {}
dict_lines['textiles-leather-apparel'] = {}
dict_lines['wood-and-wood-products'] = {}


# transportation
dict_lines['road-transportation'] = {}

def plot_stairs(gdf_asset, choice_group, choice_color, dict_color, dict_lines, selected_assets, cond={}):
    #Setup
    cond0 = {
        'label': True,
        'label_distance': 0.003,
        'label_distance_scalar': 20,
        'label_limit': 0.2,
        'sort': ['emissions_factor','activity'],
        'sort_order': [False,True],
        'xaxis': ['activity'],  #not sured as yet
        'yaxis': ['emissions_factor'],   #not used as yet
    }
    for k,v in cond0.items():
        if k not in cond: cond[k] = v

    # Example data
    df = gdf_asset.copy()
    activity_unit = df['activity_units'][0]
    sector1 = df.subsector.unique()[0]

    # *** Remove data for easy viewing ***
    if choice_group == 'asset':
        hover_id = 'asset_id'
        hover_name = 'asset_name'
        if sector1 in ['solid-waste-disposal']:
            df = df.loc[df['emissions_factor']<=3,:]
        elif sector1 in ['electricity-generation']:
            df = df.loc[df['emissions_factor']<=1.5,:]
        elif sector1 in ['road-transportation']:
            df = df.loc[df['emissions_factor']<=5,:]

    if choice_group == 'asset':
        df = df.sort_values(cond['sort'], ascending=cond['sort_order'])
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
                fds_key = [choice_color] + ['iso3_country','country_name','sector','subsector']
        else:
            hover_name = 'balancing_authority_region'
            hover_id = 'balancing_authority_region'
            if choice_color == 'sector':
                fds_key = ['iso3_country','country_name', choice_group, 'sector', 'subsector']
            else:
                fds_key = [choice_color] + ['iso3_country','country_name',choice_group,'sector','subsector']

        df = df.pivot_table(index=fds_key, values=['activity','emissions_quantity'], aggfunc='sum')
        df['emissions_factor'] = df['emissions_quantity']/df['activity']
        df = df.sort_values(cond['sort'], ascending=cond['sort_order'])

        if sector1 in ['road-transportation']:
            df = df.loc[df['emissions_factor']<=5,:]
        elif sector1 in ['electricity-generation']:
            df = df.loc[df['emissions_factor']<=1.5,:]
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

    # Create the figure
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=[0, df['activity_cum'][1]],  # From 0 to the second data point (row 1) and back to 0
        y=[df['emissions_factor'][1], df['emissions_factor'][1]],  # From 0 to the second emissions factor (row 1) and back to 0
        fill='tozeroy',  # Fill the area under the line (this is the key)
        fillcolor=f'{df["color"][1]}',  # Use the color of row 1 for the shading
        line=dict(color=f'{df["color"][1]}', width=0),  # Line color for the shading (row 1)
        mode='lines',  # Lines to connect the points
        name=f"{df['iso3_country'][1]}",  # Name for the first point (row 1)
        line_shape='hv',  # Step function line shape (horizontal-vertical)
        legendgroup=f'{df["color"][1]}',  # Grouping by color
        showlegend=False  # Show legend entry for each segment
    ))

    list_label, count_label = [], 0
    ax_x_max = df['activity_cum'].max() 
    num_max = len(df)
    y_min = df['emissions_factor'].min()
    y_max = df['emissions_factor'].max()
    y_offset = (y_max - y_min) * 0.03

    for i in range(2,len(df)):
        color_value = df['color'][i]  # Get the color from the color_variable
        fig.add_trace(go.Scatter(
            x=[df['activity_cum'][i-1], df['activity_cum'][i]],  # X values for the segment
            y=[df['emissions_factor'][i-1], df['emissions_factor'][i]],  # Y values for the segment
            fill='tozeroy',  # Fill the area under the line
            fillcolor=f'{color_value}',  # Set fill color
            line=dict(color=f'{color_value}', width=2),  # Set line color
            mode='lines',  # Lines to connect the points
            name=f"{df['iso3_country'][i]}",  # Name for the legend
            line_shape='hv',  # Step function line shape (horizontal-vertical)
            legendgroup=f"{color_value}",  # Grouping by color
            showlegend=False,  # Show legend entry for each segment
            hoverinfo="text",
            hovertext=f"{df['country_name'][i]}<br><i>{df[hover_id][i]}</i><br>Activity: {round(df['activity'][i], 2)}<br>EF: {round(df['emissions_factor'][i], 3)}",
            hoverlabel=dict(
                bgcolor="white",
                font=dict(color=color_value, size=14))))

        # # Add annotation for the shaded area with a line pointing to the area
        # if cond['label']:
        #     count_label += df['activity'][i]
        #     if df['activity'][i] / ax_x_max >= cond['label_distance']:
        #         if (i <= num_max*(1-cond['label_limit'])) and (df['country_name'][i] not in list_label) and (count_label/ax_x_max >= cond['label_distance']*cond['label_distance_scalar']):
        #             count_label = 0
        #             list_label += [df['country_name'][i]]
        #             fig.add_annotation(
        #                 x=df['activity_cum'][i-1] + (df['activity_cum'][i]-df['activity_cum'][i-1])/2,  # Position the annotation at the x-value of the end of the shaded area
        #                 y=df['emissions_factor'][i]*1.01,  # Position it slightly above the maximum y-value of the shaded area
        #                 text='<br>'.join(df['country_name'][i].split(' ')),  # Replace with your desired text
        #                 showarrow=True,  # Show an arrow pointing to the shaded area
        #                 arrowhead=1,  # Customize the arrow's appearance
        #                 ax=0,  # Set the x distance for the arrow line (zero for no offset)
        #                 font=dict(size=12, color="#444546"),  # Customize the annotation text style
        #                 align="center",  # Align the text in the center
        #             )

    selected_df = df[df[hover_name].isin(selected_assets)].copy()
    
    if choice_group == 'asset':
        highlight_hover_text = [
            f"{country}<br>{hover_val}<br><i>{hover_val2}</i><br>Activity: {activity:,.1f}<br>EF: {ef:.3f}"
            for country, hover_val, hover_val2, activity, ef in zip(
                selected_df['country_name'], 
                selected_df[hover_id], 
                selected_df[hover_name],
                selected_df['activity'], 
                selected_df['emissions_factor']
                )
            ]
    else:
        highlight_hover_text = [
        f"{country}<br><i>{hover_val}</i><br>Activity: {activity:,.1f}<br>EF: {ef:.3f}"
        for country, hover_val, activity, ef in zip(
            selected_df['iso3_country'], 
            selected_df[hover_name],
            selected_df['activity'], 
            selected_df['emissions_factor']
            )
        ]
    fig.add_trace(go.Scatter(
        x=selected_df['activity_cum'] - selected_df['activity'] / 2,
        y=selected_df['emissions_factor'] + y_offset,
        mode='markers',
        marker=dict(size=12, color='#A94442', symbol='triangle-down'),
        name="Selected Assets",
        hoverinfo='text',
        hovertext=highlight_hover_text,
        hoverlabel=dict(
            bgcolor="white",
            font=dict(color='#A94442', size=14))
    ))
    fig.add_trace(go.Scatter(
        x=selected_df['activity_cum'] - selected_df['activity'] / 2,
        y=selected_df['emissions_factor'] + y_offset * 1.5,
        mode='text',
        hoverinfo=None,
        text=selected_df[hover_name],
        textposition="top center",
        textfont=dict(size=14, color="#A94442"),
        showlegend=False
    ))
    # Add custom legend items (invisible markers) for each color in the color field
    for color_label, color_value in dict_color[choice_color].items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None],  # Invisible data point (None)
            mode='markers',  # Marker mode
            marker=dict(color=color_value, size=10),  # Marker color
            name=f"{color_label}",  # Custom legend name based on color
            showlegend=True  # Ensure it shows in the legend
        ))

    # Update layout
    fig.update_layout(
        xaxis_title=f"activity ({activity_unit if 'xaxis_title' not in cond else cond['xaxis_title']})",
        yaxis_title=f"emissions factor (t of CO2e per {activity_unit if 'yaxis_title' not in cond else cond['yaxis_title']})",
        showlegend=True,  # Show legend
        legend=dict(
            x=0.9,  # X position (0 is the left edge)
            y=1,  # Y position (1 is the top edge)
            xanchor='right', 
            yanchor='top',  # Anchors the legend at the top side
        ),
        plot_bgcolor='rgba(0,0,0,0)',  # Transparent background
        margin=dict(l=50, r=50, t=20, b=50),  # Adjust margins

        xaxis=dict(
            showgrid=True,  # Show grid lines on the x-axis
            zeroline=True,  # Hide the x-axis zero line (optional)
            zerolinecolor='lightgrey',
            gridcolor='lightgrey',  # Set grid line color to light grey
            range=[0, math.ceil(max(df['activity_cum']))*1.1],  # Adjust the x-axis range
        ),
        yaxis=dict(
            showgrid=True,  # Show grid lines on the y-axis
            zeroline=True,  # Hide the x-axis zero line (optional)
            zerolinecolor='lightgrey',
            gridcolor='lightgrey',  # Set grid line color to light grey
            range=[0, round(df['emissions_factor'].quantile(0.95) * 1.1, 4) if max(df['emissions_factor'])<1 else math.ceil(df['emissions_factor'].quantile(0.95) * 1.1)],  # Adjust the y-axis range
        ),
        height=700
    
    )

    # Add lines to the plot
    x_min, x_max = min(df['activity_cum']), max(df['activity_cum'])
    for line_name, line_y in dict_lines[sector1].items():
        # Add horizontal line
        fig.add_shape(
            type="line",  # Shape type is a line
            x0=x_min, x1=x_max,  # Horizontal line spans from the left to the right of the plot
            y0=line_y, y1=line_y,  # y value where the horizontal line is placed
            line=dict(color="#444546", width=1, dash="dash"),  # Line color, width, and style
        )
        
        # Add annotation for the line, placed to the right outside the plot
        ax_y_max = max(df['emissions_factor'])
        text_y = line_y
        if line_y + 0.015 * ax_y_max > ax_y_max:
            text_y = line_y - 0.015 * ax_y_max
        elif line_y - 0.015 * ax_y_max < 0:
            text_y = line_y + 0.015 * ax_y_max

        fig.add_annotation(
            x=x_max + 1, 
            y=text_y,  # Position text at the same y-value as the line
            text=line_name,  # Text to display
            showarrow=False,  # No arrow pointing to the text
            font=dict(size=12, color="#444546"),  # Font size and color
            align="left",  # Align the text to the left
            xanchor="left",  # Anchor the text to the left
            yanchor="middle",  # Anchor the text vertically at the middle of the line
            xref="x",  # Set the reference system for the x-coordinate
            yref="y"  # Set the reference system for the y-coordinate
        )

    return fig

def show_abatement_curve():

    annual_asset_path = CONFIG['annual_asset_path']
    gadm_0_path = CONFIG['gadm_0_path']
    gadm_1_path = CONFIG['gadm_1_path']
    gadm_2_path = CONFIG['gadm_2_path']

    # add drop-down options for filtering data
    sector_col, subsector_col, gas_col, year_col = st.columns(4)

    with sector_col:
        selected_sector= st.selectbox(
            "Sector",
            options=['manufacturing', 'power', 'waste']
        )

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
            options=subsector_options[selected_sector]
        )

    with gas_col:
        selected_gas = st.selectbox(
            "Gas",
            options=['co2e_100yr', 'ch4'],
            disabled=True
        )

    with year_col:
        selected_year = st.selectbox(
            "Year",
            options=[2024],
            disabled=True

        )


    con = duckdb.connect()

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
            ae.capacity,
            ae.activity,
            ae.emissions_quantity
        FROM '{annual_asset_path}' ae
        WHERE 
            subsector = '{selected_subsector}'
            AND year = {selected_year}
        '''
    
    #cond = {'sort_order': [True, True], 'label_limit': 0, 'label_distance': 0.0015}

    df_assets = con.execute(query_assets).df()
    df_assets = df_assets.drop_duplicates(['asset_id'])
    df_assets['emissions_factor'] = df_assets['emissions_quantity'] / df_assets['activity']
    df_assets =  relabel_regions(df_assets)

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

    activity_unit = df_assets['activity_units'][0]
    total_emissions = df_assets['emissions_quantity'].sum()
    total_assets = df_assets['asset_id'].nunique()

    metric_col, group_col, color_col, asset_col = st.columns(4)

    with metric_col:
        selected_metric= st.selectbox(
            "Metric",
            options=['emissions_factor'],
            disabled=True
        )

    with group_col:
        if selected_subsector == 'electricity-generation':
            group_options = ["country", "balancing_authority_region"]
        else:
            group_options= ["asset", "country"]
        selected_group = st.selectbox(
            "Group type",
            options=group_options
        )

    with color_col:
        selected_color = st.selectbox(
            "Color group",
            options=['unfccc_annex', 'em_finance', 'continent', 'developed_un', 'sector']
        )

    with asset_col:
        if selected_group == 'asset':
            asset_options = 'asset_name'
        elif selected_group == 'country':
            asset_options = 'country_name'
        else:
            asset_options = 'balancing_authority_region'
        selected_assets = st.multiselect(
            "Assets to highlight",
            options=df_assets[asset_options].unique(),
            default=[]
        )

    # Call your function
    fig = plot_stairs(df_assets, selected_group, selected_color, dict_color, dict_lines, selected_assets)

        # ---------- Title ----------
    
    iron_and_steel = (
        f"The iron and steel sector emits approximately {round(total_emissions / 1000000000, 1)} billion tons of CO₂ equivalent worldwide "
        f"each year. One of the most effective strategies to reduce these emissions is upgrading steel plants with greener technologies "
        f"such as Direct Reduced Iron–Electric Arc Furnace (DRI-EAF). <br><br> While greener steel technologies almost always lower "
        f"emissions, their impact is greatest when applied to mills with higher-emitting existing technology types, strong suitability "
        f"for conversion to low-emission options like DRI-EAF, and access to cleaner electricity sources in the local grid. "
        f"Climate TRACE analyzed the world's largest {total_assets} steel mills to determine which facilities combine "
        f"these factors most effectively. The chart below shows the impact of all opportunities, ranked by "
        f"the emissions reduction potential per ton of steel produced using cleaner technology."
    )

    aluminum = (
        f"The aluminum sector emits approximately {round(total_emissions / 1000000, 1)} billion tons of CO₂ equivalent worldwide "
        f"each year. One of the most effective strategies to _____. <br><br>____ "
        f"Climate TRACE analyzed the world's largest {total_assets} ____ to determine which facilities combine "
        f"these factors most effectively. The chart below shows the impact of all opportunities, ranked by "
        f"the emissions reduction potential per ton of aluminum produced using cleaner technology."
    )
    
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
        f"offer the greatest emissions reductions per ton of waste covered."
    )
    
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
        f"kilowatt-hour of renewable energy produced."
    )

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
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    df_assets['id_str'] = df_assets['asset_id'].astype(str) + " (" + df_assets['iso3_country'] + ")"

    ef_max = df_assets['emissions_factor'].max()
    ef_max_asset = df_assets[df_assets['emissions_factor'] == ef_max]['id_str'].unique()
    if len(ef_max_asset) > 3:
        ef_max_asset = ef_max_asset[:3]
        ef_max_asset = ', '.join(map(str, ef_max_asset)) + ', etc.'
    else:
        ef_max_asset = ', '.join(map(str, ef_max_asset))  
    ef_max = round(ef_max, 3)
    ef_min = df_assets['emissions_factor'].min()
    ef_min_asset = df_assets[df_assets['emissions_factor'] == ef_min]['id_str'].unique()
    if len(ef_min_asset) > 3:
        ef_min_asset = ef_min_asset[:3]
        ef_min_asset = ', '.join(map(str, ef_min_asset)) + ', etc.'
    else:
        ef_min_asset = ', '.join(map(str, ef_min_asset))
    ef_min = round(ef_min, 3)
    ef_avg = round(df_assets['emissions_factor'].median(), 3)
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        bordered_metric_2("Selected Subsector", selected_subsector)
    with col2:
        bordered_metric_2("Selected Group", selected_group)
    with col3:
        bordered_metric_2("Average Emissions Factor", f"{ef_avg}t of CO<sub>2</sub>e<br><span style='font-size:0.6em;'>per {activity_unit}</span>")
    with col4:
        bordered_metric_2("Lowest Emissions Factor", f"{ef_min}<br><span style='font-size:0.6em;'>{ef_min_asset}</span>", value_color='green')
    with col5:
        bordered_metric_2("Highest Emissions Factor", f"{ef_max}<br><span style='font-size:0.6em;'>{ef_max_asset}</span>", value_color='red')


    st.markdown(
        f"""
        <div style="text-align:left; font-size:24px; margin-top:10px;">
            <b>Climate TRACE ({selected_year})</b> {selected_subsector} - {round(len(df_assets)):,} total assets
        </div>
        """,
        unsafe_allow_html=True
    )

    # Display in Streamlit
    st.plotly_chart(fig, use_container_width=True)

    df_table = df_assets.copy()
    df_table['asset_url'] = "https://climatetrace.org/explore/#admin=&gas=co2e&year=2024&timeframe=100&sector=&asset=" + df_table['asset_id'].astype(str)
    df_table = df_table[['asset_name', 'asset_url', 'country_name', 'gadm_1_name', 'gadm_2_name', 'emissions_quantity', 'emissions_factor']]
    df_table = df_table.sort_values('emissions_quantity', ascending=False).reset_index(drop=True)
    df_table['emissions_quantity'] = df_table['emissions_quantity'].round().apply(lambda x: f"{int(x):,}")
    st.markdown(f"### {selected_subsector} assets")

    row_height = 35  # pixels per row (adjust as needed)
    num_rows = 20
    table_height = row_height * num_rows + 35  # extra for header

    st.dataframe(
        df_table,
        use_container_width=True,
        column_config={
            "asset_url": st.column_config.LinkColumn(display_text="asset_name")
        },
        height=table_height
    )
