## ADDED Requirements

### Requirement: Detect missing Shenzhen GPZY SJSFW records
The system SHALL determine whether a Shenzhen A stock pledge debt detail has a corresponding SJSFW stock pledge record by matching the local debt detail's market pledge number and stock code against SJSFW records in the current stock pledge SJSFW scope.

A corresponding SJSFW record MUST satisfy all of the following conditions:
- `fwsjlb` equals `11`.
- `fwzysm` starts with `GZ`.
- `trim(fwzysm.substr(22, 24))` equals `node_gpzydebtdetail.pledgesno`.
- `fwzqdm` equals `node_gpzydebtdetail.stkcode`.

#### Scenario: SJSFW record exists for pledge number and stock code
- **WHEN** `MergeByDayContract()` processes a Shenzhen A `intf_gpzydebtdetail` record and a matching local `node_gpzydebtdetail` record has at least one corresponding SJSFW record by `pledgesno + stkcode`
- **THEN** the system MUST NOT use `intf_gpzydebtdetail` to perform the SJSFW-missing fallback refresh for that local debt detail

#### Scenario: SJSFW record does not exist for pledge number and stock code
- **WHEN** `MergeByDayContract()` processes a Shenzhen A `intf_gpzydebtdetail` record and the matching local `node_gpzydebtdetail` record has no corresponding SJSFW record by `pledgesno + stkcode`
- **THEN** the system SHALL treat the local debt detail as eligible for the SJSFW-missing fallback refresh, subject to existing local-detail matching and skip rules

### Requirement: Refresh selected debt detail quantities from interface data
When a Shenzhen A local stock pledge debt detail is eligible for SJSFW-missing fallback refresh, the system SHALL overwrite only the selected quantity fields from the matching `intf_gpzydebtdetail` record and recompute `pledgeqty` from the refreshed values.

The system MUST overwrite:
- `bonusqty`
- `backqty`
- `wysbqty`
- `wyczqty`
- `wyczmatchqty`

The system MUST recompute:
- `pledgeqty = node_gpzydebtdetail.matchqty + bonusqty - backqty - wysbqty`

If the recomputed `pledgeqty` is less than zero, the system MUST set `pledgeqty` to zero. The system MUST NOT overwrite `matchqty` or day-real fields such as `backqty_real`, `backbonusamt_real`, `czmatchamt_real`, `backczamt_real`, or `backbonusamtqty_real` as part of this fallback.

#### Scenario: Fallback refresh updates selected fields
- **WHEN** a Shenzhen A local debt detail is matched from `intf_gpzydebtdetail`, its current `pledgeqty` is not zero, and no corresponding SJSFW record exists by `pledgesno + stkcode`
- **THEN** the system SHALL overwrite `bonusqty`, `backqty`, `wysbqty`, `wyczqty`, and `wyczmatchqty` from `intf_gpzydebtdetail`
- **AND** the system SHALL recompute `pledgeqty` from local `matchqty` plus refreshed `bonusqty` minus refreshed `backqty` minus refreshed `wysbqty`

#### Scenario: Recomputed pledge quantity is negative
- **WHEN** the fallback refresh recomputes `pledgeqty` to a value less than zero
- **THEN** the system MUST write `pledgeqty` as zero

#### Scenario: Local pledge quantity is already zero
- **WHEN** `MergeByDayContract()` matches a local `node_gpzydebtdetail` whose current `pledgeqty` is zero
- **THEN** the system MUST skip the SJSFW-missing fallback refresh for that local debt detail

### Requirement: Preserve existing non-fallback behavior
The system SHALL preserve existing stock pledge contract synchronization behavior outside the SJSFW-missing Shenzhen A fallback scope.

#### Scenario: Non-Shenzhen-A details are processed
- **WHEN** `MergeByDayContract()` processes a debt detail whose market is not Shenzhen A
- **THEN** the system MUST NOT apply the SJSFW-missing fallback refresh for that detail

#### Scenario: Existing unmatched-detail handling occurs
- **WHEN** `MergeByDayContract()` cannot match an `intf_gpzydebtdetail` record to a local `node_gpzydebtdetail` record using existing matching rules
- **THEN** the system MUST preserve the existing unmatched-detail behavior and MUST NOT introduce a new error or warning path for this change

#### Scenario: SJSFW missing warning remains
- **WHEN** downstream SJSFW reconciliation detects that a system debt detail has no corresponding SJSFW record
- **THEN** the system MUST preserve the existing SJSFW missing warning behavior

### Requirement: Record fallback refresh observability
When the system performs an SJSFW-missing fallback refresh, it SHALL make the refresh observable through the local debt detail remark and an info log entry.

#### Scenario: Fallback refresh succeeds
- **WHEN** the system refreshes a local `node_gpzydebtdetail` using `intf_gpzydebtdetail` because no matching SJSFW record exists
- **THEN** the system SHALL set `remark` to `sjsfw无该证券记录，使用日间合约刷新`
- **AND** the system SHALL write an info log identifying the refreshed debt detail and key refreshed quantities
