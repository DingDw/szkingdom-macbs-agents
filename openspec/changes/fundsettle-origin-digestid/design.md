## Context

需求背景见 `proposal.md`，需求编号为 FS-CBS-21457。本设计基于当前日终源码、`MACBS-V3` 拆分模型和 Gauss 全量基线，只规划增量交付。

- `frame.xml` 与 `cbs_report/export.cpp` 确认：中间表采用 `631005` 恢复、`631004` 分段、`631003` 处理；`631006` 独立执行二次汇总和正式表生成。普通客户流程配置也采用此链路。
- `cbs_report/base/report_result.h` 中 `CFundSettleMidRlt::GetKey` 是节点汇总键及合并重建键的公共落点，当前使用固定长度缓冲区。
- `fundsettlemid/fundsettlemid_createdata/node_fundsettlemid_createdata.cpp` 分别处理 `node_logasset`、`node_settdetail` 以及资产、余额、户数等来源。
- `nodexfundsettle/nodex_fundsettle.cpp` 中 `FundSettleMidSum` 再次组键，`Node2NodexFundsettleMid` 显式复制字段；`MakeFundSettle` 执行条件过滤，`GetFieldValue`读取当前中间记录，实际统计标识由`RecordOriginValue`回写。
- 源表 `origin_digestid` 使用 `KDT_VCHAR10`，长度为 10。用户已完成模型调整并同步到工作区，两张中间表的新增字段域为 `KDT_VCHAR32`，两个配置列表为 `KDT_VCHAR4000`。
- `comm_archive_cfg.sql` 已有两张中间表的文件归档配置，Gauss 基线存在 `his_nodex_fundsettle_mid`。用户确认本需求不涉及日切和归档条件修改，沿用现有条件；新增字段与既有历史表结构的兼容性仍需检查。

## Goals / Non-Goals

**目标：** 原始摘要从源数据到两层中间表完整保留；科目筛选使用精确集合语义；在原有七阶段及缓存机制内实现；摘要配置为空时仅跳过摘要筛选，分组与方向仍按摘要粒度。

**边界：** 不新增业务功能号，不扩展最终 `node_fundsettle` 展示维度，不改变业务识别和上游摘要生成，不配置未经用户提供的银行摘要到科目映射，不扩展日间模型。界面多选控件改造不在本次明确范围，配置字段本身支持逗号多值存储与读取。

## Decisions

### 1. 两层中间表采用同一摘要定义

两张中间表按用户已调整模型新增 `origin_digestid VARCHAR(32)`，使用 `KDT_VCHAR32`；现有源字段为 `KDT_VCHAR10`，透传时不截断。源值为 NULL 或空字符串时，业务层统一按无摘要处理，不凭 `busitype` 推断摘要。`node_logasset` 和 `node_settdetail` 路径读取原字段；资产、余额、户数等没有摘要的来源显式使用统一空值语义。派生记录根据来源保留摘要，不得因复用对象残留上一笔摘要。

`comm_fundsettleset` 两个列表字段拟使用 `VARCHAR(4000)`，允许 NULL，默认不设置过滤条件。该容量与现有业务类别列表一致，模型、SQL、DAO 中必须统一；采用显式列清单的配置维护、复制及持久化路径均检查新字段覆盖。

仅改过滤代码无法恢复已经合并丢失的摘要，因此必须同时交付结构与汇总修改。

### 2. 所有中间汇总键都包含原始摘要

扩展 `CFundSettleMidRlt::GetKey` 的参数与对象重载，覆盖直接生成、数组合并和重新生成路径；显式参数要求各来源提供摘要，避免遗漏调用点。检查键长度上限，使用能够容纳全部维度的实现，禁止截断导致不同摘要碰撞。

同步修改 `nodex_fundsettle.cpp` 的组键包装和 `FundSettleMidSum`，显式复制摘要到 `nodex_fundsettle_mid`。相同原维度且相同摘要可以跨节点合并，不同摘要必须保留为不同记录。金额与笔数累加规则保持原有定义。

`rebuild_node_fundsettle_mid.h`、`rebuild_nodex_fundsettle.h` 中源数据读取、恢复合并、物理库读写使用同样的字段定义。不要直接修改公共框架来实现模块内维度扩展。

