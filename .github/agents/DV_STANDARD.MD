# DV_Gen Fintech Data Vault Standard 

## Rule Precedence

The following precedence applies throughout the Data Vault generation
workflow:

1. Explicit requirements provided in the current user request or ticket
   take priority over default rules in this standard.
2. When the ticket does not explicitly specify a behavior, the rules
   defined in this standard must be followed.
3. Agents must not invent or silently change requirements that are not
   specified by either the ticket or this standard.

This precedence applies consistently to all agents, including the
Coordinator, Model Generator, Code Reviewer, and PR Generator.

Examples of explicit ticket requirements include, but are not limited to:

- Hash Key formulas
- Business Key definitions
- Grain definitions
- Model names
- REC_SRC
- BKCC
- Requested Satellite columns
- Other explicitly specified model configuration

When an explicit ticket requirement differs from a default rule in this
standard, the ticket requirement takes priority.

Agents must preserve and apply the explicit ticket requirement
consistently throughout the workflow.


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

Staging models prepare the requested raw source data for the Data Vault
layers.

The staging model must process the required input streams separately
before consolidating them.

Every CTE must use the appropriate stream suffix:

- **Stream `_S`**: The primary business-data stream. It reads the
  requested physical raw table using the exact `source()` registration
  resolved from the current project's `sources.yml`.

- **Stream `_A`**: The authoritative metadata stream used to provide
  source-control metadata such as `REC_SRC` and `BKCC`. In the current
  project this is `{{ source('control', 'REF_SOURCE_SYSTEM') }}`.

- **Streams `_S2`, `_S3`, etc.**: Optional secondary business-data or
  lookup streams required by the current ticket and source structure.

The generator must determine which streams are required from the current
ticket, authoritative metadata, and live Snowflake metadata.

The generator must not copy source names, columns, joins, or business
logic from reference models. Reference models are used only to follow
the defined structural and calculation patterns.

The `_A` stream must not be treated as business source data. It provides
authoritative metadata required to enrich or validate the primary source
stream.

The `_A` stream must use the exact configured source or dbt reference
resolved for the current project. The generator must not assume that
`REF_SOURCE_SYSTEM` is universally the control table name for every
project.

**The 6 Mandatory Layers (Always in this order)**

1. **SRC Layer:** Extract raw data. Use `{{ source(...) }}` for verified
   physical source data tables and `{{ ref(...) }}` for the `_A` reference
   table when the current project defines the authoritative reference as a
   dbt model. If a secondary table (`_S2`) requires deduplication, apply
   `QUALIFY 1 = ROW_NUMBER() OVER (...)` directly in this layer.

2. **LOGIC Layer:** Isolate stream-specific transformations. Alias the raw
   grain columns to their Business Key names (e.g., `<raw_col> AS ITEM_BK`).
   Derive the `LOAD_DTS` column here using exact timezone conversions
   (e.g., `CONVERT_TIMEZONE('UTC', ...)`).

3. **RENAME Layer:** Select columns from the LOGIC layer, mapping them to
   standardized enterprise names. Maintain separate CTEs for each stream
   (`RENAME_S`, `RENAME_A`, etc.).

4. **FILTER Layer:** Drop invalid or null grain rows.

   For the `_A` stream, filter using the `REC_SRC` value resolved for the
   current workflow.

   - If `REC_SRC` is explicitly provided in the current ticket/request, use
     that exact value.
   - If `REC_SRC` is not provided, resolve it from the authoritative
     Business Key Collision/control metadata.
   - Never hardcode or reuse a `REC_SRC` value from a previous model, ticket,
     or remembered source-system mapping.
   - If `REC_SRC` cannot be resolved unambiguously, STOP and report the
     missing or ambiguous metadata.

5. **JOIN Layer:** Consolidate the streams into a single `JOIN_RESULT` CTE.
   `INNER JOIN` the `_A` stream using `ON '1' = '1'`. `LEFT JOIN` any `_S2`
   lookup streams using their respective keys.

6. **FINAL Layer:** Select all consolidated columns. Compute all `_HK` and
   `HASHDIFF` values exactly once in this layer using `MD5_BINARY`.

