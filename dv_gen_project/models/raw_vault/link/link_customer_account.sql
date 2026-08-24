{{ config(materialized='incremental', unique_key='CUSTOMER_ACCOUNT_LHK') }}

WITH

core_banking_keys AS (
    SELECT
        CUSTOMER_ACCOUNT_LHK,
        CUSTOMER_HK,
        ACCOUNT_HK,
        LOAD_DTS,
        REC_SRC
    FROM {{ ref('stg_core_banking_account_holder') }}
),

all_keys AS (
    SELECT * FROM core_banking_keys
),

new_keys AS (
    SELECT * FROM all_keys
    {% if is_incremental() %}
    WHERE CUSTOMER_ACCOUNT_LHK NOT IN (SELECT CUSTOMER_ACCOUNT_LHK FROM {{ this }})
    {% endif %}
),

deduped AS (
    SELECT CUSTOMER_ACCOUNT_LHK, CUSTOMER_HK, ACCOUNT_HK, LOAD_DTS, REC_SRC
    FROM new_keys
    QUALIFY ROW_NUMBER() OVER (PARTITION BY CUSTOMER_ACCOUNT_LHK ORDER BY LOAD_DTS ASC) = 1
),

ghost_records AS (
    SELECT MD5_BINARY(UPPER('0')) AS CUSTOMER_ACCOUNT_LHK, MD5_BINARY(UPPER('0')) AS CUSTOMER_HK, MD5_BINARY(UPPER('0')) AS ACCOUNT_HK, '1900-01-01T00:00:00'::TIMESTAMP_NTZ AS LOAD_DTS, 'SYSTEM' AS REC_SRC
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