## 1. 现状确认

- [x] 1.1 确认 `node_debtdetail.extsno` 生成端已按 `createdate#sno` 写入，并确认不需要修改合约处理代码。
- [x] 1.2 确认公共 `comm_fund_cost_cfg` 中 `015032/025032` 既有配置和国信个性化 patch 目录，确定新增 patch 文件名和执行位置。
- [x] 1.3 确认 `cbs_fund_cost` 一次扣收明细生成、二次扣收明细生成、扣收处理和交割流水生成的实际代码落点。

## 2. 扣收明细来源识别

- [x] 2.1 在 `cbs_fund_cost` 模块内增加业务含义明确的计划负债判断逻辑，条件限定为 `busitype in ('015032','025032')` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'`。
- [x] 2.2 在扣收明细生成阶段通过 `node_fund_cost_detail.debtsno` 回查 `node_debtdetail.sno`，取得计划负债的 `pathid` 和 `extsno`。
- [x] 2.3 为计划负债识别和回查逻辑补充业务注释，说明该逻辑只服务国信股票质押批量还息计划负债。

## 3. 扣收明细排序和金额

- [x] 3.1 为 `015032/025032` 增加专用扣收明细 handler，并在 handler 内仅选取 `GPZYDEBT_INTRREPAYPLAN` 子集按对应 `node_debtdetail.extsno` 字符串升序重排或赋内部优先级。
- [x] 3.2 确保非 `GPZYDEBT_INTRREPAYPLAN` 来源的 `015032/025032` 负债在专用 handler 中调用父类排序逻辑，其他业务类别继续使用现有排序规则。
- [x] 3.3 确保一次扣收计划负债使用 `node_debtdetail.lastfrzamt` 生成待解冻金额，并在扣收处理后落到 `node_fund_cost_detail.ufzamt`。
- [x] 3.4 确认计划负债不修改任何二次扣收生成和金额计算逻辑。
- [x] 3.5 走查 `costmode=' '` 在计划负债路径下的金额计算行为，必要时仅对计划负债补充明确金额赋值，避免影响通用扣收。

## 4. 扣收交割流水

- [x] 4.1 在 `CreateSettdetail` 相关逻辑中增加计划负债分支，判断条件限定为 `015032/025032 + GPZYDEBT_INTRREPAYPLAN`。
- [x] 4.2 对计划负债的一次和二次扣收，按 `node_fund_cost_detail.frzamt - node_fund_cost_detail.ufzamt` 写入 `frzamt` 子表金额。
- [x] 4.3 保持现有零金额处理行为，`frzamt - ufzamt` 为 0 时不生成零金额 `node_settdetailsub`。
- [x] 4.4 确认非计划负债仍按现有 `remark` 中初始待解冻金额计算 `frzamt` 子表，避免影响限售股所得税等既有场景。

## 5. 国信个性化配置

- [x] 5.1 在 `macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_comm/2.data/` 新增 `comm_fund_cost_cfg` 个性化 patch。
- [x] 5.2 patch 使用 `delete + insert` 模式覆盖 `015032` 配置，写入 `costpriority=900000`、`costunit=1`、`closemode='1'`、`costmode=' '`、`advfrzflag='0'`、`remark='上海股票质押利息偿还'`。
- [x] 5.3 patch 使用 `delete + insert` 模式覆盖 `025032` 配置，写入 `costpriority=900000`、`costunit=1`、`closemode='1'`、`costmode=' '`、`advfrzflag='0'`、`remark='深圳股票质押利息偿还'`。
- [x] 5.4 检查 patch 路径、数据库类型、清算场景和库名均为国信、Gauss、日终 `fs_cbs`、`fs_cbs_comm`。

## 6. 规格和验证

- [x] 6.1 校验 `gpzy-intrrepay-fund-cost` spec 覆盖配置、来源识别、排序、一次金额语义、二次扣收不改动约束和交割流水冻结净额。
- [x] 6.2 校验 `gpzy-intrrepay-contract-deal` spec 固化 `extsno=createdate#sno` 和 `pathid='GPZYDEBT_INTRREPAYPLAN'`。
- [x] 6.3 使用 `openspec status --change gpzy-intrrepay-fund-cost-adjust` 确认 OpenSpec 工件完整。
- [x] 6.4 如进入实现阶段，优先执行静态代码走查和定向编译检查；未明确要求时不执行全量构建或数据库脚本。
