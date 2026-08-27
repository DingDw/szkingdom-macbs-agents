# logasset-intramt-adjustment Specification

## Purpose
TBD - created by archiving change logasset-intramt-adjust. Update Purpose after archive.
## Requirements
### Requirement: 按业务类型配置资金股份流水利息并入成交金额并清零利息
系统 SHALL 使用系统参数 `60209` 作为逗号分隔的 `busitype` 列表，用于控制生成 `node_logasset` 时需要将利息金额并入成交金额并清零利息金额的业务类型。

#### Scenario: 业务类型配置在 60209 中
- **WHEN** 系统生成 `node_logasset`，且当前 `busitype` 包含在 `60209` 中
- **THEN** 系统 MUST 将 `node_logasset.intramt` 累加到 `node_logasset.matchamt`
- **AND** 系统 MUST 将 `node_logasset.intramt` 设置为 `0`

#### Scenario: 60209 配置为空字符串
- **WHEN** 系统参数 `60209` 为空字符串
- **THEN** 系统 MUST 将其视为未配置任何 `busitype`
- **AND** 系统 MUST NOT 对任何 `busitype` 应用 `60209` 对应的利息并入成交金额并清零利息逻辑

#### Scenario: 60209 承接原 60207 控制的业务类型
- **WHEN** 原系统参数 `60207` 曾用于控制 `010201`、`010202`、`0202P1`、`0202P2`
- **THEN** 对于原先启用 `60207` 的客户，系统 MUST 将这些业务类型纳入 `60209`
- **AND** 系统 MUST NOT 再读取 `60207` 决定该处理逻辑

### Requirement: 按业务类型配置资金股份流水利息并入成交金额但保留利息
系统 SHALL 使用系统参数 `60210` 作为逗号分隔的 `busitype` 列表，用于控制生成 `node_logasset` 时需要将利息金额并入成交金额但保留利息金额的业务类型。

#### Scenario: 业务类型配置在 60210 中
- **WHEN** 系统生成 `node_logasset`，且当前 `busitype` 包含在 `60210` 中
- **THEN** 系统 MUST 将 `node_logasset.intramt` 累加到 `node_logasset.matchamt`
- **AND** 系统 MUST 保留 `node_logasset.intramt` 原值

#### Scenario: 60210 替代原保留利息宏定义行为
- **WHEN** 某个 `busitype` 原先由 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET` 控制
- **THEN** 等价处理行为 MUST 改由 `60210` 驱动
- **AND** 运行时生效逻辑 MUST NOT 依赖 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET`

#### Scenario: 60210 不受旧债券利息开关影响
- **WHEN** 某客户原先将 `25070401` 设置为 `0`
- **THEN** `60210` MUST 仍包含利息并入成交金额但保留利息的业务类型集合
- **AND** 系统 MUST 保持这些业务类型的保留利息并入成交金额逻辑可生效

### Requirement: 按业务类型配置资金股份流水仅清零利息
系统 SHALL 使用系统参数 `60211` 作为逗号分隔的 `busitype` 列表，用于控制生成 `node_logasset` 时只清零利息金额且不调整成交金额的业务类型。

#### Scenario: 业务类型配置在 60211 中
- **WHEN** 系统生成 `node_logasset`，且当前 `busitype` 包含在 `60211` 中
- **THEN** 系统 MUST 将 `node_logasset.intramt` 设置为 `0`
- **AND** 系统 MUST NOT 因 `60211` 改变 `node_logasset.matchamt`

#### Scenario: 60211 配置为空字符串
- **WHEN** 系统参数 `60211` 为空字符串
- **THEN** 系统 MUST 将其视为未配置任何仅清零利息的 `busitype`

### Requirement: 扣税业务类型不受 60211 控制
系统 SHALL 保留 `013909`、`023909`、`503909` 的现有扣税业务特殊处理，并且该处理不受系统参数 `60211` 控制。

