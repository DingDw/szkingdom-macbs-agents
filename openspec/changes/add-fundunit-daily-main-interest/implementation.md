# FS-CBS-21645 实施与静态验收记录

实施日期：2026-10-09。变更：`add-fundunit-daily-main-interest`。本记录的数值是待运行验收的输入和预期，并非业务环境测试结果；按项目要求，本次未构建、未运行业务测试、未执行数据库脚本。

## 实际实现

参数 `67042` 新增 `INTR_FUNDUNIT_MODE_DAILY_MAIN`，值为 `'2'`。模式 `'0'`、`'1'` 的宏和默认值均保留。Gauss 日终 patch 仅更新 `sysid=86,paramid=67042` 的 `dictitem,paramname,remark`；不修改默认值、用户取值、全量脚本、模型及日间参数。

`m_mapFundunitSrcData`统一保存模式2各来源单元的余额、未交收、转账、六类历史索引、账号状态及日间调整，不使用`m_mapSrcData`另建主单元结果。各科目及流水分支不逐条查询主单元；全部输入缓存完成后统一调用`CompleteMainFundunitData()`，准备主单元并合并账号状态、待替换流水及调整。主子单元余额、未交收、指定单元转账和历史索引保持独立。

`CalcDailyMainAwardamt()` 复用原 `GetTodayAwardamt()/GetCumulativeMultiple()`，逐单元逐日期计算、乘倍数、分类，再合计分类日结果并仅在首次结息时向主单元追加非零利息、罚息积数。四个积数计算入口的模式2分支直接调用该方法，随后直接调用 `CalcDailyMainInterest()` 计算主单元利息。`CalcAwardamt()` 已移除模式2消费分支及提前返回，仅保留模式0/1算法；未使用的 `m_bDailyMainCalculated` 已删除。模式2的GenFundIntrdetail直接返回，不创建明细。首次结息才实际追加积数；日间沿原路径追加一次调整，日终不读取调整表。重复试算仍保持首次追加控制，原依赖明细的日积数和已结息展示暂保持默认值。

本模块新增的`Check()`覆写和`CacheDailyMainAccounts()`已删除。主单元指针和标志由Cache末尾的`CompleteMainFundunitData()`统一准备。共享、单客户基础资料保持现有加载方式。任务基础资料随有效簿记账号缓存，模式2补充状态流水独有账号，流水后关联加载全部资金单元；三种模式共用客户特殊利率和客户货币利率的有效账号过滤缓存，不加载客户计息模式及计息天数，不整分段扫描账号和单元。当前结算资料沿用户更新后的簿记及流水关联方式；无余额主单元结算资料和周期归主的评审问题仍待单独修复。子单元历史不检查或迁移。

`CalcDailyMainInterest()` 由四个模式2计算入口直接调用，`CalcAwardintr()` 的模式2分支及提前返回已删除。专用方法在主单元上一次计算、一次取整应收应付；已有行更新，结果变零也更新，缺失行仅非零时创建。所有新结果初始化均使用真实主单元。新模式税使用主单元最终应收，不依赖独立模式的 `m_dbTotalYSLX`。最低起扣比较沿用现有严格大于条件。

计息执行的只读基础资料仍用Ptr，单客户由物理库填充的资料仍用非Ptr；簿记和待写流水使用可修改CacheManager。归集方法仅使用已缓存的主单元资料，不重复加载表；模式2不加载或维护明细，任务重做和分段保持原访问层与处理范围，日终不读取调整表。

## 执行路径与写库边界

| 功能号 | 新模式链路 | 最终写库边界 |
|---|---|---|
| 627012（日终） | Cache统一单元输入/历史索引/主单元状态 → 主单元累计 → 一次利息；不加载调整表、不生成明细 | Write批量插入/更新内存簿记，跳过明细 |
| 627013 | 取参校验模式及extfundunit → 物理库输入副本 → Cache主单元状态 → 首次追加控制 → 主单元积数及利息 → 原26列账号整体结果；明细依赖展示暂默认 | PHASE_END，不执行结息写库；模式2仅接受未传、空值或0的extfundunit |
| 627014 | 取参校验模式及extfundunit → 同口径计算 → 一次主单元利息、罚息、税预交割 | 原物理库写入与簿记状态清理；模式2仅接受账号级入参，输入余额状态清理规则保持原行为 |
| 627017 | 原内存簿记翻滚 → Cache保存各来源单元索引和状态 → Cache末尾统一归主 → 客户筛选 → 账号计算 → 主单元预交割 | 原 Write 仅内存预交割主子表，不持久化临时簿记 |
| 627020 | Cache保存单元簿记索引及来源账号标志 → Cache末尾统一归主 → 周期/利率/机构规则 → 主单元正式流水；不加载或维护明细 | Write正式主子流水，跳过明细；不调用日积数计算 |

批量模式0/1/2当前共用原`RollFundbookkeeping()`：先通过MemdbManager准备当日簿记，再按原科目Cache分支保存单元索引。本轮不修改用户已调整的共用翻滚，不保留模式2专属翻滚列表或期初重置。后续Write仍仅写预交割主子表；不能将这一边界解释为此前翻滚未操作共享内存。

三种已结息标志及待替换业务流水，在模式2先保存到来源单元，再在Cache完成后统一归主，不依赖数组第一行。日间调整在全部输入完成后归集；转账保持所属单元，不搬移或清空，来源金额及待替换流水清空；税、明细和计算模式分支保持原行为。

## 缓存归属样例

