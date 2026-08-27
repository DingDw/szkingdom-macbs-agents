## Why

深圳股票质押证券退市后，`sz_sjsfw` 不再下发该证券代码的股票质押冻结数据，现有逻辑只能保留 SJSFW 缺失告警，无法刷新本地 `node_gpzydebtdetail` 的数量字段。需要在无 SJSFW 数据时使用 `intf_gpzydebtdetail` 下场合约作为兜底来源，避免本地合约明细数量长期滞后。

## What Changes

- 在股票质押合约日间同步处理中，针对深圳 A 股合约明细增加 SJSFW 缺失兜底刷新逻辑。
- 当按当前 SJSFW 股票质押处理范围找不到 `pledgesno + stkcode` 对应记录时，使用 `intf_gpzydebtdetail` 覆盖本地合约明细的 `bonusqty`、`backqty`、`wysbqty`、`wyczqty`、`wyczmatchqty`。
- 基于本地 `matchqty` 和刷新后的数量重算 `pledgeqty`，计算结果小于 0 时置为 0。
- 保留现有 SJSFW 正常存在时的处理逻辑、SJSFW 缺失告警逻辑、下场合约找不到本地明细时的处理逻辑。
- 刷新成功时更新 `remark` 并输出 info 日志，便于定位兜底处理记录。

## Capabilities

### New Capabilities
- `gpzydebtdetail-intf-fallback`: 股票质押合约明细在深圳 SJSFW 无对应记录时使用下场合约刷新本地数量字段的兜底能力。

### Modified Capabilities
- None

## Impact

- Affected code: `macbs-base/lbm_pro/macbs/cbs_clear/contract_deal/contract_deal/handler/clear_gpzy.cpp` 中 `CClearGpzy::MergeByDayContract()`。
- Affected data: `node_gpzydebtdetail` 的 `pledgeqty`、`bonusqty`、`backqty`、`wysbqty`、`wyczqty`、`wyczmatchqty`、`remark`。
- Affected input: `intf_gpzydebtdetail` 与 `sz_sjsfw` 缓存数据。
- No database schema change and no new external dependency.
