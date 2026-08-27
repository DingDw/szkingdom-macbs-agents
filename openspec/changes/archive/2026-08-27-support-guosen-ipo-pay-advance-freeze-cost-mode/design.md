## Context

`cbs_fund_cost` 的 `632006` 资金扣收处理在 `CFundcostclear::CalFundcostDetail()` 中按 `costmode` 计算已扣收金额 `costamt` 和已冻结金额 `frzamt`。现有 `1-有多少扣多少` 会先将有效余额裁剪为 `min(资金余额, 资金可用)`，因此当资金可用因日间冻结偏低时，即使本笔新股新债缴款已有提前冻结金额，也无法按资金余额完成提前冻结覆盖部分的扣收。

国信证券新股新债缴款当前需要在日间已有提前冻结时，允许提前冻结覆盖部分使资金可用扣为负数，但资金余额仍不得扣为负数；未被提前冻结覆盖的剩余扣收仍必须同时受资金余额和解冻后资金可用约束。

## Goals / Non-Goals

**Goals:**

- 新增扣收模式 `8`，作为通用扣收模式供配置使用。
- 使用 `node_fund_cost_detail.toufzamt > 0` 判断本笔是否存在实际提前冻结金额。
- 模式 `8` 只改变扣余额金额 `costamt` 的计算，不改变 `toufzamt` 全额解冻行为。
- 模式 `8` 的冻结金额 `frzamt` 沿用模式 `1` 逻辑，不允许冻结导致可用为负。
- 模式 `8` 一次扣收未扣完时参与二次扣收生成，二次扣收明细生成时直接转为模式 `1`。
- 对 IPO 新股新债缴款负债流水，配置为模式 `8` 时增加国信主动预冻结资格判断，不满足资格时在生成扣收明细阶段降级为模式 `1-有多少扣多少`。
- 公用字典增加 `60025=8`，国信证券 patch 只更新四个新股新债缴款业务的 `costmode`。

**Non-Goals:**

- 不限制模式 `8` 只能由 IPO 缴款业务使用。
- 不修改 `advfrzflag=1` 的既有全局提前解冻行为。
- 不调整 IPO 预冻结业务 `0120D1/0120D2/0220D1/0220D2`。
- 不更新 `docs/modules/cbs_fund_cost/README.md`，待需求测试发布完成后再同步知识库。
- 不修改 PDMA 字典文件，本次由需求方手工维护。

## Decisions

### 1. 使用模式值 `8`

使用 `8` 表示“提前冻结时，有多少扣多少，可用允许为负数；否则有多少扣多少”。不复用知识库中提到但源码和字典未落地的 `7`，避免与潜在历史语义冲突。

### 2. 以 `toufzamt > 0` 判断实际提前冻结

模式 `8` 不以 `advfrzflag` 判断是否存在提前冻结，而以 `node_fund_cost_detail.toufzamt > 0` 判断。本字段来自扣收明细实际待解冻金额，能够表达本笔是否有真实可释放的提前冻结金额。

`advfrzflag` 继续只控制现有解冻时点：

- `advfrzflag=1` 时沿用现有全局提前解冻行为。
- `advfrzflag=0` 时沿用当前明细计算时释放 `toufzamt` 的行为。

### 2A. IPO 缴款模式 `8` 需通过国信主动预冻结资格判断

对 IPO 新股新债缴款负债流水（`012003/012008/022003/022008`），即使业务配置为模式 `8`，仍需在生成资金扣收明细时进行资格判断。只有同时满足以下条件时才保留模式 `8`：

```text
GetCbssysid() == "101"
node_fund_cost_detail.toufzamt > 0
node_logmateno.sno = node_debtdetail.extsno
node_logmateno.paydate = node_debtdetail.busidate
node_settdetail.applycode = node_logmateno.orderid
node_settdetail.busitype = 899308
node_settdetail.origin_digestid = "ipoprepay"
```

不满足上述条件时，将当前 IPO 缴款扣收明细的 `costmode` 从 `8` 降级为 `1-有多少扣多少`。该限制只放在 IPO 缴款 handler 中，不改变模式 `8` 的通用计算能力。

### 3. 模式 `8` 的扣收金额按提前冻结覆盖部分和普通部分分段计算

