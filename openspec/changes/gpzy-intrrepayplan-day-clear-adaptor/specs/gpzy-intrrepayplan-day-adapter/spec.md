## ADDED Requirements

### Requirement: 通过日间适配 scope 启用股票质押批量还息计划处理
624001 日间清算适配功能 SHALL 新增 `gpzy_intrrepay` scope，并 MUST 仅在 `PARAMID_DAY_CBS_ADAPTER_SCOPE` 参数包含该 scope 值时执行股票质押批量还息计划处理。

#### Scenario: 参数未启用新 scope
- **WHEN** `PARAMID_DAY_CBS_ADAPTER_SCOPE` 不包含 `gpzy_intrrepay` scope 值
- **THEN** 624001 MUST 不读取日间股票质押批量还息指令
- **AND** MUST 不生成、滚动或更新 `node_gpzydebt_intrrepayplan`

#### Scenario: 国信默认启用新 scope
- **WHEN** 国信 patch 更新 `sys_param_define.paramid=62029` 的默认值为 `1,2,4`
- **THEN** 624001 MUST 在国信环境启用征税反馈、LOF 非担保和股票质押批量还息计划处理

### Requirement: 按任务市场范围处理股票质押批量还息指令
系统 SHALL 支持按 624001 任务参数 `markets` 限定股票质押批量还息处理范围。`day_gpzydebt_command.market` 和 `node_gpzydebt_intrrepayplan.market` MUST 用于区分不同市场的指令和计划，重做删除、数据缓存、指令处理和计划生成 MUST 均纳入市场过滤。

#### Scenario: 过滤任务市场范围内的日间指令
- **WHEN** `gpzy_intrrepay` scope 已启用且 `markets` 参数配置为一个或多个逗号分隔市场
- **THEN** 系统 MUST 仅处理 `day_gpzydebt_command.market` 位于 `markets` 参数范围内的日间指令
- **AND** MUST 忽略不在任务市场范围内的日间指令

#### Scenario: 重做恢复限定市场范围
- **WHEN** 系统在 `Before()` 阶段执行股票质押批量还息计划重做恢复
- **THEN** 系统 MUST 仅删除当前业务日且 `market` 位于任务 `markets` 范围内的 `node_gpzydebt_intrrepayplan` 记录
- **AND** MUST 不删除其他市场的还息计划记录

#### Scenario: 缓存计划限定市场范围
- **WHEN** 系统在 `Cache()` 阶段缓存 T-1 日还息计划
- **THEN** 系统 MUST 仅缓存 `busidate=上一业务日` 且 `market` 位于任务 `markets` 范围内的 `node_gpzydebt_intrrepayplan` 记录

#### Scenario: 生成计划保留市场
- **WHEN** 系统根据日间指令新生成或滚动 T 日 `node_gpzydebt_intrrepayplan` 计划
- **THEN** 新计划的 `market` MUST 与对应 `day_gpzydebt_command.market` 保持一致

### Requirement: 从日间 nodex 物理库按条件读取并过滤还息指令
系统 SHALL 在 `Cache()` 阶段切换到 nodex 数据源后使用 `kcps_stream` 读取日间物理库 `day_gpzydebt_command`，读取 SQL MUST 直接追加当前结算主体 `settbody` 和任务市场 `market` 条件，读取完成后 MUST 恢复原日终数据源。系统 MUST 在代码层按上一业务日股票质押合约存在性过滤指令。系统 MUST 在后续处理阶段按 `createdate` 区分当日新增指令和历史指令，并对进入生成或滚动处理的指令使用日间指令状态判断有效性。

#### Scenario: 切换 nodex 数据源读取日间指令
- **WHEN** `gpzy_intrrepay` scope 已启用且系统读取 `day_gpzydebt_command`
- **THEN** 系统 MUST 先切换到 nodex 数据源
- **AND** MUST 使用 `kcps_stream` 读取日间物理库表
- **AND** 读取 SQL MUST 包含 `settbody = 当前 624001 运行结算主体` 条件
- **AND** 读取 SQL MUST 包含 `market` 位于任务 `markets` 范围内的条件
- **AND** 读取完成后 MUST 恢复原日终数据源，避免影响后续日终内存库缓存和处理

