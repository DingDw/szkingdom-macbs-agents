## 1. 配置化处理者接入

- [x] 1.1 在股票质押合约处理目录新增默认扩展处理者和国信扩展处理者，提供 Cache、自动偿还利息处理、处理后负债生成、恢复重做四类扩展方法。
- [x] 1.2 使用 `REGISTER_CLEAR_HANDLER_CLASS` 注册默认处理者和国信处理者，class path 遵循 `cbs_clear.contract_deal.*` 命名并与 `comm_featureconfig` 配置一致。
- [x] 1.3 在 `CClearGpzy` 生命周期中接入扩展处理者，确保非国信默认处理者为空实现且不改变现有行为。
- [x] 1.4 在 `comm_featureconfig` Gauss 增量脚本中增加默认配置和 `@cbssysid="101"` 国信配置。

## 2. 缓存和写入扩展

- [x] 2.1 在 `CClearGpzy::Cache()` 或扩展处理者 Cache 方法中，通过 `CacheManager` 缓存当前任务市场范围内的 T 日 `node_gpzydebt_intrrepayplan`。
- [x] 2.2 在 Cache 阶段缓存自动偿还处理所需的 `node_gpzydebt_intrdetail`，并在处理者内建立按 `gpzysno + market` 查询的内存辅助结构。
- [x] 2.3 在 `CClearGpzy::Write()` 中增加 `node_gpzydebt_intrrepayplan` 和 `node_gpzydebt_intrdetail` 的批量更新写入。
- [x] 2.4 确认新增缓存和写入路径只覆盖日终清算任务市场范围，不处理日间清算数据源。

## 3. 自动偿还利息计划处理

- [x] 3.1 在 `CClearGpzy::AutoRepay()` 的 `GPZY_AUTO_REPAY_TYPE_LX` 利息自动偿还分支中，完成现有流水生成和合约回写后调用国信扩展处理。
- [x] 3.2 查询当前合约、当前市场、T 日的还息计划；存在多条时按 `startdate` 升序排序。
- [x] 3.3 校验第一条还息计划前不存在 `busidate < startdate` 且 `repayflag != '1'` 的利息明细。
- [x] 3.4 校验多条还息计划满足自然日连续性：后一条 `startdate` 等于前一条 `enddate + 1`。
- [x] 3.5 对每条还息计划按 `min(intramt - repayintr, 剩余自动偿还利息金额)` 计算本次偿还金额，并累加 `repayintr` 和 `otherrepayintr`。
- [x] 3.6 当还息计划完成偿还时，将 `status` 更新为 `1`，将 `settdate` 更新为 T 日。

## 4. 利息明细抵扣和合约回写

- [x] 4.1 对计划周期内的利息明细按 `busidate` 升序抵扣 `todayintr - repayintr`，并保留 10 位高精度金额计算。
- [x] 4.2 当利息明细全部抵扣完成时，更新该明细 `repayflag='1'`。
- [x] 4.3 当还息计划已完成但周期最后一条利息明细存在高精度尾差，未被更新为`repayflag='1'`时，将周期最后一条利息明细 `repayflag` 更新为 `1`，不修正`repayintr`
- [x] 4.4 当还息计划已完成且周期最后一条利息明细已被更新为`repayflag='1'`,如果仍然存在未偿还完成尾差，累加到周期最后一条利息明细`repayintr`上。
- [x] 4.5 当当前合约 T 日不存在还息计划时，按 `busidate` 升序直接抵扣所有 `repayflag != '1'` 的利息明细。
- [x] 4.6 根据本次最后一条完成偿还的利息明细，回写 `node_gpzydebt.lastallrepayintrdate`。
- [x] 4.7 根据最后完成日下一条利息明细的 `todayintr - repayintr` 回写 `node_gpzydebt.allrepayintrdatedayleft`；不存在下一条时写 0。

## 5. 利息解冻流水生成

