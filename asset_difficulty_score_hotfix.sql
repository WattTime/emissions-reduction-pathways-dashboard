--- Need history table step here

CREATE TEMP TABLE rdf as
select rdf.*
	, cs.native_strategy_id as native_strategy_id_new
	, coalesce(rdf.asset_output, 'other') asset_output_fixed
	, cs.confidence as confidence_new
	, cs.confidence_score as confidence_score_new
	, cs.feasibility as feasibility_new
	, cs.feasibility_score as feasibility_score_new
	, cs.cost as cost_new
	, cs.cost_score as cost_score_new

FROM reductions_data_fusion rdf

LEFT JOIN ( 
	select cs.*
			, sdf.strategy_id strategy_id_fixed
			
	from categorical_scoring_dpm_20251111 cs
	left join strategy_data_fusion sdf
		on sdf.native_strategy_id = cs.native_strategy_id
) cs
	on cs.strategy_id_fixed = rdf.strategy_id 
	and cast(cs.subsector as text) = cast(rdf.original_inventory_sector as text)

where rdf.strategy_rank = 1
	and rdf.gas = 'co2e_100yr'
;

drop table if exists asset_difficulty_score;
CREATE table asset_difficulty_score as
WITH asset_rf AS (
	SELECT
		asset_id
		, asset_output_fixed asset_output
		, strategy_id
		, native_strategy_id_new as native_strategy_id
		, strategy_name
		, strategy_description
		, iso3_country
		, original_inventory_sector AS subsector
		, old_emissions_factor
		, old_activity
		, total_emissions_reduced_per_year
		, (total_emissions_reduced_per_year / old_activity) AS reduction_factor
		, baseline_emissions AS w_inventory
		, confidence_new as confidence
		, confidence_score_new as confidence_score
		, feasibility_new as feasibility
		, feasibility_score_new as feasibility_score
		, cost_new as cost
		, cost_score_new as cost_score
		, most_granular
	
	FROM rdf
	
	WHERE total_emissions_reduced_per_year IS NOT NULL
		AND old_activity IS NOT NULL
		AND old_activity > 0
),

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
						* (2.0 / 3.0)        -- scale ±3 → ±2
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

rf_rounded as (
	select *
		, ROUND(asset_rf_score::numeric, 2) AS rf_rounded

	from rf_score
),

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

rf_score_final AS (
	SELECT *,
		-- number of digits in bucket size
		LENGTH(CAST(bucket_size AS TEXT)) AS bucket_digits,

		-- adjusted opportunity score: preserve 2 base decimals, append rank digits, handle for 
		CASE 
			WHEN rf_rounded > 0 THEN
				CAST(rf_rounded AS DOUBLE PRECISION)
					+ (
						CAST(tie_break_rank AS DOUBLE PRECISION)
						/ POWER(10.0, LENGTH(CAST(bucket_size AS TEXT)) + 2)
				)
			ELSE
				CAST(rf_rounded AS DOUBLE PRECISION)
					- (
						CAST((bucket_size - tie_break_rank + 1) AS DOUBLE PRECISION)
						/ POWER(10.0, LENGTH(CAST(bucket_size AS TEXT)) + 2)
					)
		END AS rf_score_final
	FROM rf_rank
),

opp_score as (
	SELECT
		asset_id,
		strategy_id,
		native_strategy_id,
		strategy_name,
		strategy_description,
		most_granular,
		iso3_country,
		--ghs_fua,
		subsector,
		rf_score_final as asset_rf_score,
		feasibility,
		feasibility_score,
		cost,
		cost_score,
		old_activity,
		total_emissions_reduced_per_year,
		tie_break_rank,
		bucket_size,
		( ((cost_score + feasibility_score) / 2) + rf_score_final + 1 ) * 9.0/8.0 + 1 AS opportunity_score
	
	FROM rf_score_final
)

select asset_id,
	strategy_id,
	native_strategy_id,
	strategy_name,
	strategy_description,
	most_granular,
	iso3_country,
	subsector,
	old_activity,
	total_emissions_reduced_per_year,
	asset_rf_score,
	feasibility,
	feasibility_score,
	cost,
	cost_score,
	tie_break_rank,
	bucket_size,
	opportunity_score as opp_score_raw,
	1 + 9 * (
		(opportunity_score - MIN(opportunity_score) OVER ())
			/ NULLIF(MAX(opportunity_score) OVER () - MIN(opportunity_score) OVER (), 0)
	) AS asset_difficulty_score    

from opp_score
;
