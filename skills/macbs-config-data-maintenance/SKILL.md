---
name: macbs-config-data-maintenance
description: 维护 MACBS 全量或增量配置数据，连接远程 ddw 配置数据库主机并发执行标准版和券商个性化配置脚本。适用于用户要求执行、刷新、初始化、修复或维护 MACBS full/patch SQL 配置数据，使用 bundled Python 脚本读取券商 schema 配置、生成按 schema/DB_USER 区分的 db_config_temp.ini 和临时执行脚本，在远程 `/home/ddw/ddw_config` git 仓库下执行 fs_cbs/fs_cbs_comm 脚本，并在用户确认后生成 ddw_config.config_diff 差异表的场景。
---

# MACBS 配置数据维护

## 概述

使用本技能从用户指定的 git 分支，在远程服务器 `ddw@10.201.69.39` 上安全执行 MACBS 配置数据 SQL 脚本。远程 git 仓库根目录固定为 `/home/ddw/ddw_config`，并且只处理用户指定的 `full` 或 `patch` 脚本目录。

整体策略改为按 schema/DB_USER 隔离个性化数据：不再修改 SQL 表名，不再追加个性化表后缀。标准版本使用 `DB_USER=ddw_config`；券商个性化版本使用独立 DB_USER/schema，例如东方财富使用 `DB_USER=ddw_config_dfcf`。

## 必填输入

连接远程服务器或执行任何远程命令前，必须要求用户提供：

1. 需要执行脚本对应的 git 分支。
2. 执行模式：只能是 `full` 或 `patch`。

如果缺少任意必填输入，必须先向用户确认，不能连接远程服务器执行脚本。

用户不需要指定 `standard` 或具体券商。脚本会自动执行该模式下全部标准版内容和全部已配置个性化券商内容。

## 实际脚本目录结构

远程仓库中脚本路径均以 `database/script` 为根。当前 `full` 和 `patch` 的可用目录结构如下，执行时必须从这些结构中选择路径，不要依赖外部目录说明。

`full` 模式：

- 标准版本主脚本：`database/script/full/gauss/fs_cbs/fs_cbs_comm.sh`
- 标准版本补充数据：`database/script/full/金证股份/gauss/fs_cbs/fs_cbs_comm.sh`，如果缺失则跳过
- 券商个性化脚本：`database/script/full/<券商目录>/gauss/fs_cbs/fs_cbs_comm.sh`
- `full` 下存在的券商目录：`东方财富`、`广发证券`、`国投证券`、`国投poc`、`国信证券`、`华兴证券`、`银河证券`、`中金财富`、`中信建投`
- `full` 下还存在但本技能默认不执行的目录：`common`、`goldendb`、`oceanbase`
- `full` 下还存在 `fs_cbs_day` 日间清算脚本；本技能默认只执行 `fs_cbs`，不要执行 `fs_cbs_day`

`patch` 模式：

- 标准版本主脚本：`database/script/patch/gauss/fs_cbs/fs_cbs_comm.sh`
- 标准版本补充数据：`database/script/patch/金证股份/gauss/fs_cbs/fs_cbs_comm.sh`，如果缺失则跳过
- 券商个性化脚本：`database/script/patch/<券商目录>/gauss/fs_cbs/fs_cbs_comm.sh`
- `patch` 下存在的券商目录：`东方财富`、`广发证券`、`国投证券`、`国信证券`、`华兴证券`、`银河证券`、`中金财富`、`中信建投`
- `patch` 下还存在但本技能默认不执行的目录：`日间清算适配`、`oceanbase`
- `patch` 下部分目录存在 `fs_cbs_day` 日间清算脚本；本技能默认只执行 `fs_cbs`，不要执行 `fs_cbs_day`

只允许执行 `gauss/fs_cbs/fs_cbs_comm.sh`、存在时的 `金证股份/gauss/fs_cbs/fs_cbs_comm.sh`、券商个性化 `gauss/fs_cbs/fs_cbs_comm.sh`。除非用户另行明确要求，不要执行节点库、日间清算、common、goldendb、oceanbase 或其他无关 shell 脚本。

