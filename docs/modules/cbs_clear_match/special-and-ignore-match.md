# 特殊配对与无需配对

本文覆盖：

- `MATCHTYPE_TSPD`：特殊配对，对应 `CMatchSpecialBase`。
- `MATCHTYPE_WXPD`：无需配对，对应 `CMatchIgnoreBase`。

## 特殊配对总路由

`CMatchSpecialBase::Match()` 不是一个统一算法，而是按业务类型二次路由到多个专项方法。专项配对成功后，会对最后生成的交割流水调用 `InitSettGroupByFundAcct()` 补结算分组。

| 业务类型 | 专项方法 | 主要逻辑 |
|---|---|---|
| `015304/015306` | `MatchBJHGTrade()` | 上海报价逆回购初始或提前购回，按报价回购委托及子表生成交割流水。 |
| `015302/015303/015305`、部分 `025301` 至 `025306` | `MatchBJHGContract()` | 报价回购合约配对，从 `node_bjhg_contract_all` 回填账户、产品代码和合同信息。 |
| `014902/014904/024902/024904` | `MatchZyhgContract()` | 债券通用质押回购到期，按初始交易合约 `node_trade_pledgeright` 配对。 |
| 指定入/撤指定出相关业务 | `MatchZdCzSettdetail()` | 用虚拟证券 `1799999` 或 `1799998` 的历史交割流水回填账户。 |
| `013702` | `MatchPgPzSbSettdetail()` | 上海配股配债申报，按委托数量或成交数量与清算数量匹配。 |
| `021401/021402/501401/501402` | `MatchCollateralTrans()` | 担保品转入转出，信用账户走委托配对，非信用账户先账户配对再专项委托兜底。 |
| `015504/025504/025509` | `MatchXyhgSettdetail()` | 协议回购逆回购到期，按协议回购合约编号查 `node_zqzycontract`。 |
| `021905/021906/042203/042205` | 周期配对后委托兜底 | 先调用 `MATCHTYPE_ZQPD`，失败后调用 `MATCHTYPE_BDHTXH`。 |
| `022971/022973/012971/012973` | `MatchETFMainOrder()` | 跨市场 ETF 全实物申赎，用主委托市场查委托。 |
| `012201/012202` | `MatchShYysgOrder()` | 上海要约收购，按业务方向、数量、要约代码或申请编号匹配委托。 |
| `012301/012302` | `MatchShZqhsOrder()` | 上海债券回售，按买卖标志和数量匹配委托。 |
| `028114` | `MatchSzATransferOut()` | 深圳 A 股场内转托管转出，先委托配对，失败后用对应转托管入流水席位做账户配对。 |

## 报价回购委托配对

`MatchBJHGTrade()` 处理上海报价逆回购：

- `015304` 且 `recordtype == '3'`：按 `market + orderdate + orderid` 从 `node_trade` 查报价回购委托。
- `015306` 且 `recordtype == '3'`：先按 `market + reladate + linkorderid` 查 `node_trade_bjhg`，再回查 `node_trade`。
- 成功后生成交割流水，回填委托流水号、合同序号、操作机构、账户、委托时间、委托价格、委托数量、买卖标志等。
- 报价回购委托子表不存在时写流程日志。

## 报价回购合约配对

`MatchBJHGContract()` 从 `node_bjhg_contract_all` 查历史或当日合约：

- 深圳提前购回 `025302/025305` 从 `reserve2` 截取原委托日期和合同号，再查上一业务日合约。
- 深圳到期/初始结果 `025301/025303/025304/025306` 按当前委托日期、市场、申请编号、上一业务日查合约。
- 上海 `015302/015305/015303` 且结果记录 `recordtype == '3'` 查上一业务日合约。
- 其他场景按 `createdate = 0` 查合约。

成功后回填账户、产品代码 `stkid1`、合同序号、流水号，投资类型置交易型，配对状态置默认配对。

## 债券通用质押回购到期

`MatchZyhgContract()` 先把到期业务映射到初始交易业务：

- `014902 -> 014901`
- `014904 -> 014903`
- `024902 -> 024901`
- `024904 -> 024903`

再按 `secuid + 初始业务类型 + contractid + market + stkcode + createdate` 查 `node_trade_pledgeright`。必须唯一命中。

成功后生成交割流水，并从合约回填账户、结算分组、委托数量、委托价格、成交编号；重置委托时间和成交时间。

## 指定入与撤指定出

`MatchZdCzSettdetail()` 用历史交割流水承接账户：

- 指定入业务查虚拟证券 `1799999`。
- 撤指定出业务查虚拟证券 `1799998`。
- 均要求 `settbody + secuid + 虚拟证券` 命中，且托管席位与清算流水一致。

成功后用清算流水构造新交割流水，再从目标历史流水回填结算单元、资金单元、持仓单元、资金账号、机构、合同序号和买卖标志，配对状态置自动配对。

## 担保品转入转出

`MatchCollateralTrans()`：

- 信用账户，即股东代码以 `06` 开头，直接走委托配对。
- 非信用账户先调用 `CAcctMatchUtil::AcctMatch()` 做账户配对。
- 账户配对失败后，会查委托及账户关系，尝试配到同一客户号下的非信用资金账户。

## ETF、要约、回售与转托管专项

`MatchETFMainOrder()`：

- `022971/022973` 使用上海 A 作为主委托市场。
- `012971/012973` 使用深圳 A 作为主委托市场。
- 按 `market + orderdate + orderid` 查唯一委托。

`MatchShYysgOrder()`：

- 遍历上海非交易文件 `sh_fjy` 收集申请编号到要约证券代码映射。
- 在同股东、同市场、同委托日期下找已报或已确认委托。
- `012201` 要求委托买卖标志 `0Y`，`012202` 要求 `0E`。
- 清算数量 `qty1` 与委托数量绝对值一致。
- 可按正股代码、要约代码或 `sh_fjy.bz` 中的申请编号识别委托。
- 已匹配委托通过 `m_setMatchedYysgOrder` 去重。

`MatchShZqhsOrder()`：

- 按股东和证券查委托。
- `012301` 要求买卖标志属于 `0H/4N`。
- `012302` 要求买卖标志属于 `5H/4z`。
- 清算数量 `qty1` 与委托数量绝对值一致。
- 已匹配委托通过 `m_setMatchedZqhsOrder` 去重。

`MatchSzATransferOut()`：

- 先按当前 `applycode` 做委托配对。
- 失败后查对应的 `028113` 转托管入清算流水，要求市场、证券代码、申请编号、委托日期一致且转入流水有席位。
- 用转入席位替换当前席位后做账户配对；失败则恢复原席位。

## 无需配对：`MATCHTYPE_WXPD`

入口：`CMatchIgnoreBase::Match()`。

逻辑：

1. 直接按清算流水生成交割流水。
2. 若交割流水 `settgroup` 为空，则按资金单元查 `node_fundunit` 补结算分组。
3. 调用 `SetBusidefineAfterPair()` 处理配对后业务定义转换。
4. 配对状态置自动配对。

无需配对仍会进入 `AfterClearMatch()` 和 `Write()`，因此业务拆分、业务转换、交割子表生成等后处理仍然有效。
