## Context

The DDSC interface configuration currently uses both standard intfids and broker-specific legacy intfids:

- `OMS_DDSC_1570` must be standardized to `OMS_DDSC`.
- `OMS_DDSC_ZK_1570` must be standardized to `OMS_DDSC_ZK`.

The affected data lives in static configuration schemas, not runtime production data. The work must cover the standard schema and broker-specific schemas defined by the local MCP rules:

- `ddw_config`
- `ddw_config_dfcf`
- `ddw_config_gfzq`
- `ddw_config_gtzq`
- `ddw_config_gxzq`
- `ddw_config_hxzq`
- `ddw_config_yhzq`
- `ddw_config_zjcf`
- `ddw_config_zxjt`

Task parameters in `comm_flowrecord.params` are the source for effective task usage. The update scope is all task parameters that reference the legacy DDSC intfids, including pre-processing tasks, not only import/export tasks. Configuration migration uses `fileid` only when `fileid` is present in task parameters.

The confirmed table scope is:

`comm_if_file_detail`, `comm_custom_check_cfg`, `comm_file_export_params`, `comm_extsystem_export_relation`, `comm_if_filecheck`, `comm_qd_filter`, `comm_if_filename_ext`, `comm_file_supplement_log`, `comm_if_intf`, `comm_if_file`, `comm_if_domaininfoext`, `comm_if_node`, `comm_file_trancfg`, `comm_autoclear_fileinfo`, `comm_shjs_qd`, `comm_fileexport_log`, `comm_if_filepath`, `comm_acct_process_result`, `comm_inner_qd`, `comm_filedoublecheck_config`, `comm_zdql_file_cfg`, `comm_acct_intf`, `comm_file_group_dlt`, `comm_filecheck_config`, `comm_if_column`, `comm_filefilterrules`, `comm_if_file_log_sum`, `comm_if_file_log`, `comm_file_diffdata`, `comm_zip_extract_batch`, `comm_trdsys`, `comm_tainfo`, `comm_ok_file_cfg`, `comm_zdql_file_result`, `comm_filefilterrules_reverse`, `comm_shjys_qd`, `comm_custom_intf_cfg`, `comm_custom_task_cfg`.

## Goals / Non-Goals

**Goals:**

- Generate patch SQL scripts that standardize legacy DDSC intfids across all target schemas.
- Generate each target version's SQL under its corresponding standard or broker-specific patch directory.
- Avoid explicit schema-qualified table names in generated SQL so the scripts run against the current execution schema.
- Preserve the currently effective interface configuration according to task references.
- Stop safely when task usage or table data does not provide enough information for automatic migration.
- Generate separate precheck, adjustment, and postcheck scripts.
- Avoid generating DML for listed tables that have no matching data in the inspected schema.

**Non-Goals:**

- Execute the generated SQL against the database automatically.
- Modify full initialization scripts.
- Infer file configuration migration from columns other than `comm_flowrecord.params.fileid`.
- Automatically resolve old/new task conflicts for the same schema and `fileid`.
- Automatically resolve old/new data conflicts in tables that have `intfid` but no `fileid`.

## Decisions

### Use task parameters as the effective source

The generator will parse all target schema `comm_flowrecord.params` rows that contain `intfid=OMS_DDSC_1570`, `intfid=OMS_DDSC_ZK_1570`, `intfid=OMS_DDSC`, or `intfid=OMS_DDSC_ZK`. Effective usage for a file interface is determined by `(schema, intfid, fileid)` parsed from task parameters.

Alternative considered: derive effective interfaces from `comm_if_file` alone. This was rejected because a file configuration can exist without being referenced by any effective task.

### Split task updates from configuration migration

All legacy intfid task parameters will be updated regardless of whether a `fileid` parameter exists. Configuration tables will only be migrated by `fileid` when `fileid` is present in task parameters.

Alternative considered: require every affected task to have `fileid`. This was rejected because pre-processing tasks can legitimately carry an intfid without file-level configuration.

### Preserve the current effective side

For tables that have both `intfid` and `fileid`, the effective side is chosen from task usage:

- If tasks use the legacy intfid for a `fileid`, legacy rows are the source and standard rows for the same `fileid` are redundant.
- If tasks use the standard intfid for a `fileid`, standard rows are the source and legacy rows for the same `fileid` are redundant.
- If both sides are referenced by tasks for the same schema and `fileid`, the generator must stop with a precheck error.

Alternative considered: always use `OMS_DDSC_1570` / `OMS_DDSC_ZK_1570` as source. This was rejected because the current effective interface can already be the standard intfid.

### Fail fast on non-file-scoped ambiguity

For listed tables that have `intfid` but not `fileid`, automatic migration is allowed only when the old side has data and the new side has no data. If old and new sides both have data in the same schema and table, the precheck must report an error for manual confirmation.

Alternative considered: keep the new side and delete the old side. This was rejected because there is no `fileid` dimension to prove which side belongs to the effective DDSC task set.

### Generate three scripts

The output for each standard or broker-specific version will be split into:

- `00_precheck.sql`: conflict checks and affected data counts only.
- `01_adjust.sql`: DML for task parameter updates and table migration/cleanup.
- `02_postcheck.sql`: residual checks after adjustment.

This split makes review and rollback safer than a single monolithic script.

### Generate directory-scoped SQL without schema qualification

The standard version writes to `macbs-service/database/script/patch/gauss/fs_cbs/fs_cbs_comm/manual/intfid_adjust`. Each broker-specific version writes to `macbs-service/database/script/patch/<券商名称>/gauss/fs_cbs/fs_cbs_comm/manual/intfid_adjust`.

Generated SQL uses unqualified table names such as `comm_flowrecord` and `comm_if_file`. The execution environment must select the intended schema before running each script.

### Generate DML only for tables with matching data

The generator will inspect each listed table per schema. If a table has no matching legacy/standard DDSC data relevant to this adjustment, the adjustment script will omit DML for that table.

## Risks / Trade-offs

- **A table uses intfid semantics that are not equivalent to direct renaming** -> The precheck reports tables and counts before DML; tables without `fileid` fail on old/new ambiguity.
- **Task parameter parsing misses non-standard syntax** -> The generator must parse key-value segments separated by `|` and only rewrite exact `intfid=<value>` segments.
- **Primary key conflicts occur during migration** -> For `intfid,fileid` tables, target-side redundant rows are deleted before migrating source rows.
- **A generated script is re-run after partial failure** -> The adjustment SQL should be ordered and guarded by prechecks; postcheck must identify residual legacy data.
- **Static database contents change between generation and execution** -> `00_precheck.sql` must be executed immediately before `01_adjust.sql`; any reported conflict blocks execution.

## Migration Plan

1. Generate `00_precheck.sql`, `01_adjust.sql`, and `02_postcheck.sql` for the standard version and each broker-specific version from the current static configuration database.
2. Review `00_precheck.sql` output for task conflicts and non-file-scoped table conflicts.
3. Execute `01_adjust.sql` only when precheck returns no blocking conflicts.
4. Execute `02_postcheck.sql` and confirm:
   - No `comm_flowrecord.params` rows contain legacy DDSC intfids.
   - Listed tables have no residual legacy intfid data that should have been migrated or deleted.
   - No current effective DDSC file interface configuration was lost.
5. If a blocking conflict is found, stop and resolve manually before regenerating scripts.
