# cbs_clear_match 清算配对模块知识库

## 模块定位

`cbs_clear_match` 是日终清算链路中的清算配对模块，核心职责是把 `node_cleardetail` 清算流水按 `comm_busidefine.matchtype` 指定的配对方式转换为 `node_settdetail` 交割流水，并在配对后生成交割流水子表、负债明细、周期流水归档更新、多头户不处理结果等衍生数据。

源码路径：`macbs-base/lbm_pro/macbs/cbs_clear_match/`。

文档按“主流程 + 配对方式”拆分，后续 AI 或人工阅读时优先从本文定位入口，再进入对应子文档。

## 入口索引

| func_id | frame.xml module | export 绑定类 | 执行方法 | 说明 |
|---|---|---|---|---|
| `680001` | `DoCalcRange` | `CClearMatchCaclRange` | `DoClear()` | 清算配对分段计算 |
| `680002` | `DoRestore` | `CClearMatchRestore` | `DoClear()` | 重做前恢复 |
| `680003` | `DoClearMatching` | `CClearMatch` | `DoClear()` | 清算配对主处理 |
| `680004` | `DoClearMatchManual` | `CClearMatchManual` | `DoClear()` | 手工配对 |

关键文件：

| 文件 | 说明 |
|---|---|
| `macbs-base/lbm_pro/macbs/cbs_clear_match/CMakeLists.txt` | 构建 `cbs_clear_match` 共享库，包含 `clearmatch`、`clearmatch_calcrange`、`clearmatch_restore`、`manualmatch`。 |
| `macbs-base/lbm_pro/macbs/cbs_clear_match/export.cpp` | 绑定 4 个导出函数。 |
| `macbs-base/lbm_pro/macbs/cbs_clear_match/clearmatch/clearmatch.cpp` | `680003` 主流程，负责参数、缓存、逐股东配对、后处理和写内存库。 |
| `macbs-base/lbm_pro/macbs/cbs_clear_match/clearmatch/singlematch/single_clearmatch_base.cpp` | 按 `matchtype` 路由到具体配对 handler。 |
| `macbs-base/lbm_pro/macbs/cbs_clear_match/clearmatch/matchhandler/` | 各配对方式实现。 |

## 推荐阅读顺序

