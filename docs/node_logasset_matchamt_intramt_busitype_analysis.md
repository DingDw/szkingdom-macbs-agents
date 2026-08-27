# node_logasset.matchamt / intramt busitype 赋值逻辑分析

## 1. 字段传递主链路

`node_logasset.matchamt` / `intramt` 的数据主链路如下：

```text
cbs_preclear: node_cleardetail.matchamt / intramt
    -> cbs_clear_match: node_settdetail.matchamt / intramt
    -> cbs_book: CLogassetCreator*.InitLogasset()
    -> node_logasset.matchamt / intramt
```

关键点：

| 阶段 | 文件 | 逻辑 |
| --- | --- | --- |
| 预处理 | `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/*` | 根据交易所文件字段、业务识别配置、特定业务分支给 `node_cleardetail.matchamt/intramt` 赋值 |
| 清算配对 | `macbs-base/library/macbs/dao/tables/node_settdetail_memdb.h` | `CNode_settdetail_memdb::SetByCleardetail()` 将 `cleardetail.matchamt/intramt` 原样赋给 `settdetail.matchamt/intramt` |
| 簿记生成流水 | `macbs-base/library/macbs/comm/logasset_creator.h` | `InitLogasset()` 先按通用规则赋值，再按 `busitype` 特殊调整 |

`logasset_creator.h` 中基础赋值：

| 字段 | 基础赋值 |
| --- | --- |
| `node_logasset.matchamt` | `abs(node_settdetail.matchamt - GetFeeValue(subsMap, market, busitype, "matchamt"))` |
| `node_logasset.intramt` | `abs(node_settdetail.intramt)` |

## 2. logasset_creator 最终特殊处理

### 2.1 matchamt 加 intramt，intramt 清零

该逻辑位于 `CLogassetCreator_::SpecialDealIntramt()`。

前置控制：

| 参数 | 含义 | 影响 |
| --- | --- | --- |
| `PARAMID_LOGASSET_BONDINTR` | `logasset.bondintr` 特殊处理开关，默认 `'1'` | 若取值为 `'0'`，`SpecialDealIntramt()` 直接返回，下面这些 `matchamt/intramt` 特殊处理不会执行 |

处理公式：

```text
node_logasset.matchamt = node_logasset.matchamt + node_logasset.intramt
node_logasset.intramt = 0
```

