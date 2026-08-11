{{ config(
    materialized='incremental',
    unique_key=['BRANCH_HK'],
    on_schema_change='fail'
) }}

WITH SRC AS (
    SELECT *
    FROM {{ source('CORE_BANKING', 'BRANCHES') }}
),
LOGIC AS (
    SELECT
        NULLIF(TRIM(CAST(BRANCH_CODE AS VARCHAR)), '') AS BRANCH_CODE,
        NULLIF(TRIM(CAST(BRANCH_NAME AS VARCHAR)), '') AS BRANCH_NAME,
        NULLIF(TRIM(CAST(CITY AS VARCHAR)), '') AS CITY
    FROM SRC
),
RENAME AS (
    SELECT
        BRANCH_CODE,
        BRANCH_NAME,
        CITY
    FROM LOGIC
),
FILTER AS (
    SELECT *
    FROM RENAME
    WHERE BRANCH_CODE IS NOT NULL
),
SRC_REF AS (
    SELECT
        REC_SRC,
        BKCC
    FROM {{ source('control', 'REF_SOURCE_SYSTEM') }}
    WHERE SOURCE_SYSTEM = 'CORE_BANKING'
),
JOIN_LAYER AS (
    SELECT
        FILTER.*,
        SRC_REF.REC_SRC,
        SRC_REF.BKCC
    FROM FILTER
    CROSS JOIN SRC_REF
),
FINAL AS (
    SELECT
        BRANCH_CODE,
        BRANCH_NAME,
        CITY,
        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(BRANCH_CODE AS VARCHAR)), ''), '^^'),
            COALESCE(NULLIF(TRIM(CAST(JOIN_LAYER.BKCC AS VARCHAR)), ''), '^^')
        ))) AS BRANCH_HK,
        BRANCH_CODE AS BRANCH_BK,
        MD5_BINARY(UPPER(NULLIF(CONCAT_WS('||',
            IFNULL(TRIM(BRANCH_NAME::VARCHAR), '^^'),
            IFNULL(TRIM(CITY::VARCHAR), '^^')
        ), '^^'))) AS HASHDIFF_SAT_BRANCH,
        current_timestamp() AS LOAD_DTS,
        REC_SRC,
        BKCC
    FROM JOIN_LAYER
)
SELECT *
FROM FINAL
{% if is_incremental() %}
WHERE LOAD_DTS > (SELECT COALESCE(MAX(LOAD_DTS), '1900-01-01'::TIMESTAMP_NTZ) FROM {{ this }})
{% endif %}