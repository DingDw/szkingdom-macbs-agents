## Why

需求编号：FS-CBS-21457。清算业务类别 `busitype` 的粒度不足，同一业务类别下不同银行业务流水无法准确统计到保证金日结表对应科目。需要保留流水的原始摘要 `origin_digestid`，并支持在日结配置中按摘要筛选。

## What Changes

- `node_fundsettle_mid`、`nodex_fundsettle_mid` 新增 `origin_digestid`，节点首次汇总和汇总节点二次合并均将其纳入汇总键。
- 从 `node_logasset`、`node_settdetail` 透传原始摘要；无摘要的资产、余额和户数来源保留空值语义。
- `comm_fundsettleset` 增加 `pt_origin_digestid`（允许原始摘要）和 `fd_origin_digestid`（排除原始摘要），格式为 `Asset:busitypeA-111,222,333;busitypeB-111|Debtor:busitypeC-333`，Asset表示贷方、Debtor表示借方，每侧可按业务类别分别配置允许及禁止摘要。
- 生成 `node_fundsettle` 时在现有业务条件之上增加摘要过滤：原始摘要为空时跳过两项过滤；非空摘要仅使用当前借贷侧及 `busitype` 对应的允许和禁止集合，未配置侧、类别或集合为空时不限制，禁止优先；无论摘要配置是否为空，普通科目和未识别项均按摘要粒度判断方向，不跨摘要轧差。
- 覆盖清算正常生成、跨节点合并、重新生成和相关数据读写映射；配置为空仅表示不限制摘要；分组及借贷方向仍统一采用摘要粒度。

## Capabilities

### New Capabilities

- `fundsettle-origin-digestid`: 保证金日结中间数据保留原始摘要维度，支持配置允许、排除列表并生成科目汇总结果。

### Modified Capabilities

无。现有主规格未覆盖本能力。

## Impact

- `macbs-base`：`cbs_report` 模块本地汇总键、首次汇总、二次合并、日结规则过滤、重新生成路径及相关 DAO 映射。
- `macbs-service`：日终 `MACBS-V3` 模型由用户手工维护；实现时仅新增或修改 Gauss `patch` 下逐表 DDL，核对配置维护接口相关字段映射。历史表变更以归档确认结果为准。
- 沿用中间表三段式功能号 `631005/631004/631003` 和独立尾处理 `631006`；追加临时单功能号 `631049`，继承`CNodexFundSettle`，直接读取nodex磁盘中间表和comm磁盘配置生成日结结果。最终报表仍按现有科目和展示维度汇总。
- 中间数据行数可能增加；部署需要协调数据库结构、DAO 和业务代码版本。旧中间数据缺失的摘要无法通过仅增加字段恢复。
- 用户已确认模型调整完成，不涉及日切和归档条件修改；已按同步模型实施32位摘要、4000位配置列表，业务代码与增量SQL已维护，验证记录见 `verification.md`。
