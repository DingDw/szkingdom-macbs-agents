---
name: macbs-service-patch-sql-analysis
description: Use when analyzing database/script/patch SQL changes across the official release/FS-CBS-1.7.0.0 through release/FS-CBS-1.7.6.0 branches, including all 1.table schema changes and selected 2.data configuration tables, with traceable JSON, editable migration adjustments, and static HTML output.
---

# MACBS Service Patch SQL Analysis

分析正式 release 分支中 `database/script/patch` 的增量 SQL，将可追溯的中间结果保存为 JSON，并生成支持人工填写版本迁移调整和静态构建的 HTML 报表。

## 目录结构与脚本

本 skill 的文件固定放在：

```text
database/script/temp/macbs-service-patch-sql-analysis/
├── SKILL.md
├── scripts/
│   ├── release_patch_analyze.py
│   └── generate_reports.py
└── output/
    ├── json/
    │   ├── index.json
    │   └── release_FS-CBS-*/analysis.json
    ├── release-patch-change-analysis.json
    ├── release-patch-change-analysis-adjustments.json
    ├── release-patch-change-analysis-full.json
    ├── release-patch-change-analysis.html
    ├── release-patch-change-analysis-server.js
    ├── build-static.js
    ├── start.bat
    ├── build.bat
    ├── README.md
    ├── release-patch-change-analysis-static.html
    └── release-patch-change-analysis.xlsx
```

- `scripts/release_patch_analyze.py`：切换固定 release 分支，扫描 patch SQL 并生成 `output/json`。
- `scripts/generate_reports.py`：读取 `output/json`，生成并校验独立展示 JSON、可编辑 HTML 和 XLSX 报表；Web 服务及静态构建脚本位于 `output/`。
- 两个脚本都接受仓库根目录作为第一个可选参数；不传参数时使用当前工作目录。

从仓库根目录执行完整流程：

```powershell
python database/script/temp/macbs-service-patch-sql-analysis/scripts/release_patch_analyze.py .
python database/script/temp/macbs-service-patch-sql-analysis/scripts/generate_reports.py .
```

已有完整 JSON、只需重新生成报表时，仅执行：

```powershell
python database/script/temp/macbs-service-patch-sql-analysis/scripts/generate_reports.py .
```

用户明确要求为额外分支生成互不覆盖的单分支报告，并使用目录、文件名和 SQL 语句短哈希组成稳定 `change_id` 时，可执行：

```powershell
python database/script/temp/macbs-service-patch-sql-analysis/scripts/release_patch_analyze.py . --branch release/FS-CBS-1.7.6.0-upd001 --stable-change-ids --output-json-dir database/script/temp/macbs-service-patch-sql-analysis/output/release_FS-CBS-1.7.6.0-upd001/json
python database/script/temp/macbs-service-patch-sql-analysis/scripts/generate_reports.py . --analysis-json-dir database/script/temp/macbs-service-patch-sql-analysis/output/release_FS-CBS-1.7.6.0-upd001/json --output-dir database/script/temp/macbs-service-patch-sql-analysis/output/release_FS-CBS-1.7.6.0-upd001 --html-template database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis.html
```

稳定 ID 格式为 `<相对目录>/<文件名>/<SQL 语句 SHA256 前 16 位>`。文件内容 SHA256 继续单独保存在 `content_sha256` 证据字段中，不参与 ID，避免同一文件新增其他 SQL 时改变原有记录 ID。SQL 哈希仅统一换行符，不改变 SQL 的其他字符；同一分支内生成后必须校验 ID 唯一，发现短哈希冲突时停止生成。

默认生成不读取现有展示 JSON，主报告中的 `migration_adjustment` 全部为 `"无"`，且不包含 `migration_sql_updated`、新旧 SQL、匹配相似度等迁移标记字段；同时不会读取、修改或覆盖独立的 `release-patch-change-analysis-adjustments.json`。

从上一次构建生成的 full JSON 导入迁移调整备注，且指定脚本已更新、需要按 SQL 内容重新映射的分支时执行：

