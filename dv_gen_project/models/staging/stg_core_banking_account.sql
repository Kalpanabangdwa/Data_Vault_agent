WITH SRC AS (
    SELECT * FROM {{ source('core_banking', 'ACCOUNTS') }}
),

LOGIC AS (
    SELECT
        TRIM(CAST(ACCOUNT_NO AS VARCHAR))    AS ACCOUNT_NO,
        TRIM(CAST(BRANCH_CODE AS VARCHAR))   AS BRANCH_CODE,
        TRIM(CAST(ACCOUNT_TYPE AS VARCHAR))  AS ACCOUNT_TYPE,
        OPENED_DATE,
        TRIM(CAST(STATUS AS VARCHAR))        AS STATUS,
        BALANCE
    FROM SRC
),

RENAME AS (
    SELECT
        ACCOUNT_NO,
        BRANCH_CODE,
        ACCOUNT_TYPE,
        OPENED_DATE  AS ACCOUNT_OPENED_DATE,
        STATUS       AS ACCOUNT_STATUS,
        BALANCE      AS ACCOUNT_BALANCE
    FROM LOGIC
),

FILTER AS (
    SELECT * FROM RENAME
    WHERE ACCOUNT_NO IS NOT NULL
),

JOIN_LAYER AS (
    SELECT * FROM FILTER
),

FINAL AS (
    SELECT
        ACCOUNT_NO,
        BRANCH_CODE,
        ACCOUNT_TYPE,
        ACCOUNT_OPENED_DATE,
        ACCOUNT_STATUS,
        ACCOUNT_BALANCE,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(ACCOUNT_NO AS VARCHAR)), ''), '^^')
        )))                                                AS ACCOUNT_HK,

        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(BRANCH_CODE AS VARCHAR)), ''), '^^')
        )))                                                AS BRANCH_HK,

        MD5_BINARY(UPPER(NULLIF(CONCAT_WS('||',
            IFNULL(TRIM(ACCOUNT_TYPE::VARCHAR), '^^'),
            IFNULL(TRIM(ACCOUNT_STATUS::VARCHAR), '^^'),
            IFNULL(TRIM(ACCOUNT_BALANCE::VARCHAR), '^^')
        ), '^^')))                                         AS HASHDIFF_ACCOUNT_STATUS,

        current_timestamp()                               AS LOAD_DTS,
        'CORE_BANKING'                                     AS REC_SRC
    FROM JOIN_LAYER
)

SELECT * FROM FINAL