计算模式 `8` 时必须保留被 `min(余额, 可用)` 裁剪前的原始滚动资金余额。设：

```text
B = 当前滚动资金余额
A = 本笔待解冻金额释放后的滚动资金可用
U = 本笔待解冻金额 toufzamt
T = 待扣金额 tocostamt
C = 扣收单位 costunit
```

当 `U > 0`：

```text
advanceLimit = min(T, U, B)
normalLimit = min(T - advanceLimit, B - advanceLimit, max(A - advanceLimit, 0))
rawCostamt = advanceLimit + normalLimit
costamt = floor(rawCostamt / C) * C
```

含义：提前冻结覆盖部分只受余额约束，可以使可用为负；普通部分只能使用提前冻结覆盖部分扣除后仍不为负的可用。

当 `U <= 0`：

```text
costamt = 模式 1 的有多少扣多少结果
```

### 4. `toufzamt` 必须全额解冻

模式 `8` 不按 `costamt` 裁剪 `toufzamt`。现有 `m_dbToufzamt -> m_dbUfzamt` 全额解冻行为必须保持，避免改变 IPO 缴款和其他业务既有解冻簿记语义。

### 5. `costunit` 按总扣收金额统一裁剪

提前冻结覆盖部分和普通可用部分先合计为 `rawCostamt`，再按 `costunit` 统一裁剪。裁剪后实际扣收金额可以小于提前冻结覆盖金额。

### 6. 二次扣收生成时将模式 `8` 转为模式 `1`

二次扣收明细没有待解冻金额，模式 `8` 应退化为普通“有多少扣多少”。为避免二次扣收处理阶段额外改造和查询歧义，生成二次扣收明细时直接将 `costmode` 从 `8` 改为 `1`，并在代码中增加明确业务注释。

二次扣收加载范围仍需包含一次扣收模式 `8` 的明细，否则模式 `8` 一次未扣完不会生成二次扣收。

### 7. 数据脚本范围

- 公用 GAUSS patch 更新 `sys_dictvalue`，新增字典 `60025` 的模式 `8`。
- 国信证券 GAUSS patch 仅 `update comm_fund_cost_cfg set costmode='8'`，业务类别限定为 `012003/012008/022003/022008`。
- 国信 patch 不改 `advfrzflag`，保持当前 `advfrzflag=0`。
- 国信 patch 不用 `delete + insert`，避免覆盖客户个性化的优先级、了结模式、备注等字段。

## Risks / Trade-offs

- [误配置普通业务为模式 `8`] → 模式 `8` 是通用机制且允许菜单配置，误配风险由业务配置管理承担；通用扣收计算不做业务类别防守。
- [国信 IPO 缴款未关联主动预冻结流水却使用模式 `8`] → IPO 缴款 handler 按 `node_debtdetail.extsno -> node_logmateno.sno/paydate -> node_settdetail.applycode` 进行资格判断，不满足时降级为模式 `1`。
- [多笔模式 `8` 导致可用负数叠加] → 这是明确允许的行为，每笔仅在自身 `toufzamt` 覆盖范围内放开可用约束。
- [全局提前解冻金额被其他明细先消耗] → `advfrzflag=1` 沿用既有机制；国信缴款配置保持 `advfrzflag=0`，降低本次需求场景风险。
- [字典公用 patch 使所有客户可见模式 `8`] → 这是菜单可配置通用机制的预期效果；实际业务启用由配置 patch 或人工配置控制。
- [暂不更新模块知识库] → 按用户确认，待测试发布完成后再同步 `docs/modules/cbs_fund_cost/README.md`。

## Migration Plan

1. 部署 `macbs-base` 代码，新增模式宏、扣收计算逻辑、IPO 缴款主动预冻结资格判断和二次扣收生成退化逻辑。
2. 执行公用 GAUSS 字典 patch，增加 `60025=8`。
3. 执行国信证券 GAUSS 配置 patch，将四个缴款业务更新为 `costmode=8`。
4. 若需回滚业务配置，可将国信四个缴款业务 `costmode` 改回 `1`；代码保留模式 `8` 不影响未配置使用的业务。

## Open Questions

无。