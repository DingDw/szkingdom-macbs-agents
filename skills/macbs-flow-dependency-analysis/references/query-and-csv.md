# 查询与CSV约定

## 标准查询

使用同目录的 [query.sql](query.sql)。它是只读分析模板，不是数据库增量交付脚本。

- 将全部 `{{schema}}` 替换为确认后的 schema 标识符，将 `{{flowchartid}}` 替换为整数。给用户的 SQL 应替换已知参数，不让用户再次猜编号。
- PostgreSQL / Gauss 使用该模板。其他数据库需按实际方言调整字符串连接和文本类型；列别名及行类型保持一致。
- 模板输出一个结果集，便于用户只粘贴一份 CSV；`INFO` 表示流程信息、`STEP` 表示步骤、`TASK` 表示任务。
- `INFO` 包含目标流程及它的直接前置、直接后置流程，用于绘制流程边界；不展开相邻流程内部任务。
- `STEP`、`TASK` 包含目标流程全部配置。指定 `stepno` 时仍执行同一查询，绘图阶段裁剪，确保跨步骤前后置任务可查。
- `TASK` 使用 LEFT JOIN 补步骤名称，避免缺失步骤的任务被内连接隐藏。独立 `STEP` 行保留无任务步骤。
- 不按运行状态、允许执行标志或当前完成状态过滤配置任务；这些状态不能证明任务不存在。
- 三张表应来自同一版本和同一数据时点；不要把标准流程信息、客户步骤和另一批任务混用。并发变更明显时使用工具支持的一致性只读快照或说明时点限制。

表结构未知时，先给出或执行下列只读检查；替换 schema 后使用：

```sql
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = '{{schema}}'
  AND table_name IN ('comm_flowchartinfo', 'comm_flowchart', 'comm_flowrecord')
ORDER BY table_name, ordinal_position;
```

核心必需字段：

- `comm_flowchartinfo`：`flowchartid, flowchartname, pre_flowchartid`。
- `comm_flowchart`：`flowchartid, stepno, stepname, precondition, setactive`。
- `comm_flowrecord`：`flowchartid, stepno, recordno, recordname, beforerecordno`。

`stepfullname` 仅用于 `stepname` 为空时补名称；旧版本无此列时去掉对应 COALESCE 参数即可。核心依赖列缺失时不能用空字符串假装无依赖，应说明版本差异并补查实际字段。

工具结果超过单次上限时，先核对数量；可拆成三类查询分别按 `flowchartid`、`stepno`、`recordno` 稳定键分页，最终合并为同样的逻辑数据。不要在整条导出查询末尾加 LIMIT 后交付不完整图。

## CSV回传

请用户保留 SQL 输出表头和所有行，导出标准 CSV，逗号或换行出现在单元格内时用双引号包裹，单元格内双引号写成两个双引号。推荐 UTF-8，兼容 UTF-8 BOM。用户可以直接在聊天中粘贴 CSV 代码块。

标准列顺序为：

```csv
row_type,flowchartid,flowchartname,pre_flowchartid,stepno,stepname,precondition,setactive,recordno,recordname,beforerecordno
```

下列仅为格式示例，不是实际查询数据：

```csv
row_type,flowchartid,flowchartname,pre_flowchartid,stepno,stepname,precondition,setactive,recordno,recordname,beforerecordno
INFO,25,示例清算流程,,,,,,,,
STEP,25,,,10,数据加载,,20,,,
STEP,25,,,20,清算处理,10,,,,
TASK,25,,,10,数据加载,,,100010,加载数据,
TASK,25,,,20,清算处理,,,200010,初始化,
TASK,25,,,20,清算处理,,,200020,清算执行,"100010,200010"
```

解析时使用 CSV 解析器（例如 Python `csv.DictReader`），不能逐行 `split(',')`；只有 CSV 单元格解码后，才拆分依赖字段内部逗号。对空白和大小写的表头做合理规范化。空字段为无配置；字面 `NULL`、`\N` 仅在用户确认或导出格式明确时作为数据库 NULL，不能把合法名称 `NULL` 全局抹除。

同样接收用户分别导出的三张表 CSV，或带完整核心字段的关联查询 CSV。依据实际列映射，不强迫重导。只有任务数据但缺少步骤依赖时，可生成标明范围的任务显式依赖局部图，同时给出缺少步骤/流程信息的补查 SQL。

检查列数、引号、编号、重复键及重复行是否冲突；只去掉完全一致的重复数据。信息不完整时询问具体缺失项，不能替用户补造名称、任务或依赖。
