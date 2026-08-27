## Why

当前周期流水生成按业务流水逐笔保留历史周期流水；当同类业务长期积累大量周期流水时，后续周期配对会拼接多笔关联流水号，存在超过字段长度并导致清算无法继续处理的风险。需要支持由业务定义控制的周期流水合并生成能力，在保留可追溯关系的同时减少后续周期配对的有效候选流水数量。

## What Changes

- 扩展 `comm_busidefine.periodflag` 的业务语义，支持 `2-合并生成` 的周期流水生成模式。
- 在 `node_perioddetail` 增加 `mergebusiflowid` 合并流水号字段，用于记录被合并替代源周期流水所属的合并周期流水。
- 调整 `generate_perioddetail`：对 `periodflag=2` 的业务先生成普通当日周期流水，再按周期配对规则反推合并 key，对历史正常周期流水与当日新生成周期流水进行滚动合并。
- 合并后仅新合并周期流水保持正常状态；新合并周期流水按创建日和保留期设置有效归档日期，所有被合并替代的源周期流水关闭、更新归档日期和更新日期，并记录 `mergebusiflowid`。
- 基于关闭周期流水在切换下一日时一定删除的前提，明确周期配对候选口径简化为 `createdate < 当前业务日期`，不按 `status` 或 `mergebusiflowid` 过滤，并支持周期配对重做时将当天关闭的周期流水恢复为有效保留状态。
- 提供历史存量周期流水合并工程脚本，支持 dry-run，并按当前 `comm_busidefine_refrule` 配置生成合并 key 与合并结果。
- 同步数据库模型、交付 SQL、DAO/cache/memdb 结构、归档/迁移配置和相关查询/加载配置，确保新增字段与合并生命周期一致。

## Capabilities

### New Capabilities

- `perioddetail-merge-generation`: 定义周期流水合并生成、滚动合并、源流水关闭追溯、周期配对候选和重做恢复、历史存量合并工程脚本的业务能力。

### Modified Capabilities

None.

## Impact

- 影响日终清算周期流水生成模块：`macbs-base/lbm_pro/macbs/cbs_clear/generate_perioddetail/`。
- 影响日终清算周期配对模块及其重做恢复、候选加载规则：`macbs-base/lbm_pro/macbs/cbs_clear_match/`。
- 影响读取 `node_perioddetail` 作为周期配对候选来源的路径，需要统一按 `createdate < 当前业务日期` 评估；`generate_perioddetail` 合并源仍按历史正常周期流水口径筛选。
- 影响 `node_perioddetail` / `his_node_perioddetail` 表结构、PDM 模型、DAO/memdb/cache 生成结构、归档与迁移配置。
- 影响 `comm_busidefine.periodflag` 的业务配置使用方式；现有 `0-不生成`、`1-生成` 语义保持兼容。
- 需要新增 patch 工程脚本用于历史存量周期流水合并，脚本必须支持 dry-run 与冲突校验。
