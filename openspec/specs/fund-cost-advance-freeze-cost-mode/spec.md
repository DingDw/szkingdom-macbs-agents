# fund-cost-advance-freeze-cost-mode Specification

## Purpose
TBD - created by archiving change support-guosen-ipo-pay-advance-freeze-cost-mode. Update Purpose after archive.
## Requirements
### Requirement: 扣收模式 8 基础语义
系统 SHALL 支持扣收模式 `8`，用于表达“提前冻结时，有多少扣多少，可用允许为负数；否则有多少扣多少”。模式 `8` SHALL 以本笔 `node_fund_cost_detail.toufzamt > 0` 判断是否存在实际提前冻结金额。

#### Scenario: 本笔存在提前冻结金额
- **WHEN** `node_fund_cost_detail.costmode = '8'` 且 `node_fund_cost_detail.toufzamt > 0`
- **THEN** 系统 SHALL 按提前冻结覆盖部分和普通部分分段计算已扣收金额

#### Scenario: 本笔不存在提前冻结金额
- **WHEN** `node_fund_cost_detail.costmode = '8'` 且 `node_fund_cost_detail.toufzamt <= 0`
- **THEN** 系统 SHALL 按 `1-有多少扣多少` 的语义计算已扣收金额

### Requirement: 模式 8 扣收金额计算
系统 SHALL 在模式 `8` 下保证资金余额不被扣为负数。系统 SHALL 允许提前冻结覆盖部分在资金余额充足时使资金可用为负数。系统 SHALL 要求超出提前冻结覆盖的普通扣收部分同时满足资金余额和解冻后资金可用均不为负。

#### Scenario: 提前冻结覆盖部分优先扣收
- **WHEN** 模式 `8` 明细的待解冻金额 `toufzamt` 大于 0 且资金余额足以覆盖部分待扣金额
- **THEN** 系统 SHALL 允许不超过 `toufzamt` 的待扣金额只受资金余额约束完成扣收

#### Scenario: 普通部分受余额和可用共同约束
- **WHEN** 模式 `8` 明细的待扣金额超过提前冻结覆盖部分
- **THEN** 系统 SHALL 只允许剩余普通部分在扣除提前冻结覆盖部分后的余额和解冻后可用均不为负时继续扣收

#### Scenario: 资金余额不足
- **WHEN** 模式 `8` 明细的当前滚动资金余额小于待扣金额
- **THEN** 系统 SHALL 将已扣收金额限制在不使资金余额为负的范围内

#### Scenario: 解冻后可用不足
- **WHEN** 模式 `8` 明细的解冻后可用不足以覆盖普通部分
- **THEN** 系统 SHALL 仅允许提前冻结覆盖部分使可用为负，不得让普通部分继续扩大可用负数

### Requirement: 模式 8 扣收单位裁剪
系统 SHALL 在模式 `8` 下先合计提前冻结覆盖部分和普通可用部分，再按 `costunit` 对最终已扣收金额统一裁剪。

#### Scenario: 合计后满足扣收单位
- **WHEN** 模式 `8` 明细的提前冻结覆盖部分与普通部分分别不是 `costunit` 的整数倍但合计后满足扣收单位
- **THEN** 系统 SHALL 允许按合计金额统一裁剪后形成已扣收金额

#### Scenario: 裁剪后小于提前冻结覆盖金额
- **WHEN** 模式 `8` 明细按 `costunit` 裁剪后金额小于提前冻结覆盖部分
- **THEN** 系统 SHALL 以裁剪后的金额作为已扣收金额

### Requirement: 模式 8 解冻和冻结处理
系统 SHALL 在模式 `8` 下保持 `toufzamt` 全额解冻，不得按实际已扣收金额裁剪解冻金额。模式 `8` SHALL 仅影响扣余额金额 `costamt`；冻结金额 `frzamt` SHALL 沿用 `1-有多少扣多少` 的冻结逻辑，且不得因冻结导致资金可用为负。

#### Scenario: 待解冻金额大于实际扣收金额
- **WHEN** 模式 `8` 明细的 `toufzamt` 大于实际 `costamt`
- **THEN** 系统 SHALL 仍将 `toufzamt` 全额转为已解冻金额

