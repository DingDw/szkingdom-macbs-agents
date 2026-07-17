---
name: memdb-usage-analysis
description: Analyze one or many Jstp Memdb showtables text exports as independent scenarios, filter small tables, validate table-category configuration, calculate memory usage by category, baseline-record averages, per-account averages, and maximum supported customer counts, then deliver a formatted Excel workbook. Use this skill whenever the user mentions 内存库, memdb, showtables_output, 分配空间(MB), single-scenario or multi-scenario memory database occupancy analysis, table classification, capacity/customer-count estimation, or reusable analysis from exported txt files. Prompt the user for scenario data source file paths when they are not provided.
---

# Memdb Usage Analysis

Use this skill to turn Jstp Memdb `showtables` text exports into repeatable memory-usage analysis for one scenario or many scenarios.

The workflow supports three common modes:

- Single scenario: parse, filter, validate classification, and compute category/per-account statistics for that scenario.
- Multiple scenarios: parse and report each scenario independently in one run. Do not compare scenarios unless the user explicitly asks for comparison.
- Optional comparison: only generate pairwise table-level differences when the user asks to compare scenarios or when you pass `--compare-scenarios`.

1. Read one or more Memdb shell text exports.
2. Parse the ASCII table with columns like `内存表`, `记录数`, `分配空间(MB)`.
3. Filter out small tables, defaulting to `分配空间(MB) < 10`.
4. Deduplicate table names across all supplied scenarios.
5. Validate every retained table against a table-category config file.
6. Stop and ask the user to maintain the category config if new retained tables are missing.
7. Compute category summaries:
   - parameter category: total allocated memory only
   - transaction/account/asset categories: baseline table record count, total allocated memory, KB per baseline record
   - per-account averages using the account baseline table
8. Generate a formatted Excel workbook similar to `内存占用分析.xlsx`, including category summary, average account memory usage, and compute-node capacity/customer-count calculation.
9. If comparison is explicitly requested, produce table-level comparison files so follow-up questions can identify the main source of a difference.

## Inputs

Ask for or infer these inputs before running the script:

- Scenario exports: one or more txt files from `showtables`, each paired with a scenario name. If the user has not supplied file paths, ask them to provide the scene/scenario data source file path(s), for example `prod=C:\...\showtables_output_prod.txt`.
- Table category config: CSV file with at least `TableName` and either `分类` or `Category`.
- Output directory.
- Optional filter threshold. Default is `10 MB`.
- Whether scenario comparison is needed. Default is no comparison, even if multiple scenarios are supplied.
- Capacity assumptions for the Excel workbook:
  - compute node count, default `8`
  - total Memdb capacity in MB, default `512*1024`
  - transaction amplification factor, default `1.5`

Use the bundled example config as a starting point when the user does not already have one:

`config/table_categories.example.csv`

This config intentionally lives outside the script logic. Classification is business/domain knowledge, so do not guess missing categories silently.

## Category Config

The preferred config format is UTF-8 CSV:

```csv
TableName,分类
node_settdetail,交易类
node_fundacct,账户类
node_stkasset,资产类
comm_stock,参数类
```

The existing `TableName,InPutong,InSimu,分类` shape is also accepted; scenario-presence columns are ignored.

If the analysis finds retained tables that are absent from the config:

- Do not continue with category statistics.
- Tell the user which output file lists the missing tables.
- Ask the user to fill in the `分类` column and rerun.

The script writes `missing_tables_need_classification.csv` for this purpose.

## Default Baseline Semantics

Use these defaults unless the user provides different baselines:

| Category | Meaning | Baseline table |
|---|---|---|
| `参数类` | parameter/reference data | none |
| `交易类` | transaction data | `node_settdetail` |
| `账户类` | account data | `node_fundacct` |
| `资产类` | asset/holding data | `node_stkasset` |
| `持仓类` | holding data alias | `node_stkasset` |

For per-account averages, use `node_fundacct` as the account denominator by default.

When the user says "持仓类" but the config uses `资产类`, treat them as the same analytical concept only in reporting language. Do not rewrite config values unless asked.

## Run The Script

Use Python 3:

```powershell
python C:\Users\ghoul\.agents\skills\memdb-usage-analysis\scripts\analyze_memdb.py `
  --scenario scenario_a=C:\path\showtables_output_a.txt `
  --category-config C:\path\table_categories.csv `
  --output-dir C:\path\outputs `
  --min-alloc-mb 10 `
  --compute-nodes 8 `
  --total-memory-mb 524288 `
  --trade-amplification 1.5
