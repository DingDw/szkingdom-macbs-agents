# AGENTS.md

## 优先信息源

- 项目分为日终清算和日间清算两个大的业务模块组成。
- 代码阅读/代码分析/二次开发时，优先只考虑日终清算，除非用户指定了与日间清算的交互

## macbs-base模块

### 优先信息源

- 项目结构和二次开发落点直接读 `docs/macbs-base-knowledge-base.md`，不要在回答或新文档中重复展开目录树。
- 分析单个业务模块时，先看模块知识库（如 `docs/modules/cbs_clear/README.md`）；缺失时按 `CMakeLists.txt` → `export.cpp` → 本地 `*_base` → 主 `*_deal`/阶段实现 → `handler/` 的顺序读。
- 运行入口不要靠文件名猜：从 `bin64/conf/frame.xml` 查 `func_id`、动态库和导出函数，再到 `lbm_pro/macbs/<module>/export.cpp` 找实际 C++ 类和执行方法。

### 构建与验证

默认不执行构建，除非明确要求进行构建和测试，当需要构建时，要求如下：
- CMake 最低 3.19；Windows preset 需要 Visual Studio/`cl.exe` 环境，Linux preset 使用 GCC + Ninja，ARM preset 使用 Unix Makefiles。
- 常用构建：`cmake --preset x64-debug-gauss` 后 `cmake --build --preset build-x64-debug`；Linux GAUSS 对应用 `linux-debug-gauss` / `build-linux-debug`。
- DBTYPE 通过 preset 选择，不要手写默认值；已有 GAUSS、MSSQL、GOLDENDB、OCEANBASE_ORACLE 组合。
- 需要只验证某个库时优先构建目标，例如：`cmake --build --preset build-x64-debug --target cbs_clear`。
- Windows 产物复制到 `bin64\function`；Linux 产物复制到 `bin64/function_${DBTYPE}_${CMAKE_BUILD_TYPE}`。
- 仓库没有业务级 CTest；`add_test` 主要来自 vendored `fmt`/`minizip`，不要把它们当作 macbs 业务测试覆盖。

### 代码修改约束

- 优先选择最窄影响面：具体 `handler/` > 模块本地 `*_base` > 模块主流程类 > `library/macbs/base/*` 公共框架。
- 客户特有需求优先放 `lbm_pro/macbs/project/<客户>/<模块>/`；同名公共模块也要检查，避免漏同步公共修复。
- 新增或改对外入口时必须同步检查 `frame*.xml`、模块 `export.cpp`、模块 `CMakeLists.txt`、类名和执行方法。
- 清算阶段返回值只能前进或结束：使用 `PHASE_NEXT`、后续阶段常量或 `PHASE_END`，不要跳回前一阶段。
- 写库相关改动要区分 cache、memdb、phydb 和流程日志；很多模块在 `Clear()` 改缓存，真正持久化在 `Write()`。
- 新增功能必须遵守清算七阶段模型
- 新增功能需要先确认实现模式：单一功能号/三段式处理
- **MUST**：关键代码(方法声明定义/条件分支/关键业务逻辑等)必须有含义明确的业务逻辑说明注释
- 新增功能如果用户没有明确指出可以直接使用`MemdbManager`，必须使用`CacheManager`作为内存数据库访问层，先在`Cache`阶段缓存数据。
- 拥有业务含义的字符/字符串，不允许出现类似'0', "AAA"等魔法数常量，要使用含义明确的宏定义替代；对于int/long/double等数值类型，尤其是0，不需要过度定义常量。
- 如果确定在整个功能号执行阶段，某个表**都是**只读状态，**没有任何**Insert/Delete/Update操作，则优先使用表对应的`CacheManagerPtr`类

### 格式化与提交前检查

- pre-commit 配置不在仓库根，而在 `pre-commit/.pre-commit-config.yaml`。
- 首次安装按 `pre-commit/README.md`：`pip install -r pre-commit/requirements.txt`，再安装 hooks（可用 `pre-commit install --config pre-commit/.pre-commit-config.yaml`）。
- 针对全仓检查用：`pre-commit run --config pre-commit/.pre-commit-config.yaml --all-files --verbose`；单 hook 加 hook id，例如 `clang-format`、`sort-includes`、`function-comments`。
- C/C++ hook 会转换 UTF-8、clang-format、排序 include、备份 DAO 扩展头、检查类方法注释；新增头文件方法缺少规范注释会被拒绝。
- clang-format 规则在 `pre-commit/.clang-format`：LLVM 基础、4 空格、Allman braces、指针左对齐、150 列、`SortIncludes: Never`（include 排序由自定义脚本做）。

## macbs-service模块

本节先覆盖 `macbs-service/database`；`macbs-service/service` 规则待补充。

### database优先信息源

