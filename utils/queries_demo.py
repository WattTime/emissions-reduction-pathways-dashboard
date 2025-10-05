import pandas as pd
import io
import streamlit as st
import html
import numpy as np

'''
This is the SQL query for the asset filtering/highlighting in the Abatement Curve tab. 
This will change depending on the sector and year selected.

Returns: query_assets_sql

Type: string (SQL)
'''

def create_assets_filter_sql(annual_asset_path, selected_subsector, selected_year):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    query_assets_sql = f'''
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
        ORDER BY net_reduction_potential desc
        limit 1000;
    '''
    return query_assets_sql

'''
This is the SQL query to find all assets and their GADM information within a 
sector/year in the Abatement Curve tab. This table is used to create the 
abatement curve chart as well as populate the asset data table. 

Returns: query_sector_assets_sql

Type: string (SQL)
'''

def query_country_sector(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year):
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
            gadm0.gid_0,
            ae.gadm_1,
            gadm1.gid_1,
            gadm1.gadm_1_name,
            ae.gadm_2,
            gadm2.gid_2,
            gadm2.gadm_2_name,
            ae.activity_units,
            ae.strategy_name,
            count(distinct asset_id) asset_count,
            SUM(ae.activity) AS activity,
            SUM(ae.capacity) AS capacity,
            SUM(ae.emissions_quantity) AS emissions_quantity,
            SUM(ae.emissions_quantity) / NULLIF(SUM(ae.activity), 0) AS emissions_factor,
            ae.emissions_reduced_at_asset AS asset_reduction_potential,
            ae.total_emissions_reduced_per_year AS net_reduction_potential
        FROM '{annual_asset_path}' ae
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_0, 
                iso3_country 
            FROM '{gadm_0_path}'
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
        ORDER BY net_reduction_potential DESC;
    '''
    return query_sector_assets_sql

def query_top_1000_assets(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    query_top_1000_assets = f'''
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
            gadm0.gid_0,
            ae.gadm_1,
            gadm1.gid_1,
            gadm1.gadm_1_name,
            ae.gadm_2,
            gadm2.gid_2,
            gadm2.gadm_2_name,
            ae.activity_units,
            ae.strategy_name,
            SUM(ae.activity) AS activity,
            SUM(ae.capacity) AS capacity,
            SUM(ae.emissions_quantity) AS emissions_quantity,
            SUM(ae.emissions_quantity) / NULLIF(SUM(ae.activity), 0) AS emissions_factor,
            ae.emissions_reduced_at_asset AS asset_reduction_potential,
            ae.total_emissions_reduced_per_year AS net_reduction_potential
        FROM '{annual_asset_path}' ae
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_0, 
                iso3_country 
            FROM '{gadm_0_path}'
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
        ORDER BY net_reduction_potential DESC
        limit 1000;
    '''
    return query_top_1000_assets

'''
This is the SQL query for the ERS table in the Abatement Curve tab. 
This summarizes information on the varioius ERS strategies

Returns: query_ers_sql

Type: string (SQL)
'''

def summarize_ers_sql(annual_asset_path, selected_subsector, selected_year):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
    query_ers_sql = f'''
        with de_dupe as (
			select distinct asset_id
                , subsector
                , strategy_name
				, strategy_description
				, mechanism
				, emissions_reduced_at_asset
				, total_emissions_reduced_per_year
		
            from '{annual_asset_path}' 

			WHERE subsector IN ({formatted_subsectors})
		    	AND year = {selected_year}
		)
		
		select subsector
            , strategy_name
			, strategy_description
			, mechanism
			, count(distinct asset_id) assets_impacted
			, ROUND(SUM(emissions_reduced_at_asset), 0) AS total_asset_reduction_potential
			, ROUND(SUM(total_emissions_reduced_per_year), 0) AS total_net_reduction_potential
		
		from de_dupe

		group by subsector
            , strategy_name
			, strategy_description
			, mechanism
		
		order by total_net_reduction_potential DESC
    '''

    return query_ers_sql


def create_table_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year):
    formatted_subsectors = ', '.join(f"'{subsector}'" for subsector in selected_subsector)
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
            round(ae.emissions_reduced_at_asset) AS "asset_reduction_potential (t CO2e)",
            round(ae.total_emissions_reduced_per_year) AS "net_reduction_potential (t CO2e)"
        FROM read_parquet('{annual_asset_path}', filename=true) ae
        LEFT JOIN (
            SELECT DISTINCT
                gid AS gid_0, 
                iso3_country 
            FROM '{gadm_0_path}'
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