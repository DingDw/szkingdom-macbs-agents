## Context

日终数据汇总任务 `627009`（`DoDataSummary`）通过 `CSumAssetUncome101` 生成 `node_assetuncome` 资产缺失补偿明细，执行阶段为：

- `Cache()`：加载周期流水、交割流水、权益信息 `comm_rightinfo`、`sh_zqye`、`sz_sjsjg`、`sz_sjsgb` 等数据。
- `Clear()`：依次执行 `GenerateDataByPeriodDetail()`、`GenerateDataBySettdetail()`、`GenerateDataByRightInfo()`。
- `Write()`：`objAssetuncomeMgr.BatchInsert(true)` 批量写入内存库。

其中 `GenerateDataByRightInfo()` 处理三类"权益信息生成补偿"数据：上海基金现金分红（`sh_zqye` 中 `qylb=HL & zqlb=JJ`，生成 `busitype=014001`）、深圳基金分红（`sz_sjsjg`，`024001`）、深 B 红利（`sz_sjsgb`，`043802`）。

上海基金现金分红当前口径：取 `sh_zqye` 红利权记录的 `ye1-ye2` 作为份额，`comm_rightinfo.rightsamt` 作为每股补偿金额，`archivedate=当前业务日期`。

问题在于：

1. 红利权记录只有一条，其 `ltlx` 表示该年分红次数，不能表达该笔红利属于流通份额还是限售份额；但限售份额的市值不会因除权下降，不应补偿。
2. 记录每天重新生成并按当天归档，跨日之间没有任何关联，无法表达"红利未到账持续补偿、到账后停止补偿"。

## Goals / Non-Goals

**Goals:**

- 上海基金分红资产补偿只按流通份额计算，排除限售份额。
- 未到账红利补偿按业务日结转：红利权记录持续存在则补偿持续，红利权记录消失（红利到账）则当天不再生成。
- 不新增表字段、不改配置、不改下游对账单/下场导出取数口径。
- 影响面限制在 `asset_uncome_handler101.h/.cpp`。

**Non-Goals:**

- 不新增 `node_assetuncome.status` 字段（已确认不采用该方案，改用业务日结转 + 归档日期表达失效）。
- 不改深圳基金分红 `024001`、深 B 红利 `043802` 的补偿口径。
- 不改 `comm_assetuncomeconfig` 的 `014001` 配置、不改归档配置、不改 `his_node_assetuncome`。
- 不改老 handler（`asset_uncome_handler.h/.cpp`）。

## Decisions

### 按业务日结转 + 下一业务日归档

每条红利权补偿记录只在当天有效：`busidate=当前业务日期`，`archivedate=GetNextBusidate()`。现有归档配置 `delete from node_assetuncome where archivedate=@busidate` 会在下一业务日删除上一业务日的记录，因此：

- 不需要新增 `status` 字段表达失效；
- 国信对账单 `xydzd_head_f280100` 仍按 `busidate=当天` 取在途权益，跨日不漏计；
- OMS 下场导出 `a01-assetuncome` 不带 `busidate` 过滤，结转期间会同时导出当天与上一业务日记录；记录主键为 `serverid+busidate+sno`，需确认客户端按主键覆盖处理（见风险项）。

备选方案是新增 `status` 字段并把 `archivedate` 置为 `20991231` 长期保留，但会导致对账单与下场数据的取数口径都需要调整，影响面大，故不采用。

### 以"上一业务日"记录作为新增/存量判定基准

匹配键：`secuid`（`sh_zqye.zqzh`）+ `stkcode`（`sh_zqye.zqdm`）+ `busitype`（`014001`）+ `remark`（`${gpnf}_${ltlx}`）。

匹配范围：`node_assetuncome.busidate = GetLastBusidate()` 且 `busitype = 014001`。

理由：