#### Scenario: SQL 限定当前结算主体和任务市场指令
- **WHEN** 系统读取 `day_gpzydebt_command`
- **THEN** SQL MUST 仅返回 `settbody` 等于当前 624001 运行结算主体的指令
- **AND** SQL MUST 仅返回 `market` 位于任务 `markets` 范围内的指令
- **AND** MUST NOT 在统一过滤阶段用 `createdate == 当前业务日` 或 `status='1'` 排除全部其他指令

#### Scenario: 忽略无合约指令
- **WHEN** 日间指令的 `gpzysno` 不存在于上一业务日 `node_gpzydebt` 合约缓存
- **THEN** 系统 MUST 忽略该指令
- **AND** MUST 不为该指令报错、生成或滚动 T 日还息计划

#### Scenario: 无效状态指令不进入计划处理
- **WHEN** 日间指令已通过结算主体和市场过滤
- **AND** `day_gpzydebt_command.status` 不等于 `1`
- **THEN** 系统 MUST 忽略该指令
- **AND** MUST 不为该指令新增或滚动 T 日还息计划

### Requirement: 按日间模型字段类型读取并转换日期字段
系统 SHALL 以日间模型 `macbs-service/database/pdma/split_pdm/macbs-day/tables/day-clear/day_gpzydebt_command.json` 和日间 Gauss 脚本为 `day_gpzydebt_command` 的字段依据。系统 MUST 将日间指令中的 `settdate`、`deadline`、`createdate` 按字符串字段读取，并在写入或匹配日终 `node_gpzydebt_intrrepayplan` 前显式转换为日终 `kdt_date` 日期值。

#### Scenario: 日间日期字段按字符串读取
- **WHEN** 系统使用 `kcps_stream` 读取 `day_gpzydebt_command.settdate`、`day_gpzydebt_command.deadline`、`day_gpzydebt_command.createdate`
- **THEN** 系统 MUST 按字符串读取这些字段
- **AND** MUST NOT 假定日间物理表中的这些字段为整型日期列

#### Scenario: 日终计划日期字段显式转换
- **WHEN** 系统将日间指令写入或匹配 `node_gpzydebt_intrrepayplan`
- **THEN** 系统 MUST 将日间字符串日期显式转换为日终计划表的 `kdt_date` 字段值
- **AND** 转换后的 `createdate` MUST 用于与日终计划主键字段匹配

### Requirement: 使用 CacheManager 访问日终内存库
系统 SHALL 使用 `CacheManager` 作为 `node_gpzydebt` 和 `node_gpzydebt_intrrepayplan` 的常规内存库访问层，并 MUST 在 `Cache()` 阶段缓存后供 `Clear()` 阶段处理。

#### Scenario: 缓存 T-1 合约和 T-1 还息计划
- **WHEN** `gpzy_intrrepay` scope 已启用
- **THEN** 系统 MUST 在 `Cache()` 阶段缓存上一业务日 `node_gpzydebt` 合约记录，用于合约存在性过滤和已了结状态校验
- **AND** MUST 缓存上一业务日且市场位于任务 `markets` 范围内的 `node_gpzydebt_intrrepayplan` 还息计划记录，用于历史有效指令滚动

#### Scenario: 缺少还息计划 cache manager
- **WHEN** 代码生成文件缺少 `node_gpzydebt_intrrepayplan` cache manager
- **THEN** 实现 MUST 先补齐生成文件
- **AND** MUST NOT 为常规读取和写入路径绕过到 `MemdbManager`

### Requirement: 按指令级别匹配还息计划
系统 SHALL 按 `sno + gpzysno + createdate` 作为指令级别业务匹配键处理进入计划生成或滚动处理的股票质押还息指令，并 MUST 使用 `busidate` 区分 T-1 计划和 T 日计划。该业务匹配键 MUST NOT 被描述或实现为 `day_gpzydebt_command` 的物理主键；`day_gpzydebt_command` 的物理主键为 `sno`。

#### Scenario: 使用指令级别键查找计划
- **WHEN** 系统处理一条当日新增有效指令或历史有效指令
- **THEN** 系统 MUST 使用该指令的 `sno + gpzysno + createdate` 查找对应还息计划
- **AND** MUST 不按 `gpzysno` 聚合多条指令

#### Scenario: 区分业务匹配键和日间表主键
- **WHEN** 系统说明或实现日间指令到日终还息计划的匹配关系
- **THEN** 系统 MUST 将 `sno + gpzysno + createdate` 表述为业务匹配键
- **AND** MUST 保持 `day_gpzydebt_command` 物理主键为 `sno` 的模型事实

