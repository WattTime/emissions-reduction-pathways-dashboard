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
# utils_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'utils'))
# main_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
# if main_path not in sys.path:
#     sys.path.append(main_path)
# if utils_path not in sys.path:
#     sys.path.append(utils_path)

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
from utils.utils import (format_dropdown_options, 
                         map_region_condition, 
                         format_number_short, 
                         create_excel_file, 
                         bordered_metric, 
                         map_percentile_col,
                         is_country,
                         reset_city,
                         reset_state_and_county)

curYear, numYear = 2024, 1

#Relabeling group column values for charts
dict_relabel = {
        'unfccc_annex': {True: 'Annex1', False: 'Non-Annex1'},
        'em_finance': {True: 'Emerging Markets', False: 'Developed Markets'},
}

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
dict_color['asset_type'] = {
    'Smelting': '#407076',
    'Refinery': '#FBBA1A'
}
dict_color['continent'] = {
    'Europe': '#03A0E3',  # blue
    'North America': '#9554FF',  # purple
    'Asia': '#E8516C',  # red
    'Africa': '#407076',  # brown
    'South America': '#0BCF42',  # green
    'Oceania': '#FF6F42',  # orange
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

dict_lines['electricity-generation'] = {
    #MOER
    # 'more biomass above': 1.5,
    # '50th percentile': 0.63,
    # '10th percentile': 0.42,
    # 'renewables': 0.10,

    #Average ef
    # '50th percentile': 0.58,
    # '10th percentile': 0.1,
}

dict_lines['iron-and-steel'] = {
    #MOER
    # '50th percentile': 0.69,
    # '10th percentile': 0.43,

    #Average of
    # '50th percentile': 0.58,
    # '10th percentile': 0.37,
}

dict_lines['solid-waste-disposal'] = {
    'more landfills above': 3,
    # '50th percentile': 1.24,
    # '10th percentile': 0.69,
    # 'covered landfills': 0.01,
}

dict_lines['road-transportation'] = {
#     'Motorbike': 0.0000465,
#     'Hybrid': 0.000118,
#     'Sedan': 0.000155,
#     'Truck': 0.000221,
#     'Pickup': 0.000268,
}

dict_lines['aluminum'] = {
#     'Motorbike': 0.0000465,
#     'Hybrid': 0.000118,
#     'Sedan': 0.000155,
#     'Truck': 0.000221,
#     'Pickup': 0.000268,
}

def lighten_hex_color(hex_color, factor=0.2):
    """
    Lightens a hex color by a specified factor.
    
    :param hex_color: Hex code of the color to lighten (e.g., '#ff5733').
    :param factor: The factor by which to lighten the color. Default is 0.2.
    :return: Lightened hex color code.
    """
    # Convert hex to RGB
    rgb = mcolors.hex2color(hex_color)
    
    # Scale the RGB values
    rgb_lightened = [min(1, x + factor) for x in rgb]  # Ensure that the values do not go above 1
    
    # Convert back to hex
    hex_lightened = mcolors.rgb2hex(rgb_lightened)
    
    return hex_lightened

def plot_stairs(gdf_asset, choice_group, choice_color, dict_color, dict_lines, cond={}):
    #Setup
    cond0 = {
        'label': True,
        'label_distance': 0.003,
        'label_distance_scalar': 20,
        'label_limit': 0.2,
        'sort': ['average_emissions_factor','activity'],
        'sort_order': [False,True],
        'xaxis': ['activity'],  #not sured as yet
        'yaxis': ['average_emissions_factor'],   #not used as yet
    }
    for k,v in cond0.items():
        if k not in cond: cond[k] = v

    # Example data
    df = gdf_asset.copy()
    sector1 = df.subsector.unique()[0]

    # *** Remove data for easy viewing ***
    if choice_group == 'asset':
        if sector1 in ['solid-waste-disposal']:
            df = df.loc[df['average_emissions_factor']<=3,:]
        elif sector1 in ['electricity-generation']:
            df = df.loc[df['average_emissions_factor']<=1.5,:]
        elif sector1 in ['road-transportation']:
            df = df.loc[df['average_emissions_factor']<=5,:]

    if choice_group == 'asset':
        df = df.sort_values(cond['sort'], ascending=cond['sort_order'])
        df = df.reset_index(drop=True)
        df['activity_cum'] = df['activity'].cumsum()

        df[choice_color] = df[choice_color].apply(lambda x: False if pd.isna(x)==True else x)
        df['color'] = df[choice_color].map(dict_color[choice_color])
        df['color'] = df['color'].apply(lambda x: lighten_hex_color(x,0))

    elif choice_group in ['country', 'BA']:
        if choice_group == 'country':
            fds_key = [choice_color] + ['iso3_country','country_name','sector','subsector']
        else:
            fds_key = [choice_color] + ['iso3_country','country_name',choice_group,'sector','subsector']

        df = df.pivot_table(index=fds_key, values=['activity','emissions_quantity'], aggfunc='sum')
        df['average_emissions_factor'] = df['emissions_quantity']/df['activity']
        df = df.sort_values(cond['sort'], ascending=cond['sort_order'])

        if sector1 in ['road-transportation']:
            df = df.loc[df['average_emissions_factor']<=5,:]
        elif sector1 in ['electricity-generation']:
            df = df.loc[df['average_emissions_factor']<=1.5,:]
        df = df.reset_index()

        df['activity_cum'] = df['activity'].cumsum()
        df['color'] = 'red'
        df['color'] = df[choice_color].map(dict_color[choice_color])
        df['color'] = df['color'].apply(lambda x: lighten_hex_color(x,0))

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
        y=[df['average_emissions_factor'][1], df['average_emissions_factor'][1]],  # From 0 to the second emissions factor (row 1) and back to 0
        fill='tozeroy',  # Fill the area under the line (this is the key)
        fillcolor=f'{df["color"][1]}',  # Use the color of row 1 for the shading
        line=dict(color=f'{df["color"][1]}', width=2),  # Line color for the shading (row 1)
        mode='lines',  # Lines to connect the points
        name=f"{df['iso3_country'][1]}",  # Name for the first point (row 1)
        line_shape='hv',  # Step function line shape (horizontal-vertical)
        legendgroup=f'{df["color"][1]}',  # Grouping by color
        showlegend=False  # Show legend entry for each segment
    ))

    list_label, count_label = [], 0
    ax_x_max = df['activity_cum'].max() 
    num_max = len(df)
    for i in range(2,len(df)):
        color_value = df['color'][i]  # Get the color from the color_variable
        fig.add_trace(go.Scatter(
            x=[df['activity_cum'][i-1], df['activity_cum'][i]],  # X values for the segment
            y=[df['average_emissions_factor'][i-1], df['average_emissions_factor'][i]],  # Y values for the segment
            fill='tozeroy',  # Fill the area under the line
            fillcolor=f'{color_value}',  # Set fill color
            line=dict(color=f'{color_value}', width=2),  # Set line color
            mode='lines',  # Lines to connect the points
            name=f"{df['iso3_country'][i]}",  # Name for the legend
            line_shape='hv',  # Step function line shape (horizontal-vertical)
            legendgroup=f"{color_value}",  # Grouping by color
            showlegend=False  # Show legend entry for each segment
        ))

        # Add annotation for the shaded area with a line pointing to the area
        if cond['label']:
            count_label += df['activity'][i]
            if df['activity'][i] / ax_x_max >= cond['label_distance']:
                if (i <= num_max*(1-cond['label_limit'])) and (df['country_name'][i] not in list_label) and (count_label/ax_x_max >= cond['label_distance']*cond['label_distance_scalar']):
                    count_label = 0
                    list_label += [df['country_name'][i]]
                    fig.add_annotation(
                        x=df['activity_cum'][i-1] + (df['activity_cum'][i]-df['activity_cum'][i-1])/2,  # Position the annotation at the x-value of the end of the shaded area
                        y=df['average_emissions_factor'][i]*1.01,  # Position it slightly above the maximum y-value of the shaded area
                        text='<br>'.join(df['country_name'][i].split(' ')),  # Replace with your desired text
                        showarrow=True,  # Show an arrow pointing to the shaded area
                        arrowhead=1,  # Customize the arrow's appearance
                        ax=0,  # Set the x distance for the arrow line (zero for no offset)
                        font=dict(size=12, color="#444546"),  # Customize the annotation text style
                        align="center",  # Align the text in the center
                    )

    # Add custom legend items (invisible markers) for each color in the color field
    dict_color_reverse = {v: k for k, v in dict_color[choice_color].items()}
    for color_label, color_value in dict_color[choice_color].items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None],  # Invisible data point (None)
            mode='markers',  # Marker mode
            marker=dict(color=color_value, size=10),  # Marker color
            name=f"{color_label}",  # Custom legend name based on color
            showlegend=True  # Ensure it shows in the legend
        ))

    # Update layout
    # df_schema = ct.get_data('database','asset_schema')
    # fld_schema = df_schema.loc[df_schema['subsector']==gdf_asset.subsector.unique().tolist()[0], "activity"].iloc[0]
    fig.update_layout(
        title=f'Climate TRACE: {sector1} ({curYear})',
        # xaxis_title=f"activity ({fld_schema if 'xaxis_title' not in cond else cond['xaxis_title']})",
        # yaxis_title=f"emissions factor (t of CO2e per {fld_schema if 'yaxis_title' not in cond else cond['yaxis_title']})",
        showlegend=True,  # Show legend
        legend=dict(
            x=0,  # X position (0 is the left edge)
            y=1,  # Y position (1 is the top edge)
            xanchor='left',  # Anchors the legend on the left side
            yanchor='top',  # Anchors the legend at the top side
        ),
        plot_bgcolor='rgba(0,0,0,0)',  # Transparent background
        margin=dict(l=50, r=50, t=50, b=50),  # Adjust margins

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
            range=[0, round(max(df['average_emissions_factor']), 4) if max(df['average_emissions_factor'])<1 else math.ceil(max(df['average_emissions_factor']))],  # Adjust the y-axis range
        ),
        height=600,
        width=1200,
    
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
        ax_y_max = max(df['average_emissions_factor'])
        text_y = line_y
        if line_y + 0.015 * ax_y_max > ax_y_max:
            text_y = line_y - 0.015 * ax_y_max
        elif line_y - 0.015 * ax_y_max < 0:
            text_y = line_y + 0.015 * ax_y_max

        fig.add_annotation(
            x=x_max + 1,  # Place the text beyond the x-axis maximum
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

    # Filter subsector selection using Streamlit widget
    col1, col2, col3 = st.columns(3)

    with col1:
        subsector_choice = st.selectbox(
            "Select subsector",
            options=['iron-and-steel', 'aluminum', 'electricity-generation']
        )

    with col2:
        choice_group = st.selectbox(
            "Group type",
            ["asset", "country", "BA"]
        )

    with col3:
        choice_color = st.selectbox(
            "Color category",
            ['unfccc_annex', 'em_finance', 'continent', 'sector']
        )

    con = duckdb.connect()

    query_assets = f'''
            SELECT *
            FROM '{annual_asset_path}'
            WHERE subsector = '{subsector_choice}'
        '''

    test = con.execute(query_assets).df()
    test['unfccc_annex'] = test['unfccc_annex'].replace(dict_relabel['unfccc_annex'])
    test['em_finance'] = test['em_finance'].replace(dict_relabel['em_finance'])  

    # Call your function
    fig = plot_stairs(test, choice_group, choice_color, dict_color, dict_lines)

    # Display in Streamlit
    st.plotly_chart(fig, use_container_width=True)