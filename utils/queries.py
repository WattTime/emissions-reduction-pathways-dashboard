import pandas as pd
import io
import streamlit as st
import html
import numpy as np


'''
This builds SQL for the pie chart on Reduction Opportunities tab. This will
behave the same regardless of whether the user has Climate TRACE Solutions or
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
This builds SQL for the stacked bar chart Reduction Opportunities tab. This will
dynamically pull in the correct data depending on the selected reduction method,
which could be "Climate TRACE Solutions" or "Percentile Benchmarking"

Returns: sector_reduction_sql_string

Type: string (SQL)
'''
def build_sector_reduction_sql(use_ct_ers,
                                annual_asset_path,
                                dropdown_join,
                                reduction_where_sql,
                                ers_reduction_col=None,
                                percentile_path=None,
                                percentile_col=None,
                                selected_proportion=None,
                                benchmark_join=None
                            ):
    
    if use_ct_ers is True:
        if ers_reduction_col == "emissions_reduced_at_asset":

            sector_reduction_sql_string = f'''
            
                SELECT sector
                    , sum(emissions_quantity) as emissions_quantity
                    , sum(emissions_reduction_potential) emissions_reduction_potential

                FROM (
                    SELECT asset_id
                        , sector
                        , sum(emissions_quantity) as emissions_quantity
                        , {ers_reduction_col} as emissions_reduction_potential

                    FROM '{annual_asset_path}' ae
                    {dropdown_join}

                    {reduction_where_sql}
                        -- and subsector not in ('non-residential-onsite-fuel-usage',
                        --                     'residential-onsite-fuel-usage',
                        --                     'oil-and-gas-production',
                        --                     'oil-and-gas-transport'
                        --                 )


                    GROUP BY asset_id
                        , sector
                        , {ers_reduction_col}
                    
                ) asset_agg

                GROUP BY sector

            '''
            # print(sector_reduction_sql_string)
        
        else:
            sector_reduction_sql_string = f'''
                WITH sector_mapping as (
                    SELECT distinct sector
                        , subsector

                    FROM '{annual_asset_path}'
                ),
                
                induced as (
                    SELECT sector
                        , sum(induced_emissions) as induced_emissions

                    FROM (
                            SELECT
                                sector,
                                sum(induced_emissions) AS induced_emissions
                            FROM (
                                SELECT distinct asset_id
                                    , sector_mapping.sector
                                    , induced_sector_1 AS induced_subsector
                                    , induced_sector_1_induced_emissions AS induced_emissions
                                FROM '{annual_asset_path}' aap
                                LEFT JOIN sector_mapping
                                    on sector_mapping.subsector = aap.induced_sector_1
                                {dropdown_join}

                                {reduction_where_sql}
                            )  

                            group by sector
                            
                            UNION ALL
                                
                            SELECT
                                sector,
                                sum(induced_emissions) AS induced_emissions
                            FROM (
                                SELECT distinct asset_id
                                    , sector_mapping.sector
                                    , induced_sector_2 AS induced_subsector
                                    , induced_sector_2_induced_emissions AS induced_emissions
                                FROM '{annual_asset_path}' aap
                                LEFT JOIN sector_mapping
                                    on sector_mapping.subsector = aap.induced_sector_2
                                {dropdown_join}

                                {reduction_where_sql}
                            )  

                            group by sector
                                
                            UNION ALL
                                
                            SELECT
                                sector,
                                sum(induced_emissions) AS induced_emissions
                            FROM (
                                SELECT distinct asset_id
                                    , sector_mapping.sector
                                    , induced_sector_3 AS induced_subsector
                                    , induced_sector_3_induced_emissions AS induced_emissions
                                FROM '{annual_asset_path}' aap
                                LEFT JOIN sector_mapping
                                    on sector_mapping.subsector = aap.induced_sector_3
                                {dropdown_join}

                                {reduction_where_sql}
                            )  

                            group by sector
                        )

                    GROUP BY sector
                ),

                asset_reductions as (
                    SELECT sector
                        , sum(emissions_quantity) emissions_quantity
                        , sum(emissions_reduced_at_asset) emissions_reduced_at_asset
                
                    FROM (
                        SELECT asset_id
                            , sector
                            , subsector
                            , sum(emissions_quantity) emissions_quantity
                            , emissions_reduced_at_asset

                        FROM '{annual_asset_path}'
                        {dropdown_join}

                        {reduction_where_sql}

                        GROUP BY asset_id
                            , sector
                            , subsector
                            , emissions_reduced_at_asset
                    ) asset

                    GROUP BY sector
                )

                SELECT 
                    COALESCE(ar.sector, induced.sector) AS sector,
                    ar.emissions_quantity,
                    induced.induced_emissions,
                    ar.emissions_reduced_at_asset,
                    
                    CASE 
                        WHEN COALESCE(induced.induced_emissions, 0) > COALESCE(ar.emissions_reduced_at_asset, 0)
                        THEN COALESCE(induced.induced_emissions, 0) - COALESCE(ar.emissions_reduced_at_asset, 0)
                        ELSE 0 
                    END AS induced_emissions,
                    
                    CASE 
                        WHEN COALESCE(induced.induced_emissions, 0) < COALESCE(ar.emissions_reduced_at_asset, 0)
                        THEN COALESCE(ar.emissions_reduced_at_asset, 0) - COALESCE(induced.induced_emissions, 0)
                        ELSE 0 
                    END AS emissions_reduction_potential

                FROM asset_reductions ar
                FULL OUTER JOIN induced
                    on induced.sector = ar.sector
            '''
    
    else:
        sector_reduction_sql_string = f'''
            SELECT 
                sector sector,
                SUM(emissions_quantity) AS emissions_quantity,
                SUM(emissions_reduction_potential) AS emissions_reduction_potential
            
            FROM (
                SELECT 
                    ae.asset_id,
                    ae.sector,
                    ae.subsector,
                    ae.iso3_country,
                    ae.country_name,
                    SUM(ae.activity) AS activity,
                    AVG(ae.ef_12_moer) AS ef_12_moer,
                    
                    CASE 
                        WHEN AVG(ae.ef_12_moer) IS NULL 
                            THEN SUM(ae.emissions_quantity)
                        ELSE SUM(ae.activity) * AVG(ae.ef_12_moer)
                    END AS emissions_quantity,
                    
                    GREATEST(
                        0,
                        CASE 
                            WHEN AVG(ae.ef_12_moer) IS NULL 
                                THEN (SUM(ae.emissions_quantity) - SUM(ae.activity * pct.{percentile_col})) * ({selected_proportion} / 100.0)
                            ELSE ((SUM(ae.activity) * AVG(ae.ef_12_moer)) - SUM(ae.activity * pct.{percentile_col})) * ({selected_proportion} / 100.0)
                        END
                    ) AS emissions_reduction_potential
                
                FROM '{annual_asset_path}' ae
                LEFT JOIN '{percentile_path}' pct
                    ON ae.subsector = pct.original_inventory_sector
                    AND ae.asset_type_2 = pct.asset_type
                    {benchmark_join}
                {dropdown_join}

                {reduction_where_sql}
                
                GROUP BY 
                    ae.asset_id,
                    ae.sector,
                    ae.subsector,
                    ae.iso3_country,
                    ae.country_name
            ) asset_level
                    
            GROUP BY sector
        '''
        # print(sector_reduction_sql_string)

    
    return sector_reduction_sql_string


