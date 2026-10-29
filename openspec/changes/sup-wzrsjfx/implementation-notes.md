# 实施核对记录

## 2026-09-11：首次 apply 前置核对

- OpenSpec 模式为 `spec-driven`，apply 状态为 `ready`，共 42 项任务，当前完成 0 项。
- 工作区已有用户维护的模型及生成物改动；本次未修改模型、生成物或业务代码，也未执行构建、业务测试或数据库脚本。
- 业务口径评审已完成；SUP 连接及节点容量由实施环境已有配置提供，不编造部署值。

## 已核实一致的字段

| 对象 | 模型及生成物核对结果 |
| --- | --- |
| `comm_if_file.supflag` | 模型默认 `'0'`；C++ 及 Java 已有对应生成改动 |
| `comm_if_file_log.persiststatus` | 模型默认 `'0'`；C++ 已有对应生成改动，Java 尚未同步 |
| `sup_filedropdata` | 主键为 `intfid,fileid,id,busidate`；C++ 的 `id` 为 `kdt_bigint`，Java 为 `long` |
| `sup_filedropdata.dropruleid` | 与原始 `ruleid` 同域，C++ 为 `kdt_char` |
| `sup_filedropdata.dropruledesc` | 模型、C++、Java 均已使用确认后的字段名；C++ 为 `kdt_vchar128` |

## 待明确的结构差异

| 对象 | 当前 design | 当前模型与生成物 |
| --- | --- | --- |
| `sup_filedropignorerule.id` | `INTEGER` | 模型域 `KDT_BIGINT`；C++ `kdt_bigint`；Java `long` |
| `sup_filedropignorerule.rulecontent` | `VARCHAR(1024)` | 模型域 `KDT_VCHAR128`；C++ `kdt_vchar128` |

差异依据为 `macbs-service/database/pdma/split_pdm/MACBS-V3/tables/comm/sup_filedropignorerule.json`、对应 `domains/KDT_BIGINT.json`、`domains/KDT_VCHAR128.json`，以及 `macbs-base/library/macbs/dao/tables/tables_base/sup_filedropignorerule_memdb_base.h`。

需明确以上两字段采用当前模型还是 design。确定后同步工件和交付 DDL，模型及生成物由用户维护，不能由实现代码截断表达式来掩盖长度差异。

## 尚未同步的生成物

`macbs-service/service/modules/base/cbs-base-data/cbs-data-cbs/src/main/java/com/szkingdom/macbs/common/model/CommIfFileLog.java` 和 `src/main/resources/mybatis/base/CommIfFileLogBaseDao.xml` 均未包含 `persiststatus`。任务 2.2 已明确生成由人工确认，需补齐对应 Java 实体及基础 DAO/映射生成物，再核对完成标志读写链路。

任务 1.1、2.2 尚不能勾选完成；当前没有完成业务实现任务。恢复 apply 后继续沿任务清单实施，并保留用户已有改动。

## 重试核对及实施进度

- 用户确认字段以模型为准，已同步忽略规则的 BIGINT/VARCHAR(128) 及文件编号 VARCHAR(64)。
- Java CommIfFileLog 的 persiststatus 实体和基础映射已补齐。
- 已完成任务 1.1、2.1、2.6：核对字段，新增 Gauss COMM 字段及忽略规则 DDL、SUP 丢弃表 DDL、仅启用 SHJS/SH_JSMX01 的配置更新。
- 丢弃结果表的 C++ CacheManager 已补齐。用户补充确认忽略规则直接访问 COMM 磁盘库，因此忽略规则 CacheManager 不再是前置条件，代码使用现有 `CSup_filedropignorerulePhydbManager`。
- 上文首次核对的阻塞及 0/42 为历史记录，以本节和 tasks.md 最新状态为准。

## 忽略规则改为 COMM 磁盘直读

- 已同步 design、proposal、丢弃分析 spec，以及任务 2.2、2.5、4.5；保留其他手工调整和未完成任务。
- `CFileManage::Cache` 在 SUP 内存导入时切换 COMM，通过 `CSup_filedropignorerulePhydbManager` 按 `intfid/fileid` 绑定参数查询，并按 `id` 排序。成功、查询异常和预解析异常均经过恢复原连接路径；异常继续传播，不按无规则成功处理。
- 管理器的 `CacheAll()` 使用磁盘流读取到应用容器，不创建、查询或写入该表 MemDB。生成物中的记录类型或公共头文件引用不表示运行时访问 MemDB；本次未修改用户生成物。
- 每次运行先清空局部规则再重新读取。`CSupIgnoreExpression` 在 Cache 阶段预解析，导入线程仅对本次只读规则求值；`sup_filedropdata` 仍通过 CacheManager 保存结果。