执行前必须扫描所选 `full` 或 `patch` 模式下的一级目录。如果发现不在 `config/broker_schema_config.json` 的 `broker_suffixes` 中、也不在 `non_broker_dirs` 中的目录，立即终止执行，并提示需要补充配置和新建对应 schema。`日间清算适配` 和 `国投poc` 明确属于非券商目录，必须排除。

## 远程执行流程

所有实际操作都通过 SSH 在远程服务器执行：

```bash
ssh ddw@10.201.69.39
cd /home/ddw/ddw_config
```

然后按顺序执行：

1. 必要时获取远程分支信息。
2. 校验用户指定的分支是否存在。
3. 检查工作区状态。除非用户明确授权，不要覆盖远程仓库中的未提交修改。
4. 切换到用户指定的分支。
5. 确认用户指定的模式目录存在：`database/script/<mode>/`。
6. 上传并执行本技能内置脚本 `scripts/prepare_config_run.py`，由脚本生成临时执行目录和脚本清单。
7. 先执行 `--dry-run`，确认标准版执行组、全部券商执行组、临时目录、扫描结果和 `DB_USER` 符合预期。
8. 用户确认后再加 `--run` 正式执行临时脚本。默认按执行组并发执行，标准组和各券商组同时运行；每个执行组内部仍按 `gauss` 后 `金证股份` 或券商目录的顺序串行执行。
9. 保留每组执行日志，用于说明执行成功或定位失败的 SQL/脚本路径。控制台只输出组级别的启动、成功、失败摘要。
10. 全部执行组成功后不要直接执行后置数据核对；必须提示用户“数据核对耗时较长，是否执行后置数据核对生成 `ddw_config.config_diff`？”，并等待用户明确确认。
11. 只有用户明确确认后，才执行后置任务：在 `ddw_config` schema 下重建 `config_diff` 表，记录各券商 schema 与标准 schema 存在差异的表清单。

## 脚本选择

每次执行指定模式时，自动执行全部标准版和个性化内容。

标准版执行组必定执行标准 `gauss` 脚本；如果 `金证股份` 补充脚本存在，则追加执行，缺失时跳过：

```text
database/script/<mode>/gauss/fs_cbs/fs_cbs_comm.sh
database/script/<mode>/金证股份/gauss/fs_cbs/fs_cbs_comm.sh  # optional
```

每个已配置且在所选模式目录下实际存在的券商，都会生成一个独立个性化执行组，执行：

```text
database/script/<mode>/gauss/fs_cbs/fs_cbs_comm.sh
database/script/<mode>/<券商目录>/gauss/fs_cbs/fs_cbs_comm.sh
```

执行并发策略为：标准版执行组和所有券商个性化执行组并发启动。标准版执行组内部必须先执行 `gauss`，再执行存在时的 `金证股份`；券商执行组内部必须先执行该 schema 下的标准 `gauss` 脚本，再执行该券商目录脚本。券商个性化执行时，标准 `gauss` 脚本和该券商个性化脚本都使用同一个个性化 DB_USER/schema，例如东方财富执行组使用 `DB_USER=ddw_config_dfcf`，确保标准表结构和个性化配置数据落在同一个 schema 下。

## 内置 Python 脚本

优先使用本技能内置脚本：

`scripts/prepare_config_run.py`

同时使用本技能内置配置：

`config/broker_schema_config.json`

配置内容：

```json
{
  "db_user_prefix": "ddw_config",
  "broker_suffixes": {
    "东方财富": "dfcf",
    "广发证券": "gfzq",
    "国投证券": "gtzq",
    "国信证券": "gxzq",
    "华兴证券": "hxzq",
    "银河证券": "yhzq",
    "中金财富": "zjcf",
    "中信建投": "zxjt"
  },
  "non_broker_dirs": [
    "gauss",
    "common",
    "goldendb",
    "oceanbase",
    "金证股份",
    "日间清算适配",
    "国投poc"
  ]
}
```

