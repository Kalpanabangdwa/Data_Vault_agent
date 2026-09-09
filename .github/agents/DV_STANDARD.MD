# DV_Gen Fintech Data Vault Standard 

## Naming Conventions
**User-specified names always take priority.** If a ticket or prompt
explicitly names a staging model, Hub, Link, or Satellite (e.g.
`v_psa_stg_customer`, `hub_cust`, `lnk_cust_acct`), the agent MUST use
that exact name verbatim - never rename it to match the pattern below,
never "correct" it, never substitute its own naming choice.

The patterns below are a DEFAULT, used ONLY when no name is given:
- Staging: `stg_<source_system>_<entity>`
- Hub: `hub_<entity>`
- Link: `lnk_<entity1>_<entity2>`
- Satellite: `sat_<entity>_<context>`

Regardless of which naming pattern is used (user-specified or default),
these suffixes still apply to columns (not model/table names) unless the
ticket says otherwise:
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

## Staging Model Architecture (Multi-Stream)
All staging models must process data in independent, parallel streams before consolidating. Every CTE must be suffixed with its stream identifier:
*   **Stream `_S`:** The primary driver table.
*   **Stream `_A`:** The Business Key Collision reference table (`ref_business_key_collision`).
*   **Stream `_S2`, `_S3`, etc.:** Any secondary lookup tables required by the ticket.

**The 6 Mandatory Layers (Always in this order)**
1. **SRC Layer:** Extract raw data. Use `{{ source(...) }}` for data tables and `{{ ref(...) }}` for the `_A` reference table. If a secondary table (`_S2`) requires deduplication, apply `QUALIFY 1 = ROW_NUMBER() OVER (...)` directly in this layer.
2. **LOGIC Layer:** Isolate stream-specific transformations. Alias the raw grain columns to their Business Key names (e.g., `<raw_col> AS ITEM_BK`). Derive the `LOAD_DTS` column here using exact timezone conversions (e.g., `CONVERT_TIMEZONE('UTC', ...)`).
3. **RENAME Layer:** Select columns from the LOGIC layer, mapping them to standardized enterprise names. Maintain separate CTEs for each stream (`RENAME_S`, `RENAME_A`, etc.).
4. **FILTER Layer:** Drop invalid or null grain rows. For the `FILTER_A` stream, you MUST apply a hardcoded `WHERE rec_src = '<EXACT_SOURCE_STRING>'` filter.
5. **JOIN Layer:** Consolidate the streams into a single `JOIN_RESULT` CTE. `INNER JOIN` the `_A` stream using `ON '1' = '1'`. `LEFT JOIN` any `_S2` lookup streams using their respective keys.
6. **FINAL Layer:** Select all consolidated columns. Compute all `_HK` and `HASHDIFF` values exactly once in this layer using `MD5_BINARY`. 

## Hash Key Formula
**Default (no BKCC):**
```sql
MD5_BINARY(UPPER(CONCAT_WS('||',
    COALESCE(NULLIF(TRIM(CAST(<bk_col> AS VARCHAR)), ''), '^^')
)))

```

