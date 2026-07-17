## Context

国信股票质押批量还息计划在合约处理阶段会按未完成计划生成利息负债，负债通过 node_debtdetail.busitype 为 015032 或 025032 且 pathid 为 GPZYDEBT_INTRREPAYPLAN 标识，并将 extsno 写为还息计划表的 createdate#sno。资金扣收完成后，当前扣收后股票质押处理只消费负债扣收结果参与后续合约处理，尚未把计划来源利息负债的实际扣收结果回写到 node_gpzydebt_intrrepayplan 和 node_gpzydebt_intrdetail。

既有 gpzy-intrrepay-contract-deal 已在 cbs_clear.contract_deal.clear_gpzy_feature 中实现国信还息计划、利息明细抵扣、主合约利息完成信息刷新和恢复重做逻辑，并通过 comm_featureconfig 以 @cbssysid="101" 隔离国信个性化。扣收后阶段属于 cbs_after_fund_cost，生命周期和基类不同，不能直接复用合约处理 Feature 类，但应复用业务常量和利息明细抵扣算法，避免复制分配规则。

本变更需要在日终扣收后股票质押处理中补齐回写闭环，并同步维护恢复重做和错误码配置，确保重复清算不重复累计计划偿还金额。

## Goals / Non-Goals

**Goals:**

- 识别 busitype 为 015032 或 025032 且 pathid 为 GPZYDEBT_INTRREPAYPLAN 的所有计划来源利息负债；即使 paidamt 为 0，也需要定位对应还息计划并按截止日规则更新计划状态。
- 根据负债 extsno 中的 createdate#sno 定位对应单条 T 日还息计划，使用前必须 trim sno。
- 一笔负债只回写其 extsno 指定的还息计划，不跨计划顺序分配。
- 将还息计划 frzamt 覆盖为 node_debtdetail.frzamt；当 paidamt 大于 0 时，按本轮计划实际偿还金额更新 repayintr、抵扣利息明细并刷新合约利息完成信息；当 paidamt 为 0 时，不抵扣利息明细，只按截止日规则更新计划状态。
- 复用 gpzy-intrrepay-contract-deal 的利息明细抵扣和高精度尾差处理规则，更新 node_gpzydebt_intrdetail 和 node_gpzydebt 的利息完成信息。
- 新增扣收后阶段自己的 comm_featureconfig classpath，默认实现为空，国信 cbssysid=101 启用回写逻辑。
- 恢复重做时回退所有相关还息计划、利息明细和合约利息完成状态，避免重跑重复累计。
- 对正向处理找不到对应计划的负债记录错误日志并跳过，新增错误码并维护标准 patch 目录下的 base_errmsg 脚本。
- 统一复用业务常量，必要时将 GPZYDEBT_INTRREPAYPLAN、还息计划状态、利息明细偿还标志等宏定义提升到公共头文件。

**Non-Goals:**

- 扣收后阶段不生成 895005 股票质押利息解冻交割流水。
- 不改变普通股票质押利息负债和非 GPZYDEBT_INTRREPAYPLAN 来源负债的既有处理。
- 不改变资金扣收明细排序、扣收金额计算和资金扣收核心流程。
- 不新增外部依赖，不调整数据库表结构。

## Decisions

### 1. 新增扣收后股票质押 Feature，而不是直接复用合约处理 Feature 类

新增 cbs_after_fund_cost 对应 classpath，例如 cbs_after_fund_cost.afterfundcost.after_fund_cost_gpzy_feature。默认类保持空实现，国信类在 @cbssysid="101" 时启用扣收后计划回写。

理由：合约处理 Feature 依赖 CClearBase 和合约处理阶段缓存，扣收后处理依赖 CMacbsClearBase 及扣收后阶段的 node_debtdetail 扣收结果，直接复用类会造成基类、生命周期和缓存边界混乱。

备选方案是在 CAfterFundcostGpzy 中硬编码 cbssysid=101 判断。该方案实现简单，但绕过项目既有客户特性扩展机制，后续客户差异扩展成本更高，因此不采用。

### 2. 抽取或上提公共常量和算法，避免跨模块复制

将还息计划来源标识 GPZYDEBT_INTRREPAYPLAN、还息计划状态和利息明细偿还标志统一定义到可被 cbs_clear、cbs_fund_cost、cbs_after_fund_cost 共同 include 的公共位置。若属于业务字典常量，优先提升到 macbs_dict.h；若实现上需要更窄的依赖边界，可新增股票质押还息计划公共 helper 头。

利息明细抵扣、高精度尾差和主合约利息完成信息刷新规则应复用或抽成公共 helper，确保扣收后处理与 gpzy-intrrepay-contract-deal 行为一致。

备选方案是在扣收后模块复制 ApplyIntrDetails 等逻辑。该方案短期成本低，但后续两处算法容易漂移，因此不采用。

### 3. 正向处理以所有计划来源负债流水定位单条计划

扣收后处理遍历满足条件的 node_debtdetail：

- busitype 为 015032 或 025032
- pathid 为 GPZYDEBT_INTRREPAYPLAN

不再用 paidamt 大于 0 过滤计划来源负债。未扣收或扣收金额为 0 的记录仍需要参与还息计划状态判断。通过 extsno 解析 createdate#sno，对 sno trim 后，结合 matchcode 中的 gpzysno 和当前 busidate 定位 node_gpzydebt_intrrepayplan。一笔负债只更新这条计划。