'''
Builds a query that inserts data into the 4th sentence within the 
"A Possible Emissions Reduction Plan" text block on the Reduction 
Opportunities tab.

Returns: sentence_4_query

Type: string (SQL)
'''
def build_sentence_4_sql(table, where_sql, include_sectors):

    sentence_4_query = f"""
        with sector as (
            select sector
                , sum(emissions_quantity) sector_emissions_quantity

            from '{table}'

            {where_sql}
                and lower(sector) <> 'power'
                and sector in ({include_sectors})

            group by sector
        ),

        subsector as (
            select sector
                , subsector
                , sum(emissions_quantity) subsector_emissions_quantity

            from '{table}'

            {where_sql}
                and lower(sector) <> 'power'
                and sector in ({include_sectors})

            group by sector
                , subsector
        ),

        agg as (
            select subsector.sector
                , subsector.subsector
                , sum(subsector.subsector_emissions_quantity) subsector_emissions_quantity

            from subsector
            inner join sector
                on sector.sector = subsector.sector

            group by subsector.sector
                , subsector.subsector

            having (sum(subsector.subsector_emissions_quantity) / sum(sector.sector_emissions_quantity)) >= 0.05
        ),
        
        subsector_rank as (
            select *
                , row_number() over (partition by sector order by subsector_emissions_quantity desc) as subsector_rank
            from agg
        )

        select *
        from subsector_rank
        where subsector_rank.subsector_rank <= 2

    """
    
    return sentence_4_query