账号 A 主单元 M、子单元 S1/S2：人民币余额分别 `40,100,-80`，未交收分别 `0,10,0`，S1 当日起息转账 `5`。输入集合是 `A/CNY/M=(40,0,0)`、`A/CNY/S1=(100,10,5)`、`A/CNY/S2=(-80,0,0)`；原 LXJS 模式倍数 1 时新增利息 `135`、罚息 `-80`。账号展示余额合计 `60`，未交收 `10`，转账 `5`，不能用展示净额 `55` 替代利息积数。

同账号美元 S1 余额 `7` 属于 `A/USD/S1`；美元累计 `7`，不进入人民币 `135/-80`。主单元历史利息积数索引保存在 `A/CNY/M` 或 `A/USD/M` 的单元记录，所有 WSJJSJE 索引只进入各自单元的未交收集合，不写入 YFZJLX 索引。

## 待运行验收矩阵

除注明外，使用 LXJS 模式、单日倍数 1、主单元有效、历史积数/未归本/调整/转账为零。年利率样例以 360 为除数；金额符号沿用原应付负数规则。四类簿记全部只归主单元；模式2暂不生成任何明细。

| 编号 | 输入与触发条件 | 预期结果及归属 |
|---|---|---|
| V01 | 主余额 40，子余额 100/-80 | 主新增 LJLXJS=140、LJFXJS=-80；主余额自身参与一次 |
| V02 | 主无余额行，子余额100/-80 | 主新增100/-80，试算上一日余额20，明细新增数0 |
| V03 | 历史 1000/-200，子新增 100/-80 | 主最终 1100/-280；不是覆盖为 100/-80 |
| V04 | 单元余额 10，未交收 30 | 基数 -20，但上一日余额非负，新增利息和罚息均 0 |
| V05 | 余额 -10，未交收 0，转入 30 | 基数 20，主新增利息 20，罚息 0 |
| V06 | 两个单元余额各 100，日利率 0.00006 | 未取整各 0.006，主一次 round(0.012)=0.01，不得为 0.02 |
| V07 | 主累计 100/-80，日利率 0.01，罚息日率 0.02，未归本 3/-2 | 主 YSLX=4.00，YFLX=-3.60；日利率除数 1 |
| V08 | 主累计 36000/-36000，年利率 0.036，罚息率 0.072 | 除数 360 时 3.60/-7.20；365 时 3.55/-7.10 |
| V09 | 日间路径，多个单元，当日调整日志合计 50，日新增 100 | 主累计仅加150；调整不会按单元数放大，明细新增数0 |
| V10 | CNY 余额 100/-80，USD 余额 7/-3 | CNY 100/-80；USD 7/-3，各币种主单元行独立 |
| V11 | 子余额-80，实库流水指定该子单元当日起息转入100，试算extfundunit未传 | 子基数20，主利息新增20、罚息0；试算仍返回全部账号贡献，非零extfundunit的入参转账不适用于模式2 |
| V12 | 主余额0，子-80，指定主单元的转账+100 | 转账留在主单元输入，主新增利息100、罚息-80，不与子余额轧差；不使用空单元兼容 |
| V13 | 两日子余额 100/-80，第二日正单元转出 150 | 第一日 100/-80；第二日正单元基数 -50 且原余额正，不罚息；总 100/-160 |
| V14 | 两日子余额 -80，第二日转入 100 | 第一日罚息 -80，第二日利息 20；主累计 20/-80 |
| V15 | 360 模式，非闰年 2月28日余额 100/-80 | 倍数 3，主新增 300/-240；闰年2月29日倍数2则 200/-160 |
| V16 | 360 模式 31日按原规则倍数0 | 当日新增均0；仍延续当日转账后的基数，后续日不能漏转账 |
| V17 | YSLX/YFLX 旧记录 5/-6，本次有效累计及未归本归零 | 更新原主单元行 endbal=0，新增应收/应付行数0 |
| V18 | 有主单元基础资料但无主余额；子利息合计10，税率20%，最低税额0.10 | 归本只产生一次主单元税 -2.00，主单元机构缓存可用 |
| V19 | 主利息0.45/0.50/0.55，税率20%，最低税额0.10 | 税取整0.09/0.10/0.11；严格大于起扣值，前两种无税流水，最后扣0.11 |
| V20 | 有计息输入但无真实主单元 | 主单元查询报错，写库不发生，不任取子单元承载结果 |
| V21 | 主累计1000/-200，子余额100/-80，子历史累计500/-300及应收应付、未归本科目非零 | 不因子历史记录报错；主最终1100/-280，利息仅使用主历史和本次增量，子历史不自动迁移或合并 |
| V22 | 结息标志仅存在子单元 S2 的已有流水 | 账号级标志为真，按原单客户/批量跳过或替换规则处理，不看单元首行 |
| V23 | 单客户首次历史1000，分类日新增100，调整50，日率0.01 | 试算主累计1150，利息11.50；结息只用主单元预交割，Write沿原状态清理 |
| V24 | 上例结息后当日累计endbal=0、startbal=1000，再以非首次标志处理 | 不再追加100及50；依赖明细的日积数及已结积数展示暂默认0；无新增自然日利息金额 |
| V25 | 日终已算当前累计1100、startbal1000，日间批量输入日新增100、调整50 | 沿原翻滚前置准备期初1000，单次计算结果1150，不为1250；后续Write仅写预交割，需在业务环境核对原翻滚对共享簿记的影响 |
| V26 | 627012完成1100/-280，执行627010后按同输入重做 | 恢复累计endbal为startbal，YSLX恢复期初、YFLX删除、明细清空；重做仍1100/-280，明细新增数0 |
| V27 | 模式2前序主累计1100/YSLX=0.11，627020归本后执行627018再重做，另有旧明细 | 只删除本任务主子流水，不恢复或修改旧明细；重做按主单元结果生成同策略流水，不重新累计 |
| V28 | 627020不归本或利率变化后恢复重做 | 明细保持原值，按原主单元结果重新生成同策略流水，其他单客户账号不变 |
| V29 | 日间调整50独有账号，无余额但有主资料和客户日率0.01 | 主累计50，利息0.50；Cache补齐客户专属参数，主单元输出；调整在原加载分支直接归主，不产生空单元行 |
| V30 | 参数0或1；包括主余额100/子余额-80 | 新方法早退，原汇总或独立分支执行；宏及默认0未改，旧尾差代码未改 |
| V31 | 日终积数及任务分段，账号只有调整日志50，无原有簿记及转账来源 | 调整日志不作为日终分段来源，日终不读取该表，也不据此创建累计或利息结果；日间批量新模式仍补充分段账号 |
| V32 | 日终主历史累计1000、本次日积数100，另有调整日志50 | 日终累计1100，不再次加载日志变为1150；日间按其原调整路径计算时可得到1150 |
| V33 | 模式2同日利息100、罚息-80，分别执行日终积数和日间试算 | 核心四类结果正确；GenFundIntrdetail在访问明细管理器前返回，明细新增数0；试算明细依赖字段默认 |
| V34 | 模式2任务归本、不归本、利率变化及重做，内存中存在旧明细 | 不加载、结息更新或专属恢复旧明细；任务主子流水生成和删除正常；模式0明细算法保持原实现 |
| V35 | 两个单客户入口，模式0或2，extfundunit=S1 | 在GetBusiParam报错“当前模式不支持资金单元级别的单客户结息”，不进入Before或Cache；即使extsno已处理也不绕过校验 |
| V36 | 两个单客户入口，实际配置模式1，extfundunit=S1 | 先读实际模式，通过本项校验；保留原单元编号拼接、试算筛选及结息范围，不宣称已修复模式1的extinfo归集 |
| V37 | 两个单客户入口分别在模式0/1/2下，extfundunit未传、空值或0 | 均通过本项校验，不拼接单元号；模式1试算不筛选单元，模式2账号级extinfo在缓存时明确绑定主单元 |
| V38 | 实际模式1但成员初始为默认0，或参数缺失采用默认0，extfundunit=S1 | 前者取参时更新为1并通过校验；后者按0拒绝，不能靠初始成员值判断 |
| V39 | 模式2任务分段包含有效簿记账号、仅有结息状态流水账号、无相关输入账号；主单元没有余额行 | 前两类账号的全部单元及两类客户利率资料就绪，无相关输入账号不加载基础资料或参数；无余额主单元结算资料覆盖仍待修复和验证；任务不重新累计积数 |
| V40 | 模式0/1/2有效账号分别配置特殊利率及税率、客户货币利率组及生效日、不配置客户利率；另有非处理账号配置 | 按原优先级使用特殊利率或客户利率组及对应税率、生效日，无客户配置时取公共默认；非处理账号不加载两表记录；三模式均无需客户计息模式和天数资料 |

