## Context

`gpzy-intrrepay-contract-deal` 已在国信股票质押合约处理后，根据 T 日未完成还息计划生成 `node_debtdetail` 负债记录。该类负债使用 `busitype='015032'/'025032'`，并通过 `pathid='GPZYDEBT_INTRREPAYPLAN'`、`extsno='createdate#sno'` 标识来源还息计划。

`cbs_fund_cost` 当前分两段处理资金扣收：

- `fundcostsum` 读取 `node_debtdetail`，按 `comm_fund_cost_cfg` 生成 `node_fund_cost_detail`，再按资金单元和扣收优先级排序后写入实际扣收顺序。
- `fundcostclear` 按 `node_fund_cost_detail.costpriority` 执行扣收、回写 `node_debtdetail`，并生成 `node_settdetail` 与 `node_settdetailsub`。

现有 `node_fund_cost_detail` 不保存 `pathid` 或 `extsno`，只保存 `debtsno` 作为负债明细流水号。因此计划负债的来源判断和排序必须通过 `debtsno` 回查 `node_debtdetail`，不能只看扣收明细本身。

## Goals / Non-Goals

**Goals:**

- 仅对国信还息计划来源的 `015032/025032` 负债启用特殊扣收排序和交割流水冻结金额规则。
- 保持普通股票质押 `015032/025032` 负债、`015033/025033` 罚息负债和其他客户路径不变。
- 使用国信个性化 patch 覆盖 `015032/025032` 的扣收配置，不修改公共 full 基线配置。
- 对一次、二次扣收都按同一来源识别条件处理交割流水 `frzamt` 子表金额。
- 将合约处理 spec 中计划负债 `extsno` 格式修正为 `createdate#sno`，与当前代码和资金扣收排序键一致。
- 扣收结果生成`node_settdetail`时，需要将股票质押合约的`gpzysno`写入到`node_settdetail.outvoucherno`字段

**Non-Goals:**

- 不新增或调整 `node_fund_cost_detail`、`node_debtdetail` 表结构。
- 不改变 `node_debtdetail.extsno` 的生成逻辑，只对齐 OpenSpec 契约。
- 不改变资金扣收三段式功能入口、流程配置和清算阶段模型。
- 不直接执行数据库脚本或构建验证，除非后续明确要求。

## Decisions

### 1. 使用窄条件 helper 识别计划负债

在 `cbs_fund_cost` 内定义模块局部判断逻辑，例如 `IsGpzyIntrrepayPlanDebt(busitype, pathid)`，条件为：

- `busitype` 为 `015032` 或 `025032`
- `pathid` 等于 `GPZYDEBT_INTRREPAYPLAN`

该 helper 同时用于 `fundcostsum` 排序和 `fundcostclear` 交割流水金额处理，避免两个阶段条件不一致。

替代方案是在公共业务类型常量或框架层增加判断。该方案影响面更大，而且本需求是国信股票质押还息计划的局部扣收规则，不需要提升到公共框架。

### 2. 通过 `debtsno` 回查负债来源并按 `extsno` 字符串排序

`node_fund_cost_detail` 没有 `pathid/extsno` 字段，排序时应通过 `fundcostdetail.debtsno` 回查对应 `node_debtdetail.sno`，确认其为计划负债后使用 `node_debtdetail.extsno` 字符串升序排序。

`extsno` 已由合约处理生成端补齐长度，格式为 `createdate#sno`，因此资金扣收不再解析日期和流水号，只做字符串比较。对不满足计划来源条件的 `015032/025032` 记录继续走默认排序。

推荐实现方式：

- 为 `015032/025032` 增加专用扣收明细 handler，非限定pathid的记录，调用父类的排序方法，并排在最前边。再处理限定pathid的记录，按照`node_debtdetail.extsno`字符串升序排序。

### 3. 计划负债的一次保留冻结解冻净额语义

一次扣收明细生成时，继续使用 `node_debtdetail.lastfrzamt` 作为待解冻金额来源，使扣收处理阶段在 `advfrzflag=0` 下将其转成实际已解冻金额 `node_fund_cost_detail.ufzamt`。

该设计沿用现有 `CalFundcostDetail()` 的金额计算路径，只在计划来源负债的输入金额和最终子表金额处做窄条件调整。

### 4. 计划负债不修改二次扣收逻辑

计划负债只在一次扣收金额语义、排序和交割流水冻结净额处增加窄条件处理，不修改 `GenSecondCostDetail()` 等二次扣收生成和金额计算逻辑。

### 5. 交割流水 `frzamt` 子表按实际冻结减实际解冻写入

`CreateSettdetail()` 计划负债需要写入：

`frzamt子表 = node_fund_cost_detail.frzamt - node_fund_cost_detail.ufzamt`

`node_settdetail.outvoucherno = node_debtdetail.matchcode`

该公式同时适用于一次和二次扣收，但必须限定 `015032/025032 + GPZYDEBT_INTRREPAYPLAN`。公式结果为 0 时，保持现有逻辑不生成零金额 `node_settdetailsub`。

修改代码时，使用特殊条件分支，通过`busitype+pathid`判断，不要与原有的代码耦合在一起。

### 6. 国信配置使用客户 patch 覆盖公共配置

公共 full 基线中已存在 `015032/025032` 的 `comm_fund_cost_cfg` 配置。国信个性化脚本应在 `macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_comm/2.data/` 下新增 patch，采用 `delete + insert` 模式写入：

- `costpriority=900000`
- `costunit=1`
- `costorder=' '`
- `closemode='1'`
- `costmode=' '`
- `advfrzflag='0'`
- `remark` 为对应业务名称

使用 `delete + insert` 可以避免主键冲突，也使国信部署时明确覆盖公共配置。

## Risks / Trade-offs

- 计划负债和普通股票质押利息负债共享 `015032/025032` 业务类型 → 所有特殊逻辑都必须同时检查 `pathid`，并在代码注释中说明业务来源。
- `node_fund_cost_detail` 不保存 `extsno`，排序时需要回查 `node_debtdetail` → 专用 handler 内构建 `debtsno -> extsno/pathid` 的小型映射，避免排序比较函数反复扫描缓存。
- `costmode=' '` 依赖现有扣收逻辑对空格扣收模式的处理 → 实现时需要走查 `CalFundcostDetail()` 中计划负债的实际扣收/冻结金额是否由负债记录字段驱动，必要时只在计划负债路径补充明确的金额赋值。
- 本变更必须同步固化 `gpzy-intrrepay-contract-deal` 的 `createdate#sno` 契约，避免后续实现者按旧契约解析。

## Migration Plan

1. 提交国信个性化 `comm_fund_cost_cfg` patch，使用 `delete + insert` 覆盖 `015032/025032`。
2. 在 `cbs_fund_cost` 增加计划负债识别 helper，并通过 `015032/025032` 专用扣收明细 handler 接入 `extsno` 字符串排序。
3. 在扣收交割流水生成逻辑中增加计划负债 `frzamt - ufzamt` 子表金额规则，并将计划负债的股票质押合约号写入 `node_settdetail.outvoucherno`。
4. 更新 `gpzy-intrrepay-contract-deal` spec 中 `extsno` 格式为 `createdate#sno`。
5. 回退时删除国信个性化 patch 或恢复原 `015032/025032` 配置；代码侧特殊逻辑因 `pathid` 限定，不影响普通负债。

## Open Questions

无。当前已确认 `extsno` 按字符串排序、`costmode=' '`、国信 patch 使用 `delete + insert`、零金额 `frzamt` 子表不生成。
