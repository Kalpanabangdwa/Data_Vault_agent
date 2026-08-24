{{ config(materialized='incremental', unique_key='BRANCH_HK') }}
WITH SRC AS ( SELECT * FROM {{ ref('stg_core_banking_branch_ref') }} ),
LOGIC AS (
    SELECT BRANCH_HK, HASHDIFF, BRANCH_NAME, CITY, LOAD_DTS, REC_SRC
    FROM SRC
),
FINAL AS (
    SELECT * FROM LOGIC
    {% if is_incremental() and var('enable_hub_dedup_check', true) %}
    WHERE HASHDIFF NOT IN (SELECT HASHDIFF FROM {{ this }})
    {% endif %}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY BRANCH_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1
)
SELECT * FROM FINAL