### 3. 摘要按借贷侧及业务类别作为附加过滤条件

`pt_origin_digestid` 表示允许配置，`fd_origin_digestid` 表示禁止配置。两个字段均采用：

```text
Asset:busitypeA-111,222,333;busitypeB-111|Debtor:busitypeC-333
```

- `Asset` 对应贷方，`Debtor` 对应借方，大小写固定；两侧用英文竖线分隔，侧名后使用冒号，业务类别与摘要集合用连字符分隔，多个类别用分号分隔，多个摘要用逗号分隔。
- 可以仅配置一侧，侧顺序不限；重复侧及同侧同业务类别分组合并摘要并去重。去掉侧名、类别及摘要项首尾空白，忽略空侧段、空类别分组和空摘要项。
- 每个字段独立按“侧、实际中间记录busitype”选组；未配置该侧或类别、集合为空均不限制。原始摘要为空时直接跳过两项摘要过滤，仍受其他科目条件和重复统计检查约束。
- 侧内完整匹配业务类别和摘要，不支持通配符，不去掉前导零；同侧同类别命中禁止集合时禁止优先。另一侧或另一类别的配置不会参与当前匹配。
- 字段为NULL、空字符串、仅空白或竖线以及`Asset:;|Debtor:B-,,`均无有效限制。旧格式`111,222`及`B:111,222`不能继续使用，配置维护人员必须明确所属借贷侧后迁移。
- 未知侧名、缺少或重复冒号、类别分组缺少连字符、空类别、类别内含逗号或空白、类别超过16字符及摘要超过32字符均报告含模板、科目、字段和错误值的配置错误。分隔符为格式保留字符，不能作为业务类别的一部分；摘要中的连字符按摘要原文保留。
- 每条科目配置解析一次；格式校验不因记录摘要为空而跳过。业务代码使用明确的侧名称宏，模型、DAO、SQL类型与长度保持不变。

当前侧的通过条件为：`摘要为空 或 [（当前侧当前类别允许集合为空 或 命中允许集合）且（未命中当前侧当前类别禁止集合）]`。

### 4. 始终按摘要粒度处理方向

节点生成及`FundSettleMidSum`均按原有业务维度加`origin_digestid`汇总。核对组键、字段复制和缓存加载路径后，正常生成的同日中间表在该维度下已唯一；标准模式加载的上日记录按原日期独立处理。因此科目生成直接逐条处理中间记录，不再构造临时分组、合计视图或贡献列表。

普通科目在原有来源、证券类别、市场和日期检查通过后，对当前记录取值一次。明确配置借贷业务类别时仍由业务类别条件决定侧，摘要仅作为该侧附加条件；同时满足两侧沿用贷方优先。双方名称存在且业务类别均为空时，按当前记录金额正负选择侧，再检查该侧摘要规则，过滤失败不改投另一侧。

`HandWsbyw`逐条遍历真实中间记录，逐字段取值、判断方向及匹配该侧规则。零金额跳过、已统计标记及余额变动检查保留。空摘要跳过摘要过滤；配置为空只影响过滤，不改变摘要粒度。

例如其他维度相同，摘要111为+100、摘要222为-40，即使摘要配置为空，自动方向及未识别项也分别按贷方100、借方40处理。同摘要+100/-40在中间表汇总阶段已合为60。正式表仍按原科目和展示维度合计，不增加摘要展示列。

已删除`GetGroupFieldValues`、`GroupFieldValues`、`OriginSources`、`OriginGroupMap`、`AddOriginGroup`和`ForEachOriginGroup`。普通科目保留局部记录指针集合，保证精确业务类别与通配业务类别重复命中同一记录时仅处理一次。

`GetFieldValue`只读取当前记录并检查重复统计，不修改统计标记。调用方沿用两位小数统计口径，并保存本次字段索引；实际计入科目后，`RecordOriginValue`接收当前真实记录、金额、字段索引和方向，回写金额及标记。零金额及被过滤记录不回写。

### 5. 实现沿用现有阶段和访问层