```powershell
python database/script/temp/macbs-service-patch-sql-analysis/scripts/generate_reports.py . --migration-source database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis-full.json --remap-migration-branch release/FS-CBS-1.7.6.0
```

- 显式指定备注源后，未指定重映射的分支按“分支名 + change id”导入备注。
- 只有显式传入 `--migration-source` 时才导入备注，并将备注及 SQL 变化标记元数据写入独立的 `release-patch-change-analysis-adjustments.json`；主报告 JSON 始终不嵌入人工备注和迁移标记字段。
- 指定重映射的分支先按目录、文件、操作和对象信息匹配完全一致的 SQL；SQL 已修改时，只接受相似度不低于 95% 且最优候选有明确差距的匹配。
- SQL 修改后匹配的记录会保留原始 SQL、修改后 SQL 和内部匹配相似度，并在迁移调整备注正文前标记 `SQL 发生变化`。

生成后，从 `output/` 启动可编辑报表：

```powershell
database\script\temp\macbs-service-patch-sql-analysis\output\start.bat
```

- 浏览器通过本地 Node 服务分别加载 `release-patch-change-analysis.json` 和 `release-patch-change-analysis-adjustments.json`，再按“分支名 + change id”合并展示。
- 每条变更都有 `迁移调整` 输入列，默认显示 `无`；输入内容在失焦时只写回独立备注 JSON，不修改主报告 JSON。
- 版本迁移调整汇总中的每条记录提供跳转按钮，可展开并定位到对应的原始变更行。
- SQL 更新后重新映射的信息不在数据明细区展示；迁移调整备注条目在正文前显示 `SQL 发生变化`，操作区依次提供“查看 SQL 差异”和“跳转到原始变更”。差异弹窗逐行对齐新旧 SQL，删除内容使用红色、新增内容使用绿色，并进一步高亮行内变化；页面不展示匹配相似度。
- 关闭 `start.bat` 命令窗口或在该窗口按 `Ctrl+C` 停止服务，不生成 PID 文件，也不提供单独的停止脚本。
- 使用 `build.bat` 将当前 HTML、主报告 JSON 和独立备注 JSON 合并为 `release-patch-change-analysis-static.html`。
- 每次静态构建都会同时生成 `release-patch-change-analysis-full.json`，其中已合并全部备注，可在后续直接作为 `--migration-source`，替代人工保留的 old 报告文件。
- static HTML 默认包含构建时的迁移调整；执行 `node output/build-static.js --exclude-adjustments` 可构建不含备注的版本。
- static HTML 可直接打开，其中后续编辑只影响当前页面，不写回磁盘。

`release_patch_analyze.py` 会切换十一个有分析内容的 release 分支，必须遵守下文的专用 worktree 和工作区检查要求。`generate_reports.py` 不切换分支，可在 `output/json/index.json` 及各分支 JSON 完整时独立运行。

重新生成展示 JSON 时默认不读取旧展示 JSON，主报告全部 `migration_adjustment` 使用 `"无"`，也不得覆盖独立备注文件。只有用户显式指定 `--migration-source` 时，才导入人工备注并写入独立备注 JSON；已不存在的变更不再保留。

本 skill 只适用于以下任务：

- 统计 `release/FS-CBS-1.7.0.0` 到 `release/FS-CBS-1.7.6.0` 之间各正式版本分支的 patch 内容。
- 提取所有 `1.table` 目录中的表结构变更。
- 提取所有 `2.data` 目录中下列配置表的数据变更：
  - `comm_busidefine`
  - `comm_subjectdefine`
  - `comm_bookkeepingrule`
  - `sys_param_define`
  - `comm_busidefine_refrule`
- 输出按分支、原始目录和源文件区分的 JSON。
- 完整保留 SQL 注释、原始 SQL 语句和行号证据。

## 固定分支范围

必须按以下顺序检查，包含起止版本及中间正式版本：