- 结转记录每天存在且只存在一天，用上一业务日判定可以稳定区分"首次出现"和"持续存在"，不受历史存量影响。
- `gpnf`（分红年份）与 `ltlx`（该年分红次数）组合可唯一标识一笔分红事件，写入 `remark` 无需新增物理字段。
- 不使用 `jzrq` 参与匹配，因为 `sh_zqye` 是单日文件，匹配只需要账户、证券、分红事件三个维度。

### 存量记录复制，不重算金额

上一业务日存在匹配记录时，复制该记录生成当天记录：

- 保持不变：`serverid`、`corpid`、`orgid`、`fundid`、`extfundunit`、`extstkholdunit`、`moneytype`、`secuid`、`orderdate`、`orderid`、`market`、`stkcode`、`matchqty`、`matchprice`、`assettype`、`dealkind`、`matchamt`、`assetamt`、`remark`、`winbusitype`、`busitype`。
- 重新赋值：`busidate=当前业务日期`、`archivedate=GetNextBusidate()`、`sno` 按当天补偿流水号规则重新生成（主键为 `serverid+busidate+sno`）。

理由：补偿金额应按红利权首次出现当天的流通份额确定，后续持仓变化（卖出、送转、限售解禁）不应改变已确认的未到账红利金额。

### 首次出现只按流通份额计算

1. 在当天 `sh_zqye` 中查找 `zqzh + zqdm + xwh` 相同、`ltlx='0'`、`zqlb='JJ'` 且 `qylb` 为空（IS NULL）的持仓记录，取其 `ye1` 作为流通份额。流通股持仓记录的 `qylb` 为空。
2. **不能只排除 `qylb='HL'`**：红利权记录自身的 `ltlx` 是分红次数，第一笔分红时可能正好等于 `'0'`；红利权记录的 `qylb='HL'`，限定 `qylb` 为空可以从数据上彻底避免把红利权记录误当作流通持仓。
3. 补偿金额：`matchqty = ye1`、`matchprice = comm_rightinfo.rightsamt`、`assetamt = round(ye1 * rightsamt, 2)`。空值判定需兼容 NULL 与空串（必要时按 `trim(qylb)=''` 处理），与 SQL `qylb IS NULL` 语义保持一致。
4. 找不到流通持仓记录或 `ye1 <= 0` 时，说明该笔红利全部来自限售份额，不生成补偿记录并写日志。
5. `assettype`、`dealkind` 仍取 `comm_assetuncomeconfig` 中 `busitype=014001, assetmethod=9` 的配置；`winbusitype` 仍按 `comm_busitypemapped` 映射；账户配对仍使用 `CAcctMatchUtil::AcctMatch`，业务类别参数保持 `013806`。

### 红利权记录消失即停止结转

当天 `sh_zqye` 中没有该红利权记录时，不生成当天记录；上一业务日记录的 `archivedate` 等于当天，归档任务会正常删除。无需额外更新操作。

### 数据加载拆分与缓存

`Cache()` 阶段：

- 内存库默认按加载分组重置后重载，`node_assetuncome` 原先未配置加载，数据汇总执行时读不到上一业务日记录。因此必须新增 `comm_memdb_load_cfg` 配置：在国信日终实际使用的分组 `00`（公募/私募/普通/自营客户清算）与 `60`（两融客户清算）中，按 `busidate = :lastbusidate and busitype = '014001'` 加载上一业务日补偿记录。
- `sh_zqye` 缓存条件由 `qylb=HL & zqlb=JJ` 调整为 `zqlb=JJ`（`zqzh` 范围不变），在过滤回调中保留两类记录：
  - 红利权记录：`qylb='HL' && zqlb='JJ'`（驱动结转）；
  - 流通持仓记录：`ltlx='0' && zqlb='JJ'` 且 `qylb` 为空（`ISNULL(qylb)`，计算首次份额）。