| busitype | 业务说明（代码注释/配置可确认部分） | 最终处理 |
| --- | --- | --- |
| `020107`, `020108` | 深市 A 股非公开发行优先股买入/卖出 | `matchamt += intramt`; `intramt = 0` |
| `020225`, `020226` | 深圳企业债综合/固收平台买入/卖出非担保交收 | 同上 |
| `020227`, `020228` | 深圳公司债综合/固收平台买入/卖出非担保交收 | 同上 |
| `020229`, `020230` | 深圳可交换债综合/固收平台买入/卖出非担保交收 | 同上 |
| `020231`, `020232` | 深圳私募债综合/固收平台买入/卖出 | 同上 |
| `020233`, `020234` | 深圳次级债综合/固收平台买入/卖出 | 同上 |
| `020235`, `020236` | 深圳资产支持证券综合/固收平台买入/卖出 | 同上 |
| `020237`, `020238` | 深圳资产管理计划综合/固收平台买入/卖出 | 同上 |
| `020241`, `020242` | 深圳政府支持债券综合/固收平台买入/卖出 | 同上 |
| `020243`, `020244` | 深圳国债综合/固收平台买入/卖出非担保交收 | 同上 |
| `021605` | 深圳可转债债券赎回 | 同上 |
| `022301`, `022302`, `022303`, `022304`, `022305`, `022306` | 深圳债券回售申请/撤销/注销解冻/资金发放及债券注销等 | 同上 |
| `023703` | 深圳 A 股配股/债失败返款 | 同上 |
| `023804`, `023806` | 深圳 A 股红股零碎股转现金/红利入账 | 同上 |
| `023901`, `023902`, `023904`, `023905`, `023906` | 深圳债券兑息/兑付/质押券相关兑付兑息 | 同上 |
| `024001`, `024002` | 深圳基金现金分红/红利再投 | 同上 |
| `028001`, `028002` | 深圳冻结资金解冻/证券场内转托管收费 | 同上 |
| `028122`, `028123`, `028125`, `028126`, `028130`, `028131`, `028161`, `028162` | 深圳司法冻结/解冻/再冻结/证券冻结/询价转让锁定解锁等 | 同上 |
| `043802` | 深圳 B 股红利入账 | 同上 |
| `048002`, `048004`, `048109`, `048110` | 深圳 B 股转托管费用/冻结资金解冻/司法冻结/司法解冻 | 同上 |
| `0202D1`, `0202D2`, `0202D3`, `0202D4` | 现券点击成交报价申报/回复买入卖出 | 同上 |
| `0202X1`, `0202X2`, `0202X3`, `0202X4`, `0202X5`, `0202X6`, `0202X7`, `0202X8` | 现券协商成交/询价申报/询价报价/询价成交买入卖出 | 同上 |
| `0202J1`, `0202J2` | 现券相关业务类型，代码仅列入处理集合，未见就地注释说明 | 同上 |
| `503802`, `503812` | 股转/北交所红利入账、股转 B 红利入账 | 同上 |
| `013901`, `013911` | 上海债券兑息/债券兑息补领 | 同上 |
| `013902`, `013912` | 上海债券兑付（还本付息）/债券兑付补领 | 同上 |
| `010203` - `010210` | 上海企业债/公司债/政策性金融债/地方政府债竞价买入卖出 | 同上 |
| `010211` - `010220` | 上海国债/企业债/公司债/地方政府债/政策性金融债固收买入卖出 | 同上 |
| `010221`, `010222` | 上海非公开发行公司债固收非担保买入/卖出 | 同上 |
| `010223`, `010224` | 上海债券固收 RTGS 买入/卖出 | 同上 |
| `010225` - `010234` | 上海国债/企业债/公司债/地方政府债/政策性金融债大宗买入卖出 | 同上 |
| `011405`, `011408`, `011412`, `011415`, `011418`, `011422` | 上海融资融券债券买入/卖出还款/平仓/融券卖出/还券等 | 同上 |
| `018001`, `018002`, `018003` | 上海权益资金划付/特殊资金调账上账/下账 | 同上 |
| `020214` | 深圳国债综合/固收平台卖出 | 同上 |
| `0102D1`, `0102D2`, `0102D3`, `0102D4`, `0102D5`, `0102D6` | 上海现券点击成交报价类业务 | 同上 |
| `0102P1`, `0102P2` | 上海现券匹配成交买入/卖出 | 同上 |
| `0102X1`, `0102X2` | 上海现券协商成交买入/卖出 | 同上 |
| `020250`, `020251`, `020252`, `020253` | 代码仅列入处理集合，未见就地注释说明 | 同上 |

### 2.2 受参数 60207 控制的补充利息并入成交金额

本节与 2.1 的处理公式相同，但触发条件不同，不是重复集合：

| 对比项 | 2.1 固定 busitype 集合 | 2.2 参数 60207 补充分支 |
| --- | --- | --- |
| 触发方式 | `busitype` 命中代码写死的集合即处理 | `busitype` 命中补充集合且 `PARAMID_LOGASSET_MATCHAMT_CONTAIN_INTRAMT == FLAG_YES` 才处理 |
| 主要业务 | 深圳/上海债券、红利、现券点击/询价/协商等一批固定口径业务 | `010201`, `010202`, `0202P1`, `0202P2` 这 4 类按公参决定口径的业务 |
| 处理公式 | `matchamt += intramt`; `intramt = 0` | 同左 |
| 额外说明 | 仍受 `PARAMID_LOGASSET_BONDINTR` 总开关影响 | 也在 `SpecialDealIntramt()` 内，因此同样受 `PARAMID_LOGASSET_BONDINTR` 总开关影响 |

处理公式：

```text
如果 PARAMID_LOGASSET_MATCHAMT_CONTAIN_INTRAMT == FLAG_YES:
    node_logasset.matchamt = node_logasset.matchamt + node_logasset.intramt
    node_logasset.intramt = 0
```