1. `release/FS-CBS-1.7.0.0`
2. `release/FS-CBS-1.7.1.0`
3. `release/FS-CBS-1.7.2.0`
4. `release/FS-CBS-1.7.2.1`
5. `release/FS-CBS-1.7.3.0`
6. `release/FS-CBS-1.7.3.1`
7. `release/FS-CBS-1.7.4.0`
8. `release/FS-CBS-1.7.4.1`
9. `release/FS-CBS-1.7.5.0`
10. `release/FS-CBS-1.7.5.1`
11. `release/FS-CBS-1.7.6.0`

默认使用对应的远端引用：

```text
origin/release/FS-CBS-1.7.0.0
origin/release/FS-CBS-1.7.1.0
origin/release/FS-CBS-1.7.2.0
origin/release/FS-CBS-1.7.2.1
origin/release/FS-CBS-1.7.3.0
origin/release/FS-CBS-1.7.3.1
origin/release/FS-CBS-1.7.4.0
origin/release/FS-CBS-1.7.4.1
origin/release/FS-CBS-1.7.5.0
origin/release/FS-CBS-1.7.5.1
origin/release/FS-CBS-1.7.6.0
```

不要自动加入以下派生分支：

- `_upd001`、`_upd002`、`_upd003` 等更新分支。
- 客户名称后缀分支。
- `bak`、`local`、`orig`、`全量包` 等分支。
- `release/FS-CBS-1.7.6.0-upd001` 或其他超出固定范围的分支。

如果用户明确指定新增分支，才可将其加入本次任务，并在 JSON 的 `requested_extra_branches` 中记录。

## 已知 Patch 顶层结构

以下结构用于执行前校验，不可替代实际递归扫描。

### release/FS-CBS-1.7.3.1

```text
database/script/patch/
├── gauss/
├── 东方财富/
├── 中信建投/
├── 中金财富/
├── 国信证券/
├── 国投证券/
├── 广发证券/
└── 银河证券/
```

### release/FS-CBS-1.7.4.0

```text
database/script/patch/
├── gauss/
├── 东方财富/
├── 中信建投/
├── 中金财富/
├── 华兴证券/
├── 国信证券/
├── 国投证券/
├── 广发证券/
├── 日间清算适配/
└── 银河证券/
```

### release/FS-CBS-1.7.4.1

```text
database/script/patch/
├── gauss/
├── 东方财富/
├── 中信建投/
├── 中金财富/
├── 华兴证券/
├── 国信证券/
├── 国投证券/
├── 广发证券/
└── 银河证券/
```

### release/FS-CBS-1.7.5.0

```text
database/script/patch/
├── gauss/
├── 东方财富/
├── 中信建投/
├── 中金财富/
├── 华兴证券/
├── 国信证券/
├── 国投证券/
├── 广发证券/
├── 日间清算适配/
└── 银河证券/
```

### release/FS-CBS-1.7.5.1

```text
database/script/patch/
├── gauss/
├── oceanbase/
├── 东方财富/
├── 中信建投/
├── 中金财富/
├── 华兴证券/
├── 国信证券/
├── 国投证券/
├── 广发证券/
├── 日间清算适配/
└── 银河证券/
```

### release/FS-CBS-1.7.6.0

```text
database/script/patch/
├── gauss/
├── oceanbase/
├── 东方财富/
├── 中信建投/
├── 中金财富/
├── 华兴证券/
├── 国信证券/
├── 国投证券/
├── 广发证券/
├── 日间清算适配/
├── 金证股份/
└── 银河证券/
```

如果实际顶层目录与以上列表不同，不要忽略额外目录。继续扫描，并把差异写入分支 JSON 的 `directory_validation`。

## 大致目录模式

标准数据库脚本通常为：

```text
database/script/patch/<database>/<system>/<module>/1.table/**/*.sql
database/script/patch/<database>/<system>/<module>/2.data/**/*.sql
```

客户或专项脚本通常为：

```text
database/script/patch/<customer-or-adaptation>/<database>/<system>/<module>/1.table/**/*.sql
database/script/patch/<customer-or-adaptation>/<database>/<system>/<module>/2.data/**/*.sql
```

