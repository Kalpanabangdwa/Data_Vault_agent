# dv_gen_project

The dbt project where the Data Vault agents write their generated models. See the [top-level README](../README.md) for how the agents work.

## Layout and routing (`dbt_project.yml`)

| Folder | Schema | Materialization |
|---|---|---|
| `models/staging/` | `STAGING` | view |
| `models/raw_vault/hub/` | `RAW_VAULT` | incremental |
| `models/raw_vault/link/` | `RAW_VAULT` | incremental |
| `models/raw_vault/satellites/` | `RAW_VAULT` | incremental |
| `models/info_marts/` | `INFO_MART` | view |

`macros/generate_schema_name.sql` makes these schema names literal: `RAW_VAULT` stays `RAW_VAULT`, not `<target>_RAW_VAULT`.

## Sources

`models/staging/sources.yml` registers every raw table a staging model may read, plus the control table `CONTROL.REF_SOURCE_SYSTEM` (governed `REC_SRC` / `BKCC`). **A new source table must be added here before the generator can use it.** The generator stops if the table isn't registered.

## Packages

`dbt_constraints` (primary and foreign key tests), `dbt_utils`, `dbt_expectations`. Install them with `dbt deps`.

## Running

```bash
dbt deps
dbt debug                                   # checks the dv_gen_project profile in ~/.dbt/profiles.yml
dbt build --select stg_x hub_x sat_x        # what the Coordinator runs after review approval
```
