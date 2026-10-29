# 部署与回退清单

本清单尚未执行。范围为日终 Gauss，当前只启用 `SHJS/SH_JSMX01`；SUP 实例初始化样例为 `instid=9/instname=sup/partid=*/domainid=01/compute_node_num=1`。运行时按 `insttype=9` 与当前业务域选择实际实例；席位比较 GetDomainid()，不校验样例编号、名称、分区、业务域或节点数。数据库地址及凭据从部署配置获取。

## 交付入口

| 入口 | 实现与调用位置 |
| --- | --- |
| `supFlowPrepare` | Java `modules/supfile`，管理节点执行准备任务，事务提交实例映射、动态任务及结果；流程引擎刷新任务图 |
| `660030` | C++ `cbs_memdb_sync` → `LoadSupMemdb` → `CSupMemdbLoad::DoClear`，每个非空流程只生成一个共享任务，按配置加载；类型 1 仅覆盖当前业务域 |
| `625092` | 原 `cbs_file` → `BatchImpExpFileNew` → `CFileManage::DoClear`，SUP 工厂选择全量导入子类 |
| `supFilePersist` | Java 顺序调用 `600003/600001`，透传任务参数，最后更新完整日志键的完成标志 |
| `supFlowCleanup` | Java 核对持久化完成后，在同一 COMM 事务中删除本流程引用的持久化配置及 SUP 映射，不调用 C++、不清理内存数据 |
| 查询 | `querySupDiskDBByTableName`，按流程关联 `sys_config` 的业务日期、流程状态和文件持久化状态检查后读取 SUP 磁盘 |
| 页面 | `macbs-web` 的 `SupFileAnalysis/Index.json`、`SUP_FILE_ANALYSIS.json`、低代码映射及 API 注册；菜单 `606049900` |

Java 模块已加入 `modules/pom.xml` 和 `macbs-service/macbs-node` 两个 bootapp 依赖，BEX 使用现有 `bex/*-bex.xml` 资源约定；DAO 使用两个应用已有的 mapper 扫描路径。启动时仍须检查 BEX、Mapper 和数据源实际加载情况。C++ 新增加载功能号 `660030` 同步注册在 `frame.xml/frame-win.xml`，源文件由模块 CMake 纳入。已移除原专用清理 `660031` 的注册、导出及实现，部署时同步更新两端 frame 和 C++ 库；Java 清理 BEX 名称和流程配置保持。

## 部署顺序

所有下列 SQL 路径相对 `macbs-service/database/script/patch/gauss/fs_cbs`。先保存目标环境相关配置和应用版本，确认流程 `9`、实例 `9`、菜单 `606049900` 未被其他业务占用，且没有正在运行的 SUP 任务。不要执行整个工作区增量目录，以免带入其他未交付改动。

1. COMM 库分别执行 `fs_cbs_comm/1.table/comm_if_file.sql`、`comm_if_file_log.sql`、`sup_filedropignorerule.sql`，新增开关、完成标志及磁盘忽略规则表。
2. 使用 SUP 连接执行 `fs_cbs_comm/1.table/sup_filedropdata.sql`；该文件虽归入 comm 模型目录，部署目标为 SUP。用户整理后的 `fs_cbs_sup.sh` 也引用此文件，按脚本现有配置入口提供连接。源表仍由持久化前处理动态建表。
3. COMM 字典使用 `fs_cbs_comm/2.data/sys_dictvalue.sql` 中本需求片段；实例初始化样例位于 `工程脚本/1780工程脚本/文件全量导入实例创建.sql`，按现场现有实例状态审阅执行，不能把工程初始化脚本当作运行逻辑。该用户维护脚本含类型 9 实例删除语句，重做准备不会执行它。注册中心须提供一个可用空闲节点。
4. COMM 示例加载配置位于 `fs_cbs_comm/2.data/comm_memdb_load_cfg.sql`；流程脚本位于 `fs_cbs_comm/2.data/flow/9_全量数据导入分析/`，依次审阅 `comm_flowchartinfo.sql`、`comm_flowchart.sql`、`comm_flowrecord.sql`。模板默认关闭，无前置流程；准备和清理模板不固定 instid 参数，业务域按客户实际流程配置。
5. 部署 C++ 库及 frame、两个 Java bootapp 和前端资源，包含本轮任务重建、跨步骤激活和流程缓存刷新；移除之前新增的共享表锁及流程行锁接口，普通流程节点分配恢复原路径。
6. 菜单配置沿用户整理后的 `fs_cbs_comm/2.data/kd_sysmenu.sql`、`kd_sysmenu_ext.sql`、`kd_menuright_user.sql` 中本需求片段交付，保留其他需求内容；授权校验使用实际业务域及分区。
7. 验收后执行 `fs_cbs_comm/2.data/file/01_SHJS/comm_if_file.sql`，仅启用 `SHJS/SH_JSMX01`，再按当前客户结算主体启用流程模板，不扩展其他批次。更新 SQL 注释使用 `FS-CBS-7768`。


