## Why

OMS_DDSC file interface tasks currently still reference broker-specific legacy interface IDs such as `OMS_DDSC_1570` and `OMS_DDSC_ZK_1570`. These task parameters need to be standardized to `OMS_DDSC` and `OMS_DDSC_ZK` while preserving the effective file interface configuration in each standard and broker-specific schema.

## What Changes

- Generate SQL scripts for the standard version and each broker-specific version to standardize `comm_flowrecord.params` from legacy DDSC intfids to standard DDSC intfids.
- Migrate or clean related static configuration data across the confirmed interface-related table list, processing only tables with matching data.
- Preserve the currently effective interface configuration according to task usage:
  - If tasks currently use the legacy intfid for a `fileid`, migrate that legacy configuration to the standard intfid.
  - If tasks already use the standard intfid for a `fileid`, keep the standard configuration and remove redundant legacy configuration.
  - If the same schema and `fileid` are referenced by both legacy and standard intfids, stop with a precheck error for manual confirmation.
- Split generated SQL into precheck, adjustment, and postcheck scripts under each corresponding standard or broker-specific patch directory.
- Keep generated SQL executable in the current schema context by avoiding explicit schema-qualified table names.
- Add validation that all legacy DDSC intfid task parameters and related static configuration remnants are cleared after adjustment.

## Capabilities

### New Capabilities
- `ddsc-intfid-standardization`: Standardize DDSC task parameters and related static file interface configuration from legacy broker-specific intfids to standard DDSC intfids.

### Modified Capabilities
- None.

## Impact

- Affects SQL generation for `ddw_config`, `ddw_config_dfcf`, `ddw_config_gfzq`, `ddw_config_gtzq`, `ddw_config_gxzq`, `ddw_config_hxzq`, `ddw_config_yhzq`, `ddw_config_zjcf`, and `ddw_config_zxjt`.
- Reads current database metadata and data through `postgres-mcp` / PostgreSQL connection to identify affected records.
- Outputs patch SQL under the corresponding standard or broker-specific `macbs-service/database/script/patch` delivery directory following existing database-script conventions.
- Does not execute generated SQL against the database by default.
