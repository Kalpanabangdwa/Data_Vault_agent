WITH SRC AS (
    SELECT * FROM {{ source('core_banking', 'CUSTOMERS') }}
),

LOGIC AS (
    SELECT
        CUST_ID,
        TRIM(CAST(FULL_NAME AS VARCHAR))  AS FULL_NAME,
        DOB,
        TRIM(CAST(EMAIL AS VARCHAR))      AS EMAIL,
        PHONE,
        CREATED_DATE
    FROM SRC
),

RENAME AS (
    SELECT
        CUST_ID     AS SOURCE_CUSTOMER_BK,
        FULL_NAME   AS CUSTOMER_NAME,
        DOB         AS CUSTOMER_DOB,
        EMAIL       AS CUSTOMER_EMAIL,
        PHONE       AS CUSTOMER_PHONE,
        CREATED_DATE AS CUSTOMER_CREATED_DATE
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
        CUSTOMER_DOB,
        CUSTOMER_EMAIL,
        CUSTOMER_PHONE,
        CUSTOMER_CREATED_DATE,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(CUSTOMER_EMAIL AS VARCHAR)), ''), '^^')
        )))                                                AS CUSTOMER_HK,

        MD5_BINARY(UPPER(NULLIF(CONCAT_WS('||',
            IFNULL(TRIM(CUSTOMER_NAME::VARCHAR), '^^'),
            IFNULL(TRIM(CUSTOMER_PHONE::VARCHAR), '^^')
        ), '^^')))                                         AS HASHDIFF_PROFILE,

        current_timestamp()                               AS LOAD_DTS,
        'CORE_BANKING'                                     AS REC_SRC,
        'CORE_BANKING'                                     AS BKCC
    FROM JOIN_LAYER
)

SELECT * FROM FINAL