## Why

国信股票质押批量还息计划生成的利息负债在资金扣收后，目前只完成负债扣收和交割流水处理，未将扣收结果回写到还息计划 `node_gpzydebt_intrrepayplan` 与利息明细 `node_gpzydebt_intrdetail`，会导致计划状态、已还金额和后续负债生成依据与实际扣收结果不一致。

该需求需要在扣收后股票质押处理阶段补齐回写闭环，并继续通过 `comm_featureconfig` 隔离国信个性化逻辑，避免影响非国信客户和普通股票质押利息负债。

## What Changes

- 在扣收后股票质押处理逻辑中识别 `busitype in ('015032','025032')` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的负债流水。
- 处理**所有**的计划来源利息负债，未扣收或扣收金额为 0 的流水当作未能扣收处理，如有需要，要更新还息计划表状态
- 根据负债流水 `extsno` 中的 `createdate#sno` 定位对应 `node_gpzydebt_intrrepayplan` 记录。
- 按 `gpzy-intrrepay-contract-deal` 已实现的国信还息计划/利息明细抵扣规则，更新计划 `repayintr`、`otherrepayintr`、`status`、`settdate`，更新利息明细 `repayintr`、`repayflag`、`archivedate`，并刷新合约利息完成信息；其中 `allrepayintrdatedayleft` 仅在最后完成日下一条明细确实发生偿还时记录剩余利息，否则写 0。
- 通过 `comm_featureconfig` 复用现有国信股票质押还息计划 Feature 配置；抽取公共回写方法，避免合约处理和扣收后处理重复实现偿还分配算法。

## Capabilities

### New Capabilities
- `gpzy-after-fund-cost-intr-repay-writeback`: 定义国信股票质押还息计划来源利息负债在扣收后回写还息计划、利息明细、主合约利息完成信息及恢复重做规则。

### Modified Capabilities

## Impact

- 影响代码：`macbs-base/lbm_pro/macbs/cbs_after_fund_cost/afterfundcost/handler/after_fund_cost_gpzy_handler.cpp` 及其头文件/辅助 Feature 类落点。
- 复用/调整代码：`macbs-base/lbm_pro/macbs/cbs_clear/contract_deal/contract_deal/handler/clear_gpzy_feature.*` 中国信还息计划分配与利息明细抵扣逻辑，必要时抽取到公共 helper。
- 配置：检查并复用现有 `comm_featureconfig` 中 `gpzy-intrrepay-contract-deal` 的国信个性化 Feature；若无法复用，则新增最小范围的扣收后处理 Feature 配置。
- 数据：更新 `node_gpzydebt_intrrepayplan`、`node_gpzydebt_intrdetail`，并可能更新 `node_gpzydebt` 利息完成汇总字段。
- 不引入新外部依赖，不改变非国信客户及非 `GPZYDEBT_INTRREPAYPLAN` 来源负债的既有扣收后处理行为。
