## Why

国信日间股票质押批量还息指令需要在日终清算前同步到还息计划表，支持日间手工调整扣收截止日后，日终流程继续按最新计划扣收。现有 `cbs_day_clear_adapter` 的 624001 已具备按 scope 扩展日间适配业务的框架，适合在该功能号中增加受系统参数控制的股票质押批量还息计划处理。

## What Changes

- 在 624001 日间交割流水处理功能中新增 `gpzy_intrrepay` scope，用于处理股票质押批量还息计划。
- 通过 `PARAMID_DAY_CBS_ADAPTER_SCOPE` 控制新 scope 是否启用；国信 patch 将默认值更新为 `1,2,4`。
- 遵守清算七阶段模型：`Cache()` 阶段读取日间指令并缓存需要访问的 `node_gpzydebt`、`node_gpzydebt_intrrepayplan` 数据，`Clear()` 阶段生成待写计划，`Write()` 阶段批量写入。
- 使用 `kcps_stream` 直接读取日间物理库 `day_gpzydebt_command`，SQL 中直接追加 `settbody` 和 `market` 条件。
- 内存库访问优先使用 `CacheManager`；如发现 `node_gpzydebt_intrrepayplan` 缺少已生成 cache manager，需要先补齐生成文件再实现业务处理。
- 轮询日间指令，对于 `createdate=当天` 的当日新增数据，新增一笔日终的还息计划表记录 `node_gpzydebt_intrrepayplan`，`status=0` 扣收中；当日新增计划不以日间指令 `status` 作为统一过滤前提。
- 对于 `createdate!=当天` 的历史数据，匹配到 T-1 的还息计划记录，匹配键为 `sno + gpzysno + createdate`。如果指令状态为有效，则滚动 T-1 还息计划为 T 日，更新 `busidate`，并使用日间指令的 `deadline` 覆盖。
- 对进入计划生成或滚动处理的日间指令校验对应 `node_gpzydebt` 合约存在且未了结。
- 新生成计划时同步日间指令除 `status` 以外的计划要素，计划 `status` 按 `node_gpzydebt_intrrepayplan` 自身字典维护。

## Capabilities

### New Capabilities

- `gpzy-intrrepayplan-day-adapter`: 定义 624001 日间清算适配功能中股票质押批量还息指令同步、校验、滚动和生成还息计划的业务能力。

### Modified Capabilities

无。

## Impact

- 代码影响范围：`macbs-base/lbm_pro/macbs/cbs_day_clear_adapter/`，重点是 `CDaySettdetailClear` 的 scope 常量、参数解析、数据读取、处理和写入阶段。
- 数据库脚本影响范围：`macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_comm/2.data/sys_param_define.sql`，更新 `paramid=62029` 默认值。
- 数据访问：日间指令表 `day_gpzydebt_command` 使用 `kcps_stream` 读取物理库；日终 `node_gpzydebt_intrrepayplan` 和 `node_gpzydebt` 使用已生成 DAO/cache manager 访问内存库。
- 不新增功能号，不改变 624001 的单功能号执行模式。
