CREATE TEMPORARY TABLE rdf as
SELECT 
    rdf.*
        , cs.native_strategy_id
        , coalesce(rdf.asset_output, 'other') asset_output_fixed
        , cs.confidence
        , cs.confidence_score
        , cs.feasibility
        , cs.feasibility_score
        , cs.cost
        , cs.cost_score as cost_score

FROM reductions_data_fusion rdf

'''
This join uses the native strategy ID in Tings file to correctly map
to the correct strategy ID within strategy table
'''
LEFT JOIN ( 
        select cs.*
                , sdf.strategy_id strategy_id_fixed

        ''' 
        This parquet file below should be uploaded as a table in postgres for 
        future re-runs.
        '''     
        from read_parquet('data/strategy/categorical_scores/strategy_categorical_scores.parquet') cs
        left join strategy_data_fusion sdf
                on sdf.native_strategy_id = cs.native_strategy_id
) cs
        on cs.strategy_id_fixed = rdf.strategy_id 
        and cs.subsector = rdf.original_inventory_sector

where rdf.strategy_rank = 1
        and rdf.gas = 'co2e_100yr'
;


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
                , native_strategy_id
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
                --, ghs_fua
        
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
                
                , SUM(total_emissions_reduced_per_year) / NULLIF(SUM(old_activity), 0) AS mu_rf

                , SQRT(
                        GREATEST(
                                SUM(old_activity * POWER(reduction_factor, 2)) / NULLIF(SUM(old_activity), 0)
                                        - POWER( SUM(old_activity * reduction_factor) / NULLIF(SUM(old_activity), 0), 2 ),
                        0
                    )
                ) AS sigma_rf
        
        FROM asset_rf

        where most_granular = true
        
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
            , a.native_strategy_id
            , a.strategy_name
            , a.strategy_description
            , a.most_granular
            , a.iso3_country
            , a.subsector
            , a.old_emissions_factor
            , a.old_activity
            , a.total_emissions_reduced_per_year
            , a.reduction_factor
            , a.w_inventory
            , s.mu_rf
            , s.sigma_rf

            -- raw reduction factor z-score
            , CASE
                    WHEN s.sigma_rf IS NULL OR s.sigma_rf < 1e-12 THEN 0.0
                    ELSE (a.reduction_factor - s.mu_rf) / s.sigma_rf
            END AS asset_rf_zscore
            
            -- reduction factor z-score inverted so low is "more effective", bounded -3 and 3, and scaled -2 to 2
            , CASE
                    WHEN s.sigma_rf IS NULL OR s.sigma_rf < 1e-12 THEN 0.0
                    ELSE
                        GREATEST(-2.0, 
                            LEAST(2.0,
                                -1 * (                 -- invert so high z = good becomes low score
                                        CASE
                                                WHEN (a.reduction_factor - s.mu_rf) / s.sigma_rf < -3 THEN -3
                                                WHEN (a.reduction_factor - s.mu_rf) / s.sigma_rf > 3 THEN 3
                                                ELSE (a.reduction_factor - s.mu_rf) / s.sigma_rf
                                        END
                                        * (2.0 / 3.0)        -- scale +-3 to +-2
                                )
                            )
                        )
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
rf_rounded as (
    select *
            ,  ROUND(asset_rf_score, 2) AS rf_rounded

    from rf_score
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
                    ORDER BY total_emissions_reduced_per_year DESC  -- Higher emitters get higher rank
            ) AS tie_break_rank,
            
            COUNT(*) OVER (
                    PARTITION BY rf_rounded
            ) AS bucket_size
    FROM rf_rounded
),

'''
CTE: rf_score_final

Adjusts the rf_score to append the rank digits appropriately as a tiebreaker. 
Assets with a "tie" rf_score at 2 decimal places will be adjusted so the assets
with greater reduction potential get the more favorable RF score. This also ensures 
no asset will have the same RF_score or final difficulty score. However, the precision
will vary based on how large each tie break bucket is. Examples below.

Negative and positive rf_scores need tie break digits to be appended
inversely so each asset stays within its original 2 decimal digit bucket:

Positive rf_scores example: Add rank digits
    - Score Bucket: 1.11
    - Bucket Size: 131
    - Asset Ranking Within Bucket: 16 of 131 (by total reduction potential)
    Asset Final RF Score = 1.11 (score bucket) + 0.00016 (the ranking expressed in the length of bucket digits +2 decimal places)
     Result -> 1.11016

Negative rf_scores example: Subtract inversed rank digits
    - Score Bucket: -1.11
    - Bucket Size: 131
    - Asset Ranking Within Bucket: 16 of 131 (by total reduction potential)
    Asset Final RF Score = -1.11 (score bucket) - 0.00116 (bucket_size - tie_break_rank + 1 AND +2 decimal places)
     Result -> -1.11116

Although slightly confusing, this logic is necessary so more effective asset-strategy
combinations do not jump behind less effective combinations on the negative side, and vice versa. 
It will smooth the overall score distribution with fine-scale variation within each bucket,
while keeping all assets anchored within their original score ranges.
'''
rf_score_final AS (
    SELECT 
        *
        
        -- number of digits in bucket size
        , LENGTH(CAST(bucket_size AS TEXT)) AS bucket_digits

        -- adjusted opportunity score: preserve 2 base decimals, append rank digits, handle for 
        , CASE  -- simply append digits to positive score
                WHEN rf_rounded > 0 THEN
                        CAST(rf_rounded AS DOUBLE)
                                + (
                                        CAST(tie_break_rank AS DOUBLE)
                                        / POWER(10.0, LENGTH(CAST(bucket_size AS TEXT)) + 2) -- determines decimal places
                                )
                ELSE -- subtract digits for negative scores
                        CAST(rf_rounded AS DOUBLE)
                                - (
                                        CAST((bucket_size - tie_break_rank + 1) AS DOUBLE)
                                        / POWER(10.0, LENGTH(CAST(bucket_size AS TEXT)) + 2) -- determines decimal places
                                )
        END AS rf_score_final
    
    FROM rf_rank
),

'''
Calculate the asset level opportunity_score as the average 
of the feasability scores, PLUS the rf_score.
'''
opp_score as (
    SELECT
        asset_id
        , strategy_id
        , native_strategy_id
        , strategy_name
        , strategy_description
        , most_granular
        , iso3_country
        , subsector
        , rf_score_final as asset_rf_score
        , feasibility
        , feasibility_score
        , cost
        , cost_score
        , total_emissions_reduced_per_year
        , tie_break_rank
        , bucket_size
        ( ((cost_score + feasibility_score) / 2) + rf_score_final + 1 ) * 9.0/8.0 + 1 AS opportunity_score
    
    FROM rf_score_final
)

'''
To get the final asset level difficulty score, we scale the opp
score linearly to represent a number between 1 and 10, where low
signifies "easier/more effective" implementation, and a higher score
represents "harder/less effective" implementation.
'''
SELECT 
    asset_id
        , strategy_id
        , native_strategy_id
        , strategy_name
        , strategy_description
        , most_granular
        , iso3_country
        , subsector
        , asset_rf_score
        , feasibility
        , feasibility_score
        , cost
        , cost_score
        , total_emissions_reduced_per_year
        , tie_break_rank
        , bucket_size
        , opportunity_score as opp_score_raw
        , 1 + 9 * (
            (opportunity_score - MIN(opportunity_score) OVER ())
                / NULLIF(MAX(opportunity_score) OVER () - MIN(opportunity_score) OVER (), 0)
            ) AS asset_difficulty_score    

FROM opp_score
                                    

ORDER BY opportunity_score ASC
;