常见值包括：

- `<database>`：`gauss`、`oceanbase`。
- `<system>`：`fs_cbs`、`fs_cbs_day`。
- `<module>`：`fs_cbs_comm`、`fs_cbs_node`、`fs_cbs_nodex`、`fs_cbs_his` 等。
- 表结构目录：路径段名称严格等于 `1.table`。
- 数据目录：路径段名称严格等于 `2.data`。

不能只扫描示例目录。必须从 `database/script/patch` 开始递归发现所有路径段为 `1.table` 或 `2.data` 的目录。

## 分支切换规则

### 必须使用新的专用 worktree

本任务会连续切换十一个有分析内容的正式 release 分支。为避免当前开发工作区中的已修改、已暂存或未跟踪文件影响分支切换，执行前必须先提示用户在一个新建、干净、专用于本次分析的 worktree 中运行本 skill。

不要直接在用户日常开发或已有改动的 worktree 中执行。推荐用户从主仓库目录创建 detached worktree，例如：

```powershell
git worktree add --detach "..\macbs-release-patch-analysis" "origin/release/FS-CBS-1.7.3.1"
```

创建后，应将当前执行目录切换到新 worktree 根目录，再开始检查和扫描。worktree 目标路径可由用户指定，但必须满足：

- 是本次任务新建的专用 worktree。
- `git status --porcelain` 为空，或只包含本 skill 的分析器、输出目录等已确认不会被目标分支覆盖的任务文件。
- 不包含用户正在开发的未提交代码。
- 十一个目标远端引用切换时不会覆盖其中的未跟踪文件。

如果无法确认当前目录是新建的专用 worktree，先提示用户创建或切换到新 worktree，不要直接开始六个分支的切换。不得擅自替用户创建、删除或清理 worktree；只有用户明确授权后才可执行 `git worktree add`。

本任务仍要求在这个专用 worktree 内直接切换分支统计，不使用相邻分支 `git diff` 推导 patch 内容，也不在扫描过程中再创建其他 worktree 来代替逐分支切换。

执行前：

1. 执行 `git worktree list --porcelain`，记录并确认当前 worktree 路径。
2. 明确提示用户本任务应在新建的专用 worktree 中执行，并确认当前目录符合该要求。
3. 记录当前分支名、当前提交和是否处于 detached HEAD。
4. 执行 `git status --porcelain`。
5. 如果存在已修改、已暂存或可能被切换覆盖的未跟踪文件，停止切换并向用户说明。
6. 不得自动执行 `git stash`、`git clean`、`git reset` 或丢弃任何现有修改。
7. 校验十一个 `origin/release/...` 引用都存在；缺失时先报告，得到允许后再 fetch。

每个分支使用精确远端引用切换，例如：

```powershell
git switch --detach "origin/release/FS-CBS-1.7.3.1"
```

每次切换后记录：

- 请求分支名。
- 实际远端引用。
- `git rev-parse HEAD` 得到的提交号。
- `git status --short --branch` 的分支状态。

全部完成或发生异常后，必须尝试恢复原分支：

- 原来是命名分支时执行 `git switch "<original-branch>"`。
- 原来是 detached HEAD 时执行 `git switch --detach "<original-commit>"`。
- 恢复失败时立即报告，不得通过 reset 强行恢复。

## 增量统计原则

已知不同正式分支的 `database/script/patch` 不包含需要跨分支排重的重复增量，因此：

- 每个分支直接统计该分支完整 `database/script/patch`。
- 不做 `branchA..branchB` 文件差异计算。
- 不因 SQL 文本与其他分支相同而删除记录。
- 不跨分支去重。
- 同一分支内相同 SQL 出现在不同目录、不同客户或不同数据库类型下时，也必须分别保留。
- 可以生成 `content_sha256` 用于审计，但哈希只能标记相同内容，不能作为删除记录的依据。

## 扫描范围

### 表结构变更