| 场景 | 静态核对依据 |
| --- | --- |
| MemDB 无忽略规则表 | 业务读取仅调用忽略规则 PhydbManager；增量脚本仅在 COMM 建表，无该表内存加载配置 |
| 无规则或跨文件 | 查询同时绑定接口及文件；空规则集合保持 `dropignoreflag=FLAG_NO` |
| `in/and/等值` | 预解析形成条件列表；单条规则按 AND、多条忽略规则按任一命中求值 |
| 非法字段或语法 | 使用文件列名校验；预解析调用异常接口，不进入逐记录处理 |
| 修改、删除规则后重跑 | 每次 Cache 清空局部规则并执行磁盘查询，不复用上次规则 |
| 多线程、多记录 | 逐记录路径仅遍历局部规则，没有规则表磁盘查询 |
| 导出或直接导入磁盘 | 跳过 SUP 分析 Cache；不触发丢弃结果清理及写入 |

- 检查结果：OpenSpec 严格校验通过；本次涉及文件按仓库 clang-format 配置校验通过；include 顺序及方法注释检查无阻断项；已有文件的 `git diff --check` 通过。
- 未执行构建、业务测试或数据库脚本。以上为源码与配置静态核对，不代表运行环境验收通过；实际验证仍在任务 7.4 中保留。
- 任务 4.5 标记完成，当前总体进度为 4/42，其他任务保持原状态。

## 2026-09-12：继续实施及待确认边界

- 新增 660030 七表加载器及 Linux/Windows 注册，配置全表模式，类型 1 遍历全部源实例；同主键相同逻辑字段去重，不同内容报错。读取和冲突检查在 Cache，目标替换在 Clear/Write。实际模型表名为 `intf_sfhg_secuinfo`，工件已同步。
- SUP 子类保留全部源 id；过滤配置 1/6/4 预先报错，2/3/5/7/P 跳过自身专属因子，适用表达式和后续规则继续执行。表达式缓存按过滤器身份隔离，解析线程使用线程局部上下文。
- 文件开始时提交旧日志持久化标志失效；合法空文件也保留导入日志。忽略规则保持 COMM 磁盘直读；此处原新旧双缓存实现已由下文 2026-09-13 的 Before 三条件清理方案替代。
- Java 新增 supfile 模块及两个 bootapp 依赖；supFilePersist 按文件配置建立两条持久化配置，顺序调用 600003/600001，完整日志键在同一事务中更新完成标志。动态建表通过 MemdbManager 的字段和主键定义完成。
- 文件树已增加可选 supflag；查询 DAO/handler 已写入，采用配置标识符白名单及条件值绑定，并复用 SysConfigBizDao 按流程取得当前业务日期。查询与页面、权限配置尚未完成整体联调，因此 6.2—6.5 不勾选。
- 用户确认实例参数 `instid=9/instname=sup/partid=*/domainid=01/compute_node_num=1`；新增实例及字典增量、仅执行丢弃表的 SUP 初始化脚本。脚本未执行，数据库连接由部署管理提供。
- 用户随后明确 SUP 实例业务域为 `01`，已同步工件和实例增量 SQL；C++ 保留业务域相等判断，不新增通配。
- 静态检查：13 个 C++ 变更文件按仓库配置格式化，方法注释检查通过；七表字段及主键 traits 引用通过；660030 双平台注册唯一；C++ diff --check 通过；9 个 Java 文件语法解析通过；7 个模块及依赖 XML 解析通过；OpenSpec 严格校验通过。
- 未执行构建、业务测试、数据库脚本、提交或归档。任务图生成/资源释放、流程配置、页面和最终交付检查仍未完成；验收用例初稿见 acceptance.md，待剩余实现补齐后完成 7.3。

## 2026-09-12：业务域修正及实施收尾

本节替代前述阶段进度。已同步 `domainid=01` 到实例增量、流程模板、动态任务参数校验及 OpenSpec；X/T 仍比较席位与 SUP 上下文的业务域是否相等，域 `02` 等其他值不能通过该条件。