- 新增缓存上一业务日 `node_assetuncome`：`busidate=GetLastBusidate()`、`busitype='014001'`，构建 `secuid|stkcode|remark` → 缓存索引 的映射。
- 红利权对应证券沿用现有 `comm_stock` / `comm_stkprice` 缓存链路，流通持仓不需要额外证券/行情数据。

`Clear()` 阶段：

- 将 `GenerateDataByRightInfo()` 中 `sh_zqye` 分支拆为独立函数（建议 `GenerateFundDividendAssetUncome()`），遍历红利权记录做"复制或新建"；当日流通份额映射在 `Cache()` 缓存 `sh_zqye` 时同步构建（按 `股东代码|证券代码|指定交易单元` 建键，重复键保留首条并告警），避免 `Clear()` 再全量扫描缓存。
- 每次插入后把匹配键写入"当日已处理"集合，避免同一分红事件在文件中重复出现时重复插入。

`Write()` 阶段：保持 `BatchInsert(true)`，本需求只新增不更新，因此不引入 `BatchUpdate()`。

### 阶段与分段类不改动

由于不再对存量记录做失效更新，也没有跨日留存记录需要纳入分段，`CAssetUncomeCalcRangeHandler101` 与 `CAssetUncomeRestoreHandler101` 保持现状：

- 分段仍由当日 `sh_zqye` 红利权记录、周期流水、交割流水等驱动；
- 回滚重做时 `Restore` 仍整表 `TruncateTable()`，重做后按重做日 `sh_zqye` 与上一业务日记录重新结转。

## Risks / Trade-offs

- [Risk] 匹配依赖上一业务日记录仍存在。若归档任务在新一天清算任务之前执行，上一业务日记录已被删除，所有红利权会被判为新增并重新计算金额。→ 现状归档在日终清算之后执行，实施时需确认流程顺序。
- [Risk] 上一业务日任务未执行或失败时，会按新增重算金额。→ 属数据异常场景，日志中记录"按新增处理"便于排查。
- [Risk] 流通份额取当日持仓 `ye1`。若客户在股权登记日后卖出全部基金，当日无 `ltlx=0` 持仓，将不生成补偿，与"红利仍应到账"存在偏差。→ 已按业务确认口径执行，建议日志记录跳过原因。
- [Risk] `archivedate` 依赖 `GetNextBusidate()`，日历异常时取值错误或为 0，会破坏结转匹配。→ 由框架日历统一提供，异常应在日终前置检查暴露。
- [Risk] `remark` 承载业务键后语义从"备注(业务类型)"变为"分红事件标识"，与其它业务写入的 `" "` 不同。→ 仅 `busitype=014001` 的结转记录使用该格式，匹配时限定 `busitype` 即可避免串用。
- [Risk] 同一 `zqzh+zqdm+xwh` 出现多条 `ltlx='0'` 的 `zqlb=JJ` 记录时，份额取值不确定。→ 已确认增加 `xwh` 后业务上唯一；实现取第一条并记录告警日志。
- [Risk] 结转记录每天重新生成 `sno`，OMS 下场文件按天导出，同一分红事件在连续多天的文件中出现。→ 与现有每日资产补偿明细口径一致，属预期行为。
- [Risk] OMS 下场导出 `a01-assetuncome` 的 `datasql` 不带 `busidate` 过滤，结转期间节点库同时存在当天与上一业务日记录，下场文件会导出两天的记录。→ 记录主键为 `serverid+busidate+sno`，需确认客户端按主键覆盖（幂等）处理；若客户端按全量替换，需在导出 SQL 增加 `busidate=@busidate` 或 `archivedate>@busidate` 过滤。

## 存量数据评估与处理

### 现状数据生命周期

