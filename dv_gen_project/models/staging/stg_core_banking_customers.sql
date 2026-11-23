with src_s as (
    select * from {{ source('Raw_core_banking', 'CUSTOMERS') }}
),
rename_s as (
    select CUST_ID, FULL_NAME, DOB, EMAIL, PHONE, CREATED_DATE
    from src_s
),
join_results as (
    select r.*, ctl.REC_SRC, ctl.BKCC
    from rename_s r
    left join {{ source('control', 'REF_SOURCE_SYSTEM') }} ctl
        on ctl.TABLE_SCHEMA = 'RAW_CORE_BANKING'
       and ctl.TABLE_NAME = 'CUSTOMERS'
),
logic_s as (
    select * from join_results
),
filter_s as (
    select * from logic_s where CUST_ID is not null
),
final as (
    select
        *,
        MD5_BINARY(UPPER(CONCAT_WS('||', COALESCE(NULLIF(TRIM(BKCC),''),'^^'), COALESCE(NULLIF(TRIM(CUST_ID),''),'^^')))) as HUB_CUSTOMER_HK,
        MD5_BINARY(
            NVL(UPPER(TRIM(FULL_NAME)), '^^') || '|' ||
            NVL(TO_VARCHAR(DOB), '^^') || '|' ||
            NVL(UPPER(TRIM(EMAIL)), '^^') || '|' ||
            NVL(UPPER(TRIM(PHONE)), '^^')
        ) as SAT_CUSTOMER_HASHDIFF,
        CURRENT_TIMESTAMP() as LOAD_DATE
    from filter_s
)
select * from final