## 分段、恢复与边界检查

`frame.xml` 与 `export.cpp` 核对三个三段式链路 `627010/11/12`、`627015/16/17`、`627018/19/20` 及单客户单入口 `627013/14`，动态库和执行方法保持原配置；无新功能号。所有原分段均以 `set<fundacct>` 和 `CalcSetRangeByBatchSize(...,"fundacct",...)` 生成区间，同账号全部单元及币种同片。

日终 `CAwardamtCalcRange` 恢复原实现；共享 `CInterestBaseRange` 不查询调整表。只有日间 `CInterestBatchSettleRange` 覆写 `CollectExtraRangeFundacct()`，在 Clear 的分段收集过程中通过 MemdbManager 补充当日调整账号，不按计息模式过滤。日终任务沿默认空实现，原簿记及转账分段来源保持不变；所有分段类均无新增调整 Cache 或中转集合。

积数恢复原范围已经覆盖新模式主单元累计利息、累计罚息、应收和应付，并清空账号明细。批量恢复原范围删除对应路径和业务类型的预交割主子流水；新模式没有额外簿记写库。

任务恢复在GetBusiParam读取模式；模式2仅在Clear写锁内通过MemdbManager按当日、本任务路径和利息类型收集主流水号、删除对应子流水，再沿原条件删除主流水。不读取资金单元、簿记或明细。原积数恢复的全表清理保持不变，本轮不新增模式2专属明细恢复。

## 实际静态检查

- 两仓 `git diff --check`：通过。
- 只对 C++ 修改行按 `pre-commit/.clang-format` 运行 clang-format，宏文件仅保留新增两行；未大面积格式化未修改代码。
- `python pre-commit/function_comments.py --directory lbm_pro/macbs/cbs_interest_deal --dry-run`：无违规、不写盘；既有若干头/源完整映射不足，工具跳过跨文件排序。
- 对所有修改文件执行 `sort_include.py --check`：见最终检查记录。DAO扩展备份不适用，本次未改DAO。
- 静态核对访问层：计息执行只读资料使用 Ptr、单客户沿非Ptr；任务重做类按用户明确授权全部使用 MemdbManager，不登记 CacheManager；其他同表缓存类型不变。
- 检查全部模式分支，引用位置见下方清单；新模式不会调用逐单元利息取整、尾差分配。
- OpenSpec 严格校验及两仓范围检查见最终记录。未暂存、提交、部署、启用参数、同步规格或归档。

## 验证限制

