import pandas as pd
import io
import streamlit as st
import html
import numpy as np

'''
ABATEMENT CURVE TAB
- create_assets_filter_sql(), create_country_filter_sql()
- These are the SQL queries for asset filtering/highlighting. This will change depending on the sectors and year selected. 

Returns: query_assets_sql

Type: string (SQL)
'''

def create_assets_filter_sql(annual_asset_path, selected_subsector, selected_year, selected_country):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    formatted_country = ', '.join(f"'{country}'" for country in selected_country)
    query_assets_sql = f'''
        WITH top_assets AS (
            SELECT
                ae.asset_id,
                ae.asset_name,
                ae.iso3_country,
                ae.country_name,
                ae.balancing_authority_region,
                (ae.iso3_country || ': ' || ae.asset_name || ' (' || CAST(ae.asset_id AS TEXT) || ')') AS selected_asset_list,
                ae.total_emissions_reduced_per_year AS net_reduction_potential
            FROM '{annual_asset_path}' ae
            WHERE 
                ae.subsector IN ({formatted_subsectors})
                AND ae.year = {selected_year}
                AND ae.reduction_q_type = 'asset'
                AND ae.iso3_country IN ({formatted_country})
            ORDER BY net_reduction_potential DESC
        )
        SELECT *
        FROM top_assets
        ORDER BY selected_asset_list ASC;
    '''
    return query_assets_sql

def create_country_filter_sql(annual_asset_path, selected_subsector, selected_year):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    query_assets_sql = f'''
        SELECT
            ae.subsector,
            ae.iso3_country,
            ae.country_name,
            (ae.iso3_country || ': ' || ae.subsector) AS selected_asset_list,
            ae.total_emissions_reduced_per_year AS net_reduction_potential
        FROM '{annual_asset_path}' ae
        WHERE 
            ae.subsector IN ({formatted_subsectors})
            AND ae.year = {selected_year}
            AND ae.reduction_q_type = 'asset'
        GROUP BY   
            ae.subsector,
            ae.iso3_country,
            ae.country_name,
            ae.total_emissions_reduced_per_year
        ORDER BY selected_asset_list;
    '''
    return query_assets_sql

'''
ABATEMENT CURVE TAB
- find_sector_assets_sql(), find_sector_country_sql()
- These are the SQL queries to find all assets and their GADM information within selected sectors and year. 

Returns: query_sector_assets_sql

Type: string (SQL)
'''

def find_sector_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year, selected_country):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    formatted_country = ', '.join(f"'{country}'" for country in selected_country)
    query_sector_assets_sql = f'''
        SELECT 
            ae.year,
            ae.asset_id,
            ae.asset_name,
            ae.asset_type,
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
            ae.reduction_q_type,
            gadm0.gid_0,
            ae.gadm_1,
            gadm1.gid_1,
            gadm1.gadm_1_name,
            ae.gadm_2,
            gadm2.gid_2,
            gadm2.gadm_2_name,
            ae.activity_units,
            ae.strategy_name,
            CASE WHEN BOOL_OR(ae.activity_is_temporal) THEN SUM(ae.activity) ELSE AVG(ae.activity) END AS activity,
            SUM(ae.capacity) AS capacity,
            SUM(ae.emissions_quantity) AS emissions_quantity,
            SUM(ae.emissions_quantity) / 
                NULLIF(
                    (CASE WHEN BOOL_OR(ae.activity_is_temporal) 
                        THEN SUM(ae.activity) 
                            ELSE AVG(ae.activity) END), 0) AS emissions_factor,
            ae.emissions_reduced_at_asset AS asset_reduction_potential,
            ae.total_emissions_reduced_per_year AS net_reduction_potential
        FROM '{annual_asset_path}' ae
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_0, 
                iso3_country 
            FROM '{gadm_0_path}'
            WHERE try_cast(gid AS INTEGER) IS NOT NULL
        ) gadm0 ON ae.iso3_country = gadm0.iso3_country
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_1,
                gadm_id AS gadm_1,
                gadm_1_corrected_name AS gadm_1_name
            FROM '{gadm_1_path}'
        ) gadm1 ON ae.gadm_1 = gadm1.gadm_1
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_2,
                gadm_2_id AS gadm_2,
                gadm_2_corrected_name AS gadm_2_name
            FROM '{gadm_2_path}'
        ) gadm2 ON ae.gadm_2 = gadm2.gadm_2
        WHERE 
            ae.subsector IN ({formatted_subsectors})
            AND ae.year = {selected_year}
            AND ae.reduction_q_type = 'asset'
            AND ae.iso3_country IN ({formatted_country})
        GROUP BY
            ae.year,
            ae.asset_id,
            ae.asset_name,
            ae.asset_type,
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
            ae.reduction_q_type,
            gadm0.gid_0,
            ae.gadm_1,
            gadm1.gid_1,
            gadm1.gadm_1_name,
            ae.gadm_2,
            gadm2.gid_2,
            gadm2.gadm_2_name,
            ae.activity_units,
            ae.strategy_name,
            ae.emissions_reduced_at_asset,
            ae.total_emissions_reduced_per_year
        ORDER BY ae.total_emissions_reduced_per_year DESC;
    '''
    return query_sector_assets_sql

