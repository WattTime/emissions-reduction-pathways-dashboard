import pandas as pd
import io
import streamlit as st
import html
import numpy as np


'''
This function builds SQL for the pie chart on Reduction Opportunities tab. This will
function the same regardless of whether the user has Climate TRACE Solutions or
Percentile Benchmarking selected as their reduction method.

Returns: country_sql

Type: string (SQL)
'''
def build_country_sql(table, where_sql):
    
    country_sql = f"""
        SELECT 
            year,
            sector,
            SUM(emissions_quantity) AS country_emissions_quantity
        FROM '{table}'
        
        {where_sql}
        
        GROUP BY year, sector
        
        ORDER BY sector
    """

    return country_sql

'''

'''
def build_sector_reduction_sql():


    return


'''

'''
def build_asset_reduction_sql():

    
    return


'''

'''
def build_sentence_4_sql():

    
    return