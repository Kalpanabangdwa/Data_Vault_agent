{{ config(materialized='incremental', unique_key='ACCOUNT_HK') }}

WITH

-- 1. Harvesting
core_banking_keys AS (
    SELECT
        ACCOUNT_HK,
        ACCOUNT_NO AS ACCOUNT_BK,
        LOAD_DTS,
        REC_SRC
    FROM {{ ref('stg_core_banking_account') }}
),

-- 2. Consolidation (single source now; kept as UNION ALL-ready structure)
all_keys AS (
    SELECT * FROM core_banking_keys
),

-- 3. Incremental delta check
new_keys AS (
    SELECT * FROM all_keys
    {% if is_incremental() %}
    WHERE ACCOUNT_HK NOT IN (SELECT ACCOUNT_HK FROM {{ this }})
    {% endif %}
),

-- 4. Deduplication
deduped AS (
    SELECT ACCOUNT_HK, ACCOUNT_BK, LOAD_DTS, REC_SRC
    FROM new_keys
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ACCOUNT_HK ORDER BY LOAD_DTS ASC) = 1
),

-- 5. Ghost record injection
ghost_records AS (
    SELECT MD5_BINARY(UPPER('0'))  AS ACCOUNT_HK, '0'  AS ACCOUNT_BK, '1900-01-01T00:00:00'::TIMESTAMP_NTZ AS LOAD_DTS, 'SYSTEM' AS REC_SRC
    UNION ALL
    SELECT MD5_BINARY(UPPER('-1')), '-1', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
    UNION ALL
    SELECT MD5_BINARY(UPPER('-2')), '-2', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
),

FINAL AS (
    SELECT * FROM deduped
    {% if not is_incremental() %}
    UNION ALL
    SELECT * FROM ghost_records
    {% endif %}
)

SELECT * FROM FINAL