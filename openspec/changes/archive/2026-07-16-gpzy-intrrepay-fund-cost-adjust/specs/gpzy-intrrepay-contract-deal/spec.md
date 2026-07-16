## ADDED Requirements

### Requirement: 计划负债写入还息计划排序标识
国信股票质押合约处理在根据未完成还息计划生成 `node_debtdetail` 负债记录时，系统 SHALL 写入稳定的还息计划来源标识，并 MUST 将 `node_debtdetail.extsno` 设置为还息计划表的 `createdate#sno`，供后续资金扣收按字符串排序使用。

#### Scenario: 生成计划负债来源标识
- **WHEN** 系统根据未完成还息计划生成 `node_debtdetail` 负债记录
- **THEN** 负债记录 `pathid` MUST 为 `GPZYDEBT_INTRREPAYPLAN`
- **AND** 负债记录 `extsno` MUST 为还息计划表的 `createdate#sno`
- **AND** 该 `extsno` MUST 作为资金扣收还息计划专用排序键

#### Scenario: 恢复重做限定计划负债来源
- **WHEN** 股票质押合约处理恢复重做删除当日生成的计划负债流水
- **THEN** 删除条件 MUST 限定 `pathid='GPZYDEBT_INTRREPAYPLAN'`
- **AND** 系统 MUST 不删除其他来源生成的股票质押负债记录