- 旧逻辑生成的 `busitype=014001` 记录 `archivedate = 当前业务日期`。
- 日终归档流程 `52 数据归档` 位于 `32 数据上场` 之后（`comm_flowchartinfo.pre_flowchartid` 链路为 `60 收盘 → 32 数据上场 → 52 数据归档`），即当日清算结束后执行；其配置 `delete from node_assetuncome where archivedate=@busidate` 会在当日归档时删除当日记录。
- 因此正常归档情况下，`node_assetuncome` 中不会跨日残留 `014001` 记录；历史数据只存在于归档文件（`cbs[@instid]_@busidate_@insttype_node_assetuncome.txt`）。

### 结论

1. **历史已归档数据不修复。** 每天的红利权补偿记录只在其业务日有效，已随当日归档导出并从 `node` 库删除；补偿记录用于当日在途权益/对账单与下场数据，历史账已出，且归档文件不可变。若业务坚持追溯，只能按日回滚重做整个日终流程，成本高且会影响当期对账，不建议在本需求内处理。
2. **`node` 库中的历史残留不需要数值订正，但需要一次性清理。** 若归档未执行、归档失败或未启用归档，`node` 库会残留旧口径记录（`archivedate = busidate`）。改造后的首个业务日会以 `busidate = 上一业务日` 的记录作为存量判定依据，这些残留记录会被误判为存量并复制结转，导致补偿金额继续沿用旧口径（含限售份额）。清理后首个业务日按新增口径重新计算。
3. **切换日已按旧逻辑产出当日记录时，走回滚重做。** 若部署前当日 `627009 数据汇总` 已执行，`Restore` 会清空 `node_assetuncome` 后按新逻辑重新生成，无需单独订正数值；清理脚本可在此之前执行。
4. **新的结转记录不会被清理脚本误删。** 新逻辑记录 `archivedate = 下一业务日`，恒大于 `busidate`；清理条件 `archivedate <= busidate` 只命中旧口径记录，脚本可重复执行。

### 工程脚本

- 清理 SQL：`macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_node/2.data/node_assetuncome.sql`
  - `DELETE FROM node_assetuncome WHERE busitype = '014001' AND archivedate <= busidate;`
  - 头注释包含背景、删除条件说明、执行时机、幂等性与执行前预检查 SQL。
- 执行入口：`macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_node_cleanup.sh`
  - 读取同目录 `db_config.ini`，依次对 `NODE1..NODE5`、`NODEX` 中存在的配置段执行清理 SQL；
  - 支持通过参数指定节点（如 `./fs_cbs_node_cleanup.sh NODE1 NODE2`）；
  - 日志输出到同目录 `node_cleanup.log`。
- 执行时机：部署当日、`627009 数据汇总` 任务执行前；执行前用脚本头注释中的预检查 SQL 确认残留量。

## Migration Plan

1. 发布 `macbs-base` 代码与国信 `comm_memdb_load_cfg` patch；本次无表结构变更。
2. 部署当日、`627009 数据汇总` 执行前，对 `NODE1..NODEX` 执行 `fs_cbs_node_cleanup.sh`（幂等，归档正常时删除 0 行），清理旧口径 `014001` 残留记录。
3. 若部署前当日数据汇总已按旧逻辑执行：先执行清理脚本，再对当日执行回滚重做（`Restore` 会清空 `node_assetuncome` 并按新逻辑重建），保证当日对账单与下场数据为新口径。
4. 上线当日：上一业务日的 `014001` 记录已被上一日归档删除，全部红利权按新增口径计算，符合预期。
5. 次一业务日起进入结转流程：持续存在的红利权复制上一业务日记录，红利到账的红利权当天不再生成。
6. 回滚：恢复旧逻辑即可；已经生成的结转记录 `archivedate=下一业务日`，会在次日被归档任务清理。清理脚本已删除的记录本应已归档，无需恢复。

## Open Questions

无。已确认：`busitype` 保持 `014001`；匹配增加 `xwh` 且不使用 `jzrq`；不新增 `status` 字段；沿用现有归档配置；本次只改 `asset_uncome_handler101`；历史已归档数据不修复，`node` 库旧口径残留通过一次性清理脚本处理。