递归读取所有路径中包含 `/1.table/` 的 `.sql` 文件，排除 `.gitkeep` 和非 SQL 文件。

至少识别以下变更：

- `CREATE TABLE`：新增表。
- `DROP TABLE`：删除表。
- `ALTER TABLE ... ADD COLUMN`：新增字段。
- `ALTER TABLE ... DROP COLUMN`：删除字段。
- `ALTER TABLE ... ALTER COLUMN`、`MODIFY`、`TYPE`：字段定义或类型变更。
- `RENAME TABLE`、`RENAME COLUMN`：重命名。
- `SET DEFAULT`、`DROP DEFAULT`：默认值变更。
- `SET NOT NULL`、`DROP NOT NULL`：空值约束变更。
- `ADD CONSTRAINT`、`DROP CONSTRAINT`：约束变更。
- `PRIMARY KEY`、`UNIQUE`、`FOREIGN KEY`、`CHECK`：键和检查约束变更。
- `CREATE INDEX`、`DROP INDEX`：索引变更。
- `COMMENT ON TABLE`、`COMMENT ON COLUMN`：表或字段注释变更。
- Gauss/PostgreSQL 的 `DO $$ ... $$`、存储过程或条件判断块中实际执行的 DDL。
- OceanBase/MySQL 方言中的反引号标识符和 `ALTER TABLE ... MODIFY/CHANGE`。

如果 SQL 无法可靠归类，仍输出记录，`operation` 使用 `unknown_ddl`，并保留完整证据，不得静默忽略。

### 指定配置表数据变更

递归读取所有路径中包含 `/2.data/` 的 `.sql` 文件，但只输出直接操作下列目标表的语句：

```text
comm_busidefine
comm_subjectdefine
comm_bookkeepingrule
sys_param_define
comm_busidefine_refrule
```

至少识别：

- `INSERT`。
- `UPDATE`。
- `DELETE`。
- `MERGE`。
- `REPLACE`。
- `TRUNCATE`。
- 带 CTE、子查询或匿名块包装的目标表操作。

识别要求：

- 表名大小写不敏感。
- 支持 schema 限定名，例如 `schema.comm_busidefine`。
- 支持双引号、反引号等标识符引用。
- 不能只按文件名筛选。名称不规范的 SQL 文件中只要操作目标表，也必须输出。
- SQL 注释中出现目标表名不算数据变更。
- 查询目标表但不修改目标表的纯 `SELECT` 不输出为数据变更。
- 一条语句操作多个目标表时，按目标表分别形成记录，并共享原始语句证据。

## SQL 注释保留规则

JSON 必须包含 SQL 中的注释内容，不能只生成摘要。

需要提取并原样保留：

- `-- line comment` 行注释。
- `/* block comment */` 块注释。
- SQL 语句尾部的行内注释。
- 紧邻语句前方、用于说明该语句目的的注释。
- `COMMENT ON TABLE ... IS '...'` 和 `COMMENT ON COLUMN ... IS '...'` 的注释文本。
- 注释中的版本号、需求号、作者、日期和业务说明。

每条注释至少记录：

- `kind`：`line`、`block`、`inline`、`comment_on_table`、`comment_on_column`。
- `line_start`。
- `line_end`。
- `raw`：包含原始注释符号的完整文本。
- `text`：去掉注释符号后的文本；不得改写语义。
- `association`：`file`、`preceding_statement`、`inline_statement` 或 `ddl_comment`。

文件开头或无法明确关联到单条语句的注释放入 `file_comments`。禁止把字符串字面量中的 `--` 或 `/* */` 误判为注释。

## SQL 解析要求

1. 尽量按 SQL 语句边界解析，不能简单地对每个分号无条件切割。
2. 正确处理单引号字符串、双引号标识符、反引号标识符、转义字符和多行语句。
3. 正确处理 `DO $$ ... $$`、函数体和过程体内部的分号。
4. 保存源文件相对路径、行号范围、文件编码和原始 SQL。
5. 文件解码优先尝试 UTF-8；失败后尝试 UTF-8 BOM、GB18030/GBK，并在 JSON 中写入实际采用的 `encoding`。
6. 不修改源 SQL 文件。
7. 不执行任何 SQL。
8. 摘要不能代替 `raw_sql`。无法完整解析时保留整个相关代码块。