本记录证明静态代码落点、调用链及交付范围，数值场景尚待真实业务环境验证。运行验收应逐项记录缓存结果、实际四类簿记资产单元、明细新增数为零及流水主子表；需要恢复重做完整链路，不能将直接重复执行Clear当作有恢复前置的重做。历史结果只读取主单元，子单元历史记录不检查或自动迁移；SQL交付不会自动启用模式2。

## 模式分支位置清单

以下按本轮磁盘源码重新扫描。模式2以用户更新后的日终积数缓存为参考，先按来源单元保存，全部Cache完成后集中归主；此前缓存前移及直接定位主单元的记录仅表示历史实施过程，当前缓存设计见第18至22节任务及下方最新实施记录。

| 源码位置（相对 macbs-base） | 所在方法 | 处理属性 |
|---|---|---|
| `lbm_pro/macbs/cbs_interest_deal/awardamt_clear/awardamt_clear.h:52` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/awardamt_clear/awardamt_clear.h:54` | `Cache` | Cache末尾统一归主 |
| `lbm_pro/macbs/cbs_interest_deal/awardamt_clear/awardamt_clear.h:65` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/awardamt_clear/awardamt_clear.h:77` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/awardamt_clear/awardamt_clear.h:92` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/awardamt_clear/awardamt_clear.h:94` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/awardamt_clear/awardamt_clear.h:152` | `Write` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:137` | `CalcDailyMainAwardamt` | 专用方法声明或定义 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:180` | `CalcDailyMainInterest` | 专用方法声明或定义 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:655` | `GetInterestPublicParam` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:719` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:731` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:748` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:759` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:776` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:787` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:804` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:815` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:832` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:843` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:860` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:871` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:887` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:902` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:913` | `CacheCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1004` | `CompleteMainFundunitData` | 专用方法声明或定义 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1055` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1065` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1087` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1098` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1123` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1134` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1211` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1218` | `CacheYZZZSettdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1547` | `DealSettleData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.cpp:1754` | `GenFundIntrdetail` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.h:25` | `CalcDailyMainAwardamt` | 专用方法声明或定义 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.h:27` | `CalcDailyMainInterest` | 专用方法声明或定义 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.h:119` | `CompleteMainFundunitData` | 专用方法声明或定义 |
| `lbm_pro/macbs/cbs_interest_deal/interest_base.h:135` | `CompleteMainFundunitData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:161` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:185` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:208` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:210` | `Cache` | Cache末尾统一归主 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:228` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:243` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:259` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/interest_batch_settle/interest_batch_settle.cpp:261` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:48` | `GetBusiParam` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:54` | `GetBusiParam` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:106` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:139` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:155` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:157` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:218` | `DealReslutData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:235` | `DealReslutData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_calc/interest_single_calc.cpp:326` | `DealReslutData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:82` | `GetBusiParam` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:88` | `GetBusiParam` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:149` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:151` | `Cache` | Cache末尾统一归主 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:164` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:188` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:209` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:211` | `Clear` | 模式2直接调用专用计算方法 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:426` | `DealSettleData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:430` | `DealSettleData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:596` | `LoadBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:847` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:859` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:877` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:888` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:907` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:918` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:937` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:948` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:967` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:978` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:996` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:1008` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:1023` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:1034` | `CacheSingleCustBusiData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:1076` | `LoadIntrAdjustLog` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:1097` | `LoadIntrAdjustLog` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_single_settle/interest_single_settle.cpp:1144` | `InitBankTransAndDayIntrSett` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:74` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:86` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:103` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:114` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:130` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:141` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:157` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:168` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:184` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:195` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:211` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:222` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:238` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:249` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:268` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:315` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:325` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:341` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:351` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:367` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:377` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:390` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:411` | `Cache` | 各模式共用客户利率缓存 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:421` | `Cache` | 各模式共用客户利率缓存 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:430` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:439` | `Cache` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:441` | `Cache` | Cache末尾统一归主 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:453` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:485` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:542` | `Write` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:977` | `ProcPerData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:997` | `ProcPerData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle.cpp:1011` | `ProcPerData` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle_restore.h:26` | `GetBusiParam` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle_restore.h:38` | `Clear` | 模式判断；原模式路径保持不变 |
| `lbm_pro/macbs/cbs_interest_deal/interest_task_settle/interest_task_settle_restore.h:88` | `Clear` | 模式判断；原模式路径保持不变 |
| `library/macbs/include/macbs_dict.h:3215` | `宏定义或成员参数` | 模式判断；原模式路径保持不变 |
| `library/macbs/include/macbs_dict.h:3216` | `宏定义或成员参数` | 模式判断；原模式路径保持不变 |
| `library/macbs/include/macbs_dict.h:3217` | `宏定义或成员参数` | 模式判断；原模式路径保持不变 |

## 最终交付检查结果

- 12个修改的C++文件include顺序检查全部通过；业务方法注释检查无违规；修改行格式化完成。
- `macbs-base` 改动仅模块本地11个文件及模式宏1个文件；`macbs-service` 仅1份Gauss日终patch参数SQL。
- 两仓 `git diff --check` 通过；无新增表、模型、功能号、全量SQL、独立日间模块或日间参数SQL改动。
- `openspec validate add-fundunit-daily-main-interest --strict` 通过；设计已补记分段、缓存翻滚及恢复实现。
- 本次无构建、业务测试或数据库执行，40组验收是待运行场景；最新评审中的主单元结算资料及周期归主问题仍待修复。未提交、同步或归档。

## 补充命名规范核对（2026-10-09）