- [x] 5.1 对本次完成偿还且 `frzamt` 不为 0 的还息计划，生成 `busitype=895005` 的 `node_settdetail` 利息解冻流水。
- [x] 5.2 解冻流水必须设置 `createpoint=CREATE_POINT_HYCL` 和 `bookkeepingpoint=BOOKKEEPINGPOINT_TY`。
- [x] 5.3 为每笔解冻流水生成对应 `node_settdetailsub`，设置 `fieldname='frzamt'`、`fieldvalue=-frzamt`。
- [x] 5.4 检查目标基线是否已存在 `895005` 业务定义和记账配置；缺失时补充 Gauss 增量脚本。

## 6. 处理后负债生成

- [x] 6.1 在股票质押合约处理完成后，国信扩展处理 T 日所有 `status != '1'` 的还息计划。
- [x] 6.2 为深圳市场 `market='0'` 的未完成计划生成 `busitype=025032` 的 `node_debtdetail`。
- [x] 6.3 为非深圳市场的未完成计划生成 `busitype=015032` 的 `node_debtdetail`。
- [x] 6.4 设置负债金额字段：`debtamt`、`unpaidamt`、`matchamt` 均为 `intramt - repayintr`，`lastfrzamt` 为计划 `frzamt`。
- [x] 6.5 根据 `deadline` 设置 `costmode`：`deadline=T日` 时为 `1`，否则为 `4`。
- [x] 6.6 为计划生成负债设置 design 指定的稳定恢复标识：`pathid='GPZYDEBT_INTRREPAYPLAN'`，`extsno=还息计划createdate#sno`。
- [x] 6.7 避免国信路径与现有 `CreateDebtDetail()` 重复生成 `015032/025032` 利息负债。

## 7. 恢复重做处理

- [x] 7.1 在 `CClearRestoreGpzy::Clear()` 中接入国信扩展恢复逻辑，并保持非国信恢复行为不变。
- [x] 7.2 对 T 日 `node_gpzydebt_intrrepayplan`，按 `sno + gpzysno + createdate` 存在匹配 T-1 计划时恢复 `repayintr`、`otherrepayintr`、`status`、`settdate`。
- [x] 7.3 对按 `sno + gpzysno + createdate` 不存在匹配 T-1 计划的 T 日还息计划，重置 `repayintr=0`、`otherrepayintr=0`、`status='0'`，并清空完成日。
- [x] 7.4 使用 T-1 `node_gpzydebt.lastallrepayintrdate` 和 `allrepayintrdatedayleft` 回退 T 日 `node_gpzydebt_intrdetail` 偿还状态：完成日前不处理，完成日及以后恢复未完成并回退 `archivedate=0`，完成日下一日的 `repayintr` 恢复为 `todayintr-allrepayintrdatedayleft`。
- [x] 7.5 删除当日生成的 `busitype=895005`、`createpoint=CREATE_POINT_HYCL` 的 `node_settdetail` 及对应 `node_settdetailsub`。
- [x] 7.6 删除当日基于还息计划生成的 `node_debtdetail`，删除条件必须限定 `pathid='GPZYDEBT_INTRREPAYPLAN'`，确保不删除其他来源负债。

## 8. 校验和回归

- [x] 8.1 用 `rg` 检查 `comm_featureconfig`、`895005`、`015032`、`025032`、`node_gpzydebt_intrrepayplan`、`node_gpzydebt_intrdetail` 的既有定义和冲突点。
- [x] 8.2 走查国信场景：存在多条连续还息计划、计划完成生成解冻流水、利息明细尾差完成标记、合约字段回写。
- [x] 8.3 走查国信场景：不存在还息计划时直接抵扣未完成利息明细。
- [x] 8.4 走查异常场景：第一条计划前存在未完成利息明细、多条计划自然日不连续。
- [x] 8.5 走查恢复重做场景：还息计划按 T-1 回退、无 T-1 计划重置、利息明细按 T-1 合约完成信息回退、当日解冻流水和计划负债删除。
- [x] 8.6 走查非国信场景，确认默认处理者为空实现且现有股票质押合约处理行为不变。
- [x] 8.7 如明确要求构建，执行 `cmake --build --preset build-x64-debug --target cbs_clear` 或对应环境目标；否则不默认构建。
- [x] 8.8 运行 `openspec validate gpzy-intrrepay-contract-deal-adjust`，确认 proposal、design、specs、tasks 均通过校验。