## 路径分类

对每个发现的 `1.table` 或 `2.data` 目录生成分类字段。

规则如下：

- 第一段为 `gauss` 或 `oceanbase`：`scope = "standard"`，`customer = null`。
- 第二段为 `gauss` 或 `oceanbase`：`scope = "customer"`，第一段作为 `customer`。
- 其他形态：`scope = "unknown"`，保留全部路径段并写入 `classification_warning`。

目录对象至少包含：

- `relative_path`：相对于 `database/script/patch` 的目录。
- `database`：`gauss`、`oceanbase` 或无法识别时的值。
- `scope`。
- `customer`。
- `system`。
- `module`。
- `category`：`table` 或 `data`。

## 输出位置

所有生成结果必须保存到本 skill 的 `output` 目录。JSON 中间结果保存到：

```text
database/script/temp/macbs-service-patch-sql-analysis/output/json/
```

分支名中的 `/` 替换为 `_`，输出结构为：

```text
database/script/temp/macbs-service-patch-sql-analysis/output/json/
├── index.json
├── release_FS-CBS-1.7.3.1/
│   └── analysis.json
├── release_FS-CBS-1.7.4.0/
│   └── analysis.json
├── release_FS-CBS-1.7.4.1/
│   └── analysis.json
├── release_FS-CBS-1.7.5.0/
│   └── analysis.json
├── release_FS-CBS-1.7.5.1/
│   └── analysis.json
└── release_FS-CBS-1.7.6.0/
    └── analysis.json
```

最终报表保存到：

```text
database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis.json
database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis-adjustments.json
database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis-full.json
database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis.html
database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis-static.html
database/script/temp/macbs-service-patch-sql-analysis/output/release-patch-change-analysis.xlsx
```

`output/release-patch-change-analysis.json` 是供 HTML 使用的紧凑展示 JSON，不替代 `output/json/` 中包含完整追溯字段的分析 JSON，也不保存人工备注或 SQL 变化标记。人工备注、`migration_sql_updated`、原始 SQL、修改后 SQL 和内部匹配相似度均保存在 `output/release-patch-change-analysis-adjustments.json`。`output/release-patch-change-analysis-full.json` 是静态构建时生成的主报告与 adjustments 合并结果，可作为后续 `--migration-source`。HTML 中不得内嵌这些 JSON；只有 `build-static.js` 生成 static HTML 时才按构建选项内嵌。

展示 JSON 中每条变更至少包含：

```json
{
  "id": "table-000001",
  "category": "table",
  "operation": "add_column",
  "table": "example_table",
  "column": "example_column",
  "description": "字段业务说明",
  "line_start": 1,
  "line_end": 8,
  "raw_sql": "original SQL with formatting",
  "migration_adjustment": "无"
}
```

`migration_adjustment` 是人工维护字段，不回写分支 `analysis.json`。默认重新生成不合并该字段；显式指定 `--migration-source` 时只能按稳定键合并，只有通过 `--remap-migration-branch` 明确指定的脚本更新分支才允许使用受限 SQL 内容匹配。

先将单个分支结果完整写入并验证为合法 JSON，再切换下一个分支。最后生成 `index.json`。

## 分支 JSON 格式