- 已重新读取发布目录和 `macbs-base` 的 `AGENTS.md`；按用户明确限定，仅对本需求新增加的变量、参数及其引用应用新增命名规范，涉及 8 个 C++ 文件，宏、类名及成员名已核对符合规范。
- 新增记录和键使用 `obj`，单元计算输入使用 `vec`，簿记及明细索引使用 `idx`，日期及位置使用 `n`，计息模式及天数配置使用 `c`，流水号使用 `str`，字符指针使用 `p`，结果集使用 `rs`，计算回调使用 `fn`。
- 已撤回对已有变量 `record`、`index`、`date`、`iDay`、`iDate`、`ret`、`nSettunitIndex`、`nIntrperiodIndex`、`nCustIntrperiodIndex`、`key1`、`key2` 的重命名；恢复关联引用及旧代码格式，避免扩大业务差异范围。新增分支仍使用已有变量原名。
- 根据命名修改前快照重新应用仅涉及新增变量的调整；逐 token 核对确认字符串、数字、运算符和业务流程未改变，并刷新上述源码行号。
- 12 个变更 C++ 文件的 include 顺序检查通过；业务方法注释检查无违规；两仓 `git diff --check` 通过；OpenSpec 严格校验通过。
- 遵循默认验证范围，本轮未构建、未运行业务测试、未执行 SQL，未暂存或提交。

## 删除子单元历史利息存量检查（2026-10-09）

- 按用户补充要求，删除对子资产单元历史累计利息积数、累计罚息积数、应收应付及未归本利息的非零判断和阻断报错；删除专用历史状态索引集合及前日校验来源。
- 主单元历史索引直接按日期、结算单元、资金账号、主资金单元、币种、科目主键读取，六类索引各归其位；保留主单元缺失和输入所属账号检查，子单元历史金额不自动归入主单元累计。
- 两个计算分段类删除为存量检查增加的历史簿记扫描及 include，只保留当日调整补充来源；原簿记及转账分段循环保持一致。单客户已有当日应收应付缓存保留，用于更新主单元结果和避免重复主键。
- 对照本轮修改前快照，确认日积数分类、利息计算、明细算法及原分段循环的代码 token 保持一致；静态确认专用集合和存量错误无残留，主单元六类索引读取对应正确。
- 12 个变更 C++ 文件 include 检查通过；业务方法注释检查无违规；修改行格式化及两仓 `git diff --check` 通过；OpenSpec 严格校验通过。规格和验收矩阵 V20/V21 已同步最新行为。
- 本轮未构建、未运行业务测试、未执行 SQL；未暂存、提交或归档，数值验收仍待业务环境运行。

## 任务重做改为直接操作内存库（2026-10-09）

本节保留此前实施记录；模式2的明细恢复已按最新要求移除，以文末记录为准。

- 按用户明确要求，`interest_task_settle_restore.h` 内全部读取、更新和删除改用 `MemdbManager`，移除 CacheManager include、缓存调用、Cache/Write 覆写以及跨阶段集合成员。模式在 GetBusiParam 读取。
- Clear 在原有内存库写锁内收集当日本任务路径及利息类型的账号币种和流水号，按主单元簿记恢复账号明细，检查直接 Update 返回值；按这些流水号直接删除子流水并检查返回值，最后沿原条件删除主流水。
- 对照修改前快照，7 项明细恢复字段的赋值及原主流水删除循环保持一致；主单元簿记和资金单元均只读，无重算日积数、全表明细恢复或子流水全表删除。
- 已核对 SelectByIdx_fundacct_mainflag、GetRecord、Update、条件 Delete 的 MemdbManager API 签名；确认所有恢复读写均在 Clear 写锁内，目标类无 CacheManager 或延后批量写入残留。
- 修改文件格式、include 顺序、业务方法注释、两仓差异检查及 OpenSpec 严格校验通过。本轮仅修改该重做头文件及 OpenSpec 文档，未构建、运行业务测试、执行 SQL、暂存或提交。

## 积数分段改为直接读取内存库（2026-10-09）

本节为此前访问层修改记录；按用户最新日终、日间边界，此处新增的日终调整查询已回退，以后续记录为准。

- 按用户本轮要求，仅修改 `awardamt_calcrange.h` 的访问方式：将调整表 include 替换为 MemdbManager，在 Clear 中读取模式，并在新模式下按当日查询调整记录，将账号直接加入原 `setFundacct`。移除新增 Cache 覆写和中转成员集合。
- 保留资金账号去重与分段维度、原簿记及转账查询条件，已有变量名称未调整。本轮未修改 `interest_base_calcrange.h` 或明细结息、重做逻辑。
- 已核对 MemdbManager 查询签名和只读回调，确认新模式及当日过滤保留，原分段循环和已有变量名与本轮修改前快照一致。格式、include 顺序、业务方法注释、两仓差异检查及 OpenSpec 严格校验通过。本轮未构建、运行业务测试或执行 SQL；任务现为 34/34 完成。

## 回退日终新增调整表消费（2026-10-09）

- 日终使用 awardamt_clear、interest_task_settle；日间使用 interest_batch_settle、interest_single_calc、interest_single_settle。本轮按该边界回退 Node_intradjustlog 的日终新增消费，不将原日终不读取该表视为遗漏。
- 删除 CacheDailyMainAdjustments 的声明、定义、调用及专用 include；awardamt_calcrange.h 恢复原有账号来源。日终仍保留新模式分算、主单元累计及转账账号基础资料补齐，原任务文件的未使用 include 保留。
- 共享分段类删除调整 Cache 和中转集合，日间批量通过专用覆写方法直接使用 MemdbManager 收集调整账号，日终任务默认不补充。日间原有批量及单客户加载、调整归集与核心计算不改动。
- 验收矩阵补充日终不因调整日志扩大范围或追加金额的 V31/V32，并明确 V09/V25/V29 的日间适用范围；数值场景仍未运行业务环境验证。
- 已对照修改前快照确认日间批量、单客户加载及核心计算未改动；积数分段文件与原仓库版本一致，共享分段除空扩展方法及调用外与原版本一致，日终任务未覆写该方法。格式、include 顺序、业务注释、两仓差异及 OpenSpec 严格校验通过；任务 38/38 完成，未构建、运行业务测试、执行 SQL、暂存或提交。

