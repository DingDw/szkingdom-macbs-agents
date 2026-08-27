## Context

`CClearGpzy::Clear()` 在股票质押合约处理后处理中先执行 `MergeByDayContract()` 同步 `intf_gpzydebtdetail`，随后再执行中登流水处理、债务明细生成、场外质押物处理与 `RefreshGpzydebtBySjsfw()`。现有 `MergeByDayContract()` 对存量合约明细主要同步基础属性，并仅实际刷新 `wyczmatchqty`；深圳 SJSFW 刷新逻辑则依赖 `sz_sjsfw` 中股票质押记录更新本地 `node_gpzydebtdetail.pledgeqty` 等字段。

当深圳股票质押证券退市后，SJSFW 不再下发该证券代码数据。此时如果仍只依赖 `RefreshGpzydebtBySjsfw()`，系统只能产生缺失告警，不能刷新本地合约明细数量。需求要求在 `MergeByDayContract()` 中按 SJSFW 缺失情况使用 `intf_gpzydebtdetail` 兜底刷新指定字段，并保持其他现有逻辑不变。

## Goals / Non-Goals

**Goals:**
- 仅在深圳 A 股股票质押合约明细无对应 SJSFW 股票质押记录时，使用 `intf_gpzydebtdetail` 兜底刷新本地合约明细指定数量字段。
- SJSFW 有对应记录时保持现有 SJSFW 刷新逻辑不变。
- 仅覆盖 `pledgeqty`、`bonusqty`、`backqty`、`wysbqty`、`wyczqty`、`wyczmatchqty`，不刷新 `matchqty` 和日间字段。
- 保留现有 SJSFW 缺失告警、下场合约找不到本地明细等处理逻辑。

**Non-Goals:**
- 不调整 `RefreshGpzydebtBySjsfw()` 的既有核对与告警逻辑。
- 不调整上海 QTSL 逻辑或其他市场逻辑。
- 不修改表结构、接口定义、功能号配置或构建配置。
- 不改变 `node_gpzydebtdetail` 的既有定位规则。

## Decisions

1. **兜底逻辑放在 `MergeByDayContract()` 内。**
   - Rationale: 需求明确只调整该方法；同时该方法已遍历 `intf_gpzydebtdetail` 并定位本地 `node_gpzydebtdetail`，是最窄影响面。
   - Alternative considered: 在 `RefreshGpzydebtBySjsfw()` 系统单边分支中兜底。该方案会改变 SJSFW 刷新逻辑，并且发生在部分后续计算之后，不符合需求约束。

2. **SJSFW 缺失按 `pledgesno + stkcode` 粒度判断。**
   - Rationale: 用户确认只按本地明细的 `pledgesno + stkcode` 判断，不按 `stkprop` 判断。只要存在任意符合范围的 SJSFW 记录，该合约证券即不触发兜底。
   - Matching scope: `fwsjlb = '11'`、`fwzysm` 前两位为 `GZ`、`trim(fwzysm.substr(22, 24)) = node_gpzydebtdetail.pledgesno`、`fwzqdm = node_gpzydebtdetail.stkcode`。

3. **仅限定深圳 A 市场。**
   - Rationale: 需求背景为深圳股票质押，上海继续由 QTSL 相关逻辑处理。

4. **字段覆盖与 `pledgeqty` 重算。**
   - `bonusqty`、`backqty`、`wysbqty`、`wyczqty`、`wyczmatchqty` 使用 `intf_gpzydebtdetail` 对应字段覆盖。
   - `pledgeqty` 使用本地 `matchqty + bonusqty - backqty - wysbqty` 重算；如结果小于 0 则置为 0。
   - `matchqty` 不刷新，日间字段不刷新。

5. **保持现有定位和跳过规则。**
   - 沿用 `gpzysno + itemno + busidate` 优先定位，必要时按 `origin_itemno + equittype` 兜底定位。
   - 本地明细 `pledgeqty = 0` 时不进行本次兜底刷新。
   - 找不到本地明细、找不到下场合约等现有行为不调整。

6. **刷新可观测性。**
   - 成功兜底刷新时，将 `remark` 覆盖为 `sjsfw无该证券记录，使用日间合约刷新`。
   - 同时输出 info 日志，记录 `gpzysno`、`itemno`、`pledgesno`、`stkcode` 和刷新后的关键数量，便于问题定位。

## Risks / Trade-offs

- [Risk] SJSFW 存在同 `pledgesno + stkcode` 但缺少某个 `stkprop` 时不会触发兜底。→ Mitigation: 这是确认后的业务口径，保持现有股份性质差异处理逻辑。
- [Risk] `pledgeqty` 由本地 `matchqty` 和接口字段推导，若上游数据异常可能计算为负数。→ Mitigation: 负数置为 0，避免写入非法剩余质押数量。
- [Risk] 覆盖 `remark` 会替换原备注。→ Mitigation: 用户明确要求更新备注记录兜底来源，以便后续追踪。
- [Risk] 保留原 SJSFW 缺失告警会在成功兜底后继续出现告警。→ Mitigation: 用户明确要求保留告警；新增 info 日志用于区分已兜底刷新记录。