每个 `analysis.json` 使用以下结构。字段可增加，但不得删除用于追溯的核心字段。

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-07-28T12:00:00+08:00",
  "branch": {
    "name": "release/FS-CBS-1.7.6.0",
    "ref": "origin/release/FS-CBS-1.7.6.0",
    "commit": "full commit sha"
  },
  "patch_root": "database/script/patch",
  "scan_policy": {
    "cross_branch_diff": false,
    "cross_branch_deduplication": false,
    "table_path_segment": "1.table",
    "data_path_segment": "2.data",
    "target_data_tables": [
      "comm_busidefine",
      "comm_subjectdefine",
      "comm_bookkeepingrule",
      "sys_param_define",
      "comm_busidefine_refrule"
    ]
  },
  "directory_validation": {
    "expected_top_level": [],
    "actual_top_level": [],
    "missing_expected": [],
    "unexpected_actual": []
  },
  "directories": [
    {
      "relative_path": "gauss/fs_cbs/fs_cbs_comm/1.table",
      "database": "gauss",
      "scope": "standard",
      "customer": null,
      "system": "fs_cbs",
      "module": "fs_cbs_comm",
      "category": "table",
      "classification_warning": null,
      "files": [
        {
          "path": "database/script/patch/gauss/fs_cbs/fs_cbs_comm/1.table/example.sql",
          "encoding": "utf-8",
          "content_sha256": "sha256 hex",
          "file_comments": [],
          "changes": [
            {
              "change_id": "table-000001",
              "change_category": "table",
              "operation": "add_column",
              "object_type": "column",
              "table_name": "example_table",
              "column_name": "example_column",
              "constraint_name": null,
              "index_name": null,
              "definition_before": null,
              "definition_after": "varchar(64)",
              "description": "字段业务说明",
              "line_start": 1,
              "line_end": 8,
              "raw_sql": "original SQL with formatting",
              "comments": [],
              "parse_warnings": []
            }
          ]
        }
      ]
    },
    {
      "relative_path": "国信证券/gauss/fs_cbs/fs_cbs_comm/2.data",
      "database": "gauss",
      "scope": "customer",
      "customer": "国信证券",
      "system": "fs_cbs",
      "module": "fs_cbs_comm",
      "category": "data",
      "classification_warning": null,
      "files": [
        {
          "path": "database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_comm/2.data/custom.sql",
          "encoding": "utf-8",
          "content_sha256": "sha256 hex",
          "file_comments": [],
          "changes": [
            {
              "change_id": "data-000001",
              "change_category": "data",
              "operation": "update",
              "target_table": "comm_busidefine",
              "qualified_target_table": "comm_busidefine",
              "key_conditions": [
                {
                  "column": "busitype",
                  "operator": "=",
                  "value": "012345"
                }
              ],
              "affected_columns": ["periodflag"],
              "insert_columns": [],
              "insert_values": [],
              "line_start": 10,
              "line_end": 12,
              "raw_sql": "original SQL with formatting",
              "comments": [],
              "parse_warnings": []
            }
          ]
        }
      ]
    }
  ],
  "summary": {
    "table_directory_count": 0,
    "data_directory_count": 0,
    "scanned_sql_file_count": 0,
    "table_change_count": 0,
    "data_change_count": 0,
    "data_change_count_by_table": {},
    "change_count_by_directory": {},
    "warning_count": 0
  },
  "warnings": []
}
```

只包含注释但没有目标变更的文件可以计入扫描文件数，但不必在 `files` 中生成空记录。若需要证明已扫描，可在目录对象增加 `scanned_files` 和 `matched_files`。

## index.json 格式

`index.json` 汇总分支，不复制全部 SQL 内容：

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-07-28T12:00:00+08:00",
  "branch_order": [
    "release/FS-CBS-1.7.0.0",
    "release/FS-CBS-1.7.1.0",
    "release/FS-CBS-1.7.2.0",
    "release/FS-CBS-1.7.2.1",
    "release/FS-CBS-1.7.3.0",
    "release/FS-CBS-1.7.3.1",
    "release/FS-CBS-1.7.4.0",
    "release/FS-CBS-1.7.4.1",
    "release/FS-CBS-1.7.5.0",
    "release/FS-CBS-1.7.5.1",
    "release/FS-CBS-1.7.6.0"
  ],
  "requested_extra_branches": [],
  "branches": [
    {
      "name": "release/FS-CBS-1.7.3.1",
      "ref": "origin/release/FS-CBS-1.7.3.1",
      "commit": "full commit sha",
      "result_file": "release_FS-CBS-1.7.3.1/analysis.json",
      "table_change_count": 0,
      "data_change_count": 0,
      "warning_count": 0,
      "status": "completed"
    }
  ],
  "totals": {
    "completed_branch_count": 0,
    "failed_branch_count": 0,
    "table_change_count": 0,
    "data_change_count": 0,
    "warning_count": 0
  },
  "original_checkout": {
    "branch": "original branch or null",
    "commit": "original commit",
    "detached": false,
    "restored": true
  }
}
```