'''
Builds SQL query for the asset table at the bottom of the page. It will
dynamically determine whether or not to use Climate TRACE Solutions, or
the Percentile Benchmarking method based on user selection.

Returns: asset_table_query

Type: string (SQL)
'''
def build_asset_reduction_sql(use_ct_ers,
                                annual_asset_path,
                                dropdown_join,
                                reduction_where_sql,
                                sorting_preference,
                                percentile_path=None,
                                percentile_col=None,
                                selected_proportion=None,
                                benchmark_join=None):
    
    if sorting_preference == 'Net Reduction Potential':
        sorting_col = 'total_emissions_reduced_per_year'
    elif sorting_preference == 'Asset Reduction Potential':
        sorting_col = 'emissions_reduction_potential'
    elif sorting_preference == 'Asset Annual Emissions':
        sorting_col = 'emissions_quantity'

    if not reduction_where_sql:
            reduction_where_sql = f"""Where lower(ae.asset_type) <> 'biomass'"""

    if use_ct_ers is True:

        asset_table_query = f"""
            SELECT asset_id,
                asset_name,
                iso3_country,
                country_name,
                sector,
                subsector,
                asset_type,
                strategy_name,
                SUM(emissions_quantity) AS emissions_quantity,
                coalesce(emissions_reduced_at_asset,0) AS emissions_reduction_potential,
                coalesce(total_emissions_reduced_per_year,0) AS total_emissions_reduced_per_year
            
            FROM '{annual_asset_path}' ae
            {dropdown_join}

            {reduction_where_sql}
            
            GROUP BY asset_id,
                asset_name,
                iso3_country,
                country_name,
                sector,
                subsector,
                asset_type,
                strategy_name,
                coalesce(emissions_reduced_at_asset,0),
                coalesce(total_emissions_reduced_per_year,0)
            
            ORDER BY 
                {sorting_col} DESC
            
            LIMIT 100
        """
    
    else:

        asset_table_query = f"""
            SELECT asset_id 
                , asset_name
                , iso3_country
                , country_name
                , sector
                , subsector
                , asset_type
                , emissions_quantity
                , emissions_reduction_potential
            
            FROM (
                SELECT ae.asset_id,
                    ae.asset_name,
                    ae.asset_type,
                    ae.iso3_country,
                    ae.country_name,
                    ae.sector,
                    ae.subsector,
                    ae.asset_type,
                    
                    SUM(ae.emissions_quantity) AS emissions_quantity,
                    
                    --CASE 
                        --WHEN AVG(ae.ef_12_moer) IS NULL 
                        -- THEN SUM(ae.emissions_quantity)
                    -- ELSE SUM(ae.activity) * AVG(ae.ef_12_moer)
                -- END AS emissions_quantity,

                    GREATEST(
                        0,
                        CASE 
                            WHEN pct.{percentile_col} is null then 0
                            WHEN AVG(ae.ef_12_moer) IS NULL 
                                THEN (SUM(ae.emissions_quantity) - SUM(ae.activity * pct.{percentile_col})) * ({selected_proportion} / 100.0)
                            ELSE ((SUM(ae.activity) * AVG(ae.ef_12_moer)) - SUM(ae.activity * pct.{percentile_col})) * ({selected_proportion} / 100.0)
                        END
                    ) AS emissions_reduction_potential,

                    ROW_NUMBER() OVER (
                        ORDER BY 
                            GREATEST(
                                0,
                                CASE 
                                    WHEN pct.{percentile_col} is null then 0
                                    WHEN AVG(ae.ef_12_moer) IS NULL 
                                        THEN (SUM(ae.emissions_quantity) - SUM(ae.activity * pct.{percentile_col})) * ({selected_proportion} / 100.0)
                                    ELSE ((SUM(ae.activity) * AVG(ae.ef_12_moer)) - SUM(ae.activity * pct.{percentile_col})) * ({selected_proportion} / 100.0)
                                END
                            ) DESC
                    ) AS rank
                
                FROM '{annual_asset_path}' ae
                LEFT JOIN '{percentile_path}' pct
                    ON ae.subsector = pct.original_inventory_sector
                    AND ae.asset_type_2 = pct.asset_type
                    {benchmark_join}
                {dropdown_join}

                {reduction_where_sql}
                
                GROUP BY ae.asset_id,
                    ae.asset_name,     
                    ae.iso3_country,           
                    ae.country_name,
                    ae.sector,
                    ae.subsector,
                    ae.asset_type,
                    pct.{percentile_col}
            ) assets

            -- where rank <= 100

            order by {sorting_col} desc

            limit 100
        """
    
    return asset_table_query