新增数据访问使用 `CacheManager`，在 `Cache()` 阶段加载；整段只读的表优先 `CacheManagerPtr`。`Clear()` 处理局部缓存，`Write()` 按现有持久化职责输出，阶段只前进或结束。已有直接 `MemdbManager` 路径属于存量实现，不据此扩大新逻辑的直接访问范围。

用户已确认模型手工维护完成，核对工作区模型同步后再生成 DAO、表结构、缓存及物理库映射；关键方法、条件及统计口径写清业务注释，业务常量采用明确宏定义。

## Risks / Trade-offs

- 摘要拆分增加行数和缓存内存 → 以节点分片及最大摘要数评估增长，规则解析一次；候选去重集合限定在单规则生命周期。
- 正负轧差发生变化 → 强制覆盖同一旧键下 `+100/-40`、不同摘要的回归，无论过滤是否为空都按各摘要净额判断方向，明确与原跨摘要净额结果的差异。
- 统计标识和金额不一致 → 直接回写实际中间记录，检查被过滤数据可供其他规则使用，未识别项与小计合计一致。
- 历史中间数据无摘要 → 不伪造历史值；需要摘要分类的日期必须有原始源数据并从首次汇总重建。
- 归档使用 `select *`，新增列可能改变文件列数，历史表也可能列不一致 → 保持用户确认的现有日切和归档条件，检查归档消费者及历史表字段兼容，必要时同步历史表结构。
- 客户存在多个 `comm_fundsettleset.sql` → 默认新增字段为空，检查客户配置读取兼容性；仅对明确提供的客户及映射交付 DML。

## Migration Plan

1. 用户已确认模型调整完成且不涉及日切、归档条件修改。实施前核对已调整模型同步到工作区，并检查既有历史表字段兼容；当前提案不执行结构变更。
2. 在 `database/script/patch/gauss/fs_cbs/fs_cbs_comm/1.table/comm_fundsettleset.sql` 与 `fs_cbs_nodex/1.table/` 下两张中间表的同名 SQL 中维护增量 DDL。按确认的部署拓扑核对 node/nodex 实际对象，不将节点对象放入公共库；需要历史表时逐表新增其同名 patch。
3. 所有新增 SQL 注释标注 FS-CBS-21457；日切和归档条件沿用现状，本需求不生成条件变更脚本。全量基线仅供读取，不修改。
4. 协调部署结构、DAO 和报表代码，在生成任务开始前完成版本切换。先让新字段为空验证兼容，再配置经确认的摘要科目映射。
   非空摘要配置必须使用Asset/Debtor侧前缀和业务类别-摘要格式；旧纯摘要列表及旧业务类别:摘要格式需按实际侧和业务类别迁移，未启用的空字段无需补录。
5. 需要按摘要重算时从原始流水重新生成节点中间表，再运行尾处理；既有无摘要中间表不能仅运行尾处理恢复明细。
6. 回退时停用新增过滤配置并恢复匹配的旧程序版本，从源数据重新生成旧口径结果；新增数据库列可保留，避免通过删除列回退造成数据损失。

## Open Questions

- 模型及目标 DAO 已同步并完成静态一致性核对；日切和归档条件保持不变，既有 `his_nodex_fundsettle_mid` 仅同步新增字段。
- 实际启用摘要筛选的客户、模板、科目及摘要清单尚未提供；本变更先交付通用能力，具体配置在明确映射后维护。

### 单条记录的显式传递

单次处理的数据不保存在对象成员中。当前记录引用、局部金额和字段索引通过参数传给正式表累加和统计回写，收付差额关联只保存真实缓存记录指针。已移除m_pOriginSources、m_vecOriginValues及临时分组结构，无需每轮重置成员状态或异常清理。

## 临时磁盘重生成入口

