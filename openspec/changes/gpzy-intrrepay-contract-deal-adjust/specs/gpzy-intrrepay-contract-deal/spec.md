## ADDED Requirements

### Requirement: 通过配置启用国信股票质押还息计划合约处理
系统 SHALL 在股票质押合约处理中通过 `comm_featureconfig` 启用国信特色处理者，并 MUST 仅在 `cbssysid=101` 时执行股票质押违约处置自动偿还利息的还息计划和利息明细处理。非国信客户 MUST 保持现有股票质押合约处理行为。

#### Scenario: 国信环境启用特色处理者
- **WHEN** 当前清算系统号 `cbssysid` 等于 `101`
- **THEN** 系统 MUST 匹配股票质押国信特色处理者
- **AND** MUST 执行还息计划、利息明细、计划负债和恢复重做的国信扩展逻辑

#### Scenario: 非国信环境保持默认行为
- **WHEN** 当前清算系统号 `cbssysid` 不等于 `101`
- **THEN** 系统 MUST 不执行国信股票质押还息计划扩展逻辑
- **AND** MUST 保持现有违约处置自动偿还和负债生成行为

### Requirement: 使用 CacheManager 缓存还息计划和利息明细
系统 SHALL 使用 `CacheManager` 作为日终内存库常规访问层，在股票质押合约处理的 Cache 阶段缓存 `node_gpzydebt_intrrepayplan` 和 `node_gpzydebt_intrdetail`，并 MUST 按任务市场范围处理数据。

#### Scenario: 缓存当前任务市场的 T 日还息计划
- **WHEN** 国信特色处理者在 Cache 阶段运行
- **THEN** 系统 MUST 缓存 `busidate=T日` 且 `market` 位于当前任务 `markets` 范围内的 `node_gpzydebt_intrrepayplan`
- **AND** 后续还息计划处理 MUST 仅使用任务市场范围内的计划记录

#### Scenario: 缓存利息明细用于偿还抵扣
- **WHEN** 国信特色处理者在 Cache 阶段运行
- **THEN** 系统 MUST 缓存股票质押利息明细 `node_gpzydebt_intrdetail`
- **AND** 后续处理 MUST 按当前自动偿还合约编号 `gpzysno` 筛选利息明细记录

### Requirement: 按 T 日还息计划处理违约处置自动偿还利息
当股票质押违约处置自动偿还产生利息偿还金额时，系统 SHALL 查找 `busidate=T日`、`gpzysno=当前自动偿还合约编号`、`market=当前合约市场` 的 `node_gpzydebt_intrrepayplan` 记录。若存在还息计划，系统 MUST 按 `startdate` 升序逐条处理。

#### Scenario: 按开始日期顺序处理多条还息计划
- **WHEN** 当前自动偿还合约在 T 日存在多条还息计划
- **THEN** 系统 MUST 按 `node_gpzydebt_intrrepayplan.startdate` 正向排序
- **AND** MUST 按排序结果依次分配本次自动偿还利息金额

#### Scenario: 更新还息计划已还金额
- **WHEN** 系统处理一条还息计划
- **THEN** 系统 MUST 将计划剩余代还金额计算为 `intramt - repayintr`
- **AND** MUST 将本计划本次偿还金额计算为 `min(计划剩余代还金额, 剩余自动偿还利息金额)`
- **AND** MUST 将本计划本次偿还金额累加到 `repayintr`
- **AND** MUST 将本计划本次偿还金额累加到 `otherrepayintr`

#### Scenario: 还息计划完成后更新状态和完成日
- **WHEN** 一条还息计划在本次处理后已经全部完成偿还
- **THEN** 系统 MUST 将 `status` 更新为 `1`
- **AND** MUST 将 `settdate` 更新为 T 日

### Requirement: 校验还息计划和历史未偿还利息明细
系统 SHALL 在按还息计划处理自动偿还利息前执行异常校验。第一条匹配还息计划之前不允许存在未完成偿还的历史利息明细；多条还息计划必须按自然日连续。

#### Scenario: 第一条计划前存在未完成利息明细时报错
- **WHEN** 第一条匹配还息计划的 `startdate` 之前存在同一合约 `busidate < startdate` 且 `repayflag != '1'` 的 `node_gpzydebt_intrdetail`
- **THEN** 系统 MUST 报错并中止当前自动偿还利息处理

#### Scenario: 多条还息计划不连续时报错
- **WHEN** 同一合约和市场存在多条 T 日还息计划
- **AND** 任意相邻两条计划不满足后一条 `startdate = 前一条 enddate + 1`
- **THEN** 系统 MUST 报错并中止当前自动偿还利息处理

### Requirement: 还息计划完成时生成利息解冻流水
当一条还息计划完成偿还且计划存在冻结金额时，系统 SHALL 生成股票质押利息解冻交割流水和对应子表记录，用于释放计划冻结金额。