'''
This is the SQL query for the asset filtering/highlighting in the Abatement Curve tab. 
This will change depending on the sector and year selected.

Returns: query_assets_sql

Type: string (SQL)
'''
def create_assets_filter_sql(annual_asset_path, selected_subsector, selected_year):
    
    query_assets_sql = f'''
        SELECT DISTINCT
            ae.asset_id,
            ae.asset_name,
            ae.iso3_country,
            ae.country_name,
            ae.balancing_authority_region,
            (ae.iso3_country || ': ' || ae.asset_name || ' (' || CAST(ae.asset_id AS TEXT) || ')') AS selected_asset_list
        FROM '{annual_asset_path}' ae
        WHERE 
            ae.subsector = '{selected_subsector}'
            AND ae.year = {selected_year}
        ORDER BY selected_asset_list; 
    '''

    return query_assets_sql

'''
This is the SQL query to find all assets and their GADM information within a 
sector/year in the Abatement Curve tab. This table is used to create the 
abatement curve chart as well as populate the asset data table. 

Returns: query_sector_assets_sql

Type: string (SQL)
'''
def find_sector_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year):
    
    query_sector_assets_sql = f'''
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
    '''

    return query_sector_assets_sql


'''
This is the SQL query for the ERS table in the Abatement Curve tab. 
This summarizes information on the varioius ERS strategies

Returns: query_ers_sql

Type: string (SQL)
'''
def summarize_ers_sql(annual_asset_path, selected_subsector, selected_year):
    
    query_ers_sql = f'''
        SELECT 
            ae.strategy_name,
            ae.strategy_description,
            ae.mechanism,
            COUNT(DISTINCT ae.asset_id) AS assets_impacted,
            ROUND(SUM(ae.emissions_reduced_at_asset), 0) AS total_asset_reduction_potential,
            ROUND(SUM(ae.total_emissions_reduced_per_year), 0) AS total_net_reduction_potential
        FROM '{annual_asset_path}' ae
        WHERE 
            ae.subsector = '{selected_subsector}'
            AND ae.year = {selected_year}
        GROUP BY 
            ae.strategy_name,
            ae.strategy_description,
            ae.mechanism
        ORDER BY 
            total_net_reduction_potential DESC
    '''

    return query_ers_sql

def create_table_assets_sql(annual_asset_path, gadm_0_path, gadm_1_path, gadm_2_path, selected_subsector, selected_year):
    
    query_table_assets_sql = f'''
        SELECT 
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
            ROUND(COALESCE(ae.emissions_reduced_at_asset, 0), 0) AS "asset_reduction_potential (t CO2e)",
            ROUND(COALESCE(ae.total_emissions_reduced_per_year, 0), 0) AS "net_reduction_potential (t CO2e)"
        FROM '{annual_asset_path}' ae
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
            subsector = '{selected_subsector}'
            AND year = {selected_year}
        GROUP BY
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
        ORDER BY "emissions_quantity (t CO2e)" DESC
        LIMIT 500
    '''

    return query_table_assets_sql
