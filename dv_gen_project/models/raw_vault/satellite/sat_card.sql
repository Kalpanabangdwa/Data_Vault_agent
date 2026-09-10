{{ config(materialized='incremental', unique_key=['CARD_HK', 'LOAD_DTS']) }}
WITH SRC AS ( SELECT * FROM {{ ref('stg_card_processor_card') }} ),
LOGIC AS (
    SELECT CARD_HK, HASHDIFF, CARD_STATUS, CREDIT_LIMIT, ISSUED_DATE, LOAD_DTS, REC_SRC
    FROM SRC
),
FINAL AS (
    SELECT * FROM LOGIC
    {% if is_incremental() %}
    WHERE NOT EXISTS (
        SELECT 1 FROM {{ this }} t
        WHERE t.CARD_HK = LOGIC.CARD_HK
        AND t.HASHDIFF = LOGIC.HASHDIFF
    )
    {% endif %}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY CARD_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1
)
SELECT * FROM FINAL