## 模式2暂不记录资金利息明细（2026-10-09）

- 按用户要求，现表单个todayawardamt无法分别记录同日利息、罚息积数，模式2暂不记录且不扩表；生成、加载、写入及任务重做分支均保留原因注释。
- 恢复原GenFundIntrdetail与结息明细算法，删除本需求的分类明细、更新登记及试算明细专属展示算法；模式2在生成与试算展示读取前直接返回，主单元积数、利息、罚息、税及余额计算保留。
- 任务只在模式0调用明细结息方法；模式2Cache/Write跳过明细，任务重做删除专属明细恢复及相关资料读取，只保留任务主子流水删除。原积数恢复的全表清理不调整。
- 原26列试算结构保持不变，transferamt、transferbal、todayadjustamt、todayawardamt、intrawardamt、intrsettamt、taxsettamt、days、intrdays、ratedays暂保持默认值；不增加替代明细。
- V33/V34补充无明细写入和原有明细不被任务更新的待运行场景；数值矩阵共34组，未构建、未运行业务测试或执行SQL。
- 对照本轮修改前快照，确认仅6个C++文件发生变化；分类日积数、主单元累计及利息计算保持一致，原明细方法与仓库原版本一致，仅生成方法增加模式2前置返回。试算的核心结果填充和任务主子流水删除未改变，模式分支清单已刷新。
- 修改行格式、6个文件include顺序、模块业务方法注释检查、两仓git diff --check及OpenSpec严格校验通过；任务42/42完成。未构建、运行业务测试、执行SQL、暂存、提交或归档。

## 单客户入口校验外部资金单元（2026-10-09）

- 两个GetBusiParam先通过m_objMixedCfg读取实际参数67042，沿用物理库查询及默认模式0；仅模式1允许非空且非0的extfundunit，其他模式在第一阶段直接报业务错误，提示“当前模式不支持资金单元级别的单客户结息”，同时附带模式与外部单元值。
- 未传、空值或0视为未指定资金单元，使用本地宏INTR_EXTFUNDUNIT_ACCOUNT表达0的业务含义；不拼接单元号，模式1试算也不按账号拼接出的单元号筛选。保留原变量名，本轮没有改变模式1的extinfo归集或结息流水范围。
- 模式2的单客户extinfo转账仅按账号级入参归主单元，实库流水仍按其资金单元分算；此前允许模式2传非零extfundunit的规格及V11已同步修订，新增V35至V38覆盖两个入口的模式和参数组合，待运行验收场景共38组。
- 对照本轮快照，代码变化仅两个取参方法、一条转账业务注释及interest_clear_common.h中的业务宏；其余缓存、计算、结息、写库和恢复逻辑保持一致。确认实际模式读取先于参数校验、单元拼接、Before防重及Cache加载；69处源码引用已核对。
- 修改行格式、3个文件include顺序、模块方法注释、两仓git diff --check及OpenSpec严格校验通过；任务45/45完成。未构建、运行业务测试、执行SQL、暂存、提交或归档。

## 按科目展开模式2簿记缓存（2026-10-09）

本节记录此前实现，双集合缓存与Check绑定已由下节最新调整替代。

- 按用户要求删除CacheDailyMainBookkeeping声明、定义和全部4处调用；模式2缓存逻辑回到通用客户缓存、单客户缓存及任务Cache的原科目分支，与模式1判断平级展示，不再在回调入口提前接管。
- 当日余额及前日未交收索引继续分别追加到单元输入和账号结果；当日六类积数、应收应付及未归本状态只建立账号结果，Check按主单元完整主键绑定索引。原辅助方法接受、但原科目分支未列出的模式2科目已显式展开，三个路径均保持八类科目的日期范围及归属。
- 批量前日七类科目仍只进入待翻滚集合；当日记录不存在才插入应用缓存，翻滚新余额同时加入双层输入，六类状态只建立账号结果，已有当日记录不重复追加。单客户模式2各分支继续直接返回LOOP_CONTINUE，原计数行为保持不变。
- 对照修改前快照，三个缓存方法中原模式1及汇总处理块分别7、6、7组保持一致；删除辅助方法后，目标缓存方法以外的代码及其他模块源码保持不变，含单客户参数校验、核心计算、结息、明细、写库和恢复。新增局部变量遵守命名规范，既有变量未重命名；91处模式引用已刷新核对。
- 修改行格式、4个文件include顺序、模块业务方法注释、两仓git diff --check及OpenSpec严格校验通过；任务48/48完成。38组数值场景仍待业务环境运行，本轮未构建、运行业务测试、执行SQL、暂存、提交或归档。

## 模式2统一缓存并取消Check补全（2026-10-10）

本节记录此前完成的重构；其中末尾主单元归集和专属翻滚已由当前源码及下节直接归属实现替代。

