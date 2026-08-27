# ddsc-intfid-standardization Specification

## Purpose
TBD - created by archiving change intfid-adjust. Update Purpose after archive.
## Requirements
### Requirement: Standardize DDSC task intfid parameters
The SQL generation process SHALL update all target schema `comm_flowrecord.params` rows that contain legacy DDSC intfid task parameters. It MUST replace exact task parameter segments `intfid=OMS_DDSC_1570` with `intfid=OMS_DDSC` and `intfid=OMS_DDSC_ZK_1570` with `intfid=OMS_DDSC_ZK`.

#### Scenario: Legacy DDSC task parameter is replaced
- **WHEN** a target schema `comm_flowrecord.params` contains the segment `intfid=OMS_DDSC_1570`
- **THEN** the generated adjustment SQL MUST replace that segment with `intfid=OMS_DDSC`

#### Scenario: Legacy DDSC_ZK task parameter is replaced
- **WHEN** a target schema `comm_flowrecord.params` contains the segment `intfid=OMS_DDSC_ZK_1570`
- **THEN** the generated adjustment SQL MUST replace that segment with `intfid=OMS_DDSC_ZK`

#### Scenario: Pre-processing task without fileid is still updated
- **WHEN** a target schema `comm_flowrecord.params` contains a legacy DDSC intfid segment and does not contain a `fileid` segment
- **THEN** the generated adjustment SQL MUST still standardize the `intfid` segment
- **AND** MUST NOT derive file-level configuration migration from that task row

### Requirement: Derive file-scoped migration from task fileid
The SQL generation process SHALL derive file-scoped configuration migration only from `fileid` values parsed from target schema `comm_flowrecord.params` rows. It MUST NOT infer affected `fileid` values from interface configuration tables alone.

#### Scenario: Task contains legacy intfid and fileid
- **WHEN** a target schema task parameter row contains a legacy DDSC intfid segment and a `fileid=<value>` segment
- **THEN** the generated SQL MUST include that `(schema, old_intfid, new_intfid, fileid)` pair in the file-scoped migration set

#### Scenario: Configuration exists without task reference
- **WHEN** a listed configuration table contains legacy DDSC intfid data for a `fileid` that is not referenced by any parsed task parameter
- **THEN** the generated SQL MUST NOT treat that configuration row as an effective file-scoped migration source

### Requirement: Preserve currently effective file-scoped configuration
For listed tables that contain both `intfid` and `fileid`, the SQL generation process SHALL preserve the side currently referenced by task parameters. It MUST migrate legacy-side configuration to the standard intfid when tasks reference the legacy side, and MUST remove legacy-side redundancy when tasks reference the standard side.

#### Scenario: Legacy side is effective
- **WHEN** target schema tasks reference `(old_intfid, fileid)` and do not reference `(new_intfid, fileid)`
- **THEN** the generated adjustment SQL MUST remove redundant `(new_intfid, fileid)` rows from listed file-scoped tables when they exist
- **AND** MUST migrate existing `(old_intfid, fileid)` rows in listed file-scoped tables to `(new_intfid, fileid)`

#### Scenario: Standard side is already effective
- **WHEN** target schema tasks reference `(new_intfid, fileid)` and do not reference `(old_intfid, fileid)`
- **THEN** the generated adjustment SQL MUST keep `(new_intfid, fileid)` rows in listed file-scoped tables
- **AND** MUST remove redundant `(old_intfid, fileid)` rows in listed file-scoped tables when they exist

#### Scenario: Old and new task references conflict
- **WHEN** the same target schema and `fileid` are referenced by both old and new DDSC intfids in task parameters
- **THEN** the precheck SQL MUST report a blocking conflict
- **AND** the adjustment SQL MUST NOT be considered executable until the conflict is manually resolved

### Requirement: Handle non-file-scoped tables conservatively
For listed tables that contain `intfid` but do not contain `fileid`, the SQL generation process SHALL only generate automatic DML when old-side data exists and matching new-side data does not exist for the same table and schema. It MUST report a blocking conflict when both old-side and new-side data exist.

#### Scenario: Non-file-scoped table has only old-side data
- **WHEN** a listed non-file-scoped table contains rows for `OMS_DDSC_1570` or `OMS_DDSC_ZK_1570`
- **AND** the same schema and table contains no rows for the mapped standard intfid
- **THEN** the generated adjustment SQL MAY update the old intfid rows to the mapped standard intfid

#### Scenario: Non-file-scoped table has old-side and new-side data
- **WHEN** a listed non-file-scoped table contains rows for a legacy DDSC intfid
- **AND** the same schema and table also contains rows for the mapped standard intfid
- **THEN** the precheck SQL MUST report a blocking conflict for manual confirmation

### Requirement: Process only confirmed tables with matching data
The SQL generation process SHALL limit table DML to the confirmed table list and SHALL omit adjustment DML for any listed table that has no matching DDSC legacy or standard data in the inspected schema.

#### Scenario: Listed table has no matching data
- **WHEN** a confirmed table exists in a target schema but contains no matching DDSC legacy or standard rows relevant to the adjustment
- **THEN** the generated adjustment SQL MUST omit DML for that table and schema

#### Scenario: Table is outside the confirmed list
- **WHEN** a database table contains `intfid` or `fileid` columns but is not in the confirmed table list
- **THEN** the generated adjustment SQL MUST NOT modify that table

### Requirement: Generate separate precheck adjustment and postcheck scripts
The SQL generation process SHALL produce separate SQL scripts for precheck, adjustment, and postcheck execution. The precheck script MUST be read-only, the adjustment script MUST contain the required DML, and the postcheck script MUST verify that legacy DDSC intfids are no longer effective.

#### Scenario: Precheck script identifies blockers
- **WHEN** a task conflict or non-file-scoped table conflict exists
- **THEN** `00_precheck.sql` MUST report the conflict with schema, table or fileid context
- **AND** the operator MUST be able to stop before running `01_adjust.sql`

#### Scenario: Postcheck validates task cleanup
- **WHEN** `01_adjust.sql` has been executed
- **THEN** `02_postcheck.sql` MUST report zero `comm_flowrecord.params` rows containing `intfid=OMS_DDSC_1570` or `intfid=OMS_DDSC_ZK_1570`

#### Scenario: Postcheck validates static table cleanup
- **WHEN** `01_adjust.sql` has been executed
- **THEN** `02_postcheck.sql` MUST report residual legacy intfid rows in the confirmed table list, if any remain

### Requirement: Place scripts by target version without schema-qualified SQL
The SQL generation process SHALL write one precheck, adjustment, and postcheck script set under the standard patch directory and one script set under each broker-specific patch directory. The generated SQL MUST use the current execution schema and MUST NOT contain explicit schema-qualified table names.

#### Scenario: Standard script set is generated
- **WHEN** the generator processes the standard version
- **THEN** it MUST write `00_precheck.sql`, `01_adjust.sql`, and `02_postcheck.sql` under the standard Gauss fs_cbs_comm patch directory
- **AND** those SQL files MUST NOT qualify tables with the standard schema name

#### Scenario: Broker-specific script set is generated
- **WHEN** the generator processes a broker-specific version
- **THEN** it MUST write `00_precheck.sql`, `01_adjust.sql`, and `02_postcheck.sql` under that broker's Gauss fs_cbs_comm patch directory
- **AND** those SQL files MUST NOT qualify tables with the broker schema name

