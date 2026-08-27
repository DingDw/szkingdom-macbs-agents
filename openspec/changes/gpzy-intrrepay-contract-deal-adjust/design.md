## 背景

`cbs_clear` 的合约处理入口是三段式功能，股票质押逻辑集中在 `contract_deal/contract_deal/handler/clear_gpzy.cpp`。当前 `CClearGpzy::AutoRepay()` 在违约处置自动偿还时按罚息、利息、本金顺序生成偿还流水，并回写 `node_gpzydebt` 和 `node_gpzydebtdetail_disposal`，但利息偿还分支没有同步更新 `node_gpzydebt_intrrepayplan` 和 `node_gpzydebt_intrdetail`。

现有项目已经通过 `comm_featureconfig` 和 `GetClearHandler()` 支持按 `cbssysid` 选择特色处理者，例如 `clear_pledge_cash` 对 `cbssysid=101` 使用国信实现。该模式适合本次需求：国信新增还息计划和利息明细处理，其他客户保持现有股票质押合约处理行为。

`node_gpzydebt_intrrepayplan`、`node_gpzydebt_intrdetail` 的 `CacheManager` 和 `MemdbManager` 已存在。两张表当前只有主键索引，按合约、市场、日期范围处理时不依赖新增 DAO 索引，优先通过 Cache 阶段过滤加载后在处理者内排序和筛选，避免扩大生成代码影响面。

## 目标和非目标

**目标：**

- 仅对国信 `cbssysid=101` 启用股票质押违约处置自动偿还利息的还息计划和利息明细处理。
- 在日终合约处理中使用 `node_gpzydebt_intrrepayplan` 的 T 日计划驱动利息抵扣，支持多计划按 `startdate` 升序处理。
- 校验多条还息计划周期按自然日连续，即下一条 `startdate` 必须等于上一条 `enddate + 1`。
- 在计划不存在时，退化为直接抵扣所有未完成偿还的利息明细。
- 在还息计划完成且存在冻结金额时生成 `895005` 股票质押利息解冻流水和对应 `node_settdetailsub`。
- 在股票质押合约处理完成后，基于 T 日未完成还息计划生成后续扣收使用的 `node_debtdetail`。
- 在恢复重做中恢复还息计划、利息明细、当日解冻流水和计划生成负债流水。

**非目标：**

- 不调整日间适配生成和滚动 `node_gpzydebt_intrrepayplan` 的既有能力。
- 不改变非国信客户的股票质押自动偿还、负债生成和恢复逻辑。
- 不改造 `node_gpzydebt_intrrepayplan`、`node_gpzydebt_intrdetail` 的表结构或生成 DAO 索引。
- 不直接执行数据库脚本或构建验证，除非后续明确要求。

## 技术决策

### 使用 `comm_featureconfig` 配置化扩展处理者

新增一个轻量的股票质押国信扩展处理者，不在 `CClearGpzy` 的公共主流程中到处嵌入 `cbssysid=101` 判断。

默认处理者提供空实现方法，用于覆盖以下扩展点：

- 缓存新增相关表。
- 在 `GPZY_AUTO_REPAY_TYPE_LX` 利息自动偿还后处理还息计划和利息明细。
- 在 `CClearGpzy::Clear()` 核心逻辑完成后，基于还息计划生成负债明细。
- 在 `CClearRestoreGpzy` 中恢复国信特有更新。

国信实现通过 `comm_featureconfig` 配置 `@cbssysid="101"` 选中。这样沿用已有 `clear_pledge_cash` 的处理者选择模式，把客户差异控制在配置和国信处理者内。

**不可以** 在 `AutoRepay()`、`Clear()` 和恢复代码中直接写 `cbssysid == 101` 判断。该方式实现更快，但会把客户逻辑散落在公共代码里，后续增加客户差异时更难维护。

### 挂接到既有股票质押生命周期

接入点如下：

