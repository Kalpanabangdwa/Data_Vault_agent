{{ config(materialized='incremental', unique_key='TRANSACTION_HK') }}

WITH
src AS (
    SELECT
        TRANSACTION_HK,
        HASHDIFF_SAT_TRANSACTION,
        TXN_TYPE,
        AMOUNT,
        TXN_TIMESTAMP,
        BALANCE_AFTER,
        LOAD_DTS,
        REC_SRC
    FROM {{ ref('stg_core_banking_transactions') }}
),
incremental AS (
    SELECT
        *
    FROM src
    {% if is_incremental() %}
    WHERE LOAD_DTS > (SELECT MAX(LOAD_DTS) FROM {{ this }})
    {% endif %}
),
dedup AS (
    SELECT
        *
    FROM incremental
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY TRANSACTION_HK
        ORDER BY LOAD_DTS DESC
    ) = 1
)
SELECT
    TRANSACTION_HK,
    HASHDIFF_SAT_TRANSACTION,
    TXN_TYPE,
    AMOUNT,
    TXN_TIMESTAMP,
    BALANCE_AFTER,
    LOAD_DTS,
    REC_SRC
FROM dedup
