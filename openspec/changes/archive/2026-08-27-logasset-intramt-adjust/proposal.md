## Why

`node_logasset.matchamt` 和 `intramt` 当前依赖硬编码 `busitype` 列表、旧参数 `60207`，以及债券利息开关 `25070401`。这种实现不利于审计客户差异，也导致后续新增或调整业务类型时必须改代码。

## What Changes

- 新增资金股份流水利息处理的业务类型参数化控制：
  - `60209` 控制“利息并入成交金额且清零利息”的业务类型。
  - `60210` 控制“利息并入成交金额但保留利息”的业务类型。
  - `60211` 控制“只清零利息且不调整成交金额”的业务类型。
- 删除旧参数 `60207` 和 `25070401`，并移除对应控制逻辑。
- 保留 `013909`、`023909`、`503909` 的现有扣税业务特殊处理；这三个业务不受 `60211` 控制。
- 将 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET` 的生效逻辑迁移为读取 `60210` 配置，并检查该宏的其它引用。
- 基于 `D:\szkingdom\projects\MACBS\src\last_version\macbs-service\database\script\full` 中的标准版及客户全量 Gauss 脚本推导当前最终参数行为；这些全量脚本只作为分析依据。
- 在本次提交中生成标准版及客户个性化 `patch` 增量 Gauss 脚本：
  - 标准版
  - 东方财富
  - 广发证券
  - 国投证券
  - 国信证券
  - 华兴证券
  - 金证股份
  - 银河证券
  - 中金财富
  - 中信建投
- 按“基线全量脚本已执行，本次标准版增量脚本先执行，再执行客户个性化增量脚本”的顺序，保持现有最终行为不变。
- 国信证券个性化增量脚本中，`60211` 默认值初始化为 `015501,015503,025501,025503,024901,014901,014903,024903,025301,025304`。
- **BREAKING**：资金股份流水利息处理不再通过旧参数 `60207` 和 `25070401` 控制。

## Capabilities

### New Capabilities

- `logasset-intramt-adjustment`：按 `busitype` 配置 `node_logasset.matchamt` 和 `intramt` 的利息处理行为。

### Modified Capabilities

- 无。

## Impact

- 代码影响：
  - `macbs-base/library/macbs/comm/logasset_creator.h`
  - `macbs-base/library/macbs/include/macbs_dict.h`
  - `macbs-base/library/macbs/include/macbs_busitypes.h`
  - 搜索并处理 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET`、`PARAMID_LOGASSET_MATCHAMT_CONTAIN_INTRAMT`、`PARAMID_LOGASSET_BONDINTR` 的其它引用。
- 数据库脚本影响：
  - `macbs-service/database/script/patch/gauss` 标准版增量 Gauss 脚本。
  - `macbs-service/database/script/patch/<客户>/gauss` 下 9 个客户目录的增量 Gauss 脚本。
  - 不修改 `macbs-service/database/script/full` 下的全量脚本。
- 运行时影响：
  - `node_logasset.matchamt/intramt` 的处理由配置的 `busitype` 列表控制。
  - `013909/023909/503909` 扣税业务逻辑保持独立。
