## 1. Data Discovery

- [x] 1.1 Confirm the target schema list from the MCP rules and use the corrected broker names in generated summaries.
- [x] 1.2 Define the legacy-to-standard intfid mapping for `OMS_DDSC_1570 -> OMS_DDSC` and `OMS_DDSC_ZK_1570 -> OMS_DDSC_ZK`.
- [x] 1.3 Define the confirmed 38-table processing list and introspect each table's `intfid` and `fileid` columns from the database metadata.
- [x] 1.4 Parse all target schema `comm_flowrecord.params` rows that reference old or new DDSC intfids, including rows without `fileid`.
- [x] 1.5 Build file-scoped effective interface sets from parsed `(schema, intfid, fileid)` task parameters.

## 2. Precheck Generation

- [x] 2.1 Generate task conflict checks for cases where the same schema and `fileid` are referenced by both old and new DDSC intfids.
- [x] 2.2 Generate non-file-scoped table conflict checks for tables that have `intfid` but no `fileid` and contain both old-side and new-side data.
- [x] 2.3 Generate affected-row count queries for all matching target schemas and confirmed tables.
- [x] 2.4 Ensure `00_precheck.sql` is read-only and clearly labels blocking conflicts versus informational counts.

## 3. Adjustment SQL Generation

- [x] 3.1 Generate exact task parameter replacement SQL for all target schema `comm_flowrecord.params` rows containing legacy DDSC intfid segments.
- [x] 3.2 For file-scoped tables where legacy intfid is the effective source, generate delete-then-update SQL that removes redundant target rows and migrates source rows to the standard intfid.
- [x] 3.3 For file-scoped tables where the standard intfid is already the effective source, generate SQL that removes redundant legacy rows without changing the standard rows.
- [x] 3.4 For non-file-scoped tables with only old-side data, generate SQL that updates the legacy intfid to the mapped standard intfid.
- [x] 3.5 Omit adjustment DML for confirmed tables and schema combinations that have no matching data.
- [x] 3.6 Place generated adjustment SQL in `01_adjust.sql` with comments explaining each schema, table, and migration category.

## 4. Postcheck Generation

- [x] 4.1 Generate task residual checks proving `comm_flowrecord.params` no longer contains `intfid=OMS_DDSC_1570` or `intfid=OMS_DDSC_ZK_1570`.
- [x] 4.2 Generate confirmed-table residual checks for legacy DDSC intfid rows after adjustment.
- [x] 4.3 Generate file-scoped completeness checks for each effective `(schema, new_intfid, fileid)` target derived from task parameters.
- [x] 4.4 Place post-adjustment validation SQL in `02_postcheck.sql`.

## 5. Script Packaging

- [x] 5.1 Implement or update a local generator script that reads database metadata/data and writes `00_precheck.sql`, `01_adjust.sql`, and `02_postcheck.sql`.
- [x] 5.2 Put generated SQL under the appropriate standard or broker-specific `macbs-service/database/script/patch` path for Gauss fs_cbs configuration delivery.
- [x] 5.3 Include business comments in generated SQL explaining the DDSC intfid standardization and target version scope without schema-qualified table names.
- [x] 5.4 Do not modify full initialization SQL scripts.

## 6. Verification

- [x] 6.1 Run the generator and verify that all three SQL scripts are produced.
- [x] 6.2 Review generated precheck SQL for the known conflict categories and ensure conflicts stop execution by operator process.
- [x] 6.3 Validate generated SQL syntax and confirm the generated SQL does not contain explicit schema-qualified table names, without executing DML against the database.
- [x] 6.4 Re-run the OMS DDSC interface analysis report after generation, if needed, to confirm expected target intfid usage.
- [x] 6.5 Summarize affected schemas, tables with generated DML, and any manual-confirmation blockers.