- 完成 `supFlowPrepare` 及动态任务图：Gauss 普通流程与 SUP 共用节点映射事务锁；同一事务提交映射和任务结果，重复准备复用，空启用清单不占用节点。引擎沿现有动态任务机制刷新准备后任务图。
- 完成步骤 40 的 `supFlowCleanup/660031`：核对节点归属、日期、持久化完成后清理本流程九张内存临时表，再释放引用配置及映射。失败保留恢复上下文，磁盘及完成日志不删。
- 完成查询、低代码页面及菜单增量。菜单 `606049900`，页面 `SupFileAnalysis`；使用只读业务日期、可选仅未导入条件、动态源列及原因/忽略列。字段元数据沿现有独立接口获取，分页保持项目统一返回结构。日期变化清空结果的页面运行验收仍待执行。
- 参数核对确认：现有 `FlowTaskExecuteHandler.parseParams` 将任务参数展开到 C++ 请求顶层，`CFileManage::Cache` 可直接读取。Java 持久化及清理调用补齐 `compute_node` 与现有节点调用别名，清理保留结算主体、步骤及任务日志上下文。
- 字典增量核对发现旧基线数据 INSERT 包含模型及建表 DDL 没有的 `settbody`，本变更增量已去掉该列；未修改旧基线脚本。
- 部署及回退清单见 [deployment-and-rollback.md](deployment-and-rollback.md)，全链路运行用例见 [acceptance.md](acceptance.md)。保留用户手工调整的任务描述及用户模型/生成物改动。

| 静态检查 | 结果与范围 |
| --- | --- |
| C++ 格式、include 和方法说明 | 15 个实际变更 C++ 文件应用仓库 `pre-commit/.clang-format` 与 include 脚本；格式检查无错误，头文件方法注释无阻断项；未改写提示中的无关历史注释 |
| 新增功能入口 | `660030/660031` 在 Linux/Windows frame 中各唯一注册，export、类及模块 CMake 对应；保留 `600003/600001/625092` 原入口 |
| Java 语法 | 14 个模块及相关变更文件解析无语法错误；主要任务模型 setter 与本地接口核对一致，不能替代 javac 类型检查 |
| XML 与 Mapper | 11 个模块及相关依赖 XML 解析通过；新增 Mapper 语句与 DAO 方法对应 |
| 页面资源 | 3 个 JSON 解析、18 个模板 JavaScript 函数语法检查通过；原低代码映射仅追加新项，旧历史页面不改动 |
| SQL 字段 | 流程、实例及字典共 5 处 INSERT 列与当前模型核对通过，菜单及 API 遵循现有增量结构；SQL 未执行 |
| 差异检查 | 实际变更范围 `git diff --check` 通过，未执行暂存、提交或覆盖用户模型生成物 |

当前任务完成 **41/42**；唯一未完成项为 **7.4 构建及业务运行验收**。按用户提供的 AGENTS.md“默认不执行构建，除非明确要求进行构建和测试”，本次未运行构建、应用启动、数据库脚本或业务测试，也未归档。静态检查不证明联调和运行验收通过。


## FS-CBS-7768：按本轮手工 design 调整重新 apply

本节记录上一轮调整，替代前文关于复用旧任务图、共享事务锁及固定样例实例校验的描述；加载任务数量及依赖以文末“唯一共享加载任务”记录为准。保留用户手工修改的按实际业务域选择实例、移除锁调用及 SQL 目录整理。

- `SupFlowService` 使用类型 9 实例集合识别本流程映射：有映射复用真实实例，无映射按任务当前业务域选择。分配、参数、结果分区及释放均取实际实例；没有固定 instid/instname/domainid/partid/compute_node_num 校验。持久化中的 sup 为原有配置路由标识，C++ 通用组件会映射到当前 GetInstname()；X/T 原本已比较 GetDomainid()，本轮核对保留。
- 每次准备先定位本流程预留编号范围内三类动态任务，删除其引用的临时持久化配置、任务结果和任务，再按当前启用文件生成新结果编号及任务。`import_result_id` 引用新导入结果。空清单也执行旧任务删除；映射和全部任务变更处于同一 COMM 事务。
- 后续步骤和占位、清理模板执行状态重置，定义及编号保留；其他流程、原日志及磁盘结果不删除。新的任务和结果以 runflag=0 等待前置驱动。
- 动态任务使用 PRE_RECORD；每个导入同时依赖自身加载及末个串行加载，满足允许跨步骤激活且全部加载完成再导入。持久化依赖自身导入。
- 成功准备回调立即刷新流程任务图，清除当前流程的完成/驱动缓存；兼容旧驱动入口的重建刷新。清理检查覆盖所有持久化任务，包括尚未激活的任务。
- 移除本变更新增的共享映射表锁、流程行锁及无用 DAO 定义；普通 DayInit 和映射 DAO 已恢复至原逻辑，无对应差异。未恢复用户已注释移除的锁或固定值校验。
- 采用用户整理后的 `2.data/flow/9_全量数据导入分析/comm_flowrecord.sql`，去掉准备及清理模板中的 instid=9 参数。原启用示例旧路径已不存在，按当前文件目录约定补齐 `2.data/file/01_SHJS/comm_if_file.sql`，仅启用 SHJS/SH_JSMX01，注释使用用户确认的 FS-CBS-7768。部署清单同步现有脚本路径，不还原旧目录。

