WITH SRC AS (
    SELECT * FROM {{ source('card_processor', 'CARDS') }}
),

LOGIC AS (
    SELECT
        TRIM(CAST(CARD_NO AS VARCHAR))          AS CARD_NO,
        TRIM(CAST(CP_CUSTOMER_CODE AS VARCHAR))  AS CP_CUSTOMER_CODE,
        TRIM(CAST(ACCOUNT_NO AS VARCHAR))        AS ACCOUNT_NO,
        TRIM(CAST(CARD_STATUS AS VARCHAR))       AS CARD_STATUS,
        CREDIT_LIMIT,
        ISSUED_DATE
    FROM SRC
),

RENAME AS (
    SELECT
        CARD_NO,
        CP_CUSTOMER_CODE,
        ACCOUNT_NO,
        CARD_STATUS,
        CREDIT_LIMIT   AS CARD_CREDIT_LIMIT,
        ISSUED_DATE    AS CARD_ISSUED_DATE
    FROM LOGIC
),

FILTER AS (
    SELECT * FROM RENAME
    WHERE CARD_NO IS NOT NULL AND ACCOUNT_NO IS NOT NULL
),

JOIN_LAYER AS (
    SELECT * FROM FILTER
),

FINAL AS (
    SELECT
        CARD_NO,
        CP_CUSTOMER_CODE,
        ACCOUNT_NO,
        CARD_STATUS,
        CARD_CREDIT_LIMIT,
        CARD_ISSUED_DATE,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(CARD_NO AS VARCHAR)), ''), '^^')
        )))                                                AS CARD_HK,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(ACCOUNT_NO AS VARCHAR)), ''), '^^')
        )))                                                AS ACCOUNT_HK,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(ACCOUNT_NO AS VARCHAR)), ''), '^^'),
            COALESCE(NULLIF(TRIM(CAST(CARD_NO AS VARCHAR)), ''), '^^')
        )))                                                AS ACCOUNT_CARD_LHK,

        MD5_BINARY(UPPER(NULLIF(CONCAT_WS('||',
            IFNULL(TRIM(CARD_STATUS::VARCHAR), '^^'),
            IFNULL(TRIM(CARD_CREDIT_LIMIT::VARCHAR), '^^'),
            IFNULL(TRIM(CARD_ISSUED_DATE::VARCHAR), '^^')
        ), '^^')))                                         AS HASHDIFF_CARD_PROFILE,

        current_timestamp()                               AS LOAD_DTS,
        'CARD_PROCESSOR'                                   AS REC_SRC,
        'CARD_PROCESSOR'                                   AS BKCC
    FROM JOIN_LAYER
)

SELECT * FROM FINAL