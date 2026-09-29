WITH SRC AS ( SELECT * FROM {{ source('Raw_core_banking', 'CUSTOMERS') }} ),
SRC_A AS ( SELECT * FROM {{ source('control', 'REF_SOURCE_SYSTEM') }} ),

LOGIC AS (
    SELECT 
        NULLIF(TRIM(CAST(CUST_ID AS VARCHAR)), '') AS CUSTOMER_BK,
        FULL_NAME,
        DOB,
        EMAIL,
        PHONE,
        CREATED_DATE,
        CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())::TIMESTAMP_NTZ AS LOAD_DTS
    FROM SRC
),
LOGIC_A AS ( SELECT * FROM SRC_A ),

RENAME AS (
    SELECT CUSTOMER_BK, FULL_NAME, DOB, EMAIL, PHONE, CREATED_DATE, LOAD_DTS FROM LOGIC
),
RENAME_A AS (
    SELECT TABLE_NAME, REC_SRC, BKCC FROM LOGIC_A
),

FILTER AS (
    SELECT * FROM RENAME WHERE CUSTOMER_BK IS NOT NULL
),
FILTER_A AS (
    SELECT * FROM RENAME_A WHERE TABLE_NAME = 'CUSTOMERS'
),

JOIN_LAYER AS (
    SELECT 
        s.*, 
        a.REC_SRC, 
        a.BKCC
    FROM FILTER s
    INNER JOIN FILTER_A a ON '1' = '1'
),

FINAL AS (
    SELECT 
        *,
        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(CUSTOMER_BK AS VARCHAR)), ''), '^^')
        ))) AS CUSTOMER_HK,
        MD5_BINARY(UPPER(NULLIF(CONCAT(
              IFNULL(TRIM(FULL_NAME::text), '^^'), '||'
            , IFNULL(TRIM(DOB::text), '^^'), '||'
            , IFNULL(TRIM(EMAIL::text), '^^'), '||'
            , IFNULL(TRIM(PHONE::text), '^^'), '||'
            , IFNULL(TRIM(CREATED_DATE::text), '^^')
        ), '^^||^^||^^||^^||^^'))) AS HASHDIFF
    FROM JOIN_LAYER
)
SELECT * FROM FINAL