`sup_SH_JSMX01` 的持久化配置在运行时生成，`sh_jsmx` 在前处理通过 MemdbManager 元数据动态建表，无需静态初始化全部接口表。忽略规则不进入内存初始化、SUP 配置加载或 CacheManager 注册。

前轮唯一共享加载任务调整涉及 Java 任务生成逻辑及 Mapper 说明，本轮清理调整涉及 Java 清理调用及 C++ 专用清理入口移除，两轮均不新增表结构或增量 SQL。停止在途任务并部署后，按现有恢复操作重做准备：保留本流程已有 SUP 节点，清除旧编号段内全部逐文件加载任务及结果，再生成唯一 `100100` 加载任务及逐文件导入、持久化任务。不能继续使用升级前的旧任务图；空文件清单不生成加载任务。

## 当天数据与资源恢复

- 当前源表在首个物理文件导入前沿现有入口替换内存数据，持久化全表替换 SUP 磁盘源表。每次全量导入按 `fileid` 重新生成丢弃结果，持久化前同样按 `fileid` 删除旧磁盘丢弃结果。
- 导入开始使旧完成标志失效；成功标志在全量及丢弃数据均提交后更新。查询只接受当前业务日期及最新成功流程，旧数据和旧成功状态不能开放为当天结果；不新增日切删库、历史表或归档配置。
- 成功清理仅由 Java 在 COMM 事务中删除本流程引用的临时持久化配置及 SUP 映射；不清理内存数据，保留磁盘结果、任务结果及日志。内存源数据、丢弃结果及依赖表仍在下次导入或加载时按既有范围替换；本次清理不新增远端调用。
- 失败使用现有任务重做机制；准备重做保留已有映射，删除重建动态任务和结果，并刷新当前流程缓存；仅重试持久化时复用当前分析数据。清理失败可重做清理；未完成持久化时不强行调用正常成功清理。
- 如需放弃失败流程，先使用系统现有停止流程/节点管理入口，确认该流程在途任务已停止，再按已记录的 `flowchartid/compute_node/instid` 释放其资源。禁止仅按实例类型删除所有映射。该操作按现场恢复流程执行，本交付不提供自动全库清理脚本。

## 回退

1. 禁用本客户 SUP 流程入口及已启用文件开关，停止在途任务，记录流程和节点占用情况。
2. 确认停止后，通过现有恢复入口释放本流程资源；保留日志及磁盘结果供排查。
3. 回退两个 Java 应用、C++ 库及 frame 配置、前端配置和新菜单授权到部署前版本；共同回退任务重建、激活与缓存刷新改动，避免混装版本。
4. 保留新增表、字段和分析数据；不自动执行 DROP/TRUNCATE，不回退或覆盖用户自行维护的模型和生成物。不将清理整个增量目录作为回退步骤。

静态检查记录见 `implementation-notes.md`。构建、应用启动、数据库脚本和业务验收均尚未执行，待任务 7.4 的明确授权。

本轮加载调整需同步部署 cbs_memdb_sync 库（SUP 加载器及通用分段组件的可派发数据源路由），入口仍为 660030。仅在 Gauss 日终 patch 的 comm_memdb_load_cfg.sql 更新 FS-CBS-7768 片段：保留现有示例表集合和源类型，账户映射使用 load_method=0 的全表配置，executesql 为空，由 SUP 内部转换为四字段 settgroup 取模 SQL。表集合由配置决定，不要求维持七张；类型 1 的 comm_instance.domainid 必须匹配当前业务域。普通加载入口及配置不变。部署后通过重新运行共享加载生成新数据，运行验收按 acceptance.md；回退时库及本需求配置片段共同恢复。

本轮移除 SUP 专用主键去重和冲突比较，批次经通用写入队列沿用现有写入策略；没有新增数据库对象。部署时同步加载器及账户映射全表配置，不能沿用前轮的外部 SQL 配置。空表方式只清表、不创建源读取任务。


本轮线程模型调整需整体部署 cbs_memdb_sync 库，包含通用 CAsyncMemdbSync 的可派发扩展点及 SUP 子类；不涉及新的功能号、数据库字段或 SQL 配置。可沿现有任务参数传入 threadnum、prepare_queue_size、process_queue_size、timeout。升级及回退前等待在途加载结束，通用驱动与 SUP 子类必须使用同一版本；重新运行共享加载生成本次数据。普通 600000 和 SUP 660030 均按验收清单验证。


本轮持久化调整需同步部署 Java supfile 模块（任务传入 instid、实例查询及 Mapper dbname 参数）与 C++ cbs_memdb_sync。运行时配置通过重新执行持久化准备生成，dbname 来自当前 comm_instance.instname。动态建表开启时，空删除条件或 truncate 配置表每次 DROP 后按当前模型重建；delete 配置表不会自动创建或重建，因此 sup_filedropdata 必须由既有部署脚本准备及升级。执行期间停止在途持久化后再升级或回退；重建会移除源表原有数据，后续由当前内存数据重新持久化。回退到旧二进制不自动恢复已删除的数据或旧结构。
