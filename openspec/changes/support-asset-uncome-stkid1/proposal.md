## Why

国信个性化资产补偿配置中，上海 A 股配股配债申报业务 `013702` 需要按周期流水 `stkid1` 对应证券计算补偿市值，并在最终资产补偿明细中体现 `stkid1` 对应的市场和证券代码。当前资产补偿逻辑固定使用源流水自身 `stkid/stkcode`，无法通过配置表达这一类目标证券切换需求。

## What Changes

- 在标准表 `comm_assetuncomeconfig` 增加 `extfieldassign` 字段，用于配置资产补偿生成时的扩展字段赋值规则。
- 支持 `extfieldassign='stkid=stkid1'`，在 `assetmethod=1/2/3` 的周期流水和交割流水资产补偿生成场景中，使用源流水 `stkid1` 推导 `node_assetuncome.market/stkcode`。
- 扩展资产补偿表达式函数 `GetMktValue`，支持可选第二参数 `stkid` 或 `stkid1`，用于控制市值计算采用的证券内码来源。
- `stkid1` 为空时回退原默认 `stkid/market/stkcode` 逻辑；非法 `extfieldassign` 或非法 `GetMktValue` 第二参数必须报错阻断。
- 更新国信 `013702` 资产补偿配置，使其通过 `GetMktValue("1","stkid1")` 和 `extfieldassign='stkid=stkid1'` 按 `stkid1` 计算市值并生成补偿资产证券代码。

## Capabilities

### New Capabilities
- `asset-uncome-configurable-stkid-source`: 资产补偿配置支持通过标准配置控制补偿明细证券字段和市值计算证券内码来源。

### Modified Capabilities

## Impact

- 代码影响：`macbs-base` 日终数据汇总资产补偿处理器、资产补偿表达式函数、相关 DAO 表结构生成文件。
- 数据库影响：`comm_assetuncomeconfig` 标准表新增字段；新增公共 Gauss patch DDL 和国信个性化 Gauss patch DML。
- 配置影响：国信 `comm_assetuncomeconfig` 中 `busitype=013702` 的 `valueexplain` 和新增 `extfieldassign`。
- 兼容性：旧配置 `GetMktValue("1")` 继续按原默认 `stkid` 逻辑执行；未配置 `extfieldassign` 的业务保持原行为。
