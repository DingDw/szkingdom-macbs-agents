## Why

国信股票质押批量还息计划已在合约处理阶段生成 `015032/025032` 计划负债流水，但资金扣收仍按通用负债扣收规则处理，无法保证计划负债按还息计划来源流水顺序扣收，也无法在扣收生成交割流水时准确反映计划冻结解冻净额。

需要在资金扣收链路中识别 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的计划负债，只对这类国信批量还息记录增加专用扣收配置、排序和交割流水冻结金额规则，避免影响其他股票质押负债和其他客户。

## What Changes

- 在国信个性化数据库 patch 中为 `015032` 和 `025032` 增加 `comm_fund_cost_cfg` 扣收配置，使用 `delete + insert` 模式，`costpriority=900000`、`costunit=1`、`closemode=1`、`costmode=' '`、`advfrzflag=0`，备注使用对应业务名称。
- 在 `cbs_fund_cost` 扣收明细生成逻辑中，为 `015032/025032` 增加专用扣收明细 handler，识别 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的负债明细，并仅对这些记录按 `node_debtdetail.extsno` 字符串升序生成扣收优先级；非限定 `pathid` 的记录调用父类排序逻辑。一次扣收继续沿用现有 `node_debtdetail.lastfrzamt` 待解冻语义，不修改任何二次扣收生成和金额计算逻辑。
- 在扣收完成生成 `node_settdetail` 时，对 `015032/025032` 且 `pathid='GPZYDEBT_INTRREPAYPLAN'` 的记录，一次和二次扣收均按 `node_fund_cost_detail.frzamt - node_fund_cost_detail.ufzamt` 写入 `frzamt` 子表字段；结果为 0 时保持现有不生成零金额子表的行为。
- 修正既有股票质押还息计划合约处理契约中计划负债 `extsno` 格式，明确为 `createdate#sno`，并作为资金扣收排序键使用。
- 无破坏性变更；普通 `015032/025032` 股票质押负债和非国信路径保持现有扣收行为。

## Capabilities

### New Capabilities
- `gpzy-intrrepay-fund-cost`: 覆盖国信股票质押批量还息计划负债在资金扣收中的配置、扣收明细排序和扣收交割流水冻结金额规则。

### Modified Capabilities
- `gpzy-intrrepay-contract-deal`: 将计划负债 `node_debtdetail.extsno` 的要求修正为 `createdate#sno`，使合约处理输出与后续资金扣收排序契约一致。

## Impact

- 受影响代码：
  - `macbs-base/lbm_pro/macbs/cbs_fund_cost/fundcostsum/`
  - `macbs-base/lbm_pro/macbs/cbs_fund_cost/fundcostsum/handler/`
  - `macbs-base/lbm_pro/macbs/cbs_fund_cost/fundcostclear/`
  - `macbs-base/lbm_pro/macbs/cbs_clear/contract_deal/contract_deal/handler/clear_gpzy_feature.*`（仅用于对齐 `extsno` 契约）
- 受影响配置和脚本：
  - `macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_comm/2.data/`
- 受影响数据表：
  - `comm_fund_cost_cfg`
  - `node_debtdetail`
  - `node_fund_cost_detail`
  - `node_settdetail`
  - `node_settdetailsub`