静态核对结果：14 个 Java 文件语法解析、5 个模块 XML 解析通过；新增 Mapper 绑定、重置 SQL 字段与当前模型核对通过；C++ 清理入口按仓库格式及 include 规则检查通过；变更范围 diff --check 通过；OpenSpec 严格校验通过。任务图边界依据现有 PRE_RECORD 激活、runflag 驱动和步骤状态统计逻辑核对。

当前 **41/42**，本轮重新打开的 11 项已完成。**7.4 构建和业务验收未执行**，未执行数据库脚本、提交或归档。新增的非样例实例、任务重建、空清单、状态重置和缓存失效运行用例已写入 acceptance.md，不能以语法及静态检查代替业务验收。

## FS-CBS-7768：唯一共享加载任务

本节记录本轮手工 design 的最新调整，替代前文逐文件串行加载及导入等待末个加载的实现说明。

- 已同步 proposal、design、全量导入 spec、tasks、验收和部署回退说明，保留其他手工修改。非空清单只生成一个编号 `100100` 的 `660030` 任务及对应结果，前置为当前准备任务，使用实际实例参数及 `cfg_group=sup`，不绑定接口或文件。
- `SupFlowService.prepare` 在文件循环前生成共享加载任务；循环内仅生成文件导入和持久化。所有导入前置均为 `100100`，各持久化仍依赖自身导入。非空清单动态任务及结果数量均为 `1+2×文件数`。
- 空清单提前返回发生在旧任务清理之后、节点新分配及共享加载创建之前。已有节点复用、事务回滚、PRE_RECORD、初始 runflag=0、状态重置和缓存刷新逻辑保持。
- `SupFlowDao.xml` 保留旧加载编号段 `100100～190099` 的清理条件并补充业务注释，兼容删除旧版逐文件加载任务及结果。本轮未修改 C++、数据库脚本、模型或页面；既有 C++ 加载入口使用实例上下文及配置组，不依赖单文件参数。
- 已补充两文件生成五个动态任务、共享加载失败阻断全部导入、旧版任务重建和空清单验收场景；升级后按部署说明重做准备，不能沿用旧任务图。

验证结果：本轮修改的 Java 文件语法解析、Mapper XML 解析及尾部空白检查通过；模块范围 `git diff --check` 通过（未跟踪文件另行检查）；OpenSpec 严格校验通过。静态核对共享加载位于文件循环外，空清单不生成加载任务，所有导入均指向共享加载任务。以上不能替代 Java 编译或流程运行验收。

本轮重新打开的 3.2、3.4、7.2、7.3、7.5 已完成，当前 **41/42**。按 AGENTS.md 约定，**7.4 构建和业务验收仍未执行**；本轮未执行数据库脚本、提交或归档。

## FS-CBS-7768：supFlowCleanup 改为 Java 直接释放

本节为清理行为最新口径，替代前文调用 `660031` 清理九张内存表后释放映射的描述；唯一共享加载及其他已确认业务规则保持。

- 已按手工 design 同步提案、全量导入规范、任务、验收及部署回退说明。`SupFlowCleanup` 保留全部持久化任务及结果完成检查和业务日期核对，随后直接调用 `SupFlowService.release`，成功或异常后均恢复原数据源。
- 移除节点映射遍历中的执行上下文查询和 `CallNodeUtil` 远端调用及其依赖。清理仅在 Java 的 COMM 事务内先删本流程任务引用的持久化配置，再按实际 `insttype=9` 实例集合删除本流程 SUP 映射；异常停止后续操作，事务回滚。内存数据、磁盘结果、任务结果及日志保留。
- 删除 `SupFileConst.CLEANUP`、`sup_memdb_cleanup.h/.cpp`、对应 export 宏和 include，以及 Linux/Windows frame 中的 `660031` 注册。模块 CMake 采用带 `CONFIGURE_DEPENDS` 的源文件扫描，无需新增或保留删除文件的显式条目。加载 `660030` 和持久化入口保持，Java 清理 BEX 与流程配置保持。
- 验收说明已补充纯 Java 清理、内存保留、其他流程隔离、持久化未完成阻断、配置/映射删除失败回滚、空清单及重复清理场景。本轮未修改模型、数据库脚本、页面或其他手工代码。

