{{ config(materialized='incremental', unique_key='BRANCH_HK') }}
WITH
harvest AS (
    SELECT BRANCH_HK, BRANCH_BK, LOAD_DTS, REC_SRC
    FROM {{ ref('stg_core_banking_branch_ref') }}
),
consolidate AS ( SELECT * FROM harvest ),
new_keys AS (
    SELECT * FROM consolidate
    {% if is_incremental() %}
    WHERE BRANCH_HK NOT IN (SELECT BRANCH_HK FROM {{ this }})
    {% endif %}
),
deduped AS (
    SELECT * FROM new_keys
    QUALIFY ROW_NUMBER() OVER (PARTITION BY BRANCH_HK ORDER BY LOAD_DTS ASC) = 1
),
ghost_records AS (
    SELECT MD5_BINARY(UPPER('0')) AS BRANCH_HK, '0' AS BRANCH_BK, '1900-01-01T00:00:00'::TIMESTAMP_NTZ AS LOAD_DTS, 'SYSTEM' AS REC_SRC
    UNION ALL
    SELECT MD5_BINARY(UPPER('-1')), '-1', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
    UNION ALL
    SELECT MD5_BINARY(UPPER('-2')), '-2', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
),
FINAL AS (
    SELECT * FROM deduped
    {% if not is_incremental() %}
    UNION ALL SELECT * FROM ghost_records
    {% endif %}
)
SELECT * FROM FINAL