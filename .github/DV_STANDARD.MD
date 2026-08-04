# DV_Gen Fintech Data Vault Standard (v2.0)

## Naming Conventions
- Staging: `stg_<source_system>_<entity>`
- Hub: `hub_<entity>`
- Link: `lnk_<entity1>_<entity2>`
- Satellite: `sat_<entity>_<context>`
- Hash key suffix: `_HK` | Business key suffix: `_BK` | Link key suffix: `_LHK`
- Standard metadata columns: `LOAD_DTS`, `REC_SRC`, `BKCC` (staging + hubs only)

## Schemas
- Staging models -> `STAGING` schema
- Hub/Link/Satellite models -> `RAW_VAULT` schema
- Mart models -> `INFO_MART` schema
(Folder names under `models/raw_vault/` must exactly match the keys used in `dbt_project.yml` - `hub`, `link`, `satellites`, or whatever is chosen - mismatches silently break schema routing.)

## Golden Rule: Hashing Happens Once, In Staging
All `_HK`, `_LHK`, and `HASHDIFF_*` columns are computed EXACTLY ONCE, in the
staging model, using MD5_BINARY. Hub, Link, and Satellite models NEVER call
MD5_BINARY on real business data - they only SELECT pre-computed hash columns.

**The one allowed exception**: ghost record injection (ghost records are
synthetic system rows with no source data to stage - see below).

## Staging Model Structure (6 layers, always in this order)
- SRC: raw pull from `{{ source(...) }}`
- LOGIC: trim/cast raw columns
- RENAME: map to standardized column names
- FILTER: drop invalid/null rows that can't be matched downstream
- JOIN: bring in any needed lookups (e.g. resolving a shared Hub key from
  another staging model, as in stg_core_banking_account_holder joining to
  stg_core_banking_customer)
- FINAL: compute every `_HK`, `_LHK`, `HASHDIFF_*`, `LOAD_DTS`, `REC_SRC`, `BKCC`

## Hash Key Formula
```sql
MD5_BINARY(UPPER(CONCAT_WS('||',
    COALESCE(NULLIF(TRIM(CAST(<bk_col> AS VARCHAR)), ''), '^^')
)))
```
Multi-key (Link) hashes concatenate multiple components in a fixed order.

## HASHDIFF Formula (staging, for Satellites)
```sql
MD5_BINARY(UPPER(NULLIF(CONCAT_WS('||',
    IFNULL(TRIM(<col>::VARCHAR), '^^')
    -- one line per descriptive column
), '^^')))
```

## Cross-Source Entity Matching
When the same real-world entity appears in multiple source systems under
different internal IDs, the Hub key must be hashed from a SHARED identifier
common to both systems (e.g. email), never from either system's internal ID.
Each system's own ID is still stored as that staging model's `_BK` column for
traceability. `BKCC` records which source system each staged row came from.

## Hub / Link Structure (5 stages, always in this order)
Even single-source Hubs/Links use this same 5-stage shape for consistency.

## Ghost Records
Three sentinel rows per Hub/Link, inserted only on the first run:
```sql
MD5_BINARY(UPPER('0'))   -- BK = '0'   (SYSTEM)
MD5_BINARY(UPPER('-1'))  -- BK = '-1'  (unknown, required)
MD5_BINARY(UPPER('-2'))  -- BK = '-2'  (unknown, optional)
```
LOAD_DTS = `'1900-01-01T00:00:00'::TIMESTAMP_NTZ`, REC_SRC = `'SYSTEM'`.

## Satellite Structure
Select `_HK` and `HASHDIFF` straight from staging (never recompute).
```sql
{% if is_incremental() %}
WHERE HASHDIFF NOT IN (SELECT HASHDIFF FROM {{ this }})
{% endif %}
QUALIFY ROW_NUMBER() OVER (PARTITION BY <parent>_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1
```
Every satellite gets a matching `.yml` with `dbt_constraints.primary_key`
(`<parent>_hk` + `load_dts`) and `dbt_constraints.foreign_key` back to its
parent Hub.

## Materialization
| Layer | Materialization |
|---|---|
| Staging | view |
| Hub / Link / Satellite | incremental |
| Mart | view |

## Dedup Rule
Never `SELECT DISTINCT` anywhere in staging or raw vault. Always `QUALIFY ROW_NUMBER()`.

## Source/Ref Rules
- Staging: only `{{ source(...) }}`, plus `{{ ref() }}` to another staging
  model when a lookup is genuinely needed (e.g. resolving a shared key).
- Raw vault and above: only `{{ ref(...) }}`, never `source()`.

## Links Never Carry Descriptive Payload
A Link stores only hash keys + metadata. Any descriptive attribute of the
relationship (e.g. account-holder role) belongs in its own Satellite on the Link.