- 模式2按科目直接向`m_mapFundunitSrcData`保存八类输入或簿记索引；批量翻滚记录同步保存所属单元索引，已有当日记录不重复归集。删除Check覆写及无单元转账专用成员，不再使用`m_mapSrcData`保存模式2结果。
- 转账、日间调整、结息标志及替换流水先按来源单元缓存，Cache结束前归集账号状态至主单元；空单元临时行归主后删除。四个Cache实现均只调用一次主单元准备，单客户试算继承单客户结息Cache。五个Clear入口从统一集合仅处理主单元，试算余额展示独立汇总全部单元，分算输入不合并。
- 对照本轮修改前快照，模式0账号分支和模式1独立分支保持一致，13个核心计算、积数、税及结息方法保持原代码。日终不新增调整表消费，模式2仍不维护明细，单客户extfundunit校验保持不变。回调接受当日应付记录及任务前日未交收记录，保存有效缓存索引。仅有子单元历史索引的行不新增基础资料或存量检查。
- 本轮默认不构建、不运行业务测试、不执行SQL、不暂存、提交或归档；38组验收场景继续待业务环境运行。修改行格式、8个文件include顺序、模块业务方法注释、两仓git diff --check及OpenSpec严格校验通过；95处源码引用已按最终代码刷新，任务51/51完成。文档脚本误写的无关头文件已从本轮快照完整恢复，未扩大代码改动范围。

## 原Cache分支直接确定主单元及归属（2026-10-10）

- 删除CacheDailyMainAccounts声明、实现和四处调用。三处八类簿记分支直接准备主单元记录，再保存来源单元输入或历史索引；不通过Check或末尾方法补全。
- 六处结息标志分支直接将账号状态、待替换流水保存到主单元；两个日间调整分支直接累计主单元调整。CacheDailyMainTransfer直接将无单元转账归真实主单元，明确单元转账仍保留来源归属，不创建空单元或二次归集。
- 模式2账号、资金单元及主单元结算资料在原Cache科目处理前按本分段一次加载；原位置跳过同表重复加载。客户参数在原Cache按分段一次加载，避免调整独有账号丢失专属利率；单客户沿物理库已加载的非Ptr资料。未保留额外单元归属或子历史存量检查。
- 对照本轮快照，本轮仅修改六个目标C++文件，模式0账号分支、模式1独立分支及14个核心积数、利息、税、结息、主单元查询与共用翻滚方法保持一致。用户已移除的专属翻滚列表及应用缓存翻滚逻辑未恢复。日终未新增调整表消费，模式2不维护明细，既有变量未重命名。
- 修改行格式、六个文件include顺序、模块业务方法注释及macbs-base差异检查通过；两仓git diff --check、OpenSpec严格校验及114处当前源码引用核对全部通过，任务54/54完成。未构建、运行业务测试、执行SQL、暂存、提交或归档；38组数值场景仍待业务环境运行。

## 模式2积数方法合并（2026-10-10）

- 将CalcAwardamt的模式2消费块原样移入CalcDailyMainAwardamt，先分算全部单元、分类日结果，再由m_bIsFirstIntr控制非零增量仅追加到主单元。CalcAwardamt的模式2判断及提前返回已删除，原模式0/1计算保留。
- 日终积数、单客户试算、单客户结息、批量结息四处模式2入口直接调用专用方法；后续CalcAwardintr、首次调整控制及结果处理保持原顺序。日终任务不新增积数计算。删除当前仅剩声明、已无读写的m_bDailyMainCalculated。
- 对照本轮磁盘快照，仅修改七个目标C++文件：原CalcAwardamt剩余计算体、专用方法原分算部分及移入的首次消费块均静态等价；基类其他全部方法及四入口其余代码保持一致。缓存、翻滚、恢复、税、利息、写库和macbs-service脚本未改，既有变量未重命名。
- 修改行格式、七文件include顺序、模块方法注释、OpenSpec严格校验及macbs-service的git diff --check通过。本轮新增或修改行无尾随空白；macbs-base全工作区git diff --check仍报告本轮快照已有的两处空白：interest_base.cpp当前1024行、interest_base.h当前119行，均未由本轮引入，保留原状态。
- 当前源码114处模式或专用方法引用已重新扫描。未构建、未运行业务测试、未执行SQL，未暂存、提交或归档。

## 模式2入口直接计算主单元利息（2026-10-10）

- 删除CalcAwardintr中模式2转调用及提前返回；日终积数、单客户试算、单客户结息、批量结息的模式2分支直接调用CalcDailyMainInterest，与CalcDailyMainAwardamt顺序执行。
- 对照本轮修改前快照，仅修改五个目标C++文件。CalcDailyMainInterest和基类其余全部方法的代码保持一致，CalcAwardintr删除模式2分支后的模式0/1计算体保持一致；四处入口其余代码、首次控制、税和后续结果处理均不变。日终任务、缓存、翻滚、恢复、写库及macbs-service脚本未改，既有变量未重命名。
- 修改行格式、五文件include顺序、模块业务注释、静态对照及OpenSpec严格校验通过；当前119处模式和专用方法引用已刷新。macbs-service的git diff --check通过，本轮新增或修改行无尾随空白；macbs-base仍有修改前快照已有的两处空白：interest_base.cpp当前1018行、interest_base.h当前119行，保持原状态。
- 未构建、未运行业务测试、未执行SQL，未暂存、提交或归档。

## 按日终积数参考实现统一模式2缓存（2026-10-10）

