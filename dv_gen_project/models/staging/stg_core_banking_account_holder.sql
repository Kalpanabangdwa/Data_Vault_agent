WITH SRC AS (
    SELECT * FROM {{ source('core_banking', 'ACCOUNT_HOLDERS') }}
),

LOGIC AS (
    SELECT
        TRIM(CAST(ACCOUNT_NO AS VARCHAR)) AS ACCOUNT_NO,
        TRIM(CAST(CUST_ID AS VARCHAR))    AS CUST_ID,
        TRIM(CAST(ROLE AS VARCHAR))       AS ROLE
    FROM SRC
),

RENAME AS (
    SELECT
        ACCOUNT_NO,
        CUST_ID AS SOURCE_CUSTOMER_BK,
        ROLE    AS HOLDER_ROLE
    FROM LOGIC
),

FILTER AS (
    SELECT * FROM RENAME
    WHERE ACCOUNT_NO IS NOT NULL AND SOURCE_CUSTOMER_BK IS NOT NULL
),

JOIN_LAYER AS (
    SELECT
        f.ACCOUNT_NO,
        f.SOURCE_CUSTOMER_BK,
        f.HOLDER_ROLE,
        c.CUSTOMER_HK
    FROM FILTER f
    INNER JOIN {{ ref('stg_core_banking_customer') }} c
        ON f.SOURCE_CUSTOMER_BK = c.SOURCE_CUSTOMER_BK
),

FINAL AS (
    SELECT
        ACCOUNT_NO,
        SOURCE_CUSTOMER_BK,
        HOLDER_ROLE,
        CUSTOMER_HK,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(ACCOUNT_NO AS VARCHAR)), ''), '^^')
        )))                                                AS ACCOUNT_HK,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(ACCOUNT_NO AS VARCHAR)), ''), '^^'),
            COALESCE(NULLIF(TRIM(CAST(SOURCE_CUSTOMER_BK AS VARCHAR)), ''), '^^')
        )))                                                AS CUSTOMER_ACCOUNT_LHK,

        current_timestamp()                               AS LOAD_DTS,
        'CORE_BANKING'                                     AS REC_SRC
    FROM JOIN_LAYER
)

SELECT * FROM FINAL