| busitype | 业务说明 | 参数关闭 | 参数开启 |
| --- | --- | --- | --- |
| `010201` | 上海国债竞价买入 | 保持基础值 | `matchamt += intramt`; `intramt = 0` |
| `010202` | 上海国债竞价卖出 | 保持基础值 | 同左 |
| `0202P1` | 现券匹配成交买入 | 保持基础值 | 同左 |
| `0202P2` | 现券匹配成交卖出 | 保持基础值 | 同左 |

### 2.3 matchamt 加 intramt，但 intramt 不清零

处理公式：

```text
node_logasset.matchamt = node_logasset.matchamt + node_logasset.intramt
node_logasset.intramt 保留原值
```

对应宏：`BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET`。

| busitype | 业务说明（代码注释/配置可确认部分） | 最终处理 |
| --- | --- | --- |
| `014902` | 上海债券质押正回购购回交易 | `matchamt += intramt`; `intramt` 保留 |
| `014904` | 上海债券质押逆回购购回交易 | 同上 |
| `024902` | 深圳债券质押正回购购回交易 | 同上 |
| `024904` | 深圳债券质押逆回购购回交易 | 同上 |
| `015305` | 上海报价逆回购 1 天期到期购回 | 同上 |
| `015302`, `015303`, `015306`, `015309`, `015310` | 上海报价回购到期/提前购回类 | 同上 |
| `025302`, `025303`, `025305`, `025306` | 深圳报价回购提前/到期购回类 | 同上 |
| `015502`, `015504` | 上海债券质押式协议正/逆回购到期购回 | 同上 |
| `015505`, `015507` | 上海债券质押式协议正/逆回购到期续做（前期合约了结） | 同上 |
| `015509`, `015510` | 上海债券质押式协议正/逆回购提前终止 | 同上 |
| `025502`, `025504` | 深圳债券质押式协议正/逆回购购回交易 | 同上 |
| `025505`, `025506`, `025507`, `025509` | 深圳债券质押式协议回购到期续做/前期了结类 | 同上 |
| `025510`, `025511` | 深圳债券质押式协议正/逆回购提前购回 | 同上 |
| `025512`, `025513` | 深圳债券质押式协议正/逆回购违约了结 | 同上 |
| `014603`, `014604`, `014605`, `014606`, `014607`, `014608` | 上海债券借贷借入/借出方到期、提前终止、逾期结算 | 同上 |
| `024603`, `024604`, `024605`, `024606` | 深圳债券借贷相关业务类别，宏集合列入，当前就地注释未展开 | 同上 |

