{{ config(materialized='incremental', unique_key='LNK_ACCOUNT_TRANSACTION_HK') }}

WITH

harvest AS (
    SELECT
        LNK_ACCOUNT_TRANSACTION_HK,
        TRANSACTION_HK,
        ACCOUNT_HK,
        LOAD_DTS,
        REC_SRC
    FROM {{ ref('stg_core_banking_transactions') }}
),

consolidate AS (
    SELECT * FROM harvest
),

new_keys AS (
    SELECT * FROM consolidate
    {% if is_incremental() %}
    WHERE LNK_ACCOUNT_TRANSACTION_HK NOT IN (SELECT LNK_ACCOUNT_TRANSACTION_HK FROM {{ this }})
    {% endif %}
),

deduped AS (
    SELECT
        LNK_ACCOUNT_TRANSACTION_HK,
        TRANSACTION_HK,
        ACCOUNT_HK,
        LOAD_DTS,
        REC_SRC
    FROM new_keys
    QUALIFY ROW_NUMBER() OVER (PARTITION BY LNK_ACCOUNT_TRANSACTION_HK ORDER BY LOAD_DTS ASC) = 1
),

ghost_records AS (
    SELECT MD5_BINARY(UPPER('0')) AS LNK_ACCOUNT_TRANSACTION_HK, MD5_BINARY(UPPER('0')) AS TRANSACTION_HK, MD5_BINARY(UPPER('0')) AS ACCOUNT_HK, '1900-01-01T00:00:00'::TIMESTAMP_NTZ AS LOAD_DTS, 'SYSTEM' AS REC_SRC
    UNION ALL
    SELECT MD5_BINARY(UPPER('-1')), MD5_BINARY(UPPER('-1')), MD5_BINARY(UPPER('-1')), '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
    UNION ALL
    SELECT MD5_BINARY(UPPER('-2')), MD5_BINARY(UPPER('-2')), MD5_BINARY(UPPER('-2')), '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
),

FINAL AS (
    SELECT * FROM deduped
    {% if not is_incremental() %}
    UNION ALL
    SELECT * FROM ghost_records
    {% endif %}
)

SELECT * FROM FINAL
