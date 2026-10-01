with harvest as (
    select HUB_CUSTOMER_HK, CUST_ID, BKCC, REC_SRC, LOAD_DATE
    from {{ ref('stg_core_banking_customers') }}
),
consolidate as ( select * from harvest ),
incremental as (
    select * from consolidate
    {% if is_incremental() %}
    where HUB_CUSTOMER_HK not in (select HUB_CUSTOMER_HK from {{ this }})
    {% endif %}
),
dedup as (
    select HUB_CUSTOMER_HK, CUST_ID, BKCC, REC_SRC, LOAD_DATE
    from incremental
    qualify row_number() over (partition by HUB_CUSTOMER_HK order by LOAD_DATE asc) = 1
)
{% if not is_incremental() %}
,
ghost_records as (
    select MD5_BINARY(UPPER('0'))  as HUB_CUSTOMER_HK, '0'  as CUST_ID, '0'  as BKCC, 'SYSTEM' as REC_SRC, '1900-01-01'::timestamp as LOAD_DATE
    union all
    select MD5_BINARY(UPPER('-1')) as HUB_CUSTOMER_HK, '-1' as CUST_ID, '-1' as BKCC, 'SYSTEM' as REC_SRC, '1900-01-01'::timestamp as LOAD_DATE
    union all
    select MD5_BINARY(UPPER('-2')) as HUB_CUSTOMER_HK, '-2' as CUST_ID, '-2' as BKCC, 'SYSTEM' as REC_SRC, '1900-01-01'::timestamp as LOAD_DATE
)
{% endif %}
select * from dedup
{% if not is_incremental() %}
union all
select * from ghost_records
{% endif %}
