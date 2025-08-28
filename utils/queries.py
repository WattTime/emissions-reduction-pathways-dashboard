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

                    FROM '{annual_asset_path}'

                    WHERE subsector not in ('non-residential-onsite-fuel-usage',
                                            'residential-onsite-fuel-usage',
                                            'oil-and-gas-production',
                                            'oil-and-gas-transport'
                                        )

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
                                WHERE induced_sector_1 IS NOT NULL
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
                                WHERE induced_sector_2 IS NOT NULL
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
                                WHERE induced_sector_3 IS NOT NULL
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

'''
def build_asset_reduction_sql(use_ct_ers,
                                annual_asset_path,
                                dropdown_join,
                                reduction_where_sql,
                                percentile_path=None,
                                percentile_col=None,
                                selected_proportion=None,
                                benchmark_join=None):

    if use_ct_ers is True:
        
        asset_table_query = f"""
            SELECT

            FROM (
                asset_name
            )
        """
    
    else:

        asset_table_query = f"""
            SELECT asset_name
                , country_name
                , sector
                , subsector
                , asset_type
                , emissions_quantity
                , emissions_reduction_potential
            
            FROM (
                SELECT 
                    ae.asset_name,
                    ae.asset_type,
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
                    and lower(ae.asset_type) <> 'biomass'
                
                GROUP BY 
                    ae.asset_name,                
                    ae.country_name,
                    ae.sector,
                    ae.subsector,
                    ae.asset_type,
                    pct.{percentile_col}
            ) assets

            where rank <= 100

            order by rank asc
        """
    
    return asset_table_query