该脚本上传到远程仓库下的隐藏工具目录 `.macbs_config_tools/`，并在远程仓库中创建 `.macbs_config_work/<timestamp>/...` 临时工作目录，不修改原始 `db_config.ini`、`fs_cbs_comm.sh` 或 SQL 文件。脚本会复制目标 `fs_cbs` 目录到临时工作目录，并在临时副本中执行以下处理：

- 自动生成标准版执行组和全部已配置券商执行组
- 为每个执行组生成按 schema/DB_USER 区分的 `db_config_temp.ini`
- 从 `broker_schema_config.json` 读取券商缩写并生成 DB_USER
- 扫描所选模式目录，发现未配置券商目录时终止执行
- 将 `fs_cbs_comm.sh` 复制为 `fs_cbs_comm_temp.sh`，并把配置文件名从 `db_config.ini` 改成 `db_config_temp.ini`
- 不扫描、不修改、不重写任何 SQL 文件
- 加 `--run` 时按执行组并发执行生成的 `fs_cbs_comm_temp.sh`，组内保持脚本顺序
- 默认并发数为执行组数量；可用 `--jobs <N>` 限制同时运行的执行组数量
- 每个执行组的详细 stdout/stderr 写入该组临时目录下的 `run.log`
- 全部执行组成功后不会自动运行差异统计 SQL；脚本只输出待确认的 `--post-task-only` 命令
- 用户确认执行数据核对后，使用 `--post-task-only --work-root <本次临时目录>` 生成 `<work-root>/config_diff.sql` 和 `<work-root>/config_diff.log`

## 后置差异统计

每次 `--run` 全部执行组成功后，不要自动重建 `config_diff` 表。必须先向用户说明“数据核对耗时较长”，由用户决定是否执行后置数据核对。用户明确确认后，才在标准 schema `ddw_config` 下重建 `config_diff` 表，用于记录个性化券商 schema 与标准 schema 存在差异的表清单。任一执行组失败时，不执行后置差异统计，避免基于半完成数据生成误导性结果。表清单必须从 `pg_tables` 按 schema 获取，避免 `information_schema.tables` 在权限、可见性或兼容性细节上导致误判。

`config_diff` 表每次重建，只保留本次执行完成后的当前差异快照。表字段固定为：

```text
run_id          临时工作目录时间戳
mode            full 或 patch
broker_name     券商名称
standard_schema 标准 schema，固定为 ddw_config
broker_schema   券商 schema，例如 ddw_config_dfcf
table_name      存在差异的表名
diff_type       only_in_standard / only_in_broker / structure_diff / data_diff / compare_error
standard_rows   标准 schema 表行数
broker_rows     券商 schema 表行数
detail          差异说明或比较异常信息
created_at      记录生成时间
```

差异判断规则：

- `only_in_standard`：表只存在于标准 schema。
- `only_in_broker`：表只存在于券商 schema。
- `structure_diff`：同名表存在，但列名、列顺序或核心类型定义不同。
- `data_diff`：结构一致，但行数不同或 `EXCEPT` 双向比较发现内容不同。
- `compare_error`：结构一致但数据比较 SQL 异常，记录异常信息，便于人工确认。

后置任务连接信息仍使用标准配置：

```ini
[COMM]
DB_IP=10.201.69.44
DB_PORT=30100
DB_USER=ddw_config
DB_PASSWORD=SZtest30
DB_NAME=macbs_db
```

后置任务只允许在用户确认后执行。后置任务失败时，必须报告 `config_diff.log` 路径；此时配置脚本本身可能已经全部执行成功，但差异表生成失败，需要单独处理。

只重新生成当前临时目录的差异表示例：

```bash
ssh ddw@10.201.69.39 'cd /home/ddw/ddw_config && python3 .macbs_config_tools/prepare_config_run.py --repo-root /home/ddw/ddw_config --broker-config /home/ddw/ddw_config/.macbs_config_tools/broker_schema_config.json --mode patch --post-task-only --work-root /home/ddw/ddw_config/.macbs_config_work/20260730_191559'
```

标准版本生成的 `db_config_temp.ini`：

```ini
[COMM]
DB_IP=10.201.69.44
DB_PORT=30100
DB_USER=ddw_config
DB_PASSWORD=SZtest30
DB_NAME=macbs_db
```

