## Why

国信证券新股新债缴款在日间已提前冻结资金时，现有 `1-有多少扣多少` 扣收模式仍会同时受资金余额和资金可用约束，无法保证提前冻结覆盖部分在资金余额充足时完成扣收。

需要新增一种资金扣收模式，使提前冻结覆盖部分可允许资金可用扣为负数，同时始终保证资金余额不扣为负数，并保持未提前冻结部分仍按普通“有多少扣多少”处理。

## What Changes

- 新增扣收模式 `8`：提前冻结时，有多少扣多少，可用允许为负数；否则有多少扣多少。
- 模式 `8` 按 `node_fund_cost_detail.toufzamt > 0` 判断本笔是否存在实际提前冻结金额。
- 模式 `8` 仅对扣余额金额 `costamt` 生效；冻结金额 `frzamt` 沿用模式 `1` 逻辑，不允许冻结导致可用为负。
- 模式 `8` 的提前冻结覆盖部分只受资金余额约束；超出提前冻结覆盖部分同时受资金余额和解冻后资金可用约束。
- 模式 `8` 参与二次扣收生成，但二次扣收明细生成时直接退化为 `1-有多少扣多少`。
- 对 IPO 新股新债缴款负债流水，配置为模式 `8` 时增加国信主动预冻结资格判断：仅 `cbssysid=101`、`toufzamt>0`，且能通过 `node_debtdetail.extsno -> node_logmateno.sno/paydate -> node_settdetail.applycode` 关联到当天 `899308` 且 `origin_digestid=ipoprepay` 的客户主动预冻结流水时保留模式 `8`，否则降级为 `1-有多少扣多少`。
- 公用字典 `60025` 增加模式 `8`，允许菜单选择该扣收模式。
- 国信证券增量脚本只更新四个新股新债缴款业务的 `costmode` 为 `8`，不调整预冻结业务和其他配置字段。

## Capabilities

### New Capabilities
- `fund-cost-advance-freeze-cost-mode`: 定义资金扣收模式 `8` 的业务语义、扣收金额计算、二次扣收退化、字典与国信缴款配置要求。

### Modified Capabilities

无。

## Impact

- `macbs-base`：影响 `cbs_fund_cost` 模块的资金扣收计算、IPO 缴款扣收明细生成资格判断和二次扣收明细生成逻辑。
- `macbs-base`：新增扣收模式宏定义。
- `macbs-service/database`：公用 GAUSS patch 增加 `60025` 字典值 `8`；国信证券 GAUSS patch 更新四个缴款业务配置。
- 不新增外部依赖，不改变日间清算流程。
- 暂不更新 `docs/modules/cbs_fund_cost/README.md`，待需求测试发布完成后再同步知识库。
