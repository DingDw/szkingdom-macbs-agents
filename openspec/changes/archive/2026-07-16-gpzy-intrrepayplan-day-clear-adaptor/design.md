## Context

624001 `cbs_day_clear_adapter` 当前通过 `PARAMID_DAY_CBS_ADAPTER_SCOPE` 读取逗号分隔的业务 scope，并在 `CDaySettdetailClear` 的清算七阶段中按 scope 执行日间适配逻辑。现有 scope 包括征税反馈、LOF 非担保和股权激励扣税。

国信日间股票质押批量还息业务会在日间库生成 `day_gpzydebt_command` 指令。日终清算需要根据日间指令维护 `node_gpzydebt_intrrepayplan` 还息计划：当日新增指令生成 T 日计划，历史有效指令滚动 T-1 计划并调整扣收截止日。

实现必须遵守本仓库 `AGENTS.md` 的代码修改约束：新增功能遵守清算七阶段模型，内存库访问优先使用 `CacheManager`，在 `Cache()` 阶段缓存数据，在 `Clear()` 阶段处理缓存，在 `Write()` 阶段批量写库。

## Goals / Non-Goals

**Goals:**

- 支持分市场处理
- 在 624001 中新增股票质押批量还息计划处理 scope，并保持默认不影响未配置客户。
- 通过国信 patch 将 `PARAMID_DAY_CBS_ADAPTER_SCOPE` 默认值设置为 `1,2,4`，由系统参数控制国信启用新 scope。
- 使用 `CacheManager` 作为 `node_gpzydebt` 和 `node_gpzydebt_intrrepayplan` 内存库访问层；如还息计划表缺少 cache manager，先补齐生成文件。
- 使用日间物理库 `day_gpzydebt_command` 作为输入，日间清算的该表在 nodex 物理库，需要先切换数据源读取后再恢复数据源；查询 SQL 必须直接追加 `settbody` 和 `market` 条件，代码层只继续过滤不存在的股票质押合约。
- 按 `createdate` 区分当日新增指令和历史指令：当日新增指令新增 T 日计划；历史有效指令滚动 T-1 计划。
- 按 `sno + gpzysno + createdate` 的指令级别匹配 T-1 还息计划。
- 在生成或滚动 T 日计划前校验 `node_gpzydebt` 合约未了结。

**Non-Goals:**

- 不新增 624001 以外的新功能号，不改为三段式处理。
- 不通过券商编码、客户名称或国信硬编码判断是否生效。
- 不为 `day_gpzydebt_command` 新增 phydb manager 依赖。
- 不直接用 `MemdbManager` 承担新增功能的常规内存库读取与写入路径；重做恢复删除如需使用 `MemdbManager`，必须限制在 `Before()` 阶段并写清业务原因。
- 不改变 `node_gpzydebt_intrrepayplan.status` 的字典语义和后续日终扣收流程。

## Decisions

### 使用现有 scope 参数控制启用

新增 scope 常量 `4` 表示 `gpzy_intrrepay`，继续复用 `PARAMID_DAY_CBS_ADAPTER_SCOPE`。国信通过 patch 更新 `sys_param_define.defaultvalue='1,2,4'` 启用，其他客户不配置 `4` 时不生效。

备选方案是在代码中判断国信券商标识或新建客户定制模块。该方案会把客户判断写入业务代码，和现有 scope 扩展模式不一致，因此不采用。

### 分市场支持逻辑

`day_gpzydebt_command.market`和`node_gpzydebt_intrrepayplan.market` 字段用于区分不同市场的指令，可以与任务参数中的`markets`字段进行匹配过滤，任务参数`markets`格式为多个市场逗号分隔。

重做删除/缓存数据/处理时都需要加入市场过滤。

### 使用 `kcps_stream` 读取日间指令

