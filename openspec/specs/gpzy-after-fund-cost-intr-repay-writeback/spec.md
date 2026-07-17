# gpzy-after-fund-cost-intr-repay-writeback Specification

## Purpose

定义国信股票质押还息计划来源利息负债在扣收后回写还息计划、利息明细、主合约利息完成信息及恢复重做规则。

## Requirements

### Requirement: 扣收后识别所有还息计划来源利息负债
系统 SHALL 在扣收后股票质押处理阶段识别所有国信股票质押还息计划来源利息负债，并 MUST 仅当负债 busitype 为 015032 或 025032 且 pathid 为 GPZYDEBT_INTRREPAYPLAN 时启用扣收后还息计划回写处理。系统 MUST 不以 paidamt 是否大于 0 作为识别过滤条件。

#### Scenario: paidamt 大于 0 的计划来源负债进入回写
- **WHEN** 扣收后股票质押处理阶段读取到 busitype 为 015032 或 025032 的 node_debtdetail
- **AND** 该负债 pathid 等于 GPZYDEBT_INTRREPAYPLAN
- **AND** 该负债 paidamt 大于 0
- **THEN** 系统 MUST 将该负债纳入还息计划回写处理

#### Scenario: paidamt 等于 0 的计划来源负债进入状态处理
- **WHEN** 扣收后股票质押处理阶段读取到 busitype 为 015032 或 025032 的 node_debtdetail
- **AND** 该负债 pathid 等于 GPZYDEBT_INTRREPAYPLAN
- **AND** 该负债 paidamt 等于 0
- **THEN** 系统 MUST 将该负债纳入还息计划状态处理
- **AND** 系统 MUST 不因 paidamt 为 0 跳过该负债

#### Scenario: 非计划来源负债不触发回写
- **WHEN** 扣收后股票质押处理阶段读取到 busitype 为 015032 或 025032 的 node_debtdetail
- **AND** 该负债 pathid 不等于 GPZYDEBT_INTRREPAYPLAN
- **THEN** 系统 MUST 不执行还息计划和利息明细回写
- **AND** 系统 MUST 保持普通股票质押利息负债的既有扣收后处理行为

### Requirement: 根据负债来源标识定位单条还息计划
系统 SHALL 根据计划来源利息负债 extsno 中的 createdate#sno 定位对应 node_gpzydebt_intrrepayplan 记录，并 MUST 在使用 sno 前执行 trim。系统 MUST 将一笔负债只回写到其 extsno 指定的单条还息计划，不得跨计划分配扣收结果。

#### Scenario: 根据 createdate 和 trim 后 sno 定位计划
- **WHEN** 系统处理 pathid 为 GPZYDEBT_INTRREPAYPLAN 的计划来源负债
- **AND** 该负债 extsno 可解析为 createdate#sno
- **THEN** 系统 MUST trim 解析出的 sno
- **AND** 系统 MUST 使用当前 busidate、负债 matchcode 对应 gpzysno、createdate 和 trim 后 sno 定位 node_gpzydebt_intrrepayplan

#### Scenario: 一笔负债只更新对应计划
- **WHEN** 系统已定位计划来源负债对应的 node_gpzydebt_intrrepayplan
- **THEN** 系统 MUST 只更新该计划记录
- **AND** 系统 MUST 不将该负债的 paidamt 分配到其他还息计划

#### Scenario: 无法定位计划时记录错误并跳过
- **WHEN** 系统处理计划来源负债
- **AND** 该负债 extsno 解析失败或无法定位对应 node_gpzydebt_intrrepayplan
- **THEN** 系统 MUST 记录包含新增错误码的错误日志
- **AND** 系统 MUST 跳过该条负债的计划和利息明细回写
- **AND** 系统 MUST 继续处理其他计划来源负债

### Requirement: 扣收后回写还息计划扣收结果
系统 SHALL 在扣收后将计划来源负债扣收结果回写到对应 node_gpzydebt_intrrepayplan。系统 MUST 使用 node_debtdetail.frzamt 覆盖还息计划 frzamt；当 paidamt 大于 0 时，系统 MUST 按本轮计划实际偿还金额更新 repayintr；当 paidamt 等于 0 时，系统 MUST 不增加 repayintr。

#### Scenario: paidamt 大于 0 时更新计划金额
- **WHEN** 系统处理已定位还息计划的计划来源负债
- **AND** 该负债 paidamt 大于 0
- **THEN** 系统 MUST 将还息计划 frzamt 更新为 node_debtdetail.frzamt
- **AND** 系统 MUST 按本轮计划实际偿还金额累加还息计划 repayintr

#### Scenario: paidamt 等于 0 时只更新冻结金额和状态
- **WHEN** 系统处理已定位还息计划的计划来源负债
- **AND** 该负债 paidamt 等于 0
- **THEN** 系统 MUST 将还息计划 frzamt 更新为 node_debtdetail.frzamt
- **AND** 系统 MUST 不增加还息计划 repayintr
- **AND** 系统 MUST 不抵扣利息明细

#### Scenario: 计划完成偿还时更新完成状态
- **WHEN** 系统回写计划来源负债后还息计划已完成偿还
- **THEN** 系统 MUST 将还息计划 status 更新为 1
- **AND** 系统 MUST 将还息计划 settdate 更新为当前 busidate

#### Scenario: 截止日未完成时更新未完成扣收状态
- **WHEN** 系统回写计划来源负债后还息计划未完成偿还
- **AND** 还息计划 deadline 等于当前 busidate
- **THEN** 系统 MUST 将还息计划 status 更新为 2
- **AND** 系统 MUST 不将还息计划 settdate 更新为完成日期