- 以当前CacheCustBusiData按来源单元保存的实现为参考，单客户及任务的八类科目删除逐条准备主单元逻辑；任务三类流水状态改存来源单元。日间两处调整及extinfo解析直接复用资金单元集合，移除残留且无定义的CacheDailyMainTransfer声明和调用。单客户计数及LOOP_CONTINUE保持原值。
- CompleteMainFundunitData移至四个执行Cache末尾：日终积数在共享缓存后，批量在调整后，单客户在调整与extinfo后，任务在流水及基础参数后。试算复用单客户结息Cache，不重复调用。方法只定位主单元并归集账号级状态、调整与空单元转账，已归集来源清空，各单元余额、未交收、指定单元转账和历史索引不合并。
- 任务模式2原分段资料及四类参数整体从Cache前部移至末尾，查询管理器、范围及次数不变。共享与单客户资料加载方式保持原代码。日终不新增调整表读取，任务不重新计算积数；全部计算、利息、税、结果、翻滚、恢复及写库方法保持本轮快照。
- 对照修改前快照，仅修改六个目标C++文件；模块所有原独立模式分支及原账号结果写法保持一致。共享科目缓存仅移除归主调用，单客户科目仅删逐条主单元准备，来源字段及返回控制等价；四入口全部输入完成后只归集一次，归集方法不重新加载表或补全历史。macbs-service脚本保持本轮快照。
- 修改行格式、六文件include顺序、模块方法注释、静态对照、两仓git diff --check及OpenSpec严格校验通过。方法注释工具对既有头源非唯一映射仍跳过跨文件重排；本轮未写盘重排。当前128处模式和专用方法引用已刷新。未构建、未运行业务测试、未执行SQL，未暂存、提交或归档。

## 删除未指定资金单元转账兼容（2026-10-10）

- 用户确认实库转账记录均指定资金单元。删除CompleteMainFundunitData中按ISNULL判断空单元、转入主单元及清空来源转账的全部兼容代码；归集方法只合并账号状态、待替换流水和日间调整，不搬移或清空任何单元转账。
- 单客户模式2的extinfo仍按既有账号级业务语义处理，在解析缓存时直接使用真实主单元编号，不再生成空单元转账。extfundunit的模式校验及原模式0/1保持不变；实库转账仍按自身单元缓存和计算。同步注释、规格和V12显式主单元转账场景，第18节历史记录中的空单元兼容由本节替代。
- 对照本轮修改前快照，仅修改interest_base.cpp、interest_base.h和interest_single_settle.cpp三文件。除兼容删除及extinfo目标单元明确绑定外，其余全部方法、取参校验、各缓存范围、算法、翻滚、恢复、写库和macbs-service脚本保持一致；原变量未重命名。
- 修改行格式、三文件include顺序、模块方法注释、静态对照、两仓git diff --check及OpenSpec严格校验通过。未构建、未运行业务测试、未执行SQL，未暂存、提交或归档。

## 删除未使用的转账单元成员（2026-10-10）

- 删除interest_base.h中的m_szTransferFundunit声明，以及单客户试算、结息GetBusiParam中的两处赋值。试算继续拼接m_szFundunit并执行原单元筛选；两个入口的extfundunit模式校验及错误提示不变。
- 全仓lbm_pro和library扫描无残留引用；对照本轮快照，仅三个目标文件变化，删除三条无效语句后的其余可执行代码保持一致。include、模块方法注释和macbs-base的git diff --check通过。未构建、未运行业务测试、未执行SQL，未暂存、提交或归档。

## 任务结息基础缓存与通用逻辑一致（2026-10-10）

- 各模式均在有效簿记加载成功后缓存资金账号；模式2对仅由任务结息状态流水进入处理集合的账号补加载资料。流水处理后统一从账号关联全部资金单元，删除模式2整分段账号和单元扫描。任务四类客户参数保持原表、Ptr管理器及分段查询条件，增加有效账号过滤；从资金单元补齐无余额主单元的结算资料，末尾仍只归主一次。本节替代第18节中任务整分段基础缓存的实现。
- 保留任务专用科目、前日未交收输入、周期表、三类流水状态及流水回调return false。模式0/1处理账号及参数范围保持原实现，资金单元加载统一移到流水之后；模式2不维护明细、不新增日积数计算或调整表读取。没有直接以CacheCustBusiData替换任务缓存，避免遗漏旧模式已计算的应收应付利息。
- 对照本轮磁盘快照，仅interest_task_settle.cpp的Cache方法变更；簿记筛选及科目填充、三类流水分类状态、其余所有方法、其他模块源码和macbs-service脚本完全保持。新增回调参数遵守命名规范，既有变量未重命名。任务源码引用已按最终行号刷新，V39记录待业务环境运行的资料覆盖场景。
- 修改行格式、include顺序、模块方法注释、静态对照、两仓git diff --check及OpenSpec严格校验通过；任务68/68完成。未构建、未运行业务测试、未执行SQL，未暂存、提交或归档。

## 修复任务结息客户利率缓存遗漏（2026-10-11）

- 以用户当前代码为准，只修复评审第1项：在来源账号及资金单元加载完成后新增node_fund_special_intrrate和node_cust_curintrrate缓存。模式0/1/2共用Ptr管理器和分段查询条件，并通过objFundacctPreFilter过滤有效账号，不依赖其他功能号的应用缓存。GetIntrrate的特殊利率、客户利率组及公共默认利率优先级保持原算法。
- 未恢复已经删除的客户计息模式和计息天数缓存；任务不重新计算积数。评审第2项结算单元关联及第3项周期归主保持用户当前代码，仍待单独修复，第21节中的覆盖结论仅为历史记录。V40补充三模式客户利率、税率、生效日及无配置默认的待运行验收场景。
- 对照本轮快照，仅interest_task_settle.cpp的Cache新增两表加载块；删除新增块后原代码完全保持，其他模块源码及macbs-service脚本不变。新局部参数符合命名规范，既有变量未重命名；目标源码清单已刷新。
- 修改行格式、include、模块方法注释、静态对照、两仓git diff --check及OpenSpec严格校验通过；本轮任务2/2完成，累计70/70项已勾选。此任务计数不代表评审第2/3项已修复。未构建、未运行业务测试、未执行SQL，未暂存、提交或归档。