- 功能号631049，导出DoPhydbNodexFundSettle，类CPhydbNodexFundSettle继承CNodexFundSettle，运行于nodex。采用单功能号七阶段模型，业务日期、settlekind和模板获取规则继承原入口；新增类覆盖Before、Cache、Clear、Write。partid可不传，基础参数层使用TryGetValue读取；无论是否传入，都一次处理全部源批次。
- Before不调用父类删除中间表和清空交收结算表的逻辑。Cache从comm磁盘读取六张指定配置表，使用拥有完整执行期生命周期的记录存储绑定CacheManagerPtr；按当前模板复制科目规则，排序并设置净手续费口径，初始化市场和存管银行列表。两张转换表按要求加载，但该入口不重新执行节点转换。
- CacheDict继续读取comm磁盘字典。nodex_fundsettle_mid由PhydbManager读取到CacheManager，按当前日期、模板加载所有partid；标准模式追加所有批次中上日生成、当日交收的交收流水。沿用日结类型筛选，补齐m_strBusitype通配值、m_szSumFlag和金额映射后重建索引，不依赖内存中间表或其他计算节点。
- Clear按源partid拆成局部工作集，各自调用原明细和小计合计方法。切换批次前清理科目缓存、结果映射和源记录关联，重建当前批次中间表索引。PrepareFundSettle显式接收当前源partid，补齐结果并独立校验金额，不逐批改写调用参数成员；所有批次结果累计到输出集合，避免原汇总键不含partid导致跨批次混算。原FlowClear仍调用FundSettleMidSum，正常入口在Write中显式传入原m_szPartid，行为保持不变。
- 按用户确认，临时入口仅更新nodex磁盘node_fundsettle。Cache不读取旧内存结果，Clear准备和校验各批次的应用缓存结果；Write由PhydbManager统一替换当前日期、模板及报表类型下全部批次的磁盘结果，空类型兼容NULL。本次无源数据的旧批次结果也随全量替换清除。应用缓存的Insert仅组织本次记录，不执行内存数据库DML；新入口无内存库删除、批量写入或写锁，不写中间表及交收结算表。原入口仍在自己的Write阶段调用内存库BatchInsert，行为保持不变。
- Linux的frame.xml和Windows的frame-win.xml同步注册631049；export.cpp导出类映射。cbs_report的CMakeLists.txt递归收集.h/.cpp并启用CONFIGURE_DEPENDS，新增实现文件可触发构建系统重新生成。原先不带该选项的GLOB只在配置阶段收集源文件；已有构建目录需重新配置并构建cbs_report，再替换实际加载的动态库。
- 未新增DDL或流程自动调度配置，临时入口通过功能号调用。配置和中间数据需已存在于对应磁盘库；本次仅实现代码，不执行数据库操作或上线调用。

### 磁盘批量插入参数容量修复

后续工作区中该DAO修复已不在当前源码，用户要求先增加写库前主键诊断，本次不恢复或进一步调整BatchInsert。

用户反馈仅传busidate=20260609、清空目标表后仍发生主键冲突。静态核对发现node_fundsettle的PhydbManager向量批量插入方法误用chunksVec.size()（批次数）设置参数数组容量，但实际循环写入chunkVec.size()条记录。修正为当前批次实际记录数，并在成功完成后返回输入记录总数，修正临时入口完成日志恒为0的问题。修复仅涉及该表的向量批量插入方法，不改变业务序号、汇总粒度和删除范围。尚未在报错环境复现，不能仅凭此源码缺陷断言主键冲突已解决。

### 写库前主键诊断

临时入口Clear在每批向m_fundSettleResults执行insert追加后立即校验累计结果，Write不再重复校验。采用局部map保存四字段主键(templateid,createdate,sno,partid)及首次出现的下标，逐字段比较，不拼接字符串，也不把busisno加入主键。发现重复即报告完整主键、首次及重复记录的零起始下标和busisno并抛出异常，终止当前批次，不进入磁盘写入；校验通过则记录累计条数。该诊断不修改生成结果、不去重、不重新编号，用于区分生成集合内部重复与磁盘写入阶段冲突。

### logflag来源日志

本节日志实现由下方“来源关系表”方案替代，保留来源追溯规则及成员集合设计。

GetFlowParam读取可选整数logflag，每次读取前恢复默认0，只有值为1启用新增来源日志。CPhydbNodexFundSettle的GetBusiParam显式调用父类参数阶段，两入口使用同一解析及开关。