- `CClearGpzy::Cache()`：通过 `CacheManager` 加载 T 日 `node_gpzydebt_intrrepayplan` 和相关 `node_gpzydebt_intrdetail`，过滤当前任务市场和结算分组范围。
- `CClearGpzy::AutoRepay()`：现有利息自动偿还流水生成和 `UpdateAfterAutoRepay()` 完成后，调用扩展处理者，并传入当前 `objGpzydebt`、本次偿还金额和市场。
- `CClearGpzy::Clear()`：既有股票质押主处理完成后、写库前，调用扩展处理者，根据未完成 T 日还息计划生成负债明细。国信逻辑需要避免与现有合约级 `CreateDebtDetail()` 生成重复的 `015032/025032` 利息负债。
- `CClearGpzy::Write()`：在现有股票质押表写入路径中，增加 `node_gpzydebt_intrrepayplan` 和 `node_gpzydebt_intrdetail` 的批量更新/写入。
- `CClearRestoreGpzy::Clear()`：在恢复路径中调用扩展处理者，恢复还息计划、利息明细，并删除当日生成的解冻流水和计划负债流水。

### 使用还息计划驱动计划内利息偿还

当 T 日存在同一 `gpzysno` 和市场的还息计划时：

1. 按 `startdate` 升序排序。
2. 校验第一条匹配计划之前不允许存在 `busidate < startdate` 且 `repayflag != '1'` 的利息明细。
3. 多条计划之间按自然日连续性校验：`next.startdate == prior.enddate + 1`。
4. 每条计划的剩余代还金额为 `intramt - repayintr`。
5. 本计划本次偿还金额为 `min(计划剩余代还金额, 剩余自动偿还金额)`。
6. 本次偿还金额同时累加到 `repayintr` 和 `otherrepayintr`。
7. 计划偿还完成后，设置 `status='1'`，并将 `settdate` 更新为 T 日。
8. 偿还完成的计划如果存在非零 `frzamt`，生成一笔 `895005` 交割流水，并生成一笔子表记录：`fieldname='frzamt'`、`fieldvalue=-frzamt`。
9. 使用计划 `startdate` 到 `enddate` 范围内的利息明细执行抵扣。

当 T 日不存在还息计划时，处理者按 `busidate` 升序处理当前合约下所有 `repayflag != '1'` 的利息明细。

### 保留利息明细的 10 位高精度

`node_gpzydebt_intrdetail.todayintr` 和 `repayintr` 是 10 位高精度金额。明细抵扣过程不应先压成 2 位金额再分摊。每条明细按 `todayintr - repayintr` 计算剩余未还利息，再使用本次可用偿还金额逐条抵扣并累加到 `repayintr`。

当某条利息明细全部偿还后(`repayintr == todayintr`)，设置 `repayflag='1'`,`archivedate=当前Busidate`。

如果还息计划已经完成: 如果高精度尾差导致周期内最后一条明细未被标记完成，则按需求强制将该周期最后一条明细的 `repayflag` 更新为 `1`,`archivedate=当前Busidate`, 但是不可以更新`repayintr`； 如果周期内最后一条明细已被标记完成，但是仍有尾差，将尾差累加到`repayintr`上。保证利息明细中的总`repayintr`等于合约中的已还利息。

明细处理完成后，回写主合约字段：

- `lastallrepayintrdate`：本次逻辑中最后一条被更新为 `repayflag='1'` 的利息明细 `busidate`。
- `allrepayintrdatedayleft`：当最后完成日下一日利息明细**确实进行了偿还**时，更新为 `todayintr - repayintr`；如果下一日利息**没有进行偿还**或者不存在下一日明细，则写 0。

### 基于未完成还息计划生成处理后负债

国信逻辑在股票质押合约处理完成后，遍历 T 日 `node_gpzydebt_intrrepayplan` 中 `status != '1'` 的记录并生成 `node_debtdetail`：