静态检查：3 个 Java 文件语法及尾部空白检查通过；6 个模块及 frame XML 解析通过；两端 frame 已移除清理并保留唯一加载注册。实际代码及运行配置无旧清理入口引用；C++ export 按仓库 pre-commit 的 clang-format 配置及 include 排序脚本检查通过，方法解析确认仅含导出宏、无类方法声明定义需要补注释。变更范围 `git diff --check`、OpenSpec 严格校验通过。上述结果不代表编译、数据库事务或业务运行验收通过。

本轮重新打开的 3.5、5.5、7.2、7.3、7.5 已完成，当前 **41/42**。**7.4 构建和业务验收未执行**，未执行数据库脚本、暂存、提交或归档。

## FS-CBS-7768：配置驱动加载、业务域范围和四字段账户投影

本节为加载行为最新口径，替代前文固定七表、跨全部业务域及全字段账户快照加载说明；唯一共享加载任务和纯 Java 成功清理保持。

- 已同步 proposal、design、全量导入 spec、tasks、acceptance 和部署回退说明。原表集合保留为初始化示例，运行按精确配置组、启用及目标类型选择，不校验七表或固定数量。忽略规则继续通过 COMM PhydbManager 读取。
- CSupMemdbLoad 缓存当前 GetDomainid() 下的类型 1 实例，逐表遍历全部匹配实例。模块内 CMemdbSyncShared.DBSelect 改为可派发，SUP 局部覆盖类型 1 路由；其他类型及普通加载入口继续走原实现。来源统计和读取均使用当前实例。
- 复用 CMemdbSyncShared 的 SQL 参数替换、取模分段、按条数分段、按来源表结算分组分段及流读取。SUP 的一个目标节点覆盖完整取模余数；没有依赖普通节点序号得到的余数子集。普通加载组件实现未添加 SUP 条件分支。
- 账户映射使用局部 CSupAccountmappedMemdbManager，仅向 SQL 重写器提供四字段元数据，并只解析 market/secuid/fundacct/settunit；其他属性保持模型默认值，不补查。原 SQL 的过滤条件保留，SQL 方式必须带取模占位符；原全表方式可在 SUP 内适配，空表方式仍只清表。
- Cache 加载配置及实例，Clear 通过通用加载管理器只替换本次配置目标表并分段写入。通用加载基础设施在 Clear 写入，不宣称仍由 Write 统一提交快照。合并依据真实模型主键及逐字段逻辑内容，排除对象填充及扩展字段，字符串长度编码避免分隔符碰撞，浮点正负零按相等处理；同键不同内容明确失败，失败阻断后续导入，重做替换配置表。
- 仅更新 Gauss 日终 patch 的 comm_memdb_load_cfg.sql 中 FS-CBS-7768 片段，账户映射改为四字段 settgroup 取模 SQL，保留用户维护的示例源类型及其他需求片段。没有修改 full、模型、Java 或页面。

验证：SUP 头/源文件按仓库 clang-format 和 include 排序规则检查通过，头文件方法注释规范化后检查无待修项；三个 C++ 文件语法解析通过（源文件仅替换字符串宏以供解析，不是预处理或编译验证）。四字段及 settgroup 与当前 MACBS-V3 模型核对一致；跨域筛选、取模完整覆盖、四字段 SQL 重写、主键合并、源实例路由及失败阻断已作静态路径核对。变更范围 diff --check 和 OpenSpec 严格校验通过。构建、数据库执行和业务运行未执行，性能及联调结果仍待验收。

本轮重新打开的 2.5、3.3、3.4、7.2、7.3、7.5 已完成，当前 **41/42**。**7.4 构建及业务验收仍未执行**，未暂存、提交或归档。


## FS-CBS-7768：取消加载主键冲突处理并对齐手工加载调整

本节为加载行为最新口径，替代上一节关于主键合并、字段比较、同键异值报错和外部账户 SQL 配置的说明；保留用户在 design 中注释掉的旧设计作为编辑记录。

- 同步 proposal、design、全量导入 spec、tasks、acceptance 及部署回退说明。移除 SUP 的 m_seen、MergeBatch、RecordFields 及无用依赖；读取批次直接调用 WriteLocalVecToMemdb 默认插入或更新，不额外去重或比较内容。底层读取及写入异常仍由通用读取回调捕获并向加载入口传播，失败阻断导入。
- 保留用户简化的配置遍历、取消提前创建管理器及账户只接受全表配置的调整。账户全表配置在 Cache 内转换为四字段 settgroup 取模 SQL，以保持既定的完整取模分段；外部 SQL 配置明确报错。四字段 SQL 重写、流解析和未读取属性使用模型默认值保持。
- 补齐空表方式的清表后跳过读取分支，不为该方式创建源实例读取或分段任务。类型 1 继续遍历当前业务域全部源实例，其他来源继续通用路由。
- Gauss 日终 patch 的 FS-CBS-7768 账户映射配置同步为 load_method=0、executesql=NULL，保留用户维护的源类型和其他需求 SQL。本轮未修改模型、full 脚本、通用加载组件、Java 或页面。