> 注：本节按 `macbs_busitypes.h` 中 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET` 宏整理，表格按业务族归并。

### 2.4 扣税业务覆盖 matchamt，intramt 清零

处理公式：

```text
node_logasset.matchamt = abs(node_settdetail.intrtax)
node_logasset.intramt = 0
```

| busitype | 业务说明 | 最终处理 |
| --- | --- | --- |
| `013909` | 上海债券兑息扣税业务 | `matchamt = abs(intrtax)`; `intramt = 0` |
| `023909` | 深圳债券兑息扣税业务 | 同上 |
| `503909` | 股转/北交所债券兑息扣税业务 | 同上 |

### 2.5 matchamt 置零或覆盖

| busitype | 条件 | 最终处理 |
| --- | --- | --- |
| `012915` | 上海 ETF 现金申购份额 | `matchamt = 0` |
| `898201` | 日间结息 | `matchamt = 0` |
| `012711`, `012504`, `022708` | `stkeffect != 0` 且 `fundeffect == 0` | `matchamt = 0` |
| `040153` | `fundsettdate != busidate` | `matchamt = 0` |
| `011424`, `021424`, `501424` | 融资借入 | `matchamt = 0`; 同时 `matchqty/orderqty/orderprice/matchprice/matchtime/matchtimes/seat` 等展示字段清空或置零 |
| `011425`, `021425`, `501425` | 融券借入 | 同上 |
| `013809`, `023809`, `508002`, `508003` | `subsMap` 中存在 `xsgsds_zrsramt` | `matchamt = subsMap["xsgsds_zrsramt"]` |

## 3. 预处理阶段具体赋值逻辑

### 3.1 上海 SHJS / shjsmx_handler.h

| 条件 / busitype | 来源字段 | 预处理赋值 | 后续 logasset 影响 |
| --- | --- | --- | --- |
| `zqlb=GZ` 且 `ywlx in 003,004,00D,352,353,601,605,611,631,691` | `shjsmx.cjsl`, `shjsmx.jg2`, `shjsmx.qsje` | `matchqty = matchqty / 100`; `matchamt = -matchqty * jg2`; `intramt = qsje - matchamt` | 若最终 `busitype` 命中 `SpecialDealIntramt()`，可能进一步合并利息 |
| `014901`, `014902`, `014903`, `014904` | `shjsmx.cjsl`, `shjsmx.qsje`, `shjsmx.jg2` | `matchqty = cjsl / 100`; `matchamt = -cjsl`; 其中 `ywlx=024` 购回：`intramt = cjsl + qsje`; `ywlx=023` 初始：按回购利率和天数计算 `intramt` | `014902`, `014904` 属于 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET`，最终 `matchamt += intramt` 且 `intramt` 保留 |
| `ywlx=117` | `shjsmx.qsje`, `shjsmx.jg2`, `shjsmx.cjsl`, `shjsmx.mmbz` | 报价回购初始：`intramt = round(abs(qsje * jg2 / 100 * days / 365), 2)`；`matchqty = cjsl / 100`；买入方向按 NODEX 主分区条件保留，否则忽略；卖出方向 `matchamt = -cjsl` | 后续是否合并看映射后的 `busitype` 是否命中最终特殊集合 |
| `ywlx=118` | `shjsmx.cjsl`, `shjsmx.qsje`, `shjsmx.mmbz` | 报价回购购回：`matchqty = -cjsl / 100`; 买入方向 `matchamt = -cjsl`, `intramt = qsje + cjsl`; 卖出方向 `matchamt = cjsl`, `intramt = abs(qsje - cjsl)` | `015302`, `015303`, `015305`, `015306`, `015309`, `015310` 等购回类最终通常 `matchamt += intramt` 且 `intramt` 保留 |
| `390` 且 `qsbz in 400,411` 且附加说明含“利息划付/划付(息)” | `shjsmx.qsje` | `matchamt = 0`; `intramt = qsje`; `busitype = 013911` | `013911` 在最终处理中 `matchamt += intramt`; `intramt = 0` |
| `390` 且 `qsbz in 400,411` 且附加说明含“本金划付”和“债” | `shjsmx.cjsl`, `shjsmx.jg2`, `shjsmx.qsje` | `matchqty = 0`; `matchamt = abs(cjsl / 100 * jg2)`; `intramt = abs(qsje) - matchamt`; `busitype = 013912` | `013912` 在最终处理中 `matchamt += intramt`; `intramt = 0` |
| `390` 且 `qsbz in 408,409` | `shjsmx.sl`, `shjsmx.cjsl`, `shjsmx.jg1`, `shjsmx.jg2`, `shjsmx.qsje` | 债券兑付/兑息：`matchqty = sl`; 若兑付且 `cjsl=0`，`matchamt = abs(sl / 100 * jg2)`, `intramt = abs(qsje) - matchamt`; 否则 `matchprice = jg1`, `matchamt = abs(cjsl / 100 * jg2)`, `intramt = abs(qsje) - matchamt` | 映射为 `013901/013902` 等时，最终可能 `matchamt += intramt`; `intramt = 0` |
| `014603`, `014604`, `014605`, `014606`, `014607`, `014608` | `shjsmx` 已填入的清算流水字段 | 写入 `matchamt`、`intramt` 到 `cleardetailsub` | 这些 busitype 属于 `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET`，最终 `matchamt += intramt` 且 `intramt` 保留 |

### 3.2 深圳 SZJS / szsjsmx1_handler.h

