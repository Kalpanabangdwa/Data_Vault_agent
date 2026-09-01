{{ config(materialized='incremental', unique_key='CREDIT_CARD_HK') }}
WITH
harvest AS (
    SELECT CREDIT_CARD_HK, CREDIT_CARD_BK, BKCC, LOAD_DTS, REC_SRC
    FROM {{ ref('stg_core_banking_credit_card') }}
),
consolidate AS ( SELECT * FROM harvest ),
new_keys AS (
    SELECT * FROM consolidate
    {% if is_incremental() %}
    WHERE CREDIT_CARD_HK NOT IN (SELECT CREDIT_CARD_HK FROM {{ this }})
    {% endif %}
),
deduped AS (
    SELECT * FROM new_keys
    QUALIFY ROW_NUMBER() OVER (PARTITION BY CREDIT_CARD_HK ORDER BY LOAD_DTS ASC) = 1
),
ghost_records AS (
    SELECT MD5_BINARY(UPPER('0')) AS CREDIT_CARD_HK, '0' AS CREDIT_CARD_BK, 'SYSTEM' AS BKCC, '1900-01-01T00:00:00'::TIMESTAMP_NTZ AS LOAD_DTS, 'SYSTEM' AS REC_SRC
    UNION ALL
    SELECT MD5_BINARY(UPPER('-1')), '-1', 'SYSTEM', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
    UNION ALL
    SELECT MD5_BINARY(UPPER('-2')), '-2', 'SYSTEM', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
),
FINAL AS (
    SELECT * FROM deduped
    {% if not is_incremental() %}
    UNION ALL SELECT * FROM ghost_records
    {% endif %}
)
SELECT * FROM FINAL
