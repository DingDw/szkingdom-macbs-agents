# 分段、恢复与手工配对

本文覆盖 `680001`、`680002`、`680004`，这些入口不直接实现具体配对算法，但决定清算配对的执行边界、重做一致性和人工认领流程。

## 分段计算：`680001`

入口：`CClearMatchCaclRange`。

参数：

- `markets`：交易市场，多个市场逗号分隔。
- `dealpoint`：处理时点。

参数校验：

- 转融通处理时点以外，上海 A 与沪港通必须一起处理。
- 转融通处理时点以外，深圳 A 与深港通必须一起处理。

分段逻辑：

1. 按业务日期、结算主体、市场、处理时点、非失败状态读取 `node_cleardetail`。
2. 股东账户和资金账号不能同时为空。
3. 股东账户为空的流水计入 `m_nTolalMissingSecuid`，后续按市场生成 `beginsecuid = *`、`endsecuid = *` 的独立分段。
4. 有股东账户的流水按市场和股东代码统计笔数。
5. 上海 A 与沪港通合并为同一个市场分段；深圳 A 与深港通合并为同一个市场分段。
6. 每个市场内调用 `CalcMapRangeByBatchSize()` 按股东代码范围拆分。
7. 每个分段补充 `threadno`、`markets`、`busidate`、`settbody`、`domainid`、`partid`、`instid`、`compute_node`。

输出：

- `Write()` 调用 `MakeRangeResult(m_vecRange)` 返回分段结果。

## 重做前恢复：`680002`

入口：`CClearMatchRestore`。

参数：

- `markets`：必填。
- `dealpoint`：处理时点。

前置条件：

- `m_cRestoreflag == FLAG_NO` 时直接 `PHASE_END`，不做恢复。

恢复逻辑：

1. 对本业务日期、结算主体、市场、处理时点生成的交割流水，逐条删除对应 `node_settdetailsub`。
2. 删除本业务日期、结算主体、市场、处理时点生成的 `node_settdetail`。
3. 港股拆分合并置为无效的历史交割流水，若本次更新日期为当前业务日且不属于当前交收日，恢复为有效。
4. 清算处理时点 `DEALPOINT_QSCL` 下，删除本日清算生成的负债明细，但排除 `FUNDCOST_DETAIL`、`FUNDAUTOCLAIM_NODEX`。
5. 清算处理时点 `DEALPOINT_QSCL` 下，恢复周期配对关闭的周期流水：
   - 查 `updatedate = 当前业务日期` 且 `status = '1'` 的 `node_perioddetail`。
   - 周期流水子表清空 `archivedate`、`updatedate`。
   - 周期流水主表置 `status = '0'`，清空 `archivedate`、`updatedate`、`mergebusiflowid`。
6. 删除本市场、当前处理时点对应的 `node_mutisecuid_result`。

注意点：

- 周期配对是三段式功能的一部分，周期流水状态恢复必须在 restore 阶段完成。
- 当前恢复逻辑不按 `mergebusiflowid` 区分关闭来源，而是恢复所有当天关闭的周期流水。

## 手工配对：`680004`

入口：`CClearMatchManual`。

参数：

- `settgroup`
- `settunit`
- `fundunit`
- `stkholdunit`
- `busiflowid`

缓存：

- 按 `stkholdunit` 加载持仓单元。
- 按资金账号加载资金账号。
- 按 `busiflowid` 加载交割流水及其子表。

检查：

1. 持仓单元必须存在。
2. 持仓单元对应资金账号必须存在。
3. 从资金账号回填 `settgroup`、`fundacct`、`orgid`、`brhid`、`coreid`。

处理：

1. 按 `busiflowid` 查询待手工配对的交割流水，不存在则抛业务异常。
2. 把人工指定的 `settgroup`、`settunit`、`fundunit`、`stkholdunit`、`fundacct`、`orgid`、`brhid`、`coreid` 写回交割流水。
3. 配对状态置 `MATCHSTATUS_SGPD`。
4. 同步更新交割流水子表的 `fundacct` 和 `updatedate`。

写入：

- 加写锁后批量更新 `node_settdetail` 和 `node_settdetailsub`。