东方财富个性化生成的 `db_config_temp.ini` 示例：

```ini
[COMM]
DB_IP=10.201.69.44
DB_PORT=30100
DB_USER=ddw_config_dfcf
DB_PASSWORD=SZtest30
DB_NAME=macbs_db
```

上传和 dry-run 示例：

```bash
ssh ddw@10.201.69.39 'mkdir -p /home/ddw/ddw_config/.macbs_config_tools'
scp scripts/prepare_config_run.py ddw@10.201.69.39:/home/ddw/ddw_config/.macbs_config_tools/prepare_config_run.py
scp config/broker_schema_config.json ddw@10.201.69.39:/home/ddw/ddw_config/.macbs_config_tools/broker_schema_config.json
ssh ddw@10.201.69.39 'cd /home/ddw/ddw_config && python3 .macbs_config_tools/prepare_config_run.py --repo-root /home/ddw/ddw_config --broker-config /home/ddw/ddw_config/.macbs_config_tools/broker_schema_config.json --mode full --dry-run'
```

用户确认 dry-run 输出后，再正式执行：

```bash
ssh ddw@10.201.69.39 'cd /home/ddw/ddw_config && python3 .macbs_config_tools/prepare_config_run.py --repo-root /home/ddw/ddw_config --broker-config /home/ddw/ddw_config/.macbs_config_tools/broker_schema_config.json --mode full --run'
```

正式执行成功后，脚本会输出 `POST-TASK PENDING` 和 `--post-task-only` 命令。此时不要直接执行该命令，先提示用户数据核对耗时较长，并询问是否执行后置数据核对。

如需限制并发数，例如最多同时执行 3 个 schema：

```bash
ssh ddw@10.201.69.39 'cd /home/ddw/ddw_config && python3 .macbs_config_tools/prepare_config_run.py --repo-root /home/ddw/ddw_config --broker-config /home/ddw/ddw_config/.macbs_config_tools/broker_schema_config.json --mode full --run --jobs 3'
```

patch 模式 dry-run 示例：

```bash
ssh ddw@10.201.69.39 'cd /home/ddw/ddw_config && python3 .macbs_config_tools/prepare_config_run.py --repo-root /home/ddw/ddw_config --broker-config /home/ddw/ddw_config/.macbs_config_tools/broker_schema_config.json --mode patch --dry-run'
```

## db_config_temp.ini 规则

- 不要读取、修改或依赖原目录下已有的 `db_config.ini`。
- 不要直接执行原 `fs_cbs_comm.sh`。
- 只执行内置脚本生成的 `fs_cbs_comm_temp.sh`。
- 执行前确认临时脚本中不再引用 `db_config.ini`。
- 不要因为原 `db_config.ini` 缺失、内容错误或环境不匹配而阻塞；本流程只以新生成的 `db_config_temp.ini` 为准。
- 不要通过修改 SQL 表名实现个性化隔离；个性化隔离只通过 `DB_USER`/schema 实现。

## 安全规则

- 将该流程视为会变更数据库的操作。没有明确分支和模式时，不要执行。
- 发现未配置券商目录时必须终止执行；不要自动推断缩写、不要自动创建 schema。
- 不要同时执行 `full` 和 `patch`，除非用户明确要求同时执行并确认执行顺序。
- 不要执行本地数据库脚本；执行路径必须来自本技能列出的远程仓库相对路径结构。
- 除非用户明确要求，不要在远程仓库使用递归清理或破坏性 git 命令。
- 优先使用非交互命令并保留日志。并发执行时，任一执行组失败都要报告分支、模式、失败组、失败脚本路径、返回码和该组 `run.log` 路径；其他已经启动的 schema 执行组可能已经完成，报告时必须说明实际完成范围。
- 后置差异统计只允许在所有执行组成功后，且用户明确确认后运行。不要在脚本失败、用户中断或用户尚未确认时生成 `config_diff`，除非用户明确要求基于当前数据库状态单独生成。
- 如果 SSH 认证、权限、git 状态或脚本目录结构阻塞执行，直接报告阻塞点，不要临时改用其他执行路径。
