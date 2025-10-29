
'''
Creating base table, this can be converted into CTE if desired. 
The left join within this query needs to be changed to whatever table name
you create in postgres with Tings categorical scores
'''
DROP TABLE IF EXISTS RDF;
CREATE TEMPORARY TABLE rdf as
SELECT rdf.*
        , coalesce(rdf.asset_output, 'other') asset_output_fixed
        , cs.confidence
        , cs.confidence_score
        , cs.feasibility
        , cs.feasibility_score
        , cs.cost
        , cs.cost_score as cost_score
        , mg.most_granular
        , mg.ghs_fua

FROM reductions_data_fusion rdf
inner join (
        select distinct ae.asset_id
                , ae.most_granular
                , al.ghs_fua

        from asset_emissions_data_fusion ae
        left join asset_location_data_fusion al
                on al.asset_id = ae.asset_id

        where (start_time >= '2024-01-01'
                and start_time <= '2024-12-01')
                and gas = 'co2e_100yr'
) mg
        on mg.asset_id = rdf.asset_id

''' 
Upload this file below as a table in postgres. One thing that might make
sense to do is to add the feasibility and cost text values and numeric scores
into the prod strategy table.
'''
LEFT JOIN read_parquet('data/strategy/categorical_scores/strategy_categorical_scores.parquet') cs
        AND cs.strategy_id = rdf.strategy_id 

WHERE rdf.strategy_rank = 1
        AND rdf.gas = 'co2e_100yr';



'''
This first CTE calculates a reduction factor for each asset as
its reduction potential per unit of activity. 

As of right now, we are only calculating scores for assets that 
have both activity and total_emissions_produced_per_year populated.
'''
WITH asset_rf AS (
        SELECT
                asset_id
                , asset_output_fixed asset_output
                , strategy_id
                , strategy_name
                , strategy_description
                , iso3_country
                , original_inventory_sector AS subsector
                , old_emissions_factor
                , old_activity
                , total_emissions_reduced_per_year
                , (total_emissions_reduced_per_year / old_activity) AS reduction_factor
                , baseline_emissions AS w_inventory
                , confidence
                , confidence_score
                , feasibility
                , feasibility_score
                , cost
                , cost_score
                , most_granular
                , ghs_fua
        
        FROM rdf
        
        WHERE total_emissions_reduced_per_year IS NOT NULL
                AND old_activity IS NOT NULL
                AND old_activity > 0
        ),

'''
Calculates the mean and standard deviation reduction factor (calculated above)
at the subsector-asset output level, weighted by activity.
'''
subsector_stats AS (
        SELECT
                subsector
                , asset_output
                , SUM(w_inventory) AS subsector_emissions_inventory

                -- activity weighted RF mean                
                , SUM(total_emissions_reduced_per_year) / NULLIF(SUM(old_activity), 0) AS mu_rf

                -- activited weighted RF std_dev 
                , SQRT(
                        GREATEST(
                                SUM(old_activity * POWER(reduction_factor, 2)) / NULLIF(SUM(old_activity), 0)
                                        - POWER( SUM(old_activity * reduction_factor) / NULLIF(SUM(old_activity), 0), 2 ),
                        0
                )
                ) AS sigma_rf
        
        FROM asset_rf

        WHERE most_granular = TRUE
        
        GROUP BY subsector
                , asset_output
),