| 条件 / busitype | 来源字段 | 预处理赋值 | 后续 logasset 影响 |
| --- | --- | --- | --- |
| 默认赋值 | `sz_sjsmx1.mxqsbj`, `mxqssl`, `mxcjjg`, `mxzjje` | `matchamt = mxqsbj`; `matchqty = mxqssl`; `matchprice = mxcjjg`; `intramt = mxzjje` | 后续按 `busitype` 特殊集合处理 |
| `025306` 且订单编号与附加说明不同 | `sz_sjsmx1.mxddbh`, `mxfjsm` | `busitype` 转为 `025305`; `matchtype = MATCHTYPE_BDHTXH` | `025305` 最终 `matchamt += intramt` 且 `intramt` 保留 |
| `025303` 且订单编号与附加说明不同 | `sz_sjsmx1.mxddbh`, `mxfjsm` | `busitype` 转为 `025302` | `025302` 最终 `matchamt += intramt` 且 `intramt` 保留 |
| `HGCS` | `mxqsbj`, `mxqssl`, `mxcjjg`, `mxjsrq`, `mxqtrq` | 回购初始：按 `清算金额 * 利率 * 天数 / 365` 计算 `intramt = abs(购回金额 - abs(matchamt))` | 初始类是否合并取决于最终 busitype |
| `HGDQ` | `mxqssl`, `mxsfje` | 回购购回：`matchamt = -mxqssl * 100`; `intramt = mxsfje + mxqssl * 100` | 购回类最终通常 `matchamt += intramt` 且 `intramt` 保留 |
| `BJDQ` 且 `busitype in 025305,025302` | `mxcjsl`, `mxsfje`, `mxqssl`, `mxddbh`, `mxfjsm` | 报价回购购回：`matchqty = mxcjsl`; `matchamt = -mxqssl * 100`; `intramt = mxsfje + mxqssl * 100`; 同时重置委托日期/附加字段 | `025305/025302` 最终 `matchamt += intramt` 且 `intramt` 保留 |
| `BJDQ` 且 `busitype in 025306,025303` | `mxcjsl`, `mxsfje`, `mxqssl`, `mxddbh` | 同上，但委托日期/合同序号从 `mxddbh` 截取 | `025306/025303` 最终 `matchamt += intramt` 且 `intramt` 保留 |
| `JY00/JY01` 且 `mxqsjg > mxcjjg` | `mxqsbj`, `mxqssl`, `mxcjjg` | 债券交易净价拆分：`matchamt = round(-matchqty * mxcjjg, 2)`; `intramt = mxqsbj - matchamt` | 现券类命中特殊集合时可能最终合并利息 |

### 3.3 深圳 SZJS / szsjsjg_handler.h

| 条件 / busitype | 来源字段 | 预处理赋值 | 后续 logasset 影响 |
| --- | --- | --- | --- |
| 默认赋值 | `sz_sjsjg.jgqsbj`, `jgjssl/jgcjsl`, `jgcjjg` | `matchamt = jgqsbj`; `matchqty = jgjssl`，若为 0 则取 `jgcjsl`; `matchprice = jgcjjg` | 后续按 `busitype` 特殊集合处理 |
| `DJJX` 且 `busitype=023902` | `jgzjje`, `jgqsbj` | 债券兑付：`matchamt = jgqsbj`; `intramt = jgzjje`，若 `jgzjje <= 0` 则 `intramt = 0` | `023902` 最终 `matchamt += intramt`; `intramt = 0` |
| `DJJX` 且 `busitype=023901` | `jgzjje`, `jgsfje` | 债券兑息：优先 `intramt = jgzjje`，否则 `intramt = jgsfje`; `matchamt = 0` | `023901` 最终 `matchamt += intramt`; `intramt = 0` |
| `QPPX` | `jgzjje`, 债券税率 | 红利/利息派发：`intramt = jgzjje`; `intrtax = intramt * taxRate` | 命中最终特殊集合时可能合并到 `matchamt` |
| `HGDQ` | `jgjssl`, `jgsfje` | 报价回购购回：`matchamt = -jgjssl * 100`; `intramt = jgsfje + jgjssl * 100` | 购回类最终通常 `matchamt += intramt` 且 `intramt` 保留 |
| `BJDQ` 且 `busitype in 025305,025302` | `jgjssl`, `jgsfje`, `jgddbh`, `jgfjsm` | 报价回购购回：`matchqty = abs(matchqty)`; `matchamt = abs(jgjssl * 100)`; `intramt = jgsfje + jgjssl * 100`; 同时按 `jgddbh/jgfjsm` 设置委托信息 | `025305/025302` 最终 `matchamt += intramt` 且 `intramt` 保留 |
| `BJDQ` 且 `busitype in 025306,025303` | `jgjssl`, `jgsfje`, `jgddbh` | 同上；若 `jgddbh` 长度小于等于 10，`025306 -> 025305`、`025303 -> 025302` | 转换后的 busitype 仍属于最终保留 `intramt` 的集合 |
| `BJCS` | `jgqsbj` 与当前 `matchamt` | 若为 NODEX 主分区且 `jgqsbj > 0`：`matchqty = abs(matchqty)`; `matchamt = abs(matchamt)`；否则忽略 | 初始类是否合并取决于最终 busitype |
| `JY00/JY01` 且 `jgqsjg > jgcjjg` | `jgqsbj`, `jgcjjg`, `matchqty` | 债券交易净价拆分：`matchamt = -matchqty * jgcjjg`; `intramt = jgqsbj - matchamt` | 现券类命中特殊集合时可能最终合并利息 |