- `busitype`：深圳市场 `0` 使用 `025032`，其他市场使用 `015032`。
- `debtamt`、`unpaidamt`、`matchamt`：均为 `intramt - repayintr`。
- `lastfrzamt`：取还息计划 `frzamt`。
- `costmode`：当 `deadline == T日` 时为 `1`，否则为 `4`。
- 合约、账号、结算单元等身份字段优先复用现有 `GenDebtDetail()` 的赋值逻辑，并结合还息计划字段补齐。

生成的负债记录必须能在重做恢复中被稳定识别，例如使用业务类型、`matchcode=gpzysno`、业务日期、市场以及额外标记共同限定，避免误删其他股票质押负债。

### 按 T-1 状态恢复派生更新

恢复逻辑如下：

- `node_gpzydebt` 本身已经由当前合约逻辑滚动生成，不需要为本次国信扩展做特殊恢复。
- 对 T 日 `node_gpzydebt_intrrepayplan`，按 `sno + gpzysno + createdate` 查找 T-1 计划。存在 T-1 计划时，恢复 `repayintr`、`otherrepayintr`、`status`、`settdate`；不存在 T-1 计划时，重置 `repayintr=0`、`otherrepayintr=0`、`status='0'`，并清空 `settdate`。
- 对 `node_gpzydebt_intrdetail`，使用 T-1 `node_gpzydebt.lastallrepayintrdate` 和 `allrepayintrdatedayleft` 回退 T 日明细偿还状态：`lastallrepayintrdate`完成日之前的记录不需要处理。以后的明细全部更新为未完成，并回退`archivedate=0`，**当allrepayintrdatedayleft不为0时**,更新完成日期下一日明细的`repayintr`为`todayintr - allrepayintrdatedayleft`。
- 删除当日生成的 `895005` `node_settdetail` 及其 `node_settdetailsub`，限定 `createpoint=CREATE_POINT_HYCL`。
- 删除当日基于还息计划生成的 `015032/025032` `node_debtdetail`，限定 T 日、市场和股票质押还息计划标记(`pathid`='GPZYDEBT_INTRREPAYPLAN'),同时记录`extsno`=还息计划表的`createdate#sno`。

## 风险与权衡

- 风险：新增两张表只有主键索引，大范围扫描可能影响性能。缓解：Cache 阶段按任务市场、业务日期、结算分组尽量缩小加载范围，并在处理者内维护 `gpzysno + market` 到记录列表的内存映射。
- 风险：现有 `CreateDebtDetail()` 可能与国信计划负债重复生成 `015032/025032`。缓解：国信扩展需要抑制合约级利息负债路径，或明确只在现有路径跳过后生成计划负债。
- 风险：恢复删除 `015032/025032` 负债时可能误删其他来源负债。缓解：计划生成负债必须写入确定性标识，例如 `matchcode=gpzysno` 结合 remark 或 extsno 标记，恢复时按标记过滤。
- 风险：10 位高精度利息尾差可能导致利息明细和还息计划状态不一致。缓解：明细分摊保留 10 位精度，并在计划完成时显式处理周期最后一条明细的完成标志。
- 风险：`comm_featureconfig` 配置缺失或错误会导致处理者匹配失败。缓解：提供默认空实现和国信实现两类配置，沿用既有 classpath 优先级模式。

## 迁移计划

1. 在 `cbs_clear` 中新增代码侧默认处理者和国信处理者，并完成注册。
2. 增加默认处理者和 `@cbssysid="101"` 国信处理者的 `comm_featureconfig` 配置。
3. 仅在目标基线缺少 `895005` 业务定义或记账配置时，补充相应 Gauss 增量脚本。
4. 按正常日终清算包和数据库 patch 流程交付。
5. 回退时删除或停用国信 `comm_featureconfig` 配置；默认空实现保留，非国信路径不受影响。

## 待确认问题

- 目标交付基线是否已存在 `895005` 业务定义和记账配置；如果不存在，需要补充数据库 patch。
- 计划生成的 `node_debtdetail` 使用哪个字段作为恢复标记最稳妥，避免与现有股票质押负债明细冲突。
