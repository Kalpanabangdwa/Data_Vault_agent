{{ config(materialized='incremental', unique_key='BRANCH_HK') }}
WITH SRC AS (
    SELECT *
    FROM {{ ref('stg_core_banking_branch') }}
),
LOGIC AS (
    SELECT
        BRANCH_HK,
        HASHDIFF_SAT_BRANCH AS HASHDIFF,
        BRANCH_NAME,
        CITY,
        LOAD_DTS,
        REC_SRC
    FROM SRC
),
FINAL AS (
    SELECT * FROM LOGIC
    {% if is_incremental() %}
    WHERE HASHDIFF NOT IN (SELECT HASHDIFF FROM {{ this }})
    {% endif %}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY BRANCH_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1
)
SELECT * FROM FINAL