## 结果校验

每个分支完成后执行以下校验：

1. JSON 可以被标准 JSON 解析器读取，禁止注释和尾逗号。
2. `branch.commit` 等于切换后实际 `HEAD`。
3. 每个变更都有 `path`、`line_start`、`line_end` 和 `raw_sql`。
4. 每个源文件都有 `encoding` 和 `content_sha256`。
5. 所有 `1.table` SQL 都已进入扫描清单。
6. 所有 `2.data` SQL 都经过目标表内容匹配，不允许只按文件名过滤。
7. 数据变更的 `target_table` 必须属于固定五张表。
8. 注释已保留 `raw`；`COMMENT ON` 的文字已写入对应变更。
9. `summary` 数量与 `directories[].files[].changes[]` 实际数量一致。
10. 不同分支、不同目录的记录没有被跨范围合并。
11. `index.json` 中的结果文件全部存在且可解析。
12. 最终已恢复执行前的原分支或原提交。
13. 展示 JSON 可以独立解析，明细数等于各分支表结构变更数与配置数据变更数之和。
14. HTML 不内嵌展示 JSON，且分别加载 `release-patch-change-analysis.json` 和 `release-patch-change-analysis-adjustments.json`。
15. HTML 包含 `迁移调整` 列、失焦保存逻辑和版本迁移调整汇总。
16. 默认重新生成不修改独立备注 JSON；显式指定备注源时，非重映射分支按“分支名 + change id”导入，指定重映射分支按受限 SQL 内容规则导入。
17. `start.bat`、服务脚本、`build-static.js` 和 `build.bat` 均存在于 `output/`。
18. 执行 `node output/build-static.js` 成功生成包含备注的 static HTML 和 `release-patch-change-analysis-full.json`；使用 `--exclude-adjustments` 成功生成不含备注的 static HTML，但 full JSON 仍包含备注。

## 异常处理

- 单个 SQL 解析失败：保留文件路径、相关原始 SQL、注释和行号，添加 `parse_warnings`，继续其他文件。
- 单个分支不存在：在 `index.json` 中标记 `status = "failed"`，记录原因，继续前必须向用户说明。
- 分支切换失败：停止后续切换并恢复原分支。
- 工作区不干净：不切换、不 stash、不清理，直接报告阻塞。
- 输出 JSON 已存在：默认重新生成该分支文件，不把旧结果与新结果混合；覆盖前确认文件属于本 skill 的输出目录。
- 展示 JSON 已存在：默认忽略其中的人工 `migration_adjustment` 并生成无备注报告。只有显式指定 `--migration-source` 时才读取备注源；备注源无法解析时停止覆盖并报告。
- 发现 `1.table` 或 `2.data` 之外的疑似 DDL/目标表 DML：写入 `warnings`，但默认不纳入统计范围，除非用户扩大范围。

## 最终回复

完成后向用户简要说明：

- 实际检查的分支及提交号。
- 每个分支的表结构变更数和五张配置表数据变更数。
- JSON 输出目录。
- 可编辑 HTML、独立展示 JSON、独立迁移调整 JSON、合并 full JSON 和 static HTML 路径。
- 是否显式指定备注源、实际导入的迁移调整数量，以及静态构建是否成功。
- 解析警告或缺失分支。
- 是否成功恢复原分支。

不要只在回复中展示统计结果，JSON 文件必须实际生成并通过解析校验。
