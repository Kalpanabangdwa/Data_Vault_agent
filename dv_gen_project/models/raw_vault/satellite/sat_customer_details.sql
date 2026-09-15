{{ config(materialized='incremental', unique_key='CUSTOMER_HK') }}
WITH SRC AS ( SELECT * FROM {{ ref('stg_core_banking_customers') }} ),
LOGIC AS (
    SELECT CUSTOMER_HK, HASHDIFF, FULL_NAME, DOB, EMAIL, PHONE, LOAD_DTS, REC_SRC
    FROM SRC
),
FINAL AS (
    SELECT * FROM LOGIC
    {% if is_incremental() and var('enable_hub_dedup_check', true) %}
    WHERE HASHDIFF NOT IN (SELECT HASHDIFF FROM {{ this }})
    {% endif %}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY CUSTOMER_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1
)
SELECT * FROM FINAL