#### Scenario: 扣税业务类型生成资金股份流水
- **WHEN** 系统为 `013909`、`023909` 或 `503909` 生成 `node_logasset`
- **THEN** 系统 MUST 将 `node_logasset.matchamt` 设置为 `node_settdetail.intrtax` 的绝对值
- **AND** 系统 MUST 将 `node_logasset.intramt` 设置为 `0`
- **AND** 系统 MUST NOT 要求这些业务类型配置在 `60211` 中

### Requirement: 移除旧资金股份流水利息处理参数
系统 SHALL 从资金股份流水利息处理控制链路中移除旧系统参数 `60207` 和 `25070401`。

#### Scenario: 运行时参数读取
- **WHEN** 系统判断 `node_logasset.matchamt` 和 `node_logasset.intramt` 的特殊处理逻辑
- **THEN** 系统 MUST NOT 读取 `60207`
- **AND** 系统 MUST NOT 读取 `25070401`
- **AND** 系统 MUST 使用 `60209`、`60210`、`60211` 控制可配置处理逻辑

#### Scenario: 增量脚本参数定义
- **WHEN** 标准版和客户版 Gauss 增量参数脚本完成调整
- **THEN** 脚本 MUST 定义 `60209`、`60210`、`60211`
- **AND** 脚本 MUST 移除 `60207`、`25070401` 的定义及相关默认值覆盖

### Requirement: 保持标准版及客户版最终参数行为一致
系统 SHALL 基于 `last_version/full` 脚本推导当前参数行为，并在基线全量脚本已执行、本次标准版增量 Gauss 脚本先执行、客户版增量 Gauss 脚本后执行后，保持与当前逻辑等价的最终参数行为。

#### Scenario: 标准版最终参数值
- **WHEN** 基线全量脚本已执行，并执行本次标准版增量 Gauss 脚本
- **THEN** `60209` MUST 包含固定的利息并入成交金额并清零利息业务类型集合
- **AND** `60210` MUST 包含原 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET` 对应的业务类型集合
- **AND** `60211` MUST 为空字符串

#### Scenario: 原先启用 60207 的客户最终参数值
- **WHEN** 东方财富或国投证券增量 Gauss 脚本在本次标准版增量脚本之后执行
- **THEN** `60209` MUST 包含固定集合，并追加 `010201`、`010202`、`0202P1`、`0202P2`
- **AND** `60210` MUST 与标准版 `60210` 取值一致
- **AND** `60211` MUST 为空字符串

#### Scenario: 原先关闭 25070401 的客户最终参数值
- **WHEN** 广发证券、银河证券或中信建投增量 Gauss 脚本在本次标准版增量脚本之后执行
- **THEN** `60209` MUST 为空字符串
- **AND** `60210` MUST 与标准版 `60210` 取值一致
- **AND** `60211` MUST 为空字符串

#### Scenario: 国信证券最终参数值
- **WHEN** 国信证券增量 Gauss 脚本在本次标准版增量脚本之后执行
- **THEN** `60209` MUST 为空字符串
- **AND** `60210` MUST 与标准版 `60210` 取值一致
- **AND** `60211` MUST 为 `015501,015503,025501,025503,024901,014901,014903,024903,025301,025304`
- **AND** `60211` MUST NOT 包含 `013909`、`023909`、`503909`

#### Scenario: 无相关旧参数覆盖的客户最终参数值
- **WHEN** 华兴证券、金证股份或中金财富增量 Gauss 脚本在本次标准版增量脚本之后执行
- **THEN** `60209` MUST 与标准版 `60209` 取值一致
- **AND** `60210` MUST 与标准版 `60210` 取值一致
- **AND** `60211` MUST 为空字符串

### Requirement: 配置业务类型必须按分隔符精确匹配
系统 SHALL 将 `60209`、`60210`、`60211` 中配置的业务类型按逗号分隔 token 精确匹配。

#### Scenario: 避免业务类型子串误匹配
- **WHEN** 参数中存在一个 `busitype` 文本是另一个 `busitype` 的子串
- **THEN** 系统 MUST 只匹配完整的逗号分隔 `busitype` token
- **AND** 系统 MUST NOT 因子串命中而错误应用资金股份流水利息处理逻辑