## REC_SRC and BKCC Governance

`REC_SRC` and `BKCC` are Data Vault source metadata values.

For this POC, the source metadata convention is:

- `RAW_CORE_BANKING` uses `BKCC = SAP_ECC`.
- `RAW_CARD_PROCESSOR` uses `BKCC = CARD_PROCESSOR`.
- `REC_SRC` is constructed as `<BKCC>_<TABLE_NAME>`.

Examples:

- `RAW_CORE_BANKING.BRANCHES` → `BKCC = SAP_ECC`, `REC_SRC = SAP_ECC_BRANCHES`
- `RAW_CORE_BANKING.CUSTOMERS` → `BKCC = SAP_ECC`, `REC_SRC = SAP_ECC_CUSTOMERS`
- `RAW_CARD_PROCESSOR.CARDS` → `BKCC = CARD_PROCESSOR`, `REC_SRC = CARD_PROCESSOR_CARDS`
- `RAW_CARD_PROCESSOR.CUSTOMERS` → `BKCC = CARD_PROCESSOR`, `REC_SRC = CARD_PROCESSOR_CUSTOMERS`

The resolution priority is:

1. Explicit `REC_SRC` or `BKCC` values provided in the current
   ticket/request take priority.
2. If not explicitly provided, resolve the values from the current
   `REF_SOURCE_SYSTEM` metadata.
3. The metadata lookup must use both `TABLE_SCHEMA` and `TABLE_NAME`
   to uniquely identify the source table.
4. If the required values cannot be resolved unambiguously, STOP.

The generator must not derive `REC_SRC` or `BKCC` from the dbt
`source()` name, model name, or Snowflake schema name when authoritative
values are available in `REF_SOURCE_SYSTEM`.

Explicit ticket/request values always take priority over
metadata-derived values.

## dbt Source Registration Governance

All physical source tables used by staging models MUST be registered in
the current `models/staging/sources.yml`.

The dbt `source()` name MUST come from the current source registration.

The generator MUST:

1. Verify that the physical source table exists in Snowflake.
2. Resolve its actual database, schema, and table from live Snowflake metadata.
3. Locate the matching registration in `models/staging/sources.yml`.
4. Use the exact registered dbt source name in `{{ source(...) }}`.

The generator MUST NOT:

- assume a dbt source name;
- derive a dbt source name from `REC_SRC` or `BKCC`;
- reuse source aliases from previous models or tickets;
- use historical aliases that are not present in the current `sources.yml`;
- rename a source alias simply to match a default naming convention.

For the current project, the registered source mappings are:

- `Raw_core_banking` → `CUSTOM_AGENT.RAW_CORE_BANKING`
- `Raw_card_processor` → `CUSTOM_AGENT.RAW_CARD_PROCESSOR`
- `control` → `CUSTOM_AGENT.CONTROL`

Examples:

```sql
{{ source('Raw_core_banking', 'ACCOUNTS') }}
{{ source('Raw_card_processor', 'CARDS') }}
{{ source('control', 'REF_SOURCE_SYSTEM') }}

### REC_SRC

- If `REC_SRC` is explicitly provided in the current ticket/request, the
  generator MUST use that exact value.
- If `REC_SRC` is not provided, the generator MUST resolve it from the
  authoritative current control/Business Key Collision metadata.
- The resolved `REC_SRC` value MUST be used consistently in the `_A` stream
  filter and downstream join logic.
- The generator MUST NOT derive `REC_SRC` from `BKCC` unless the current
  request explicitly defines that relationship.

### BKCC

- If `BKCC` is explicitly provided in the current ticket/request, the
  generator MUST use that exact value.
- If `BKCC` is not provided, the generator MUST resolve it from the
  authoritative current control/Business Key Collision metadata.
- The generator MUST NOT assume a default such as `SAP_ECC`.
- The generator MUST NOT reuse a BKCC value from a previous model or ticket.

### Missing or Ambiguous Metadata

If the required source/control metadata cannot be resolved:

- STOP the workflow.
- Explicitly acknowledge what could not be resolved.
- Report the physical table or metadata source that was searched.
- Do not generate SQL using guessed or placeholder values.
- Do not substitute another control table.

If multiple REC_SRC or BKCC values are possible and the correct value cannot
be determined unambiguously, STOP and report the ambiguity.

### Source Table Validation

Before generating the staging model, the generator MUST verify that the
physical driver table exists in Snowflake.

If the requested driver table does not exist:

- STOP the workflow.
- Explicitly acknowledge that the requested source table was not found.
- Report the exact table name that was searched.
- Do not generate a staging model using an assumed or placeholder source. 

## Hash Key Formula
**Default (no BKCC):**
```sql
MD5_BINARY(UPPER(CONCAT_WS('||',
    COALESCE(NULLIF(TRIM(CAST(<bk_col> AS VARCHAR)), ''), '^^')
)))

