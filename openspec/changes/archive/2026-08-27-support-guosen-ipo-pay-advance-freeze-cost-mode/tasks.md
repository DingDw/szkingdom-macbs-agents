## 1. 扣收模式常量与一次扣收计算

- [x] 1.1 在 `macbs-base/library/macbs/include/macbs_dict.h` 新增扣收模式 `8` 的宏定义和明确业务注释
- [x] 1.2 在 `CFundcostclear::CalFundcostDetail()` 中保留被 `min(余额, 可用)` 裁剪前的原始滚动资金余额
- [x] 1.3 在 `CFundcostclear::CalFundcostDetail()` 中新增模式 `8` 的 `costamt` 计算逻辑，按 `toufzamt` 覆盖部分和普通部分分段计算后统一按 `costunit` 裁剪
- [x] 1.4 确认模式 `8` 在 `toufzamt <= 0` 时按模式 `1-有多少扣多少` 计算 `costamt`
- [x] 1.5 确认模式 `8` 不改变 `toufzamt` 全额解冻行为，且 `frzamt` 沿用模式 `1` 的冻结逻辑

## 2. 二次扣收生成调整

- [x] 2.1 在 `CFundcostsum::Cache()` 的二次扣收明细加载条件中纳入一次扣收模式 `8`
- [x] 2.2 在 `CFundcostsum::GenSecondCostDetail()` 的二次扣收生成条件中纳入一次扣收模式 `8`
- [x] 2.3 生成二次扣收明细时，将来源模式 `8` 的 `costmode` 设置为 `1`，并增加说明“模式8提前冻结额度仅一次明细有效，二次扣收退化为有多少扣多少”的业务注释

## 3. 数据库增量脚本

- [x] 3.1 在公用 GAUSS patch 的 `fs_cbs_comm/2.data/sys_dictvalue.sql` 中以先删后插方式新增 `60025=8`
- [x] 3.2 新增或维护国信证券 GAUSS patch，使用 `update` 将 `012003`、`012008`、`022003`、`022008` 的 `comm_fund_cost_cfg.costmode` 更新为 `8`
- [x] 3.3 确认国信证券 patch 不修改四个缴款业务的 `advfrzflag`、`costpriority`、`costunit`、`closemode`、`remark` 等其他字段
- [x] 3.4 确认国信证券 patch 不更新 `0120D1`、`0120D2`、`0220D1`、`0220D2` 预冻结业务

## 4. 验证与检查

- [x] 4.1 运行 `openspec validate support-guosen-ipo-pay-advance-freeze-cost-mode --strict` 校验 OpenSpec 变更
- [x] 4.2 通过代码走查或局部调试验证模式 `8` 的典型场景：无提前冻结、提前冻结覆盖不足、余额不足、可用已负、多笔叠加、`costunit` 统一裁剪
- [x] 4.3 通过代码走查确认二次扣收明细由模式 `8` 转为模式 `1`，且二次扣收处理阶段无需额外识别模式 `8`
- [x] 4.4 检查 SQL patch 路径符合公用字典和国信证券客户配置落点要求
- [x] 4.5 如用户明确要求构建，再按项目规则执行目标级构建验证 `cbs_fund_cost`

## 5. 国信 IPO 主动预冻结资格判断

- [x] 5.1 在 IPO 缴款 handler 缓存当天客户主动发起的新股缴款预冻结交割流水 `899308 + origin_digestid=ipoprepay`
- [x] 5.2 在 IPO 缴款 handler 中按 `node_debtdetail.extsno -> node_logmateno.sno/paydate -> node_settdetail.applycode` 实现模式 `8` 资格判断
- [x] 5.3 对不满足 `cbssysid=101`、`toufzamt>0` 或主动预冻结关联条件的 IPO 缴款明细，将 `costmode` 降级为 `1-有多少扣多少`
- [x] 5.4 运行 OpenSpec 严格校验并进行代码走查，确认二次扣收既有模式 `8` 退化逻辑不受影响
