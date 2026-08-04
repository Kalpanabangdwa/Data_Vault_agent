{{ config(materialized='incremental', unique_key='CUSTOMER_HK') }}

WITH

-- 1. Multi-source harvesting
core_banking_keys AS (
    SELECT
        CUSTOMER_HK,
        SOURCE_CUSTOMER_BK AS CUSTOMER_BK,
        LOAD_DTS,
        REC_SRC,
        BKCC
    FROM {{ ref('stg_core_banking_customer') }}
),

card_processor_keys AS (
    SELECT
        CUSTOMER_HK,
        SOURCE_CUSTOMER_BK AS CUSTOMER_BK,
        LOAD_DTS,
        REC_SRC,
        BKCC
    FROM {{ ref('stg_card_processor_customer') }}
),

-- 2. Consolidation
all_keys AS (
    SELECT * FROM core_banking_keys
    UNION ALL
    SELECT * FROM card_processor_keys
),

-- 3. Incremental delta check
new_keys AS (
    SELECT * FROM all_keys
    {% if is_incremental() %}
    WHERE CUSTOMER_HK NOT IN (SELECT CUSTOMER_HK FROM {{ this }})
    {% endif %}
),

-- 4. Deduplication - keep earliest record per key
deduped AS (
    SELECT CUSTOMER_HK, CUSTOMER_BK, LOAD_DTS, REC_SRC, BKCC
    FROM new_keys
    QUALIFY ROW_NUMBER() OVER (PARTITION BY CUSTOMER_HK ORDER BY LOAD_DTS ASC) = 1
),

-- 5. Ghost record injection (init run only)
ghost_records AS (
    SELECT MD5_BINARY(UPPER('0'))  AS CUSTOMER_HK, '0'  AS CUSTOMER_BK, '1900-01-01T00:00:00'::TIMESTAMP_NTZ AS LOAD_DTS, 'SYSTEM' AS REC_SRC, 'SYSTEM' AS BKCC
    UNION ALL
    SELECT MD5_BINARY(UPPER('-1')), '-1', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM', 'SYSTEM'
    UNION ALL
    SELECT MD5_BINARY(UPPER('-2')), '-2', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM', 'SYSTEM'
),

FINAL AS (
    SELECT * FROM deduped
    {% if not is_incremental() %}
    UNION ALL
    SELECT * FROM ghost_records
    {% endif %}
)

SELECT * FROM FINAL