#### Scenario: 未到截止日且未完成时保持原状态
- **WHEN** 系统回写计划来源负债后还息计划未完成偿还
- **AND** 还息计划 deadline 不等于当前 busidate
- **THEN** 系统 MUST 保持还息计划原状态

#### Scenario: paidamt 超过剩余待还金额时按完成处理
- **WHEN** 计划来源负债 paidamt 大于还息计划剩余待还金额
- **THEN** 系统 MUST 按计划完成偿还处理
- **AND** 系统 MUST 按既有还息计划利息明细尾差规则处理本轮偿还金额

### Requirement: 扣收后回写利息明细和主合约完成信息
系统 SHALL 在计划来源负债 paidamt 大于 0 时，按 gpzy-intrrepay-contract-deal 既有利息明细抵扣规则更新 node_gpzydebt_intrdetail，并 MUST 在产生完成利息明细时刷新 node_gpzydebt 的 lastallrepayintrdate 和 allrepayintrdatedayleft。系统 MUST 在 paidamt 等于 0 时不抵扣利息明细且不推进主合约利息完成信息。

#### Scenario: paidamt 大于 0 时抵扣计划周期利息明细
- **WHEN** 系统处理已定位还息计划的计划来源负债
- **AND** 该负债 paidamt 大于 0
- **THEN** 系统 MUST 仅处理该计划 startdate 到 enddate 周期内的 node_gpzydebt_intrdetail
- **AND** 系统 MUST 按利息明细 busidate 正序抵扣
- **AND** 系统 MUST 沿用 gpzy-intrrepay-contract-deal 的高精度尾差处理规则

#### Scenario: 利息明细完成时更新偿还标志
- **WHEN** 一条 node_gpzydebt_intrdetail 在扣收后回写中完成偿还
- **THEN** 系统 MUST 将该利息明细 repayflag 更新为 1
- **AND** 系统 MUST 将该利息明细 archivedate 更新为当前 busidate

#### Scenario: 刷新主合约利息完成信息
- **WHEN** 扣收后回写产生完成偿还的利息明细
- **THEN** 系统 MUST 将 node_gpzydebt.lastallrepayintrdate 更新为最后一条完成利息明细日期
- **AND** 系统 MUST 将 node_gpzydebt.allrepayintrdatedayleft 更新为最后完成日期后一条利息明细的剩余未还利息

#### Scenario: paidamt 等于 0 时不推进利息明细和主合约
- **WHEN** 系统处理已定位还息计划的计划来源负债
- **AND** 该负债 paidamt 等于 0
- **THEN** 系统 MUST 不更新 node_gpzydebt_intrdetail 的 repayintr、repayflag 和 archivedate
- **AND** 系统 MUST 不更新 node_gpzydebt.lastallrepayintrdate 和 node_gpzydebt.allrepayintrdatedayleft

### Requirement: 通过配置启用扣收后国信还息计划回写
系统 SHALL 通过 comm_featureconfig 为扣收后股票质押处理配置客户特性处理者，并 MUST 仅在国信 cbssysid 为 101 时执行还息计划来源负债的扣收后回写。非国信环境 MUST 保持默认空实现。

#### Scenario: 国信环境启用扣收后回写
- **WHEN** 当前清算系统号 cbssysid 等于 101
- **THEN** 系统 MUST 匹配扣收后股票质押国信特性处理者
- **AND** 系统 MUST 执行计划来源利息负债的还息计划、利息明细和主合约回写

#### Scenario: 非国信环境保持默认处理
- **WHEN** 当前清算系统号 cbssysid 不等于 101
- **THEN** 系统 MUST 使用扣收后股票质押默认特性处理者
- **AND** 系统 MUST 不执行国信还息计划来源负债回写

### Requirement: 扣收后恢复重做回退还息计划和利息明细
系统 SHALL 在扣收后股票质押恢复重做时回退所有相关还息计划、利息明细和主合约利息完成信息。系统 MUST 将还息计划 status 回退为 0、settdate 置为 0、frzamt 回退为对应 node_debtdetail.lastfrzamt，并 MUST 将 repayintr 回退为 T-1 对应还息计划 repayintr 加 T 日还息计划 otherrepayintr。

#### Scenario: 恢复还息计划扣收后更新
- **WHEN** 扣收后股票质押恢复重做处理 T 日还息计划
- **THEN** 系统 MUST 将还息计划 status 回退为 0
- **AND** 系统 MUST 将还息计划 settdate 置为 0
- **AND** 系统 MUST 将还息计划 frzamt 回退为对应 node_debtdetail.lastfrzamt
- **AND** 系统 MUST 将还息计划 repayintr 回退为 T-1 对应还息计划 repayintr 加 T 日还息计划 otherrepayintr

#### Scenario: 恢复计划找不到对应负债时报错
- **WHEN** 扣收后股票质押恢复重做回退 T 日还息计划
- **AND** 系统无法找到该计划对应的计划来源 node_debtdetail
- **THEN** 系统 MUST 报错并中止恢复处理

#### Scenario: 恢复利息明细偿还状态
- **WHEN** 扣收后股票质押恢复重做处理利息明细
- **THEN** 系统 MUST 使用 busidate 等于当前 busidate 且 debtdealpoint 等于 1 的对应 node_gpzydebt
- **AND** 系统 MUST 根据该合约 lastallrepayintrdate 和 allrepayintrdatedayleft 回退 node_gpzydebt_intrdetail
- **AND** 系统 MUST 沿用 gpzy-intrrepay-contract-deal 的利息明细恢复赋值逻辑