- `database` 核心由 `pdma/` 数据模型和 `script/` 数据库脚本组成；脚本结构先读 `macbs-service/database/script/目录结构.txt`，不要在回答或新文档中重复展开完整目录树。
- 日终清算模型定义只看 `macbs-service/database/pdma/split_pdm/MACBS-V3/` 下拆分后的 `domains/`、`dicts/`、`tables/` JSON；不要使用 `pdma` 下其他模型目录或根级 `.pdma.json` 作为依据。
- 日间清算模型定义只看`macbs-service/database/pdma/split_pdm/macbs-day/` 下拆分后的 `domains/`、`dicts/`、`tables/` JSON；不要使用 `pdma` 下其他模型目录或根级 `.pdma.json` 作为依据。
- SQL 落点先区分 `full/` 和 `patch/`：完整初始化脚本放 `full/`，增量交付脚本放 `patch/`。
- 需要根据 `database/script` 下脚本内容判断业务逻辑时，只使用 `gauss` 下的内容，Gauss 数据库是本项目默认数据库；查找顺序优先 `full/gauss/` 下完整基线脚本，找不到对应对象、配置或流程时，再去 `patch/gauss/` 查增量脚本。
- script下日间清算的脚本都在明确的fs-cbs-day目录下，按数据库类型、清算场景、库名、脚本类别定位。
- 查找业务表脚本时按数据库类型、清算场景、库名、脚本类别定位：`common|gauss|goldendb|oceanbase|客户名` → `fs_cbs|fs_cbs_day|common` → `fs_cbs_comm|fs_cbs_node|fs_cbs_nodex|fs_cbs_day|fs_cbs_file|fs_cbs_his` → `1.table|2.data`。

### database核心业务脚本定位

- 系统参数看 `sys_param_define`
- 业务定义看 `comm_busidefine.sql`。
- 业务识别看 `comm_datapathconfig.sql`。
- 簿记规则看 `comm_bookkeepingrule.sql`。
- 流程引擎按三级设计理解：`comm_flowchartinfo`（流程信息）→ `comm_flowchart`（步骤信息）→ `comm_flowrecord`（步骤任务）。
- 流程前后置关系：`comm_flowchartinfo.pre_flowchartid` 明确流程前后置；`comm_flowchart.precondition`、`comm_flowchart.setactive` 明确步骤前后置；`comm_flowrecord.beforerecordno` 明确任务前后置。
- `comm_flowrecord.beforerecordno` 为空时，遵循上一级流程步骤的前后置依赖。
- 三段式功能号对应 `comm_flowrecord.prehandlefuncid`、`comm_flowrecord.shardingfuncid`、`comm_flowrecord.funcid`；单功能号形式对应 `comm_flowrecord.funcid`。

### database修改约束

- 优先选择最窄影响面：客户个性化目录 > 指定数据库类型目录 > `common` 通用目录；客户目录已有同名脚本时必须同时确认通用脚本是否也需要修复。
- DDL 类变更优先同步 `pdma/split_pdm/MACBS-V3/` 对应模型 JSON，再同步生成或维护 `script/full/`、`script/patch/` 中对应 `1.table` 脚本，避免模型和交付 SQL 漂移。
- DML 或初始化数据变更放 `2.data`；表结构、索引、分区、序列等对象变更放 `1.table`；流程相关配置保持在现有 `flow/` 分组下。
- 日终与日间脚本不要混放：日终使用 `fs_cbs`，日间使用 `fs_cbs_day`；日间独立部署涉及 `fs_cbs_day` 库，融合部署通常仍要检查 `fs_cbs_comm`、`fs_cbs_node`、`fs_cbs_nodex`。
- 多节点库脚本要按现有 `fs_cbs_node1.sh`、`fs_cbs_node2.sh`、`fs_cbs_node3.sh` 和 `fs_cbs_nodex.sh` 约定维护，不要把节点专属对象误放到 `fs_cbs_comm`。
- 修改安装入口时同步检查同目录 `db_config.ini`、对应 `.sh` 安装脚本和脚本子目录是否一致；不要只新增 SQL 文件而遗漏入口脚本。
- 关键数据订正、流程配置、菜单权限、字典参数等脚本必须写清业务含义注释；涉及客户定制时注释中标明客户和触发背景。
- 修改数据库脚本时，只需要修改`patch`目录下的增量脚本，不要 修改全量脚本
- 修改表结构时，需要同步调整 对应的`his_${table_name}`的历史表结构 /  归档 / 迁移配置

### database验证与清理

- 默认不直接执行数据库脚本；需要验证时先说明目标数据库类型、库名、脚本路径和执行顺序。
- 仅清理增量 SQL 时使用 `macbs-service/database/script/clean_patch_sql.bat` 或 `clean_patch_sql.sh`，它只处理 `script/patch` 下的 `.sql` 和空目录；不要用手写递归删除替代。
- 交付前至少检查新增 SQL 所在路径是否匹配数据库类型和清算场景，并用 `rg` 查同名表、同名字典、同名流程配置在 `full/`、`patch/`、客户目录中的已有定义。