```

Use one `--scenario name=path` argument for a single-scenario report. Repeat `--scenario` for every scenario that should be processed independently in the same run. Scenario names are output labels, so choose stable names like `baseline`, `stress`, `prod_20260715`, or `simu`.

For multiple independent scenarios:

```powershell
python C:\Users\ghoul\.agents\skills\memdb-usage-analysis\scripts\analyze_memdb.py `
  --scenario baseline=C:\path\showtables_output_baseline.txt `
  --scenario stress=C:\path\showtables_output_stress.txt `
  --scenario prod=C:\path\showtables_output_prod.txt `
  --category-config C:\path\table_categories.csv `
  --output-dir C:\path\outputs
```

Only add `--compare-scenarios` when the user specifically wants scenario-to-scenario table differences:

```powershell
python C:\Users\ghoul\.agents\skills\memdb-usage-analysis\scripts\analyze_memdb.py `
  --scenario baseline=C:\path\showtables_output_baseline.txt `
  --scenario stress=C:\path\showtables_output_stress.txt `
  --category-config C:\path\table_categories.csv `
  --output-dir C:\path\outputs `
  --compare-scenarios
```

When a category uses a different baseline, pass extra mappings:

```powershell
python ...\analyze_memdb.py `
  --baseline 交易类=node_settdetail `
  --baseline 账户类=node_fundacct `
  --baseline 资产类=node_stkasset `
  --account-baseline node_fundacct
```

To control the final Excel filename, pass:

```powershell
python ...\analyze_memdb.py `
  --excel-output C:\path\内存占用分析.xlsx
```

## Output Files

The script writes these files:

- `memdb_all_tables.csv`: parsed rows before filtering.
- `memdb_filtered_alloc_ge_<N>mb.csv`: retained table rows after threshold filtering.
- `memdb_filtered_dedup_table_presence.csv`: deduped retained table list with scenario presence.
- `missing_tables_need_classification.csv`: created when config lacks retained tables.
- `memdb_category_validation_summary.csv`: category counts and validation summary.
- `memdb_filtered_with_categories.csv`: retained rows joined with category config.
- `memdb_category_summary_by_scenario.csv`: category-level totals and baseline-record averages.
- `memdb_category_per_account_by_scenario.csv`: per-account category averages.
- `memdb_memory_usage_analysis.xlsx`: final formatted Excel workbook. This is the main deliverable.
- `memdb_table_diff_pairwise.csv`: table-level pairwise scenario differences only when `--compare-scenarios` is supplied. For more than two scenarios this file is long-form, with `ScenarioA` and `ScenarioB` columns.

## Excel Report Layout

The workbook uses one sheet with three sections:

1. `内存占用分析`
   - Scenario/category summary.
   - Columns: `场景`, `分类`, `基准表`, `条数`, `总记录数`, `总分配MB`, `表数`, `单条记录MB`.
2. `平均账户内存占用分析`
   - Per-account record and memory usage by non-parameter category.
   - Includes `交易放大比例`.
3. `计算节点容量计算`
   - Uses compute node count, total memory capacity, parameter-class footprint, and per-account memory to calculate max customer count.
   - `容纳客户数 = (总内存数据库大小 - 参数类占用) / 单账户总分配MB`
   - `交易放大后容纳客户数 = (总内存数据库大小 - 参数类占用) / 放大后单账户总分配MB`

Keep the workbook formulas live so users can adjust capacity assumptions directly in Excel.

## Analysis Interpretation

When explaining differences after comparison has been requested:

- Separate total-memory differences from per-baseline-record differences.
- Per-account or per-record averages can change drastically when the denominator changes, even if total MB is lower.
- For a large category-level average difference, inspect `memdb_table_diff_pairwise.csv` filtered to the scenario pair of interest and sorted by:
  - `DiffKBPerAccount_BMinusA`
  - `DiffAllocMB_BMinusA`
  - the category being discussed
- Identify whether the driver is:
  - one table using much more memory,
  - a much smaller baseline denominator,
  - a table present in one scenario but filtered out or absent in another,
  - or a business data skew such as many rows per account.

## Quality Checks

Before presenting results, verify:

- Parsed row counts are plausible for each input.
- No retained table is missing from the category config.
- Baseline tables exist in every scenario where that category is reported.
- The account baseline exists in every scenario.
- The threshold and baseline mapping are stated in the final answer.
- The generated Excel workbook exists and opens without formula reference errors.
- If the user supplied multiple scenarios but did not ask for comparison, state that the outputs are independent per-scenario statistics and no pairwise comparison file was generated.
