{{ config(
    materialized='incremental',
    unique_key=['TRANSACTION_HK'],
    on_schema_change='fail'
) }}

WITH SRC AS (
    SELECT
        TXN_ID,
        ACCOUNT_NO,
        TXN_TYPE,
        AMOUNT,
        TXN_TIMESTAMP,
        BALANCE_AFTER
    FROM {{ source('core_banking', 'TRANSACTIONS') }}
),
LOGIC AS (
    SELECT
        TXN_ID,
        ACCOUNT_NO,
        TXN_TYPE,
        AMOUNT,
        TXN_TIMESTAMP,
        BALANCE_AFTER
    FROM SRC
),
RENAME AS (
    SELECT
        TXN_ID AS TRANSACTION_BK,
        ACCOUNT_NO AS ACCOUNT_BK,
        TXN_TYPE,
        AMOUNT,
        TXN_TIMESTAMP,
        BALANCE_AFTER
    FROM LOGIC
),
FILTER AS (
    SELECT * FROM RENAME
    WHERE TRANSACTION_BK IS NOT NULL AND ACCOUNT_BK IS NOT NULL
),
SRC_REF AS (
    SELECT
        REC_SRC,
        BKCC
    FROM {{ source('control', 'REF_SOURCE_SYSTEM') }}
    WHERE SOURCE_SYSTEM = 'CORE_BANKING'
),
JOIN_LAYER AS (
    SELECT
        FILTER.*,
        SRC_REF.REC_SRC,
        SRC_REF.BKCC
    FROM FILTER
    CROSS JOIN SRC_REF
),
FINAL AS (
    SELECT
        TRANSACTION_BK,
        ACCOUNT_BK,
        TXN_TYPE,
        AMOUNT,
        TXN_TIMESTAMP,
        BALANCE_AFTER,
        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(TRANSACTION_BK AS VARCHAR)), ''), '^^'),
            COALESCE(NULLIF(TRIM(CAST(JOIN_LAYER.BKCC AS VARCHAR)), ''), '^^')
        ))) AS TRANSACTION_HK,
        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(ACCOUNT_BK AS VARCHAR)), ''), '^^')
        ))) AS ACCOUNT_HK,
        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(ACCOUNT_BK AS VARCHAR)), ''), '^^'),
            COALESCE(NULLIF(TRIM(CAST(TRANSACTION_BK AS VARCHAR)), ''), '^^')
        ))) AS LNK_ACCOUNT_TRANSACTION_HK,
        MD5_BINARY(UPPER(NULLIF(CONCAT_WS('||',
            IFNULL(TRIM(TXN_TYPE::VARCHAR), '^^'),
            IFNULL(TRIM(AMOUNT::VARCHAR), '^^'),
            IFNULL(TRIM(TXN_TIMESTAMP::VARCHAR), '^^'),
            IFNULL(TRIM(BALANCE_AFTER::VARCHAR), '^^')
        ), '^^'))) AS HASHDIFF_SAT_TRANSACTION,
        current_timestamp() AS LOAD_DTS,
        REC_SRC,
        BKCC
    FROM JOIN_LAYER
)
SELECT * FROM FINAL
{% if is_incremental() %}
WHERE LOAD_DTS > (SELECT COALESCE(MAX(LOAD_DTS), '1900-01-01'::TIMESTAMP_NTZ) FROM {{ this }})
{% endif %}
