WITH SRC AS (
    SELECT *
    FROM {{ source('CARD_PROCESSOR', 'transactions') }}
),
LOGIC AS (
    SELECT *
    FROM SRC
),
RENAME AS (
    SELECT *
    FROM LOGIC
),
FILTER AS (
    SELECT *
    FROM RENAME
    WHERE card_number IS NOT NULL
),
"JOIN" AS (
    SELECT *
    FROM FILTER
),
FINAL AS (
    SELECT
        "JOIN".*,
        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(card_number AS VARCHAR)), ''), '^^')
        ))) AS CARD_HK,
        card_number AS CARD_BK,
        current_timestamp() AS LOAD_DTS,
        'CARD_PROCESSOR' AS REC_SRC,
        'CARD_PROCESSOR' AS BKCC
    FROM "JOIN"
)
SELECT *
FROM FINAL