#### Scenario: 完成计划存在冻结金额
- **WHEN** 还息计划本次处理后 `status` 更新为 `1`
- **AND** 该计划 `frzamt` 不为 0
- **THEN** 系统 MUST 生成一笔 `node_settdetail` 记录
- **AND** 该记录 `busitype` MUST 为 `895005`
- **AND** 该记录 `createpoint` MUST 为 `CREATE_POINT_HYCL`
- **AND** 该记录 `bookkeepingpoint` MUST 为 `BOOKKEEPINGPOINT_TY`

#### Scenario: 生成冻结金额子表记录
- **WHEN** 系统生成 `895005` 股票质押利息解冻流水
- **THEN** 系统 MUST 同步生成对应 `node_settdetailsub` 记录
- **AND** 子表记录 `fieldname` MUST 为 `frzamt`
- **AND** 子表记录 `fieldvalue` MUST 为 `-frzamt`

### Requirement: 按利息明细高精度抵扣自动偿还利息
系统 SHALL 按 `node_gpzydebt_intrdetail.busidate` 升序使用本次偿还金额抵扣利息明细。系统 MUST 以 10 位高精度金额处理 `todayintr` 和 `repayintr`，并在利息明细全部完成抵扣后更新 `repayflag='1'`。

#### Scenario: 按日期顺序抵扣计划周期内利息明细
- **WHEN** 系统处理一条还息计划的本次偿还金额
- **THEN** 系统 MUST 仅处理该计划 `startdate` 到 `enddate` 周期内的利息明细
- **AND** MUST 按 `busidate` 正向排序依次抵扣
- **AND** 每条明细的剩余待还利息 MUST 按 `todayintr - repayintr` 计算

#### Scenario: 利息明细全部抵扣后标记完成
- **WHEN** 一条利息明细的 `todayintr - repayintr` 在本次处理后已经全部抵扣
- **THEN** 系统 MUST 将本次抵扣金额累加到该明细 `repayintr`
- **AND** MUST 将该明细 `repayflag` 更新为 `1`, `archivedate`更新为当前`busidate`

#### Scenario: 计划完成时处理高精度尾差
- **WHEN** 一条还息计划已经完成偿还
- **AND** 该计划周期内最后一条利息明细因高精度尾差未被标记为完成
- **THEN** 系统 MUST 将该周期内最后一条利息明细的 `repayflag` 更新为 `1`, `archivedate`更新为当前`busidate`

#### Scenario: 计划完成时处理高精度尾差
- **WHEN** 一条还息计划已经完成偿还
- **AND** 该计划周期内最后一条利息明细已被标记为完成
- **AND** 仍然有未完全分配完的尾差
- **THEN** 系统 MUST 将尾差累计到该周期内最后一条利息明细的 `repayintr` 

### Requirement: 无还息计划时直接抵扣未完成利息明细
当当前自动偿还合约在 T 日不存在还息计划时，系统 SHALL 查询该合约所有 `repayflag != '1'` 的利息明细，并直接按利息明细抵扣规则处理本次自动偿还利息金额。

#### Scenario: 不存在 T 日还息计划
- **WHEN** 当前自动偿还合约在 T 日不存在同市场还息计划
- **THEN** 系统 MUST 查询当前合约全部 `repayflag != '1'` 的 `node_gpzydebt_intrdetail`
- **AND** MUST 按 `busidate` 正向排序执行利息明细抵扣

### Requirement: 回写股票质押合约利息偿还完成信息
系统 SHALL 在完成 `node_gpzydebt_intrrepayplan` 和 `node_gpzydebt_intrdetail` 更新后，回写 T 日 `node_gpzydebt` 的最后完成利息偿还日；仅当最后完成日下一条利息明细确实发生偿还时，系统 SHALL 将下一日剩余利息写入 `allrepayintrdatedayleft`。

#### Scenario: 存在本次完成的利息明细
- **WHEN** 本次处理存在被更新为 `repayflag='1'` 的利息明细
- **THEN** 系统 MUST 将 `node_gpzydebt.lastallrepayintrdate` 更新为最后一条完成利息明细的 `busidate`

#### Scenario: 最后完成日下一条利息明细发生偿还
- **WHEN** 最后一条完成利息明细之后存在下一条同合约利息明细
- **AND** 该下一条利息明细 `repayintr` 大于 0
- **THEN** 系统 MUST 将 `node_gpzydebt.allrepayintrdatedayleft` 更新为该明细的 `todayintr - repayintr`

#### Scenario: 最后完成日下一条利息明细未发生偿还
- **WHEN** 最后一条完成利息明细之后存在下一条同合约利息明细
- **AND** 该下一条利息明细 `repayintr` 等于 0
- **THEN** 系统 MUST 将 `node_gpzydebt.allrepayintrdatedayleft` 更新为 0

#### Scenario: 最后完成日不存在下一条利息明细
- **WHEN** 最后一条完成利息明细之后不存在下一条同合约利息明细
- **THEN** 系统 MUST 将 `node_gpzydebt.allrepayintrdatedayleft` 更新为 0

### Requirement: 按未完成还息计划生成处理后负债
国信股票质押合约处理完成后，系统 SHALL 基于 T 日所有未完成偿还的还息计划生成 `node_debtdetail` 负债记录，用于后续资金扣收。

