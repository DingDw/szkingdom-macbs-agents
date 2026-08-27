## 变更背景

国信股票质押批量还息计划已经由日间适配链路滚动到日终还息计划表，但日终股票质押合约处理在违约处置自动偿还利息时仍只回写合约汇总字段，未同步处理还息计划和利息明细。需要将国信特有逻辑通过 `comm_featureconfig` 隔离，避免影响其他客户，同时保证自动偿还、重做恢复和后续扣收负债生成的数据闭环。

## 变更内容

- 在 `macbs-base` 股票质押合约处理中增加可配置的国信特色处理者，按 `cbssysid=101` 启用，默认客户保持现有逻辑。
- 国信逻辑在违约处置自动偿还利息后，按市场、合约、T 日还息计划处理 `node_gpzydebt_intrrepayplan`，并按计划周期抵扣 `node_gpzydebt_intrdetail`。
- 当 T 日存在多条还息计划时，按 `startdate` 升序处理，并校验计划周期按自然日 `enddate + 1 == next.startdate` 连续。
- 当不存在 T 日还息计划时，直接按未完成偿还的利息明细顺序抵扣。
- 完成利息明细抵扣后，回写 `node_gpzydebt.lastallrepayintrdate`；仅当最后完成日下一条利息明细确实发生偿还时，`node_gpzydebt.allrepayintrdatedayleft` 才记录该明细 `todayintr - repayintr`，否则写 0。
- 完成还息计划且存在冻结金额时，生成股票质押利息解冻交割流水及子表记录。
- 国信逻辑在股票质押合约处理完成后，基于 T 日未完成还息计划生成 `node_debtdetail` 扣收负债记录。
- 增加重做恢复规则，恢复还息计划、利息明细、当日生成的利息解冻流水和计划生成的负债流水。
- 无破坏性变更；非国信客户默认保持当前股票质押合约处理行为。

## 能力范围

### 新增能力

- `gpzy-intrrepay-contract-deal`: 覆盖国信股票质押日终合约处理中的违约处置自动偿还利息、还息计划和利息明细抵扣、处理后负债生成及重做恢复规则。

### 修改既有能力

- 无。

## 影响范围

- 受影响代码：
  - `macbs-base/lbm_pro/macbs/cbs_clear/contract_deal/contract_deal/handler/clear_gpzy.*`
  - `macbs-base/lbm_pro/macbs/cbs_clear/contract_deal/contract_deal_restore/contract_deal_restore.cpp`
  - 如新增处理者文件或 include 路径，需同步调整 `macbs-base/lbm_pro/macbs/cbs_clear/CMakeLists.txt`
- 受影响配置和脚本：
  - 新增股票质押国信处理者 classpath 对应的 `comm_featureconfig` 数据
  - 如目标基线缺少 `895005` 业务定义或记账配置，需要在 `macbs-service/database/script/patch/gauss/fs_cbs/fs_cbs_comm/2.data/` 下补充 Gauss 增量脚本
- 受影响数据表：
  - `node_gpzydebt`
  - `node_gpzydebt_intrrepayplan`
  - `node_gpzydebt_intrdetail`
  - `node_settdetail`
  - `node_settdetailsub`
  - `node_debtdetail`
- 既有 `gpzy-intrrepayplan-day-adapter` 仍作为上游能力，负责根据日间指令生成并滚动 T 日还息计划。