1. [主流程与数据流](main-flow.md)：先看 `CClearMatch` 七阶段、缓存顺序、排序和失败兜底。
2. [配对调度总表](#配对调度总表)：确认 `matchtype` 对应的 handler。
3. 按业务配置进入对应配对方式子文档。
4. 需要重做、分段或人工认领时，再看 [分段、恢复与手工配对](range-restore-manual.md)。

## 配对调度总表

`CSingleClearMatchBase::MatchByMatchType()` 是所有单笔清算流水的配对路由。进入路由前会给清算流水补默认操作方式 `OPERWAY_DEFAULT` 和操作站点 `CClearMatch::GetNetaddr()`。

| matchtype | 宏 | 业务含义 | 首次 handler | 失败后行为 | 子文档 |
|---|---|---|---|---|---|
| `0` | `MATCHTYPE_BDHTXH` | 委托配对，本地合同序号 | `CMatchTradeBase` | 自动降级到 `CMatchAccount` 账户配对；若仍失败，进入二次失败处理 | [委托与成交配对](trade-and-match-match.md) |
| `1` | `MATCHTYPE_JJGSHTXH` | 成交配对，经纪公司合同序号 | `CMatchMatchBase` | 进入二次失败处理，默认会尝试账户配对 | [委托与成交配对](trade-and-match-match.md) |
| `2` | `MATCHTYPE_JYSHTXH` | 交易所合同序号委托配对 | 未实现 | 失败处理阶段可尝试账户配对 | [主流程与数据流](main-flow.md) |
| `3` | `MATCHTYPE_JDHTH` | 约定合约号委托配对 | 未实现 | 失败处理阶段可尝试账户配对 | [主流程与数据流](main-flow.md) |
| `4` | `MATCHTYPE_JGLS` | 历史交割流水配对 | `CMatchSettdetailBase` | 进入二次失败处理，默认会尝试账户配对 | [交割流水与周期配对](settdetail-and-period-match.md) |
| `5` | `MATCHTYPE_T0ZHYE` | T 日账户余额配对 | `CMatchAccountT0Base` | 进入二次失败处理 | [余额与市值配对](balance-match.md) |
| `6` | `MATCHTYPE_TM1ZHYE` | T-1 日账户余额配对 | `CMatchAccountTM1Base` | 进入二次失败处理 | [余额与市值配对](balance-match.md) |
| `7` | `MATCHTYPE_TM2CCSZ` | T-1 日持仓市值配对 | `CMatchAccountMktvalueTM1Base` | 进入二次失败处理 | [余额与市值配对](balance-match.md) |
| `8` | `MATCHTYPE_ACCT` | 账户配对 | `CMatchAccount` | 不再重复账户配对，失败后写多头户结果或挂账交割流水 | [账户配对](account-match.md) |
| `9` | `MATCHTYPE_TSPD` | 特殊配对 | `CMatchSpecialBase` | 进入二次失败处理 | [特殊配对与无需配对](special-and-ignore-match.md) |
| `*` | `MATCHTYPE_WXPD` | 无需配对 | `CMatchIgnoreBase` | 成功直接生成交割流水 | [特殊配对与无需配对](special-and-ignore-match.md) |
| `a` | `MATCHTYPE_ZQPD` | 周期配对 | `CMatchPeriodBase` | 部分业务可委托兜底，否则进入二次失败处理 | [交割流水与周期配对](settdetail-and-period-match.md) |
| `b` | `MATCHTYPE_TM1LINKSTKID` | T-1 正股持仓余额配对 | `CMatchAccountTM1LinkStkidBase` | 进入二次失败处理 | [余额与市值配对](balance-match.md) |

## 子文档索引

| 文档 | 内容 |
|---|---|
| [主流程与数据流](main-flow.md) | `CClearMatch` 的参数、缓存、逐股东排序、失败二次处理、后处理、写入。 |
| [委托与成交配对](trade-and-match-match.md) | `MATCHTYPE_BDHTXH` 和 `MATCHTYPE_JJGSHTXH`，含合同序号兼容、成交反查委托、北交所/股转兜底等。 |
| [账户配对](account-match.md) | `MATCHTYPE_ACCT`、委托失败后的账户兜底、多头户选择、默认账户配置。 |
| [余额与市值配对](balance-match.md) | `MATCHTYPE_T0ZHYE`、`TM1ZHYE`、`TM2CCSZ`、`TM1LINKSTKID` 的分摊逻辑。 |
| [交割流水与周期配对](settdetail-and-period-match.md) | `MATCHTYPE_JGLS` 和 `MATCHTYPE_ZQPD`，含 `comm_busidefine_refrule` 规则、周期流水归档。 |
| [特殊配对与无需配对](special-and-ignore-match.md) | `MATCHTYPE_TSPD` 的业务类型路由，以及 `MATCHTYPE_WXPD` 直接生成交割流水。 |
| [分段、恢复与手工配对](range-restore-manual.md) | `680001/680002/680004` 的分段、重做恢复和人工改配对账户。 |

## 二次开发落点

1. 新增普通配对方式：优先检查 `single_clearmatch_base.cpp` 的 `MatchByMatchType()` 是否已有分支；新增 handler 时同步注册 `REGISTER_CLEAR_HANDLER_CLASS`。
2. 新增某类特殊业务：优先落在 `CMatchSpecialBase::Match()` 的业务类型分支，必要时新增私有专项方法，避免污染普通账户或委托配对。
3. 新增周期配对业务：优先通过 `comm_busidefine_refrule` 配置完成，只有配置无法表达的委托字段、归档或专项金额逻辑才改 `CMatchPeriodBase`。
4. 调整失败兜底：优先看 `CSingleClearMatch100::MatchFailedCleardetail()` 和 `CMatchDefaultBase`，确认是否会影响挂账、多头户结果和默认账户。
5. 修改写库相关行为：清算配对阶段主要通过 cache manager 暂存新增/更新，真正写入在 `CClearMatch::Write()` 批量执行。