```

### Staging Template
(Use this exact multi-stream syntax structure, adjusting column names and joins based on the ticket)
WITH 
SRC_S AS ( SELECT * FROM {{ source('<schema>', '<DRIVER_TABLE>') }} ),
SRC_A AS ( SELECT * FROM {{ source('control', 'REF_SOURCE_SYSTEM') }} ),

LOGIC_S AS (
    SELECT 
        NULLIF(TRIM(CAST(<driver_bk_col> AS VARCHAR)), '') AS <ENTITY>_BK,
        <other_columns>,
        CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())::TIMESTAMP_NTZ AS LOAD_DTS
    FROM SRC_S
),
LOGIC_A AS ( SELECT * FROM SRC_A ),

RENAME_S AS (
    SELECT <ENTITY>_BK, <other_columns>, LOAD_DTS FROM LOGIC_S
),
RENAME_A AS (
    SELECT TABLE_NAME, REC_SRC, BKCC FROM LOGIC_A
),

FILTER_S AS (
    SELECT * FROM RENAME_S WHERE <ENTITY>_BK IS NOT NULL
),
FILTER_A AS (
    SELECT * FROM RENAME_A WHERE TABLE_NAME = '<DRIVER_TABLE>'
),

JOIN_RESULT AS (
    SELECT 
        s.*, 
        a.REC_SRC, 
        a.BKCC
    FROM FILTER_S s
    INNER JOIN FILTER_A a ON '1' = '1'
    -- LEFT JOIN FILTER_S2 s2 ON s.<key> = s2.<key> (If secondary lookups exist)
),

FINAL AS (
    SELECT 
        *,
        MD5_BINARY(UPPER(CONCAT_WS('||',
            COALESCE(NULLIF(TRIM(CAST(<ENTITY>_BK AS VARCHAR)), ''), '^^'),
            COALESCE(NULLIF(TRIM(CAST(BKCC AS VARCHAR)), ''), '^^')
        ))) AS <ENTITY>_HK,
        MD5_BINARY(UPPER(NULLIF(CONCAT(
            IFNULL(TRIM(<payload_col_1>::text), '^^'), '||',
            IFNULL(TRIM(<payload_col_2>::text), '^^')
        ), '^^||^^'))) AS HASHDIFF
    FROM JOIN_RESULT
)
SELECT * FROM FINAL

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

For the `FILTER_A` stream, filter using the REC_SRC value resolved for the
current source table.

The value MUST come from either the explicit ticket/request or the
authoritative control/reference metadata.

Do not use a hardcoded REC_SRC value from a previous model or ticket.

The generator MUST use the current project configuration and authoritative
Snowflake metadata to determine the correct source.

The generator MUST NOT assume that the authoritative metadata is always
provided by a specific table or dbt model name.

If the current project explicitly defines a dbt reference model for the
Business Key Collision metadata, use that `{{ ref(...) }}` model.

If the metadata is exposed through a configured dbt source, use the exact
`{{ source(...) }}` alias defined by the current project configuration.

If the required metadata source does not exist or the required REC_SRC/BKCC
values cannot be resolved unambiguously, STOP and explicitly report the
problem.

Never invent, hardcode, or reuse REC_SRC/BKCC values from previous models.

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