按用户要求，来源集合改为成员m_fundSettleSources，恢复CreateFundSettleSum()及TotalFundSettle(objSet,rule)原有签名。CreateFundSettle每批开始清空成员集合，仅开启来源记录时在RecordOriginValue收集实际非零统计字段及取值。TotalFundSettle本次首次创建汇总键时重置对应来源，随后在实际累加借贷金额或计算值之后合并输入项来源，支持小计继续参与合计。来源项busisno严格小于目标，不会清除自身输入。来源集合按记录指针及取值字段去重，不改变现有金额、统计标记或收付差额关联。

所有汇总完成后，对最终结果逐条输出INFO级别WriteLog：先记录结果完整主键(templateid,createdate,sno,partid)、busisno、借贷金额、计算值和去重来源数，再为每条来源分别记录结果键与nodex_fundsettle_mid完整主键、busitype、origin_digestid，避免长列表日志截断。同一来源经多个汇总路径进入一个结果只输出一条关系；来源数表示参与的中间记录数，不表示金额贡献次数。被过滤、零金额未计入及重复统计拦截的来源不会新增关联；无非零来源的结果仍输出来源数0。

来源日志移至PrepareFundSettle补齐全部结果partid之后，LogFundSettleSources()直接从结果读取最终主键，不给原有汇总方法增加参数。普通入口沿用m_szPartid，磁盘入口沿用当前源partition.first。日志中源记录日期和partid保持原值，支持标准日结上日来源。输出后清空成员集合，避免跨批次保留源记录指针。日志描述本次生成结果，不代表磁盘写库已成功。未传logflag或值不为1时，不构造来源条目、不输出新增来源日志。

### 来源关系表

按用户要求不再逐条WriteLog，而在nodex磁盘库的nodex_fundsettle_rel_temp保存结果与中间记录关系。实际结果表名为node_fundsettle，保存完整结果主键templateid、createdate、sno、partid；来源除mid_sno外补充mid_templateid、mid_createdate、mid_partid，避免上日来源及跨批次同号记录歧义。另以fundsettlekind保存本次生成类型作为重跑范围标识，沿用GetFundSettleKindStr口径。同时保存mid_sumstr（varchar(32)，取值字段名）和mid_sumamt（numeric(19,2)，该字段参与计算的取值）。关系主键为双方完整主键八列加mid_sumstr，允许同一来源记录的多个字段分别留存。

PrepareFundSettle收集关系主键值到成员m_fundSettleRelations，不保留跨批次源指针。两入口Write在正式结果成功写入后调用WriteFundSettleRelations，普通入口仅替换当前日期、模板、类型及当前批次；磁盘入口替换同范围全部批次。删除和分批插入关系在同一事务内完成，失败回滚关系表；不宣称其与先前内存或磁盘结果写入是同一原子事务。每批参数数组容量等于当前记录数。空来源集合仍删除该范围旧关系，避免重跑残留。

用户确认继续由logflag=1控制，并明确该临时排查表不纳入模型，直接由代码动态建表。WriteFundSettleRelations在关系写入事务内、删除旧关系之前执行Gauss CREATE TABLE IF NOT EXISTS，字段为双方完整主键八列、fundsettlekind、mid_sumstr及mid_sumamt共十一列；双方主键八列及mid_sumstr构成关系主键。表名保持用户指定的nodex_fundsettle_rel_temp。采用持久化排查表供功能号结束后查询，不使用会话退出即消失的SQL临时表；不生成模型、交付DDL、日切或归档配置。logflag未启用时在DBSelect及DDL前直接返回，不访问该表。本次只修改代码，不直接操作运行数据库。


### 来源字段与取值追溯

FS-CBS-21457：修正排查表名为nodex_fundsettle_rel_temp。RecordOriginValue在字段实际计入科目后、乘借贷方向前保存字段名及取值，沿用日结计算的两位小数口径并保留符号；普通明细使用配置sumstr，未识别项使用当前残余字段。小计及多级合计传递这些字段来源，同一记录同一字段经过多个路径只保留一份原取值，不把汇总金额回填mid_sumamt。收付差额业务关联保持原有逻辑。

成员m_fundSettleSources继续承载当前批次来源，不改现有业务函数签名；PrepareFundSettle按值复制完整关系，切换批次后仍可安全写入。logflag=1时动态创建修正名称的新表，旧拼写表及旧数据不自动迁移或删除。
