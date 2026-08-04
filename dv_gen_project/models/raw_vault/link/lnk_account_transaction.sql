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
    SELECT
        LNK_ACCOUNT_TRANSACTION_HK,
        TRANSACTION_HK,
        ACCOUNT_HK,
        LOAD_DTS,
        REC_SRC
    FROM harvest
),
incremental AS (
    SELECT
        *
    FROM consolidate
    {% if is_incremental() %}
    WHERE LOAD_DTS > (SELECT MAX(LOAD_DTS) FROM {{ this }})
    {% endif %}
),
dedup AS (
    SELECT
        *
    FROM incremental
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY LNK_ACCOUNT_TRANSACTION_HK
        ORDER BY LOAD_DTS DESC
    ) = 1
),
ghost AS (
    {% if not is_incremental() %}
    SELECT
        MD5_BINARY(CONCAT_WS('||', '0', '-1')) AS LNK_ACCOUNT_TRANSACTION_HK,
        MD5_BINARY(CONCAT_WS('||', '0')) AS TRANSACTION_HK,
        MD5_BINARY(CONCAT_WS('||', '-1')) AS ACCOUNT_HK,
        TO_TIMESTAMP('1900-01-01 00:00:00') AS LOAD_DTS,
        'SYSTEM' AS REC_SRC
    {% endif %}
)
SELECT * FROM dedup
UNION ALL
SELECT * FROM ghost