理由：计划负债生成时 extsno 就是稳定的计划来源标识，扣收后回写应保持一笔扣收结果对应一条计划。paidamt 为 0 的负债也代表本轮扣收处理结果，若到截止日仍未完成，需要将计划状态更新为未完成扣收。

### 4. 还息计划回写规则按扣收结果覆盖状态

计划回写规则为：

- frzamt 覆盖为 node_debtdetail.frzamt
- 当 node_debtdetail.paidamt 大于 0 时，repayintr 累加本轮计划实际偿还金额，并按相同金额抵扣利息明细
- 当 node_debtdetail.paidamt 为 0 时，不抵扣利息明细，不推进合约利息完成日期，仅按计划截止日规则更新还息计划状态
- 如果完成偿还，则 status=1，settdate=当前 busidate
- 如果未完成偿还且 deadline=当前 busidate，则 status=2
- 如果未完成偿还且未到 deadline，保持原计划状态
- paidamt 超过计划剩余待还金额时按完成偿还处理

计划本轮偿还金额和利息明细尾差处理与 gpzy-intrrepay-contract-deal 保持一致，避免超额或高精度差异导致计划与明细状态不一致。

### 5. 正向找不到计划记录错误日志并跳过

当任一计划来源负债无法解析 extsno 或无法定位对应还息计划时，不中止整个扣收后流程，而是记录错误日志并跳过该条负债。需要新增错误码，并在标准 patch 目录维护 base_errmsg 数据脚本。

理由：正向处理阶段缺失计划是异常数据，但跳过可以避免单条异常阻断其他客户或其他计划的扣收后处理。通过错误码日志保留排查线索。

### 6. 恢复重做必须回退所有相关计划、利息明细和合约状态

扣收后恢复阶段需要回退所有相关还息计划、利息明细和合约利息完成信息，而不是只回退本次实际扣收到金额的负债对应计划。

还息计划恢复规则：

- status 回退为 0
- repayintr 回退为 T-1 对应还息计划的 repayintr 加 T 日计划的 otherrepayintr
- frzamt 回退为对应 node_debtdetail.lastfrzamt
- settdate 置为 0
- 理论上恢复时应能找到对应负债；找不到时直接报错

利息明细恢复规则：使用 busidate=当前 busidate 且 debtdealpoint=1 的对应合约中的 lastallrepayintrdate 和 allrepayintrdatedayleft，按 gpzy-intrrepay-contract-deal 的恢复赋值逻辑回退明细。

理由：正向处理会更新计划、明细和主合约，恢复重做若不完整回退，会导致重复清算后 repayintr、repayflag 和合约完成日期重复推进。

### 7. 写库仍遵守七阶段模型

新增逻辑在 Cache 阶段通过 CacheManager 加载 node_debtdetail、node_gpzydebt_intrrepayplan、node_gpzydebt_intrdetail 和必要的 node_gpzydebt 数据；Clear 阶段只处理缓存数据；Write 阶段统一 BatchUpdate 落库。

after_fund_cost_gpzy_handler.cpp 当前已对 node_gpzydebt_intrdetail 执行 BatchInsert，本变更需要补充 BatchUpdate；同时新增 node_gpzydebt_intrrepayplan 的 BatchUpdate。

## Risks / Trade-offs

- [风险] 公共常量继续散落在多个模块，后续 pathid 或状态值修改时出现不一致。→ 将业务常量提升到公共头或公共 helper，已有调用点同步改用公共定义。
- [风险] extsno 中的 sno 因格式宽度填充导致查不到计划。→ 解析后必须 trim sno，并对解析或定位失败记录新增错误码日志。
- [风险] 正向处理找不到计划时跳过，可能造成该笔扣收结果未回写计划。→ 通过明确错误码和业务日志暴露问题，便于数据订正；其他计划不受单条异常影响。
- [风险] paidamt 为 0 的负债未处理会遗漏截止日未完成状态。→ 正向处理遍历所有计划来源负债，不以 paidamt 大于 0 作为过滤条件。
- [风险] 恢复重做未覆盖 frzamt 或 settdate，导致计划状态与金额残留。→ 恢复时按规则回退 repayintr、frzamt、status 和 settdate，找不到恢复依赖数据时报错。
- [风险] 利息明细抵扣算法与合约处理算法漂移。→ 抽取公共 helper 或最小化复用现有算法，扣收后入口只负责指定计划定位和计划字段差异化更新。
- [风险] 新增 comm_featureconfig 缺失时国信回写不生效。→ 在标准 patch 脚本中新增默认和国信两条配置，并在交付说明中标明脚本执行顺序。

## Migration Plan

1. 新增或调整公共宏定义，替换现有模块中重复的还息计划来源 pathid 和状态常量。
2. 新增扣收后股票质押 Feature 类及注册 classpath，默认实现为空，国信实现执行计划回写和恢复回退。
3. 在 CAfterFundcostGpzy 的 Cache、Clear、Write 和 Restore 入口挂接 Feature 调用，保持七阶段处理顺序。
4. 新增标准 patch SQL：
   - comm_featureconfig 新增扣收后 Feature 默认和国信配置。
   - base_errmsg 新增计划定位失败等错误码。
5. 如实现涉及 full 基线同步，按项目交付要求将配置同步到 full 脚本。
6. 回滚时移除新增 Feature 配置或切回默认空实现，扣收后阶段将不再执行国信计划回写。

## Open Questions

暂无业务规则待确认。实现时需要根据现有错误码区间选择未占用错误码，并确认公共宏放置位置不会引入循环依赖。
