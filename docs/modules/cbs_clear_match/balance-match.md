# 余额与市值配对

本文覆盖：

- `MATCHTYPE_T0ZHYE`：T 日账户余额配对，`CMatchAccountT0Base`。
- `MATCHTYPE_TM1ZHYE`：T-1 日账户余额配对，`CMatchAccountTM1Base`。
- `MATCHTYPE_TM2CCSZ`：T-1 日持仓市值配对，`CMatchAccountMktvalueTM1Base`。
- `MATCHTYPE_TM1LINKSTKID`：T-1 正股持仓余额配对，`CMatchAccountTM1LinkStkidBase`。

这些配对方式的共同点是：先形成多个账户维度的 `CBalMatch` 候选，再调用 `CMatchAccountT0Base::AllotByStkHold()` 按余额或市值比例拆分清算流水金额、数量和子表字段，生成一条或多条交割流水。

## 公共分摊逻辑

`AllotByStkHold()` 输入：

- 原清算流水。
- 候选 `CBalMatch` 列表。
- 分摊总量 `dbTotalqty`，可能是持仓数量，也可能是市值。
- 是否有特殊账户差额需要挂账。

分摊规则：

1. 用清算流水初始化临时交割流水和尾差对象。
2. 按每个候选账户的 `amount / total` 分摊：
   - `matchamt`
   - `matchqty`
   - `intramt`
   - `ticketamt`
   - 清算流水子表中的各字段
3. `matchqty` 会截断为整数股。
4. 无特殊账户且无尾差配置时，最后一个候选账户承接剩余尾差。
5. 有 `comm_busiconfig.taildiffdealtype` 配置时按配置处理尾差：
   - `TAILDIFFDEALTYPE_FSEZDZH`：分配到发生额最大账户。
   - `TAILDIFFDEALTYPE_MRZH`：分配到默认账户；若默认账户不在拆分结果中，则新增一条默认账户交割流水。
   - 超过 `targetbal` 或无法处理时，尾差转为手工认领。
6. 所有拆分结果最终通过 `CNode_settdetailCacheManager::NewRecord()` 写入 cache。

## T 日账户余额配对：`MATCHTYPE_T0ZHYE`

入口：`CMatchAccountT0Base::Match()`。

候选余额来源：

1. 当日 `node_stkholdbookkeeping`：
   - `busidate = 当前业务日期`
   - `settbody + secuid + stkid`
   - `subjectcode = S10001`
2. 当日已生成的 `node_settdetail`，按 `settbody + secuid + stkid` 读取，用于叠加 T 日已发生变动。

过滤条件：

- 多头股东账户直接返回失败。
- 持仓方向、投保标志、托管席位必须与清算流水一致。
- 持仓单元和资金账号必须存在。
- 股东账户不存在或已销户则过滤。
- 持仓单元必须核算，且持仓单元、资金账号均不是其他账户。
- 最终只保留正余额。

特殊账户处理：

- 若候选股东命中 `comm_specialaccount`，会从登记公司余额文件读取文件总余额。
- 若文件总余额小于系统余额，抛业务异常。
- 若文件总余额大于系统余额，多出的权益转挂账，分摊基数使用文件总余额。

## T-1 日账户余额配对：`MATCHTYPE_TM1ZHYE`

入口：`CMatchAccountTM1Base::Match()`。

候选来源是 `node_stkholdbookkeeping`，查询条件与 T 日类似，但只使用簿记数据，不叠加当日交割流水。

关键过滤：

- 多头股东账户直接失败。
- 根据托管席位来源开关和市场决定是否校验席位：账户下场或深圳 A 市场时要求持仓席位与清算流水一致。
- 持仓方向、投保标志、股份性质必须一致。
- 持仓单元、资金账号、股东账户必须存在且状态有效。
- 持仓单元必须核算，持仓单元和资金账号均不是其他账户。
- 只保留 `startbal > 0`。

若清算流水交易单元为空，会按 `market + secuid + mainseat` 从股东账户表补 `trdseat`。

## T-1 日持仓市值配对：`MATCHTYPE_TM2CCSZ`

入口：`CMatchAccountMktvalueTM1Base::Match()`。

用于按 T-1 持仓市值拆分，典型场景是港股证券组合费。

候选来源：

- `node_stkholdbookkeeping` 按 `secuid + market + lastBusidate + settbody` 查询。
- 仅保留科目 `S10001`、方向/投保一致、期初余额非 0 的记录。

市值计算：

1. 从 `comm_stkprice` 取当前业务日期证券价格。
2. 价格优先级：公允价 `gyprice` > 收市价 `closeprice` > 昨收市价 `precloseprice`。
3. 找不到价格直接抛业务异常。
4. 总市值为 0 则配对失败。

最后按市值调用 `AllotByStkHold()`。

## T-1 正股持仓余额配对：`MATCHTYPE_TM1LINKSTKID`

入口：`CMatchAccountTM1LinkStkidBase::Match()`。

它与 T-1 余额配对类似，但使用正股证券内码作为持仓查询证券：

1. 优先取清算流水 `stkid1` 作为正股内码。
2. `stkid1` 为空时，从 `comm_stock.linkstkid` 获取正股内码。
3. 用正股内码查 `node_stkholdbookkeeping`。

过滤条件比普通 T-1 配对更严格：

- 托管席位必须一致。
- 方向、投保标志、股份性质必须一致。
- 持仓单元、资金账号、股东账户必须存在且状态有效。
- 只保留正余额。

最后按正股持仓余额调用 `AllotByStkHold()`。

## 缓存依赖

| 配对方式 | 缓存函数 | 关键表 |
|---|---|---|
| T 日余额 | `CacheT0ZHYE()` | `node_stkholdbookkeeping`、`node_settdetail`、`comm_specialaccount`、各市场证券余额文件。 |
| T-1 余额 | `CacheTM1ZHYE()` | `node_stkholdbookkeeping`。 |
| T-1 市值 | `CacheTM2CCSZ()` | `node_stkholdbookkeeping`、`comm_stkprice`。 |
| T-1 正股余额 | `CacheTM1LinkStkid()` | `node_stkholdbookkeeping`、`comm_stock`。 |