def find_sector_country_sql(annual_asset_path, selected_subsector, selected_year):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    query_sector_assets_sql = f'''
        SELECT 
            ae.year,
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
            ae.reduction_q_type,
            ae.activity_units,
            ae.strategy_name,
            CASE WHEN BOOL_OR(ae.activity_is_temporal) THEN SUM(ae.activity) ELSE AVG(ae.activity) END AS activity,
            SUM(ae.capacity) AS capacity,
            SUM(ae.emissions_quantity) AS emissions_quantity,
            SUM(ae.emissions_quantity) / 
                NULLIF(
                    (CASE WHEN BOOL_OR(ae.activity_is_temporal) 
                        THEN SUM(ae.activity) 
                            ELSE AVG(ae.activity) END), 0) AS emissions_factor,
            ae.emissions_reduced_at_asset AS asset_reduction_potential,
            ae.total_emissions_reduced_per_year AS net_reduction_potential
        FROM '{annual_asset_path}' ae
        WHERE 
            ae.subsector IN ({formatted_subsectors})
            AND ae.year = {selected_year}
            AND ae.reduction_q_type = 'asset'
        GROUP BY
            ae.year,
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
            ae.reduction_q_type,
            ae.activity_units,
            ae.strategy_name,
            ae.emissions_reduced_at_asset,
            ae.total_emissions_reduced_per_year
        ORDER BY ae.total_emissions_reduced_per_year DESC;
    '''
    return query_sector_assets_sql

'''
ABATEMENT CURVE TAB
- summarize_totals_sql()
- This is the SQL query to total summary information for assets, emissions, ERS, etc. 

Returns: query_total_sql

Type: string (SQL)
'''

def summarize_totals_sql(annual_asset_path, selected_subsector, selected_year, selected_country):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    formatted_country = ', '.join(f"'{country}'" for country in selected_country)
    query_total_sql = f'''
        WITH summary_by_asset AS (
            SELECT
                iso3_country,
                balancing_authority_region,
                asset_id,
                strategy_name,
                SUM(emissions_quantity) AS emissions_sum,
                total_emissions_reduced_per_year
            FROM '{annual_asset_path}'
            WHERE subsector IN ({formatted_subsectors})
            AND year = {selected_year}
            AND reduction_q_type = 'asset'
            AND iso3_country IN ({formatted_country})
            GROUP BY iso3_country, balancing_authority_region, asset_id, strategy_name, total_emissions_reduced_per_year
        )
        SELECT
            COUNT(DISTINCT strategy_name) AS total_ers,
            SUM(emissions_sum) AS total_emissions,
            SUM(total_emissions_reduced_per_year) AS total_reductions,
            COUNT(DISTINCT asset_id) AS total_assets,
            COUNT(DISTINCT iso3_country) AS total_countries,
            COUNT(DISTINCT balancing_authority_region) AS total_ba
        FROM summary_by_asset;
    '''
    return query_total_sql

'''
ABATEMENT CURVE TAB
- summarize_ers_sql(), create_table_assets_sql()
- These are the SQL queries to summarize ERS information into two tables - overview of all solutions and top opportunities

Returns: query_ers_sql, query_table_assets_sql

Type: string (SQL)
'''