**With BKCC (used when a ticket's Hub config specifies it - BKCC is always the LAST component when included):**

```sql
MD5_BINARY(UPPER(CONCAT_WS('||',
    COALESCE(NULLIF(TRIM(CAST(<bk_col> AS VARCHAR)), ''), '^^'),
    COALESCE(NULLIF(TRIM(CAST(BKCC AS VARCHAR)), ''), '^^')
)))

```

Multi-key (Link) hashes concatenate multiple components in a fixed order, with BKCC last if the ticket includes it.

**Precedence rule:** when a ticket explicitly specifies the HK formula (which columns, whether BKCC is included), the ticket's spec is followed exactly, even if it differs from this section's default. This section defines the default for when a ticket doesn't specify one.

## HASHDIFF Formula (staging, for Satellites)

```sql
MD5_BINARY(UPPER(NULLIF(CONCAT(
      IFNULL(TRIM(<col1>::text), '^^') 
    , '||', IFNULL(TRIM(<col2>::text), '^^')
    -- one line per descriptive column
), '^^||^^')))

```

HASHDIFF always excludes grain columns (the Hub/Link's own `_HK`/`_BK`), audit columns, and BKCC - it only fingerprints genuinely descriptive, changeable columns.

## Cross-Source Entity Matching

When the same real-world entity appears in multiple source systems under different internal IDs, the Hub key must be hashed from a SHARED identifier common to both systems (e.g. email), never from either system's internal ID. Each system's own ID is still stored as that staging model's `_BK` column for traceability. `BKCC` records which source system each staged row came from.

## Hub / Link Structure (5 stages, always in this order)

1. Harvest keys (one CTE per contributing staging model)
2. Consolidate (UNION ALL into one stream)
3. Incremental delta check (WHERE key NOT IN existing table)
4. Deduplication (QUALIFY ROW_NUMBER, earliest LOAD_DTS wins)
5. Ghost record injection (0, -1, -2; init run only, via NOT is_incremental())

Even single-source Hubs/Links use this same 5-stage shape for consistency.

## Ghost Records

Three sentinel rows per Hub/Link, inserted only on the first run:

```sql
MD5_BINARY(UPPER('0'))   -- BK = '0'   (SYSTEM)
MD5_BINARY(UPPER('-1'))  -- BK = '-1'  (unknown, required)
MD5_BINARY(UPPER('-2'))  -- BK = '-2'  (unknown, optional)

```

LOAD_DTS = `'1900-01-01T00:00:00'::TIMESTAMP_NTZ`, REC_SRC = `'SYSTEM'`.
Each ghost row's `_HK` must hash its OWN sentinel value ('0', '-1', '-2' respectively) - never reuse the same hash across all three rows.

## Satellite Structure

Select `_HK` and `HASHDIFF` straight from staging (never recompute).
BKCC is never part of a Satellite - it's a Hub-only identity column, not a descriptive attribute.

```sql
{% if is_incremental() %}
WHERE HASHDIFF NOT IN (SELECT HASHDIFF FROM {{ this }})
{% endif %}
QUALIFY ROW_NUMBER() OVER (PARTITION BY <parent>_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1

```

Every satellite gets a matching `.yml` with `dbt_constraints.primary_key` (`<parent>_hk` + `load_dts`) and `dbt_constraints.foreign_key` back to its parent Hub or Link.

## Materialization

| Layer | Materialization |
| --- | --- |
| Staging | view |
| Hub / Link / Satellite | incremental |
| Mart | view |

## Dedup Rule

Never `SELECT DISTINCT` anywhere in staging or raw vault. Always `QUALIFY ROW_NUMBER()`.

## Business Key Collision Governance

`REC_SRC` and `BKCC` values are fetched dynamically by joining to `{{ ref('ref_business_key_collision') }}` in the `_A` stream.
The staging model must filter this reference table in the FILTER layer using a hardcoded source string (e.g., `WHERE rec_src = '<EXACT_SOURCE_STRING>'`) and perform an `INNER JOIN ... ON '1'='1'` in the JOIN layer.

This table is populated and maintained manually by the data engineering team - never by an agent. Agents may only READ from it. If a ticket requires a source system not yet present in this table, flag it to the user rather than inventing a REC_SRC/BKCC value or attempting to insert a row.

## Links Never Carry Descriptive Payload

A Link stores only hash keys + metadata. Any descriptive attribute of the relationship (e.g. account-holder role) belongs in its own Satellite on the Link.

## Self-Contained Generation Templates

(Use these directly when building from a ticket specification. These templates are sufficient on their own - an existing example file in the project is NOT required to generate a new model. If the ticket specifies model names, use those exact names in place of the placeholders below - see Naming Conventions.)

### Staging Template

(Staging models do not use a rigid copy-paste template; they must be dynamically constructed using the **Staging Model Architecture (Multi-Stream)** rules defined above.)

### Hub template (5-stage)

```sql
{{ config(materialized='incremental', unique_key='<ENTITY>_HK') }}
WITH
harvest AS (
    SELECT <ENTITY>_HK, <ENTITY>_BK, LOAD_DTS, REC_SRC
    FROM {{ ref('<staging_model>') }}
),
consolidate AS ( SELECT * FROM harvest ),
new_keys AS (
    SELECT * FROM consolidate
    {% if is_incremental() %}
    WHERE <ENTITY>_HK NOT IN (SELECT <ENTITY>_HK FROM {{ this }})
    {% endif %}
),
deduped AS (
    SELECT * FROM new_keys
    QUALIFY ROW_NUMBER() OVER (PARTITION BY <ENTITY>_HK ORDER BY LOAD_DTS ASC) = 1
),
ghost_records AS (
    SELECT MD5_BINARY(UPPER('0'))  AS <ENTITY>_HK, '0'  AS <ENTITY>_BK, '1900-01-01T00:00:00'::TIMESTAMP_NTZ AS LOAD_DTS, 'SYSTEM' AS REC_SRC
    UNION ALL
    SELECT MD5_BINARY(UPPER('-1')), '-1', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
    UNION ALL
    SELECT MD5_BINARY(UPPER('-2')), '-2', '1900-01-01T00:00:00'::TIMESTAMP_NTZ, 'SYSTEM'
),
FINAL AS (
    SELECT * FROM deduped
    {% if not is_incremental() %}
    UNION ALL SELECT * FROM ghost_records
    {% endif %}
)
SELECT * FROM FINAL

```

Link template follows the identical shape, with two parent `_HK` columns (e.g. `CUSTOMER_HK`, `ACCOUNT_HK`) plus the Link's own `_LHK` in place of a single entity `_HK`/`_BK` pair.

### Satellite template

```sql
{{ config(materialized='incremental', unique_key='<ENTITY>_HK') }}
WITH SRC AS ( SELECT * FROM {{ ref('<staging_model>') }} ),
LOGIC AS (
    SELECT <ENTITY>_HK, HASHDIFF, <all non-grain, non-BKCC columns>, LOAD_DTS, REC_SRC
    FROM SRC
),
FINAL AS (
    SELECT * FROM LOGIC
    {% if is_incremental() and var('enable_hub_dedup_check', true) %}
    WHERE HASHDIFF NOT IN (SELECT HASHDIFF FROM {{ this }})
    {% endif %}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY <ENTITY>_HK, HASHDIFF ORDER BY LOAD_DTS DESC) = 1
)
SELECT * FROM FINAL

```

## Ticket-Driven Workflow

When given a Jira-style ticket specifying source table, HK/BK formula, grain columns, and Satellite columns:

1. A dedicated branch is created, named `<TICKET_ID>_DEV`.
2. Models are generated directly from this standard's templates above - no existing reference file in the project is required.
3. Model names follow whatever the ticket specifies (see Naming Conventions) - the templates' default naming patterns only apply when the ticket doesn't name something explicitly.
4. The ticket's explicit config always overrides this document's other defaults where the two differ (e.g. a ticket specifying BKCC in the HK formula takes precedence over the Hash Key Formula section's default, if that default were to omit it).
5. Generated models still go through `dv-code-reviewer` before merging; a REQUEST CHANGES verdict is fed back to the generator to fix, not discarded and restarted from scratch.
6. Only an APPROVE verdict proceeds to PR generation.