#### Scenario: 未完成深圳还息计划生成负债
- **WHEN** T 日存在 `market='0'` 且 `status != '1'` 的还息计划
- **THEN** 系统 MUST 生成 `node_debtdetail` 负债记录
- **AND** 负债记录 `busitype` MUST 为 `025032`
- **AND** 负债记录 `debtamt` MUST 为 `intramt - repayintr`
- **AND** 负债记录 `lastfrzamt` MUST 为还息计划 `frzamt`

#### Scenario: 未完成上海还息计划生成负债
- **WHEN** T 日存在非深圳市场且 `status != '1'` 的还息计划
- **THEN** 系统 MUST 生成 `node_debtdetail` 负债记录
- **AND** 负债记录 `busitype` MUST 为 `015032`
- **AND** 负债记录 `debtamt` MUST 为 `intramt - repayintr`
- **AND** 负债记录 `lastfrzamt` MUST 为还息计划 `frzamt`

#### Scenario: 根据扣收截止日设置扣收模式
- **WHEN** 系统根据未完成还息计划生成负债
- **AND** 还息计划 `deadline` 等于 T 日
- **THEN** 负债记录 `costmode` MUST 为 `1`
- **AND** 当还息计划 `deadline` 不等于 T 日时，负债记录 `costmode` MUST 为 `4`

#### Scenario: 计划负债写入还息计划来源标识
- **WHEN** 系统根据未完成还息计划生成 `node_debtdetail`
- **THEN** 负债记录 `pathid` MUST 为 `GPZYDEBT_INTRREPAYPLAN`
- **AND** 负债记录 `extsno` MUST 为还息计划表的 `createdate#sno`
- **AND** 该标识 MUST 用于恢复重做时区分还息计划生成负债和其他股票质押负债

### Requirement: 恢复重做还原还息计划和利息明细
系统 SHALL 在股票质押合约处理恢复重做时，还原国信还息计划和利息明细派生更新，并删除当日生成的利息解冻流水和计划负债流水。

#### Scenario: 还息计划存在上日记录时按上日恢复
- **WHEN** 恢复重做处理 T 日 `node_gpzydebt_intrrepayplan`
- **AND** 存在匹配的 T-1 日还息计划
- **THEN** 系统 MUST 按 `sno + gpzysno + createdate` 匹配 T-1 日还息计划
- **AND** MUST 使用 T-1 日计划回退 T 日计划的 `repayintr`
- **AND** MUST 使用 T-1 日计划回退 T 日计划的 `otherrepayintr`
- **AND** MUST 使用 T-1 日计划回退 T 日计划的 `status`

#### Scenario: 还息计划不存在上日记录时重置
- **WHEN** 恢复重做处理 T 日 `node_gpzydebt_intrrepayplan`
- **AND** 不存在匹配的 T-1 日还息计划
- **THEN** 系统 MUST 按 `sno + gpzysno + createdate` 判断不存在匹配的 T-1 日还息计划
- **AND** MUST 将 T 日计划 `repayintr` 重置为 0
- **AND** MUST 将 T 日计划 `otherrepayintr` 重置为 0
- **AND** MUST 将 T 日计划 `status` 重置为 `0`

#### Scenario: 利息明细按上日合约完成信息回退
- **WHEN** 恢复重做处理 T 日 `node_gpzydebt_intrdetail`
- **THEN** 系统 MUST 不处理 `busidate < T-1 lastallrepayintrdate` 的利息明细
- **AND** 系统 MUST 将 `busidate >= T-1 lastallrepayintrdate` 的利息明细恢复为未完成
- **AND** 系统 MUST 将恢复为未完成的利息明细 `archivedate` 回退为 0
- **AND** 当 T-1 `allrepayintrdatedayleft` 大于 0 时，对完成日期下一日的利息明细，系统 MUST 将 `repayintr` 恢复为 `todayintr - T-1 allrepayintrdatedayleft`
- **AND** 当 T-1 `allrepayintrdatedayleft` 等于 0 时，系统 MUST 不恢复完成日期下一日的高精度已还金额
- **AND** 对完成日期下一日之后的利息明细，系统 MUST 将 `repayintr` 恢复为 0

#### Scenario: 删除当日生成的利息解冻流水
- **WHEN** 恢复重做执行股票质押国信扩展恢复
- **THEN** 系统 MUST 删除当日生成的 `busitype=895005`、`createpoint=CREATE_POINT_HYCL` 的 `node_settdetail`
- **AND** MUST 删除这些交割流水对应的 `node_settdetailsub`

#### Scenario: 删除当日生成的计划负债流水
- **WHEN** 恢复重做执行股票质押国信扩展恢复
- **THEN** 系统 MUST 删除当日基于未完成还息计划生成的 `node_debtdetail`
- **AND** 删除条件 MUST 限定 `pathid='GPZYDEBT_INTRREPAYPLAN'`
- **AND** MUST 不删除其他来源生成的股票质押负债记录
