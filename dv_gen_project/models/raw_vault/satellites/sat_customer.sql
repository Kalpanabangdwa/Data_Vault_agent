with src_sat as (
    select HUB_CUSTOMER_HK, FULL_NAME, DOB, EMAIL, PHONE, SAT_CUSTOMER_HASHDIFF, REC_SRC, LOAD_DATE
    from {{ ref('stg_core_banking_customers') }}
    {% if is_incremental() %}
    where LOAD_DATE > (select max(LOAD_DATE) from {{ this }})
    {% endif %}
),
dedup as (
    select *,
        row_number() over (partition by HUB_CUSTOMER_HK, SAT_CUSTOMER_HASHDIFF order by LOAD_DATE asc) as rn
    from src_sat
    qualify rn = 1
),
final as (
    select HUB_CUSTOMER_HK, SAT_CUSTOMER_HASHDIFF, FULL_NAME, DOB, EMAIL, PHONE, REC_SRC, LOAD_DATE
    from dedup
)
select * from final