#### Scenario: T 日计划重做恢复后生成
- **WHEN** 系统重做执行股票质押批量还息计划处理
- **THEN** 系统 MUST 先通过 `Before()` 删除当前业务日任务市场范围内的 T 日计划
- **AND** MUST 在 `Clear()` 阶段重新生成符合条件的 T 日计划

### Requirement: 过滤并校验股票质押合约有效性
系统 SHALL 在 `Cache()` 阶段使用上一业务日 `node_gpzydebt` 合约缓存过滤不存在合约的日间指令，并 SHALL 在生成或滚动 T 日还息计划前确认进入处理的指令对应合约状态不是已了结。合约不存在过滤不需要单独输出流程日志计数。

#### Scenario: 合约不存在则过滤
- **WHEN** 日间指令对应的上一业务日 `node_gpzydebt` 合约记录不存在
- **THEN** 系统 MUST 在代码层过滤并忽略该指令
- **AND** MUST 不为该指令报错、生成或滚动 T 日还息计划

#### Scenario: 合约已了结
- **WHEN** 进入处理的日间有效指令对应的上一业务日 `node_gpzydebt` 合约状态为已了结
- **THEN** 系统 MUST 报错并拒绝为该指令生成 T 日还息计划

### Requirement: 滚动历史有效指令的 T-1 还息计划生成 T 日计划
当历史日间指令 `createdate` 不等于当前业务日、指令状态有效、存在对应 T-1 还息计划时，系统 SHALL 复制 T-1 计划生成 T 日计划。滚动生成时 MUST 只修改 `busidate` 为当前业务日，并 MUST 根据日间指令更新 `deadline` 字段和保留对应市场。

#### Scenario: 存在 T-1 计划
- **WHEN** 历史有效日间指令存在对应 `busidate` 为上一业务日的还息计划
- **THEN** 系统 MUST 复制 T-1 计划生成 T 日计划
- **AND** MUST 将新计划 `busidate` 设置为当前业务日
- **AND** MUST 将新计划 `deadline` 更新为日间指令的 `deadline`
- **AND** MUST 将新计划 `market` 保持为日间指令市场
- **AND** MUST 保留 T-1 计划中除 `busidate` 和 `deadline` 外的其他字段值

#### Scenario: 历史有效指令缺少 T-1 计划
- **WHEN** 历史有效日间指令不存在对应上一业务日还息计划
- **THEN** 系统 MUST 报错并拒绝为该历史指令补造 T 日计划

#### Scenario: 历史无效指令不滚动
- **WHEN** 历史日间指令 `createdate` 不等于当前业务日
- **AND** 日间指令 `status` 不等于 `1`
- **THEN** 系统 MUST 忽略该历史指令
- **AND** MUST 不查找 T-1 计划或生成 T 日计划

### Requirement: 根据当日新增有效指令新生成 T 日还息计划
当日间指令 `createdate` 等于当前业务日、指令状态有效时，系统 SHALL 根据日间指令新生成 T 日 `node_gpzydebt_intrrepayplan` 记录。新生成计划 MUST 同步日间指令除 `status` 以外的计划要素，并 MUST 将计划状态设置为 `0` 扣收中。

#### Scenario: 当日新增有效指令生成计划
- **WHEN** 日间指令 `createdate` 等于当前业务日
- **AND** 日间指令 `status` 等于 `1`
- **THEN** 系统 MUST 根据日间指令新生成 T 日还息计划
- **AND** MUST 同步日间指令除 `status` 以外的计划要素
- **AND** MUST 将计划 `market` 设置为日间指令市场
- **AND** MUST 将计划 `status` 设置为 `0`

#### Scenario: 当日新增无效指令不生成计划
- **WHEN** 日间指令 `createdate` 等于当前业务日
- **AND** 日间指令 `status` 不等于 `1`
- **THEN** 系统 MUST 忽略该指令
- **AND** MUST 不生成 T 日还息计划

#### Scenario: 计划状态不使用日间指令状态
- **WHEN** 系统根据日间有效指令新生成 T 日还息计划
- **THEN** 系统 MUST 不将 `day_gpzydebt_command.status` 直接写入 `node_gpzydebt_intrrepayplan.status`
- **AND** MUST 按 `node_gpzydebt_intrrepayplan.status` 自身字典维护计划状态
