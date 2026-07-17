## 1. 公共常量与复用算法

- [x] 1.1 梳理现有 GPZYDEBT_INTRREPAYPLAN、还息计划状态、利息明细偿还标志等宏定义，确定公共落点并消除重复定义
- [x] 1.2 将计划来源负债识别、extsno 解析并 trim sno、计划状态常量封装为 cbs_clear、cbs_fund_cost、cbs_after_fund_cost 可复用的公共定义或 helper
- [x] 1.3 抽取或复用 gpzy-intrrepay-contract-deal 中的利息明细抵扣、高精度尾差处理和主合约利息完成信息刷新逻辑
- [x] 1.4 更新 cbs_clear 与 cbs_fund_cost 现有调用点，统一使用公共 pathid 和识别 helper，避免继续使用模块内重复宏

## 2. 扣收后股票质押 Feature 接入

- [x] 2.1 新增扣收后股票质押 Feature 默认类和国信 101 类，注册 cbs_after_fund_cost 对应 classpath
- [x] 2.2 在 CAfterFundcostGpzy 的 Cache 阶段挂接 Feature 缓存入口，使用 CacheManager 加载计划来源 node_debtdetail、node_gpzydebt_intrrepayplan、node_gpzydebt_intrdetail 和必要的 node_gpzydebt 数据
- [x] 2.3 在 CAfterFundcostGpzy 的 Clear 阶段挂接 Feature 清算入口，确保默认实现为空且非国信不改变既有行为
- [x] 2.4 在 CAfterFundcostGpzy 的 Write 阶段挂接 Feature 写库入口，并补充 node_gpzydebt_intrrepayplan、node_gpzydebt_intrdetail、node_gpzydebt 相关 BatchUpdate 写回

## 3. 扣收后计划与明细回写

- [x] 3.1 遍历所有 busitype 为 015032/025032 且 pathid 为 GPZYDEBT_INTRREPAYPLAN 的 node_debtdetail，不以 paidamt 大于 0 过滤
- [x] 3.2 根据 node_debtdetail.extsno 的 createdate#sno 与 matchcode 对应 gpzysno 定位单条 T 日 node_gpzydebt_intrrepayplan，并对解析出的 sno 执行 trim
- [x] 3.3 对无法解析 extsno 或无法定位计划的负债记录新增错误码日志并跳过，继续处理其他负债
- [x] 3.4 使用 node_debtdetail.frzamt 覆盖还息计划 frzamt，并在 paidamt 大于 0 时按本轮计划实际偿还金额更新 repayintr
- [x] 3.5 在计划完成时更新 status=1、settdate=当前 busidate；在未完成且 deadline=当前 busidate 时更新 status=2；未到 deadline 且未完成时保持原状态
- [x] 3.6 在 paidamt 大于 0 时按计划周期抵扣 node_gpzydebt_intrdetail，并沿用既有高精度尾差处理规则
- [x] 3.7 在利息明细产生完成偿还时更新 repayflag、archivedate，并刷新 node_gpzydebt.lastallrepayintrdate 与 allrepayintrdatedayleft
- [x] 3.8 在 paidamt 等于 0 时不抵扣利息明细、不推进主合约利息完成信息，只执行计划冻结金额和状态处理

## 4. 恢复重做

- [x] 4.1 在 CAfterFundcostGpzyRestore 中挂接扣收后 Feature 恢复入口，默认实现为空，国信实现执行计划和明细回退
- [x] 4.2 恢复所有相关 T 日还息计划，将 status 回退为 0、settdate 置为 0、frzamt 回退为对应 node_debtdetail.lastfrzamt
- [x] 4.3 恢复还息计划 repayintr 为 T-1 对应计划 repayintr 加 T 日计划 otherrepayintr，找不到恢复依赖负债时直接报错
- [x] 4.4 使用 busidate=当前 busidate 且 debtdealpoint=1 的 node_gpzydebt 中 lastallrepayintrdate 和 allrepayintrdatedayleft，按既有逻辑回退 node_gpzydebt_intrdetail
- [x] 4.5 确认恢复重做后重复执行扣收后处理不会重复累计 repayintr、repayflag 或主合约完成日期

## 5. 数据库配置与错误码脚本

- [x] 5.1 在标准 patch 目录维护 comm_featureconfig，新增扣收后股票质押 Feature 默认类和国信 101 类配置
- [x] 5.2 选择未占用错误码并维护 base_errmsg 标准 patch 脚本，用于 extsno 解析失败或计划定位失败日志
- [x] 5.3 检查 full 与 patch 配置一致性要求，按项目交付规则决定是否同步 full 基线脚本
- [x] 5.4 确认新增 SQL 路径位于 fs_cbs_comm 的 2.data 配置目录，且不放入国信个性化目录

## 6. 验证

- [x] 6.1 静态检查计划来源负债 paidamt 大于 0、paidamt 等于 0、截止日未完成、非计划来源负债四类分支是否覆盖
- [x] 6.2 静态检查 extsno 中 sno trim、计划定位失败日志、恢复找不到负债时报错的异常路径
- [x] 6.3 如用户要求构建，按项目规则优先构建 cbs_after_fund_cost 相关目标或最小受影响目标
- [x] 6.4 运行可用的 OpenSpec 校验命令，确认 proposal、design、specs、tasks 均有效