#### Scenario: 待冻结金额存在
- **WHEN** 模式 `8` 明细存在 `tofrzamt > 0`
- **THEN** 系统 SHALL 按模式 `1` 的冻结逻辑计算 `frzamt`

### Requirement: IPO 缴款模式 8 主动预冻结资格判断
系统 SHALL 对 IPO 新股新债缴款负债流水的模式 `8` 增加国信主动预冻结资格判断。仅当 `cbssysid=101`、本笔 `toufzamt > 0`，且可通过 `node_logmateno.sno = node_debtdetail.extsno`、`node_logmateno.paydate = node_debtdetail.busidate`、`node_settdetail.applycode = node_logmateno.orderid` 关联到当天客户主动发起的新股缴款预冻结流水时，系统 SHALL 保留模式 `8`；否则系统 SHALL 将该 IPO 缴款扣收明细降级为 `1-有多少扣多少`。

#### Scenario: 国信主动预冻结缴款保留模式 8
- **WHEN** IPO 缴款负债流水配置 `costmode = '8'`，`cbssysid = '101'`，本笔 `toufzamt > 0`
- **AND** 存在关联 `node_settdetail.busitype = '899308'` 且 `node_settdetail.origin_digestid = 'ipoprepay'`
- **AND** 关联链满足 `node_logmateno.sno = node_debtdetail.extsno`、`node_logmateno.paydate = node_debtdetail.busidate`、`node_settdetail.applycode = node_logmateno.orderid`
- **THEN** 系统 SHALL 保留该扣收明细的 `costmode = '8'`

#### Scenario: 非国信 IPO 缴款降级
- **WHEN** IPO 缴款负债流水配置 `costmode = '8'` 但 `cbssysid != '101'`
- **THEN** 系统 SHALL 将该扣收明细的 `costmode` 设置为 `1-有多少扣多少`

#### Scenario: 无主动预冻结关联流水降级
- **WHEN** IPO 缴款负债流水配置 `costmode = '8'`，但不存在关联 `899308 + ipoprepay` 的主动预冻结交割流水
- **THEN** 系统 SHALL 将该扣收明细的 `costmode` 设置为 `1-有多少扣多少`

#### Scenario: 无待解冻金额降级
- **WHEN** IPO 缴款负债流水配置 `costmode = '8'`，但本笔 `toufzamt <= 0`
- **THEN** 系统 SHALL 将该扣收明细的 `costmode` 设置为 `1-有多少扣多少`

### Requirement: 模式 8 二次扣收生成
系统 SHALL 将一次扣收模式 `8` 纳入二次扣收明细生成范围。系统 SHALL 在生成二次扣收明细时，将来源明细的模式 `8` 转换为模式 `1`，使二次扣收按普通“有多少扣多少”处理。

#### Scenario: 一次扣收模式 8 未扣完
- **WHEN** 一次扣收明细 `costmode = '8'` 且存在未扣完待扣金额
- **THEN** 系统 SHALL 生成二次扣收明细

#### Scenario: 二次扣收明细模式退化
- **WHEN** 系统从一次模式 `8` 明细生成二次扣收明细
- **THEN** 二次扣收明细的 `costmode` SHALL 设置为 `1`

### Requirement: 模式 8 字典与国信配置
系统 SHALL 在公用字典 `60025` 中提供扣收模式 `8`。国信证券交付配置 SHALL 仅将新股新债缴款业务 `012003`、`012008`、`022003`、`022008` 的 `comm_fund_cost_cfg.costmode` 更新为 `8`。

#### Scenario: 菜单可选择模式 8
- **WHEN** 用户维护资金扣收配置的扣收模式字段
- **THEN** 系统 SHALL 能够通过字典 `60025` 展示模式 `8`

#### Scenario: 国信缴款业务启用模式 8
- **WHEN** 执行国信证券增量配置脚本
- **THEN** 业务类别 `012003`、`012008`、`022003`、`022008` 的 `costmode` SHALL 更新为 `8`

#### Scenario: 国信预冻结业务不调整
- **WHEN** 执行国信证券增量配置脚本
- **THEN** 业务类别 `0120D1`、`0120D2`、`0220D1`、`0220D2` SHALL 不因本变更被更新

