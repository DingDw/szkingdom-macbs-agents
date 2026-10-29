---
name: macbs-flow-dependency-analysis
description: "MACBS流程任务依赖分析：根据 flowchartid 或 flowchartid + stepno，通过 postgres-mcp、其他可用数据库连接或用户回传的查询CSV，分析流程、步骤、任务的前后置关系，输出 Mermaid 任务依赖图。适用于清算流程依赖梳理、跨步骤任务分析和前后置配置检查。"
---

# MACBS流程任务依赖分析

根据数据库中的真实配置生成任务前后置关系图。默认分析日终清算；仅在用户指定时分析日间清算。只读查询，不执行流程、不改配置。

## 输入和范围

- 必需：流程编号 `flowchartid`。可选：步骤号 `stepno`、客户版本、连接或 schema。
- 仅给流程编号：展示该流程的全部任务，每个任务节点必须写出**步骤号、步骤名称、任务号、任务名称**。即使使用步骤子图分组，也不能省略任务节点中的步骤信息。
- 给流程编号和步骤号：以该步骤为中心，展示全部本步骤任务以及直接跨步骤前置、后置任务；每个任务节点**只写任务号和任务名称**。跨步骤归属放在子图标题或图外说明中。默认不递归展开外部步骤的所有任务。
- 缺少流程编号时询问；连接目标有实质歧义时询问。已给编号和已知环境足够明确时直接查询。
- 后续用户粘贴 CSV 时沿用已有编号、步骤号和客户选择，不重新开始询问。

## 数据来源

优先使用 `postgres-mcp` 的只读查询工具；不可用时使用已有 DBX、其他数据库工具或已配置的 `psql` / `gsql` 连接。不安装工具、不编造连接或凭据。

使用 `ddw_config` 配置数据库时，未指定客户默认标准 schema，并在结果中说明选择。指定客户后只查询对应版本，不默认批量分析所有客户：

| 版本 | schema |
| --- | --- |
| 标准 | `ddw_config` |
| 东方财富 | `ddw_config_dfcf` |
| 广发证券 | `ddw_config_gfzq` |
| 国投证券 | `ddw_config_gtzq` |
| 国信证券 | `ddw_config_gxzq` |
| 华兴证券 | `ddw_config_hxzq` |
| 银河证券 | `ddw_config_yhzq` |
| 中金财富 | `ddw_config_zjcf` |
| 中信建投 | `ddw_config_zxjt` |

上述映射只适用于 `ddw_config` 配置数据库。业务库使用其实际 schema，不能因表名相同而套用配置库 schema。

1. 检查所选 schema 的 `comm_flowchartinfo`、`comm_flowchart`、`comm_flowrecord` 和所需列；优先查看工具元数据，必要时查询 `information_schema.columns`。
2. 读取 [查询与CSV约定](references/query-and-csv.md) 和 [只读查询模板](references/query.sql)，根据实际数据库方言、schema 和流程编号生成查询。
3. 先获取完整流程配置，再在内存中按步骤裁剪显示范围。不得先用 `stepno` 过滤任务查询而丢失跨步骤关系。
4. 检查工具是否截断结果。使用计数核对或稳定键分页读取完整数据，不能用默认行数上限的数据声称图已完整。
5. 连接无法使用时，明确说明原因，给出替换好已知参数的可执行 SELECT SQL，请用户执行并将**含表头的完整 CSV** 粘贴回来。未知 schema 时只询问 schema；表结构不明时先给列检查 SQL。未收到数据前不能把示例或仓库基线当作查询结果。

生成的查询应明确限定 schema。流程号与步骤号校验为整数，schema 使用已确认标识符或正确引用，避免把用户原始文本直接拼入 SQL。

若需从仓库核实字段，日终模型只读 `macbs-service/database/pdma/split_pdm/MACBS-V3/{domains,dicts,tables}/`，日间只读 `split_pdm/macbs-day/`。业务脚本先查 `database/script/full/gauss/`，缺失再查 `patch/gauss/`。这些内容只用于解释字段和配置语法；实际图以直连结果或回传 CSV 为准。

## 依赖解释

建图前读取 [依赖语义与绘图规则](references/dependency-graph.md)。核心字段：

| 层次 | 表和字段 | 方向及含义 |
| --- | --- | --- |
| 流程 | `comm_flowchartinfo.pre_flowchartid` | 前置流程 → 当前流程 |
| 步骤 | `comm_flowchart.precondition` | 前置步骤完成 → 当前步骤满足执行前提 |
| 步骤 | `comm_flowchart.setactive` | 当前步骤完成 → 目标步骤激活候选；不能单独当作必须等待的前置依赖 |
| 任务 | `comm_flowrecord.beforerecordno` | 前置任务 → 当前任务；为空时遵循所属步骤的前后置关系 |

逗号分隔的多个前置项表示全部满足（AND），不是任意一个满足（OR）。按编号完整匹配，不能用子串匹配。任务键为 `(flowchartid, recordno)`，步骤键为 `(flowchartid, stepno)`；任务号不得按步骤号或名称推测。

显式前置任务与步骤层关系分别保留。不能为了画图给所有任务叠加额外的步骤等待条件。空前置任务不是“无依赖”，也不能按任务号、步骤号或 `executelevel` 排序后串成依赖链。

## 交付

先简要交代数据来源、连接/schema、流程编号和名称、步骤范围及数据完整性，再输出可渲染的 `mermaid` 代码块。主图必须包含任务节点，不能只交付步骤图。

- 全流程任务节点格式：`步骤 10：清算数据加载<br/>任务 100010：数据加载至内存`。
- 单步骤任务节点格式：`任务 100010：数据加载至内存`。
- 使用 `flowchart TD` 或 `flowchart LR`；前置节点指向后置节点。
- 实线表示明确前置依赖或已确认的步骤继承关系；虚线标注 `setactive 激活`，只表示激活关系。辅助节点必须说明用途，不能冒充任务。
- 多前置时说明为 AND；步骤汇聚用“全部任务完成”的辅助节点表达，避免把整个前置步骤等同于某个尾任务。
- 显示孤立任务；发现空步骤、缺失引用、自引用、循环或配置不一致时保留证据并简要说明，不能通过删边隐藏问题。单步骤边界外省略的关系不报成配置缺失。
- 图太大时按步骤拆图，并保留跨图连接编号与名称；交付全部范围，不静默省略。

图后仅列出影响理解的异常、范围边界和未确认事项。没有完整数据时标明“局部图/待补数据”，不要宣称完整。

调用示例：

```text
使用 $macbs-flow-dependency-analysis 分析 flowchartid=25 的任务依赖。
使用 $macbs-flow-dependency-analysis 分析 flowchartid=25、stepno=50 的任务前后置关系。
使用 $macbs-flow-dependency-analysis 分析广发证券 flowchartid=25 的流程依赖；不能直连时给我SQL。
```