'''
Calculates Reduction Factor z-score at the asset level, bounded
from -3 to 3, and then linearly scaled down to -2 to 2. 

We bound first to control outliers, and then scale to fit the data cleanly.
The score is also inverted so low is "good" and high is "bad". In the 
this rf_score, low will represent more reduction per unit of activity
relative to similar assets.
'''
rf_score as (
        
        SELECT
                a.asset_id
                , a.asset_output
                , a.strategy_id
                , a.strategy_name
                , a.strategy_description
                , a.most_granular
                , a.iso3_country
                , a.ghs_fua
                , a.subsector
                , a.old_emissions_factor
                , a.old_activity
                , a.total_emissions_reduced_per_year
                , a.reduction_factor
                , a.w_inventory
                , s.mu_rf
                , s.sigma_rf
                , CASE
                        WHEN s.sigma_rf IS NULL OR s.sigma_rf < 1e-12 THEN 0.0
                        ELSE (a.reduction_factor - s.mu_rf) / s.sigma_rf
                END AS asset_rf_zscore
                
                , CASE
                        WHEN s.sigma_rf IS NULL OR s.sigma_rf < 1e-12 THEN 0.0
                        ELSE
                        GREATEST(-2.0, LEAST(2.0,
                        -1 * (                 -- invert so high z = good becomes low score
                                CASE
                                        WHEN (a.reduction_factor - s.mu_rf) / s.sigma_rf < -3 THEN -3
                                        WHEN (a.reduction_factor - s.mu_rf) / s.sigma_rf > 3 THEN 3
                                        ELSE (a.reduction_factor - s.mu_rf) / s.sigma_rf
                                END
                                * (2.0 / 3.0)        -- scale from bounds of 3 to bounds of 2
                        )
                        ))
                END AS asset_rf_score
                
                , confidence
                , confidence_score
                , feasibility
                , feasibility_score
                , cost
                , cost_score
                

        FROM asset_rf a
        INNER JOIN subsector_stats s 
                on a.subsector = s.subsector
                and a.asset_output = s.asset_output
),

'''
Round rf_score to 2 decimal places to prepare for tie breaking logic
'''
rf_rounded AS (
        SELECT *
                ,  ROUND(asset_rf_score, 2) AS rf_rounded

        FROM rf_score
),

'''
For tie breaking logic, place each asset into a bucket that has the
same Reduction Factor Score, and calculate the size of that bucket.
The ranking (rf_score tie breaker) is based on total_emissions_reduced_per_year
for a given asset.
'''
rf_rank AS (
        SELECT *,
                RANK() OVER (
                        PARTITION BY rf_rounded
                        ORDER BY total_emissions_reduced_per_year DESC  -- higher emitters get higher rank
                ) AS tie_break_rank,
                
                COUNT(*) OVER (
                        PARTITION BY rf_rounded
                ) AS bucket_size
        FROM rf_rounded
),

'''
Adjust the rf_score to append the rank digits. This ensures no
asset will have the same RF_score
'''
rf_score_final AS (
        SELECT *,
                -- number of digits in bucket size
                LENGTH(CAST(bucket_size AS TEXT)) AS bucket_digits,

                -- adjusted opportunity score: preserve 2 base decimals, append rank digits
                CASE 
                WHEN rf_rounded > 0 THEN
                CAST(rf_rounded AS DOUBLE)
                        + (
                        CAST(tie_break_rank AS DOUBLE)
                        / POWER(10.0, LENGTH(CAST(bucket_size AS TEXT)) + 2)
                        )
                ELSE
                CAST(rf_rounded AS DOUBLE)
                        - (
                        CAST(tie_break_rank AS DOUBLE)
                        / POWER(10.0, LENGTH(CAST(bucket_size AS TEXT)) + 2)
                        )
                END AS rf_score_final
        FROM rf_rank
)

'''
Calculate the asset level opportunity_score as the average 
of the feasability scores, PLUS the rf_score. The opportunity score 
is finally scaled to represent a number between 1 and 10, low being a
stronger score and high being a weaker score.
'''
SELECT
        asset_id,
        strategy_id,
        strategy_name,
        strategy_description,
        most_granular,
        iso3_country,
        ghs_fua,
        subsector,
        rf_score_final as asset_rf_score,
        feasibility,
        feasibility_score,
        cost as cost,
        cost_score,
        total_emissions_reduced_per_year,
        tie_break_rank,
        bucket_size,
        ( ((cost_score + feasibility_score) / 2) + rf_score_final + 1 ) * 9.0/8.0 + 1 AS opportunity_score

FROM rf_score_final

ORDER BY opportunity_score ASC