### 3.4 北交/股转 GZ

| 文件 | 条件 / busitype | 来源字段 | 预处理赋值 | 后续 logasset 影响 |
| --- | --- | --- | --- | --- |
| `gzbjsjg_handler.h` | 默认赋值 | `bjsjg.jgqsbj`, `jgjssl/jgcjsl`, `jgcjjg` | `matchamt = jgqsbj`; `matchqty = jgjssl`，若为 0 则取 `jgcjsl`; `matchprice = jgcjjg`; `intramt = 0` | 后续按 `busitype` 特殊集合处理 |
| `gzbjsjg_handler.h` | `jgywlb in 01,03,20,ZG` | `jgsfje`, `jgjssl` | `matchamt = jgsfje`; `intramt = jgsfje`; `matchqty = jgjssl` | 若进一步命中最终特殊集合，则可能合并利息 |
| `gzbjsjg_handler.h` | `jgywlb=20` | `jgsfje`, `jgjssl` | `matchamt = 0`; `intramt = jgsfje`; `matchqty = jgjssl` | `503802/503812` 最终 `matchamt += intramt`; `intramt = 0` |
| `gzbjsjg_handler.h` | `jgywlb in 31,34,35,60` | `jgzjje` | `intramt = jgzjje` | 债券兑付/回售/赎回/利息类后续按最终集合处理 |
| `gzbjsjg_handler.h` | `jgywlb in 36,37` | `jgsfje` | `matchamt = jgsfje` | 后续按 `busitype` 特殊集合处理 |
| `gzbjsjg_handler.h` | `jgywlb=DF` | `jgzjje` | `matchamt = jgzjje`; 市场改为北交所；委托日期置 0 | 后续按 `busitype` 特殊集合处理 |
| `gzbjsjg_handler.h` | `busitype in 500203,500204` | `matchqty`, `matchprice`, `jgqsbj` | 北交所债券买卖：`matchamt = -round(matchqty * matchprice, 2)`; `intramt = jgqsbj - matchamt` | 后续按 `busitype` 特殊集合处理 |
| `gzbjsmx1_handler.h` | `busitype in 500201,500202` | `matchqty`, `matchprice`, `mxqsbj` | 北交所债券买卖：`matchamt = -round(matchqty * matchprice, 2)`; `intramt = mxqsbj - matchamt` | 后续按 `busitype` 特殊集合处理 |

## 4. 代码位置索引

| 主题 | 文件 |
| --- | --- |
| `node_logasset` 基础赋值和最终特殊处理 | `macbs-base/library/macbs/comm/logasset_creator.h` |
| `BUSITYPE_MATCHAMT_INC_INTRAMT_UNSET` 宏 | `macbs-base/library/macbs/include/macbs_busitypes.h` |
| `node_cleardetail -> node_settdetail` 字段传递 | `macbs-base/library/macbs/dao/tables/node_settdetail_memdb.h` |
| 簿记阶段调用 `InitLogasset()` | `macbs-base/lbm_pro/macbs/cbs_book/book_deal/book_base/single_book.cpp` |
| 上海预处理 | `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/SHJS/shjsmx_handler.h` |
| 深圳明细预处理 | `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/SZJS/szsjsmx1_handler.h` |
| 深圳交收结果预处理 | `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/SZJS/szsjsjg_handler.h` |
| 北交/股转预处理 | `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/GZ/gzbjsjg_handler.h`, `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/GZ/gzbjsmx1_handler.h` |