静态检查结果：两个 SUP C++ 文件按仓库 pre-commit 配置完成 clang-format、include 顺序、方法注释及尾部空白检查；语法解析通过（仅为解析替换字符串宏，不代表预处理或编译）。专用主键索引、字段序列化及冲突处理无残留；静态核对通用管理器默认插入或更新及异常传播、账户内部取模转换和空表跳过读取路径。变更范围 git diff --check 和 OpenSpec 严格校验通过，未跟踪的 SUP 文件另行检查。验收说明覆盖外部账户 SQL 拒绝、多实例通用写入及底层失败阻断。

本轮重新打开的 2.5、3.3、3.4、7.2、7.3、7.5 已完成，当前 **41/42**。按 AGENTS.md，**7.4 构建及业务运行验收仍未执行**；未执行数据库脚本、暂存、提交或归档。静态检查不代表运行验收通过。


## 2026-09-13：FS-CBS-7768 复用通用加载双队列线程模型

本节替代上一轮在分段回调中同步读写的实现说明。已同步 design、proposal、全量导入 spec、tasks、验收和部署回退工件。

- CSupMemdbLoad 改为继承 CAsyncMemdbSync，清空本次配置目标表后调用一次 AsyncLoad，直接使用父类 m_PrepareQueue、m_ProcessQueue、准备线程、读取线程池和独立写入线程；删除同步 LoadBatches。空配置直接结束，空表配置仅清表，不生成读取任务。
- 通用类增加分段生成、管理器创建和单批读取三个可派发扩展点，原普通加载作为默认实现；AsyncLoad 的线程启动、异常汇总、等待和 WriteDataThread 保持原实现。SUP 复用同一份参数，threadnum 控制真实读取并发，队列容量及 timeout 由通用参数函数处理。
- 模块内 CMemdbLoadTask 在分段入队时复制源实例，出队及线程池提交均保留该类型。SUP 单批读取建立独立来源适配器，不使用准备线程可变来源；当前域筛选、按源统计和四字段完整取模投影保持。此运行时任务类型不属于模型或 DAO 生成物。
- 读取回调只将管理器加入 m_ProcessQueue，写入使用通用 WriteDataToMemdb 的批量插入及失败后插入或更新策略；不增加 SUP 主键冲突处理。通用背压、退出标记、活动读取任务超时诊断及等待已提交任务结束的策略保持。
- 本轮只修改 async_memdb_sync.h/.cpp、sup_memdb_load.h/.cpp 及 OpenSpec 工件；未修改模型、DAO、数据库脚本或 Java。入口 600000/660030、export 映射及 CMake 源文件扫描保持，部署及回退需整体更新 cbs_memdb_sync 库。

静态检查：四个 C++ 文件按仓库 clang-format、include 顺序、UTF-8、方法注释及尾部空白规则检查通过；语法解析通过（仅为解析替换字符串和计时宏，不代表 C++ 预处理、编译或类型检查）。与本轮修改前快照比较，AsyncLoad 和 WriteDataThread 函数实现保持；普通分段逻辑移入默认扩展点。双平台 frame XML 解析通过，600000/660030 各唯一注册；变更范围 git diff --check 通过，未跟踪 SUP 文件另行检查。OpenSpec 严格校验通过。

本轮五项任务已回填，当前 **41/42**。按 AGENTS.md 默认不构建的约定，**7.4 构建及业务运行验收仍未执行**；并发、队列背压、来源交错、异常及超时运行用例已补入 acceptance.md，不能以静态检查代替运行验收。未执行数据库脚本、暂存、提交或归档。


## 2026-09-13：FS-CBS-7768 持久化数据源与按删除条件重建

本节替代此前持久化配置固定 dbname=sup 以及 CREATE TABLE IF NOT EXISTS 保留已有表的实现说明。