日间批量还息指令从物理库 `day_gpzydebt_command` 读取，该表在 nodex 库，需要先切换数据源，使用 `kcps_stream`，不通过 `phydbManager`。该读取动作放在 `Cache()` 阶段，仅在配置 `gpzy_intrrepay` scope 后执行。SQL 必须直接追加 `settbody = GetSettbody()` 和 `market in markets` 条件，避免把非当前法人或非任务市场数据读入内存后再统计过滤。

这样避免依赖日间表 DAO 生成状态，也符合日间指令读取方式约束。

读取结果再过滤掉 `gpzysno` 不存在于 `node_gpzydebt` 的记录；该过滤只决定候选指令是否参与后续处理，不单独维护生产流程日志计数。

### 使用 CacheManager 访问日终内存库

新增功能的内存库读取与写入路径使用 `CacheManager`：

- `Cache()` 阶段缓存T-1日 `node_gpzydebt` 合约数据，用于合约存在性和已了结状态校验。
- `Cache()` 阶段缓存T-1日的 `node_gpzydebt_intrrepayplan` 数据，用于 T-1 计划滚动。
- `Clear()` 阶段只处理已读取/缓存的数据，生成待插入的 `node_gpzydebt_intrrepayplan` 缓存记录。
- `Write()` 阶段统一执行批量写入。

### 遵守七阶段边界

`Before()` 仅处理重做恢复，例如删除当前业务日已经生成的还息计划，避免重做重复生成。`Cache()` 负责读取物理库和缓存内存库数据。`Clear()` 负责校验、分支判断、滚动和新建待写计划。`Write()` 负责批量写入还息计划和输出写入结果日志。阶段返回值只使用 `PHASE_NEXT` 或 `PHASE_END`，不跳回前一阶段。

### 按 createdate 分支处理指令

`createdate == GetBusidate()` 的当日新增指令, `status=1(有效的记录)`,直接新增 T 日 `node_gpzydebt_intrrepayplan` 记录，计划状态设置为 `0` 扣收中，不沿用日间指令 `status`。

`createdate != GetBusidate()` 的历史指令用于滚动已有还息计划：当指令状态为有效时，按 `sno + gpzysno + createdate + busidate=上一业务日` 查找 T-1 计划，复制生成 T 日计划，并用日间指令 `deadline` 覆盖新计划的扣收截止日；`status!=1`的无效指令不处理。

### 按指令级别处理还息计划

还息计划匹配键采用 `sno + gpzysno + createdate`，`busidate` 只区分 T-1 计划和 T 日计划。不能只按 `gpzysno` 匹配或合并，因为日间还息指令是指令级别。

## Risks / Trade-offs

- 物理库读取可能带来数据量压力。缓解方式：只在配置 scope 后执行，并在 SQL 中直接限定结算主体和任务市场范围；后续如数据量明显增长再评估更多物理库过滤条件。
- T 日计划已存在时报错会中断当前 scope 处理。缓解方式：错误信息必须包含 `sno/gpzysno/createdate/busidate`，便于定位重复数据或重做恢复问题。
- `day_gpzydebt_command.status` 与 `node_gpzydebt_intrrepayplan.status` 字典语义不同。缓解方式：代码注释明确日间指令状态只用于历史指令滚动有效性判断，当日新增计划状态固定使用还息计划字典的 `0` 扣收中。
- 新 scope 依赖 `node_gpzydebt_intrrepayplan` DAO/cache manager 已生成。缓解方式：实现前重新定位实际 DAO/cache manager 文件；如果缺少 cache manager，先补齐生成文件再实现业务逻辑。

## Migration Plan

1. 在 `cbs_day_clear_adapter` 新增 scope 常量和处理流程。
2. 在国信 patch `sys_param_define.sql` 中更新 `paramid=62029` 默认值为 `1,2,4`。
3. 部署后国信 624001 自动启用新 scope；其他客户未配置 `4` 时行为不变。
4. 如需回退，恢复国信 `paramid=62029` 默认值去掉 `4`，新 scope 即不执行。

## Open Questions

无。