def summarize_ers_sql(annual_asset_path, selected_subsector, selected_year, selected_country):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    formatted_country = ', '.join(f"'{country}'" for country in selected_country)
    query_ers_sql = f'''
        WITH asset_level AS (
            SELECT asset_id,
                subsector,
                strategy_name,
                strategy_description,
                mechanism,
                SUM(emissions_quantity) AS total_emissions_quantity,
                MAX(emissions_reduced_at_asset) AS emissions_reduced_at_asset,
                MAX(total_emissions_reduced_per_year) AS total_emissions_reduced_per_year 
            FROM '{annual_asset_path}'
            WHERE subsector IN ({formatted_subsectors})
            AND year = {selected_year}
            AND reduction_q_type = 'asset'
            AND iso3_country in ({formatted_country})
            GROUP BY asset_id, subsector, strategy_name, strategy_description, mechanism
        )
        SELECT subsector,
            strategy_name,
            strategy_description,
            mechanism,
            COUNT(distinct asset_id) AS assets_impacted,
            ROUND(SUM(total_emissions_quantity), 0) AS emissions_quantity,
            ROUND(SUM(emissions_reduced_at_asset), 0) AS total_asset_reduction_potential,
            ROUND(SUM(total_emissions_reduced_per_year), 0) AS total_net_reduction_potential
        FROM asset_level
        GROUP BY subsector, strategy_name, strategy_description, mechanism
        ORDER BY total_net_reduction_potential DESC
    '''

    return query_ers_sql


def create_table_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year, selected_country):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    formatted_country = ', '.join(f"'{country}'" for country in selected_country)
    query_table_assets_sql = f'''
        SELECT 
            ae.subsector,
            ae.year,
            ae.asset_id,
            ae.asset_name,
            ae.iso3_country,
            ae.country_name,
            gadm0.gid_0,
            ae.gadm_1,
            gadm1.gid_1,
            gadm1.gadm_1_name,
            ae.gadm_2,
            gadm2.gid_2,
            gadm2.gadm_2_name,
            ae.activity_units,
            ae.strategy_name,
            ae.strategy_description,
            ae.mechanism,
            SUM(ae.activity) AS activity,
            SUM(ae.capacity) AS capacity,
            ROUND(SUM(ae.emissions_quantity), 0) AS "emissions_quantity (t CO2e)",
            SUM(ae.emissions_quantity) / NULLIF(SUM(ae.activity), 0) AS emissions_factor,
            ROUND(ae.emissions_reduced_at_asset) AS "asset_reduction_potential (t CO2e)",
            ROUND(ae.total_emissions_reduced_per_year) AS "net_reduction_potential (t CO2e)"
        FROM '{annual_asset_path}' ae
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_0, 
                iso3_country 
            FROM '{gadm_0_path}'
            WHERE try_cast(gid AS INTEGER) IS NOT NULL
            ) gadm0
        ON ae.iso3_country = gadm0.iso3_country
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_1,
                gadm_id AS gadm_1,
                gadm_1_corrected_name AS gadm_1_name
            FROM '{gadm_1_path}'
            ) gadm1
        ON ae.gadm_1 = gadm1.gadm_1
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_2,
                gadm_2_id AS gadm_2,
                gadm_2_corrected_name AS gadm_2_name
            FROM '{gadm_2_path}'
        ) gadm2
        ON ae.gadm_2 = gadm2.gadm_2
        WHERE 
            subsector IN ({formatted_subsectors})
            AND year = {selected_year}
            AND reduction_q_type = 'asset'
            AND ae.iso3_country IN ({formatted_country})
        GROUP BY
            ae.subsector,
            ae.year,
            ae.asset_id,
            ae.asset_name,
            ae.iso3_country,
            ae.country_name,
            gadm0.gid_0,
            ae.gadm_1,
            gadm1.gid_1,
            gadm1.gadm_1_name,
            ae.gadm_2,
            gadm2.gid_2,
            gadm2.gadm_2_name,
            ae.activity_units,
            ae.strategy_name,
            ae.strategy_description,
            ae.mechanism,
            ae.emissions_reduced_at_asset,
            ae.total_emissions_reduced_per_year
        ORDER BY total_emissions_reduced_per_year DESC
        LIMIT 200
    '''

    return query_table_assets_sql