- SupFilePersist 将当前任务参数 instid 传入 SupPersistConfigService.prepare；服务在 COMM 事务中通过既有 CommInstanceBizDao.selectByPrimaryKey 查询 instname。源表及丢弃表两条配置均使用该查询值，SupFileDao 接口与 Mapper 增加 dbname 绑定。实例缺失或名称为空时在删除原配置前报错；其余任务参数透传、调用顺序及用户手工删除条件保持。
- CMemdbPrePersist 在 dynamic_create_table 启用时先检查配置的 globaldeletesql：空串、纯空白或忽略前导空白及大小写后以 truncate 开头才进入重建；delete 及其他非空前缀直接跳过，包括对应表不存在的情况。继续保留原有表名、管理器及结构校验。
- 重建使用 DROP TABLE IF EXISTS 后 CREATE TABLE，字段及主键来自当前 MemdbManager，不额外查询存在性、不使用 CREATE TABLE IF NOT EXISTS。DROP/CREATE 失败向上传播，600001 不继续执行。源表重建，sup_filedropdata 的 delete 配置保持现有表，仍按原删除条件处理。
- 已同步提案、设计、持久化规范、任务、验收和部署回退说明。本轮未修改加载代码、用户模型、DAO 生成物、数据库脚本及页面；未启用动态建表的既有调用保持。

静态验证：3 个 Java 文件语法及尾部空白检查通过，Mapper XML 解析及 dbname 参数绑定核对通过，实例 DAO 方法与返回模型核对一致；2 个 C++ 文件按仓库 clang-format、include 顺序、方法注释和尾部空白规则检查通过，语法解析通过（仅替换线程宏供解析，不代表编译）。git diff --check 和 OpenSpec 严格校验通过。验收覆盖非 sup 实例名、实例缺失、旧结构及缺失表重建、空白/大小写、delete 保留和重建失败传播。

当前 **41/42**；**7.4 构建和业务运行验收仍未执行**。本轮未执行数据库操作、暂存、提交或归档，静态检查不代表 DDL 或业务运行验收通过。


## 2026-09-13：FS-CBS-7768 导入前处理删除旧丢弃结果

按用户确认替换新旧双缓存方案。CFileManage::Before 识别 SUP 内存导入并核对文件方向，先使旧持久化成功标志失效，再通过默认 CSup_filedropdataCacheManager 加载当前 intfid、fileid、GetBusidate() 同时匹配的旧记录，标记删除后立即 WriteToMemdb。删除成功后 ClearData 清空缓存记录、索引和操作计数，同一缓存供后续解析存放新结果。删除异常按框架传播，不继续规则加载或解析；非 SUP、导出及直接导入磁盘不执行清理。

Cache 仍直接从 COMM 磁盘读取并解析忽略规则、加载席位只读缓存；Clear 不再标记删除，Write 只写本次新结果。移除 SUP_NEW_DROP_CACHE_PREFIX，保留 resultMutex 保护多线程结果插入。磁盘删除代码未改动，工件同步当前已有 intfid+fileid+busidate 持久化条件。

已同步 proposal、design、tasks、丢弃分析及持久化规范、验收说明。静态检查：修改区域按仓库 clang-format 格式化；4 个文件的 UTF-8、尾部空白和 include 顺序检查通过，3 个头文件的方法注释检查无违规（已有无关方法的历史注释建议未修改）；Before/Cache/Clear/Write 语法解析通过，仅替换流字段类型字符串宏供解析，不代表编译或类型检查；git diff --check、OpenSpec 严格校验通过。核对三条件同时匹配、删除发生在解析前、ClearData 重置删除计数、默认缓存复用、异常传播和分支隔离；运行场景已补入 acceptance.md。

当前 41/42，7.4 构建及业务运行验收仍未执行。未修改模型、生成 DAO、数据库脚本、Java 持久化代码或其他手工调整；未执行数据库操作、暂存、提交或归档。


## 2026-09-13：SUP 忽略规则初始化函数提取

将 Cache 中的忽略规则初始化提取为 CFileManage::InitSupIgnoreRules，声明为 protected 内部函数。Cache 仅在 m_bSupFileImport 为 true 时调用，再加载原有席位缓存；标志为 false 时正常返回下一阶段。新函数保留规则清空、参数读取、COMM 查询、文件字段预校验、表达式预解析和异常时恢复连接逻辑，字段仍使用当前手工调整的 column.m_sFieldName。本轮不修改用户手工调整的 SupFileImportBefore。

设计、任务 4.5 与丢弃分析规范已同步。修改区域按仓库 clang-format 格式化；修改方法语法解析、条件调用、字段逻辑保留、UTF-8、空白及方法注释检查通过，git diff --check 通过。语法解析仅替换字段类型字符串宏，不代表编译或类型检查。当前 41/42，7.4 构建及运行验收仍未执行。


## 2026-09-13：SUP 过滤子类统一使用父类 MemdbManager

