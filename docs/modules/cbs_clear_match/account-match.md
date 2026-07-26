# 账户配对

本文覆盖：

- `MATCHTYPE_ACCT`：账户配对，对应 `CMatchAccount`。
- 委托、成交、交割流水等配对失败后的账户兜底。
- `CMatchDefaultBase` 的默认账户和挂账相关逻辑。

## 账户配对入口

`CMatchAccount::Match(CNode_cleardetail_memdb&)` 分两层：

1. `Match(objCleardetail, objRelatedAccount)` 只负责找出唯一账户组合。
2. 找到账户后，生成 `node_settdetail`，把配对类型置为 `MATCHTYPE_ACCT`，调用 `SetAccountMatchResult()` 和 `SpecialInitSettdetailExt()`，再执行 `AfterClearPair()`。

`SetAccountMatchResult()` 回填：

- `settgroup`、`settbody`、`orgid`、`brhid`、`trdsysid`、`coreid`、`fundacct`。
- `settunit`、`fundunit`、`stkholdunit`、`investtype`。
- 股转、北交所非交易业务缺少交易单元时，从股东账户表补 `trdseat`。
- `fundkind`、`fundlevel`、`fundgroup`。
- 非交易成交时间开关开启且 `matchtime == 0` 时补默认成交时间。
- 转融通专户资金划入/划出业务 `011508/011509/021508/021509`，如果股东为融券专户，则资金账号改用融资专户。

## 候选股东账户查找

常规路径按 `market + secuid + mainseat` 查 `node_secuid`，并通过 `FilterSecuid()` 过滤账户状态和指定状态。

特殊路径：

- H 股全流通业务：`BUSITYPES_HQLT` 使用 `QuerySecuidsHqltSpecial()`，通过核心参数中的 H 股全流通专用席位匹配。
- 沪港通/深港通账户共用：当 `PARAMID_GGT_ACCTMATCH_WITH_A_STKTRDACCT` 开启，且配对类型为账户配对或 T-1 余额配对时，沪港通可兜底查上海 A，深港通可兜底查深圳 A。
- 清算流水有交易单元且常规席位未命中：通过 `comm_seatconfig` 把交易单元转换为托管席位后再查股东账户。
- 深圳股票质押违约处置专用席位：可不校验原托管席位。
- 港股权证到账等非转托管业务：深港通/沪港通可不校验席位再查一次。
- 托管席位来源为中登且开启账户配对去席位兜底时，可按 `market + secuid` 再查一次。

`FilterSecuid()` 过滤规则：

- 是否允许当日销户股东配对由 `PARAMID_TODAYXHSECUID_COULD_MATCH` 控制。
- 需要检查指定状态的市场，普通业务要求已指定或首日指定；撤指定类业务要求未指定或当日撤指定。

## 候选资金账号过滤

找到股东账户后，按股东账户上的 `fundacct` 加载资金账号，并过滤：

- 当天以前已销户的资金账号。
- 币种不包含清算流水币种的资金账号。
- 若 `comm_busiconfig.fundaccttype` 有配置，还要按资金账号类型过滤。

若只剩一个资金账号，直接通过 `GetAccountByFundacct()` 查主资金单元、持仓单元、结算单元。

`GetAccountByFundacct()` 要求：

- 资金账号存在唯一未销户主资金单元。
- 主资金单元存在唯一未销户持仓单元。
- 结算单元存在且未在当日前销户。

## 多候选资金账号选择

多个资金账号先转为 `CRelatedAccount`，再按结算单元分组。

同一结算单元：

1. 只有一个资金账号，直接选中。
2. 只有一个主资金账号，优先主资金账号。
3. 多主或多辅时，通过 `comm_accountconfig` 精确选择 `fundunit + stkholdunit`。

不同结算单元，也就是多头户：

1. 先尝试 `comm_accountconfig`。
2. 再读取 `comm_busiconfig.pairfaildealtype` 决定多头处理方式。
3. `PAIRFAILDEALTYPE_SGPD` 或 `PAIRFAILDEALTYPE_PDDMRZH`：不自动选择，返回失败，后续手工或挂账。
4. `PAIRFAILDEALTYPE_MAXFUNDBAL`：选择上一日资金科目 `F100201` 期初余额最大的主资金账号；失败时转最晚开户。
5. `PAIRFAILDEALTYPE_MAXSTKHOLD`：选择证券科目 `S10001` 持仓余额最大的资金账号；失败时转最晚开户。
6. `PAIRFAILDEALTYPE_LASTOPEN`：选择开户日期最晚的结算单元，再回到同结算单元选择规则。

## 默认账户与挂账

`CMatchDefaultBase::Match()` 不是主路由中的 `matchtype`，主要供失败兜底使用。

默认账户触发条件：

- `comm_busiconfig.pairfaildealtype == PAIRFAILDEALTYPE_PDDMRZH`。
- 或配对类型是委托/成交，清算流水席位命中公共参数 `PARAMID_CHMX_DEFAULT_SEATS`。

默认账户选择：

- 通过 `comm_accountconfig` 按 `settbody + market + busitype + secuid + mainseat` 查默认资金单元和持仓单元。
- 回填资金单元、持仓单元、资金账号、机构字段、币种，配对状态置为默认配对。

二次失败处理在 `CSingleClearMatch100::MatchFailedCleardetail()` 中完成：

- 非账户配对失败会再尝试账户配对。
- 账户配对失败或多头户特殊场景会写 `node_mutisecuid_result`。
- 最终仍未成功时，调用 `BuildUnMatchedSettdetailext()` 生成挂账交割流水，挂账数量计入 `m_nHangCount`。
