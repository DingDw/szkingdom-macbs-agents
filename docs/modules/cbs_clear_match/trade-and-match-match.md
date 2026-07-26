# 委托与成交配对

本文覆盖：

- `MATCHTYPE_BDHTXH`：委托配对，本地合同序号，对应 `CMatchTradeBase`。
- `MATCHTYPE_JJGSHTXH`：成交配对，经纪公司合同序号，对应 `CMatchMatchBase`。

## 委托配对：`MATCHTYPE_BDHTXH`

入口：`CMatchTradeBase::Match()`。

主流程：

1. 确定用于查委托的市场。
   - `pathid == SZ_SCDHB` 且清算流水市场是上海 A 时，委托市场改用深圳 A，用于跨市场 ETF。
2. 确定用于查委托的申请编号。
   - 深 A、深 H 申请编号以 `00` 开头且长度大于 2 时，先去掉前两位再匹配。
3. 按 `secuid + market + orderdate + orderid` 查 `node_trade`。
4. 未命中时，按 `secuid + market + stkcode + orderdate + marketorderid` 查 `node_trade`。
5. 仍未命中时，将登记公司合同序号截去前两位再重复第 3、4 步。
6. 北交所业务未命中时，用股转 A 市场再按 `orderid` 查一次。
7. `SZ_SCDHB`、`SH_ZQBD` 特殊场景未命中时，用 `coreid * 100000000 + ordersno` 与 `applycode` 比较。
8. 多条命中直接抛业务异常；一条命中则按委托回填清算流水并生成交割流水。

成功后的字段处理：

- `AssignOneClearDetailByTrade()` 用委托补齐清算流水账户、订单、交易流水、买卖标志、机构等字段。
- `CNode_settdetailCacheManager::NewRecord(objCleardetail)` 生成交割流水。
- 结算分组优先取委托 `settgroup`；委托为空时调用 `InitSettGroupByFundAcct()` 从资金账号补齐。
- `SpecialInitSettdetailExt()` 补特殊交割流水属性。
- 额外回填 `fundlevel`、`fundgroup`、`ordergroup`、`operrole`、`operorg`。
- 调用 `AfterClearPair()` 做配对后通用补充。

专项逻辑：

- 约定购回业务 `015401` 至 `015404`、`025401` 至 `025404`：若 `node_trade_ydgh` 存在不同于原合约号的关联合约号，交割流水业务类型转换为 `0154A1` 至 `0154A4` 或 `0254A1` 至 `0254A4`。

失败行为：

- `MATCHTYPE_BDHTXH` 在 `MatchByMatchType()` 中委托配对失败后，立即降级调用 `CMatchAccount` 做账户配对。
- 账户配对仍失败时，后续进入 `MatchFailedCleardetail()`，最终可能生成挂账流水。

## 成交配对：`MATCHTYPE_JJGSHTXH`

入口：`CMatchMatchBase::Match()`。

主流程：

1. 清算流水 `matchcode` 为空时直接失败。
2. 先按 `secuid + stkcode + orderdate + extmatchcode` 从 `node_match` 查成交，取成交表 `extorderid` 作为申请编号。
3. 协议回购/三方回购业务：
   - 条件包括 `pathid == SH_JSMX` 且 `reserve2` 属于 `613/615/616/617/618/619/680...688`，或 `pathid == SH_ZQBD` 且业务类型属于 `015514/015516/015518`。
   - 改从 `intf_zqhg_match` 按 `secuid + matchcode` 查合同序号。
4. 固收平台买卖业务：
   - `pathid == SH_JSMX` 且 `reserve2` 属于 `601/605/691/550/611/690`。
   - 从 `intf_stkmatch` 按 `matchcode + trddate + market + secuid` 查申报合同序号。
5. 拿到申请编号后，再按 `secuid + market + orderdate + orderid` 查 `node_trade`。
6. 多条委托命中抛业务异常；未命中返回失败；唯一命中则按委托生成交割流水。

成功后的字段处理：

- 与委托配对类似，先 `AssignOneClearDetailByTrade()`，再 `NewRecord()` 生成交割流水。
- 调用 `SpecialInitSettdetailExt()`。
- 当前成交配对不额外调用 `AfterClearPair()`，后续统一配对后处理仍会覆盖本次插入的交割流水。

## 缓存依赖

`CacheBDHTXH()` 加载：

- `node_trade`，带合同序号、市场合同序号、委托状态、市场日期等索引。
- `node_trade_ydgh`，约定购回委托子表。
- `node_trade_gpzy`，股票质押委托子表。
- `node_trade_rzrq`，融资融券委托子表。

`CacheJJGSHTXH()` 加载：

- `node_match`：成交反查委托。
- `intf_zqhg_match`：债券协议回购成交。
- `intf_stkmatch`：固收平台成交。
- 通过收集到的申请编号批量加载 `node_trade`。
