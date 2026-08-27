## Context

资产补偿日终数据汇总由 `CSumAssetUncome101` 根据 `comm_assetuncomeconfig` 配置生成 `node_assetuncome`。当前周期流水和交割流水补偿明细生成时，证券字段固定从源流水 `market/stkcode` 赋值；资产补偿表达式函数 `GetMktValue` 当前只接收一个字符串参数，并在周期流水场景固定使用 `node_perioddetail.stkid` 查证券、行情和证券模板。

国信上海 A 股配股配债申报 `013702` 的业务口径要求以 `node_perioddetail.stkid1` 作为目标证券：补偿金额按 `stkid1` 对应证券市值计算，补偿明细 `node_assetuncome.market/stkcode` 也应由 `stkid1` 推导。表结构必须保持标准化，不能为国信创建个性化字段或个性化表结构。

## Goals / Non-Goals

**Goals:**
- 在标准 `comm_assetuncomeconfig` 中增加 `extfieldassign` 配置字段，表达资产补偿生成时的扩展证券字段赋值规则。
- 支持 `extfieldassign='stkid=stkid1'` 在 `assetmethod=1/2/3` 场景覆盖补偿明细证券字段来源。
- 扩展 `GetMktValue` 的证券内码来源，使旧配置保持兼容，新配置可指定 `stkid1`。
- 对非法配置报错阻断；对 `stkid1` 为空的业务数据回退默认逻辑。
- 通过公共 DDL patch 增加标准字段，通过国信 DML patch 更新 `013702` 配置。

**Non-Goals:**
- 不新增 `node_assetuncome.stkid` 物理字段；业务口径中的 `stkid` 仅用于从证券内码推导 `market/stkcode`。
- 不新增 `GetMktValue("2", ...)` 的交割流水市值计算能力，保留现有市值算法和现有 `assetmethod` 分支行为。
- 不改动 `comm_assetuncomeconfig.status` 的启停过滤语义。
- 不实现通用任意字段赋值引擎，本期只支持明确白名单 `stkid=stkid1`。

## Decisions

### 标准字段承载扩展赋值

在 `comm_assetuncomeconfig` 表尾新增 `extfieldassign VARCHAR(4000)`，含义为资产补偿生成时的扩展字段赋值配置。选择标准字段而不是国信个性化字段，是因为表结构要求标准化，且该能力后续可复用于其他客户或业务。

备选方案是直接对 `013702` 写死特殊分支；该方案影响面更窄但可配置性差，也会把客户规则固化在公共代码中，因此不采用。

### `extfieldassign` 采用白名单解析

本期仅支持 `stkid=stkid1`。周期流水和交割流水默认先按现有逻辑填充 `node_assetuncome.market/stkcode`，再在配置存在且源流水 `stkid1` 非空时覆盖为 `stkid1` 推导结果：`market=stkid1[0]`，`stkcode=stkid1+1`。源流水 `stkid1` 为空时保持默认值，不视为配置错误。

非法 `extfieldassign` 必须报错阻断，避免拼写错误或未支持字段被静默忽略，导致补偿资产悄悄按旧逻辑生成。

### `GetMktValue` 兼容旧配置并支持指定证券内码来源

`GetMktValue` 的 exprtk 参数签名扩展为同时接受一个或两个字符串参数，例如 `S|SS`。旧配置 `GetMktValue("1")` 等价于 `GetMktValue("1","stkid")`；新配置 `GetMktValue("1","stkid1")` 在周期流水市值计算中优先使用 `node_perioddetail.stkid1` 查证券、行情和证券模板。

实现时不能只把构造函数参数序列从 `S` 改成 `S|SS`。当前 exprtk 在参数序列包含多个候选时，会使用带参数序列下标的多模式 generic function 调用，即回调 `operator()(const std::size_t&, parameter_list_t)`；如果仍只实现现有 `operator()(parameter_list_t)`，多参数序列表达式会落到基类默认实现并返回非法结果。因此 `GetMktValue` 必须实现带 `param_seq_index` 的回调入口，并在该入口中统一处理 `S` 和 `SS` 两类调用。

第二参数只允许 `stkid` 或 `stkid1`。参数非法时必须报错阻断；第二参数为 `stkid1` 但业务数据 `stkid1` 为空时，回退 `node_perioddetail.stkid` 并保持原算法。

### 缓存阶段提前加载 `stkid1` 依赖

当资产补偿配置的 `valueexplain` 或 `extfieldassign` 需要 `stkid1` 时，缓存周期流水或交割流水时应额外缓存非空 `stkid1` 对应的证券信息。行情缓存继续沿用现有“已缓存证券加载当日行情”的方式，保证 `GetMktValue("1","stkid1")` 能使用同一套价格优先级和证券模板兜底逻辑。

### 数据库交付采用公共 DDL 与国信 DML 分离

公共 patch 增加 `comm_assetuncomeconfig.extfieldassign` 标准字段；国信 patch 只更新 `013702` 的配置值。默认不修改 full 脚本，符合增量交付约束。

## Risks / Trade-offs

- [Risk] DAO 手工维护字段顺序不完整，可能导致内存库字段读写错位。→ 优先使用既有 DAO 生成流程；如手工维护，必须同步 memdb/cache/phydb 相关生成文件并检查 stream、insert、update、merge SQL。
- [Risk] `stkid1` 证券未缓存会导致市值计算返回 0 或走异常兜底。→ 缓存阶段根据配置显式缓存非空 `stkid1`，并复用现有行情缓存链路。
- [Risk] 非法配置上线后阻断日终。→ 这是有意选择：配置错误应尽早暴露，避免资产补偿结果静默错误；上线前通过配置校验和针对性用例覆盖。
- [Risk] `stkid1` 为空回退默认逻辑可能掩盖业务数据缺失。→ `013702` 目标场景保证有值；其他误配置场景按用户确认要求回退，建议记录明确日志辅助排查。

## Migration Plan

1. 先发布标准 DDL patch，为 `comm_assetuncomeconfig` 增加 `extfieldassign` 字段。
2. 发布代码，支持新字段解析、`GetMktValue` 可选第二参数和 `stkid1` 缓存。
3. 发布国信 DML patch，将 `013702` 配置更新为 `GetMktValue("1","stkid1")` 与 `stkid=stkid1`。
4. 回滚时先恢复国信 `013702` 配置为旧表达式并清空 `extfieldassign`，再回滚代码；新增标准字段可保留为空。

## Open Questions

无。`assetmethod=3` 已确认随交割流水生成逻辑一并支持；非法配置已确认报错阻断。