按用户明确授权，CFilterManagerSup 不再使用 CacheManager/CacheManagerPtr。MatchSeat 复用父类已初始化的 m_pComm_seatconfigMemdbManager，X/T 分别调用 GetMainseat/GetTradeseat 的 MemdbManager 重载，移除局部缓存索引读取及自行聚合。保留市场补充、席位存在、当前业务域匹配、outflag 非外部共享条件及拒绝原因；其他过滤查询继续沿用父类。CFileManage::Cache 移除席位缓存预加载，保留 m_bSupFileImport 为 true 时调用 InitSupIgnoreRules。

已同步 proposal、design、tasks 4.9、丢弃分析规范与验收说明。未修改父类、公共席位工具、丢弃结果缓存、忽略规则读取及用户手工前处理。修改区域按仓库 clang-format 格式化，过滤子类语法解析、MemdbManager 调用及缓存移除静态核对、方法注释、include 顺序、UTF-8 与空白检查、git diff --check 通过；语法解析不代表编译或类型检查。当前 41/42，7.4 构建和业务运行验收未执行。


## 2026-09-13：丢弃结果按读取调用独立批量写入

本节替代此前默认 CacheManager、resultMutex 及 Write 阶段集中写回方案。ReadFileData 通过 CreateFilterResultManager 创建局部 unique_ptr，SUP 返回新的 CSup_filedropdataMemdbManager，普通导入返回空。管理器显式传入 ReadOneRecord、FilterParsedRecord，每条丢弃记录完成原因和忽略标志计算后只保存到本地批次，不访问共享缓存，不使用跨任务 static thread_local。调用正常或异常退出时自动销毁未提交批次，析构不写库。

满批在 ReadOneRecord 的源写入成功后刷新，尾批在 ReadFileData 的源尾批成功后独立检查结果条数，均调用 WriteFilterResultBatch。空批直接跳过；非空使用 WriteLocalVecToMemdb(false) 纯插入，由 DAO 表级写锁保护，核对实际条数，成功清空本地集合。源批次失败不提交对应结果，结果写入失败传播至导入任务，不保证跨表原子回滚；已提交部分通过重新导入清理恢复，持久化和成功标志不能提前放行。沿用原源数据批次阈值，未顺带调整原 count++ 判断。

移除结果 CacheManager 使用、相关 include、CSupFileContext::resultMutex 和 CFileManage::Write 的集中结果写回，只读忽略规则仍共享。SupFileImportBefore 的 initfid 改为 intfid，同时检查 Delete 返回值，失败报告接口、文件、业务日期及底层错误，不设置导入准备成功标志。补齐该方法声明和定义的业务注释。

静态验证：5 个改动文件通过 UTF-8、尾部空白和残留引用检查；修改区域按仓库 clang-format 格式化，4 个头文件的方法注释及变动 include 顺序检查通过。修改方法及 SUP 头文件语法解析通过，仅在解析副本展开原 KCPD_RCAST 和字段类型字符串宏，不代表编译或类型检查。静态核对管理器唯一创建、参数传递、满批/尾批源写入在先、空批和普通入口、纯插入、删除失败阻断及 Write 无重复写回，git diff --check 和 OpenSpec 严格校验通过。新增验收用例覆盖批次边界、来源格式、并发及线程复用、源/结果失败、重复键、重跑和性能对比。

任务 4.6、4.11 已回填，当前 41/42。7.4 构建、业务运行验收和性能压测未执行；不能据静态检查宣称实际性能提升。未修改模型、生成 DAO、SQL、Java、预过滤或其他已确认过滤逻辑，未执行数据库操作、暂存、提交或归档。


## 2026-09-13：加载表管理器扩展点重命名

用户报告 check_memdb_sync.cpp:26 编译失败。静态定位 CCheckMemdbSync 继承 CAsyncMemdbSync，新增 CreateLoadManager 成员隐藏 macbs_factory.h 的全局 CreateLoadManager 工厂，使原本取得 ILoadManager* 的调用解析到返回 shared_ptr<CMacbsMemdbManagerBase> 的成员。

将 CAsyncMemdbSync 与 CSupMemdbLoad 的扩展点统一改为 CreateLoadTableManager，修改四个文件共六处声明、定义和调用，保留 override 派发及 SUP 字段投影行为。全局工厂、跨版本检查调用保持原有名字及接口。设计、任务 3.3 和加载规范已同步。

静态核对六处引用、两级签名和 override 一致，cbs_memdb_sync 无旧成员名残留；git diff --check 通过。按项目约定未执行构建，因此尚未实际复编用户报告的报错文件。当前 41/42，7.4 运行验证仍待执行。
