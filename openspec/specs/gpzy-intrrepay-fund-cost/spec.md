## Purpose

定义国信股票质押批量还息计划负债在资金扣收中的配置、扣收明细排序和扣收交割流水冻结金额规则，确保仅对 `015032/025032 + GPZYDEBT_INTRREPAYPLAN` 来源记录启用专用处理，普通股票质押利息负债和其他来源记录继续沿用通用资金扣收行为。

## Requirements

### Requirement: 配置国信还息计划利息负债扣收规则
系统 SHALL 在国信个性化数据库 patch 中为股票质押还息计划利息负债配置资金扣收规则，并 MUST 使用 `delete + insert` 模式覆盖 `015032` 和 `025032` 的 `comm_fund_cost_cfg` 配置。

#### Scenario: 写入上海利息负债扣收配置
- **WHEN** 国信个性化 patch 初始化 `busitype='015032'` 的资金扣收配置
- **THEN** 系统 MUST 删除既有 `015032` 配置后重新插入配置
- **AND** 新配置 `costpriority` MUST 为 `900000`
- **AND** 新配置 `costunit` MUST 为 `1`
- **AND** 新配置 `closemode` MUST 为 `1`
- **AND** 新配置 `costmode` MUST 为单空格
- **AND** 新配置 `advfrzflag` MUST 为 `0`
- **AND** 新配置 `remark` MUST 为 `015032` 对应业务名称

#### Scenario: 写入深圳利息负债扣收配置
- **WHEN** 国信个性化 patch 初始化 `busitype='025032'` 的资金扣收配置
- **THEN** 系统 MUST 删除既有 `025032` 配置后重新插入配置
- **AND** 新配置 `costpriority` MUST 为 `900000`
- **AND** 新配置 `costunit` MUST 为 `1`
- **AND** 新配置 `closemode` MUST 为 `1`
- **AND** 新配置 `costmode` MUST 为单空格
- **AND** 新配置 `advfrzflag` MUST 为 `0`
- **AND** 新配置 `remark` MUST 为 `025032` 对应业务名称

### Requirement: 识别还息计划来源的利息负债扣收明细
系统 SHALL 在 `cbs_fund_cost` 扣收明细生成阶段识别国信股票质押还息计划来源负债，并 MUST 仅当负债 `busitype` 为 `015032` 或 `025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 时启用还息计划专用处理。

#### Scenario: 计划来源负债启用专用处理
- **WHEN** 扣收明细生成阶段读取到 `busitype` 为 `015032` 或 `025032` 的 `node_debtdetail`
- **AND** 该负债 `pathid` 等于 `GPZYDEBT_INTRREPAYPLAN`
- **THEN** 系统 MUST 将该负债识别为国信批量还息计划生成的利息扣收记录
- **AND** 系统 MUST 对该记录启用还息计划专用排序和金额处理

#### Scenario: 非计划来源负债保持通用处理
- **WHEN** 扣收明细生成阶段读取到 `busitype` 为 `015032` 或 `025032` 的 `node_debtdetail`
- **AND** 该负债 `pathid` 不等于 `GPZYDEBT_INTRREPAYPLAN`
- **THEN** 系统 MUST 不启用还息计划专用处理
- **AND** 系统 MUST 保持既有通用负债扣收明细生成行为

### Requirement: 按还息计划来源标识排序扣收明细
系统 SHALL 通过 `015032` 和 `025032` 专用扣收明细 handler 对国信股票质押还息计划来源利息扣收明细按对应 `node_debtdetail.extsno` 字符串升序生成扣收优先顺序，并 MUST 不解析 `extsno` 内部字段。

#### Scenario: 计划来源扣收明细按 extsno 排序
- **WHEN** 同一扣收分组中存在多条 `busitype` 为 `015032` 或 `025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的负债明细
- **THEN** 系统 MUST 通过扣收明细 `debtsno` 回查对应 `node_debtdetail`
- **AND** 专用 handler MUST 按回查得到的 `node_debtdetail.extsno` 字符串升序排列这些扣收明细
- **AND** 系统 MUST 按排序结果生成实际扣收优先级

#### Scenario: 特殊排序不影响其他负债
- **WHEN** 同一扣收处理中存在非 `GPZYDEBT_INTRREPAYPLAN` 来源的负债明细
- **THEN** 专用 handler MUST 对这些负债调用父类排序逻辑
- **AND** 系统 MUST 不因 `015032` 或 `025032` 的还息计划特殊排序改变其他来源负债的相对扣收规则

### Requirement: 保持还息计划扣收明细冻结解冻金额语义
系统 SHALL 在生成国信股票质押还息计划来源的 `015032` 和 `025032` 扣收明细时保留计划冻结解冻语义，一次扣收 MUST 使用现有 `node_debtdetail.lastfrzamt` 待解冻金额来源，且 MUST 不修改任何二次扣收生成和金额计算逻辑。

#### Scenario: 一次扣收使用计划历史冻结金额
- **WHEN** 系统为 `busitype` 为 `015032` 或 `025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的负债生成一次扣收明细
- **THEN** 系统 MUST 使用 `node_debtdetail.lastfrzamt` 生成扣收明细待解冻金额
- **AND** 扣收完成后实际已解冻金额 MUST 写入 `node_fund_cost_detail.ufzamt`

#### Scenario: 二次扣收生成逻辑保持不变
- **WHEN** 系统为 `busitype` 为 `015032` 或 `025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的负债处理二次扣收明细
- **THEN** 系统 MUST 沿用既有二次扣收生成和金额计算逻辑
- **AND** 系统 MUST 不为该计划来源负债额外覆盖二次扣收的本次待冻结金额

### Requirement: 还息计划扣收交割流水写入冻结净额
系统 SHALL 在扣收完成生成 `node_settdetail` 和对应子表时，对 `busitype` 为 `015032` 或 `025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的扣收记录，按 `node_fund_cost_detail.frzamt - node_fund_cost_detail.ufzamt` 写入 `frzamt` 子表金额。

#### Scenario: 一次扣收生成冻结解冻净额
- **WHEN** 系统为 `busitype` 为 `015032` 或 `025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的一次扣收记录生成交割流水
- **THEN** 系统 MUST 生成对应 `node_settdetail`
- **AND** 系统 MUST 将 `frzamt` 子表金额计算为 `node_fund_cost_detail.frzamt - node_fund_cost_detail.ufzamt`

#### Scenario: 已有二次扣收记录生成冻结解冻净额
- **WHEN** 系统为 `busitype` 为 `015032` 或 `025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的已有二次扣收记录生成交割流水
- **THEN** 系统 MUST 生成对应 `node_settdetail`
- **AND** 系统 MUST 将 `frzamt` 子表金额计算为 `node_fund_cost_detail.frzamt - node_fund_cost_detail.ufzamt`

#### Scenario: 零冻结净额不生成子表
- **WHEN** `node_fund_cost_detail.frzamt - node_fund_cost_detail.ufzamt` 的结果等于 0
- **THEN** 系统 MUST 保持现有零金额处理规则
- **AND** 系统 MUST 不生成金额为 0 的 `frzamt` 子表记录
