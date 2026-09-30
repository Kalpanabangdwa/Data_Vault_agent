{{ config(materialized='incremental', unique_key=['BRANCH_HK', 'LOAD_DTS']) }}
WITH SRC AS ( SELECT * FROM {{ ref('stg_core_banking_branches') }} ),
LOGIC AS (
    SELECT BRANCH_HK, HASHDIFF, BRANCH_NAME, CITY, LOAD_DTS, REC_SRC
    FROM SRC
),
FINAL AS (
    SELECT * FROM LOGIC
    {% if is_incremental() and var('enable_sat_dedup_check', true) %}
    WHERE NOT EXISTS (
        SELECT 1
        FROM {{ this }} current_sat
        WHERE current_sat.BRANCH_HK = LOGIC.BRANCH_HK
          AND current_sat.HASHDIFF = LOGIC.HASHDIFF
    )
    {% endif %}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY BRANCH_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1
)
SELECT * FROM FINAL
{% if not is_incremental() %}
UNION ALL
SELECT
    h.BRANCH_HK,
    TO_BINARY('^^||^^', 'UTF-8') AS HASHDIFF,
    NULL AS BRANCH_NAME,
    NULL AS CITY,
    CONVERT_TIMEZONE('UTC','1900-01-01'::TIMESTAMP)::TIMESTAMP_NTZ AS LOAD_DTS,
    'SYSTEM' AS REC_SRC
FROM {{ ref('hub_branch') }} h
WHERE h.BRANCH_BK IN ('0', '-1', '-2')
{% endif %}
