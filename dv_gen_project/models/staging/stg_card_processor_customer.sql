WITH SRC AS (
    SELECT * FROM {{ source('card_processor', 'CUSTOMERS') }}
),

LOGIC AS (
    SELECT
        CP_CUSTOMER_CODE,
        TRIM(CAST(CP_FULL_NAME AS VARCHAR)) AS CP_FULL_NAME,
        TRIM(CAST(CP_EMAIL AS VARCHAR))     AS CP_EMAIL,
        CP_SIGNUP_DATE
    FROM SRC
),

RENAME AS (
    SELECT
        CP_CUSTOMER_CODE AS SOURCE_CUSTOMER_BK,
        CP_FULL_NAME      AS CUSTOMER_NAME,
        CP_EMAIL          AS CUSTOMER_EMAIL,
        CP_SIGNUP_DATE    AS CUSTOMER_CREATED_DATE
    FROM LOGIC
),

FILTER AS (
    SELECT * FROM RENAME
    WHERE CUSTOMER_EMAIL IS NOT NULL
),

JOIN_LAYER AS (
    SELECT * FROM FILTER
),

FINAL AS (
    SELECT
        SOURCE_CUSTOMER_BK,
        CUSTOMER_NAME,
        CUSTOMER_EMAIL,
        CUSTOMER_CREATED_DATE,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(CUSTOMER_EMAIL AS VARCHAR)), ''), '^^')
        )))                                                AS CUSTOMER_HK,

        MD5_BINARY(UPPER(NULLIF(CONCAT_WS('||',
            IFNULL(TRIM(CUSTOMER_NAME::VARCHAR), '^^')
        ), '^^')))                                         AS HASHDIFF_PROFILE,

        current_timestamp()                               AS LOAD_DTS,
        'CARD_PROCESSOR'                                   AS REC_SRC,
        'CARD_PROCESSOR'                                   AS BKCC
    FROM JOIN_LAYER
)

SELECT * FROM FINAL