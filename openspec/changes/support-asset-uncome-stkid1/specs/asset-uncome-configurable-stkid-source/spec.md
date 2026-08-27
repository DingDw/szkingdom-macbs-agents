## ADDED Requirements

### Requirement: 资产补偿支持扩展证券字段赋值配置
系统必须在标准表 `comm_assetuncomeconfig` 中提供 `extfieldassign` 配置字段，用于控制资产补偿生成时的扩展字段赋值规则；系统必须支持 `stkid=stkid1` 作为白名单赋值规则，并适用于 `assetmethod=1`、`assetmethod=2`、`assetmethod=3`。

#### Scenario: 周期流水按 stkid1 生成补偿资产证券字段
- **WHEN** `comm_assetuncomeconfig.extfieldassign` 配置为 `stkid=stkid1`，`assetmethod` 为 `1`，且源 `node_perioddetail.stkid1` 非空
- **THEN** 生成的 `node_assetuncome.market` 和 `node_assetuncome.stkcode` 必须由 `node_perioddetail.stkid1` 推导

#### Scenario: 交割流水按 stkid1 生成补偿资产证券字段
- **WHEN** `comm_assetuncomeconfig.extfieldassign` 配置为 `stkid=stkid1`，`assetmethod` 为 `2` 或 `3`，且源 `node_settdetail.stkid1` 非空
- **THEN** 生成的 `node_assetuncome.market` 和 `node_assetuncome.stkcode` 必须由 `node_settdetail.stkid1` 推导

#### Scenario: stkid1 为空时回退默认证券字段
- **WHEN** `comm_assetuncomeconfig.extfieldassign` 配置为 `stkid=stkid1`，但源流水 `stkid1` 为空
- **THEN** 生成的 `node_assetuncome.market` 和 `node_assetuncome.stkcode` 必须保留现有默认逻辑，即使用源流水 `market/stkcode`

#### Scenario: 非法扩展字段赋值配置被拒绝
- **WHEN** `comm_assetuncomeconfig.extfieldassign` 包含空值或 `stkid=stkid1` 以外的任何不支持配置
- **THEN** 资产补偿任务必须以明确的配置错误失败，且不得继续生成可能错误的资产补偿数据

### Requirement: 市值计算支持配置证券内码来源
资产补偿表达式函数 `GetMktValue` 必须支持 `GetMktValue("1")`、`GetMktValue("1","stkid")`、`GetMktValue("1","stkid1")` 三种周期流水市值计算写法，并必须保持现有市值计算算法不变。

#### Scenario: 单参数 GetMktValue 保持兼容
- **WHEN** 资产补偿取值表达式使用 `GetMktValue("1")`
- **THEN** 系统必须继续按现有默认逻辑使用 `node_perioddetail.stkid` 计算市值

#### Scenario: GetMktValue 按配置使用 stkid1
- **WHEN** 资产补偿取值表达式使用 `GetMktValue("1","stkid1")`，且 `node_perioddetail.stkid1` 非空
- **THEN** 系统必须使用 `node_perioddetail.stkid1` 作为证券内码进行证券、行情和证券模板查询，并保持现有价格选择和市值计算规则不变

#### Scenario: GetMktValue 的 stkid1 为空时回退默认来源
- **WHEN** 资产补偿取值表达式使用 `GetMktValue("1","stkid1")`，但 `node_perioddetail.stkid1` 为空
- **THEN** 系统必须回退使用 `node_perioddetail.stkid`，并保持现有市值计算行为不变

#### Scenario: 非法 GetMktValue 来源参数被拒绝
- **WHEN** 资产补偿取值表达式调用 `GetMktValue` 时第二个参数不是 `stkid` 或 `stkid1`
- **THEN** 资产补偿任务必须以明确的配置错误失败

### Requirement: 按配置缓存 stkid1 依赖数据
资产补偿缓存阶段必须在计算前加载配置中 `stkid1` 相关资产补偿规则所需的证券和行情数据。

#### Scenario: 周期流水配置依赖 stkid1 时缓存 stkid1 证券
- **WHEN** 周期流水资产补偿配置在 `extfieldassign` 或 `GetMktValue` 中使用 `stkid1`
- **THEN** 缓存阶段必须通过现有证券和行情缓存链路加载非空 `node_perioddetail.stkid1` 对应证券及其清算日期行情

#### Scenario: 交割流水配置依赖 stkid1 时缓存 stkid1 证券
- **WHEN** 交割流水资产补偿配置在 `extfieldassign` 中使用 `stkid1`
- **THEN** 缓存阶段必须通过现有证券和行情缓存链路加载非空 `node_settdetail.stkid1` 对应证券及其清算日期行情

### Requirement: 国信 013702 使用 stkid1 资产补偿配置
国信 Gauss 增量配置必须更新 `comm_assetuncomeconfig` 中 `busitype=013702` 的资产补偿配置，使其按 `stkid1` 计算市值并生成补偿资产证券字段。

#### Scenario: 国信 013702 按 stkid1 计算和生成补偿资产
- **WHEN** 国信 `busitype=013702` 的 `comm_assetuncomeconfig` 配置被应用
- **THEN** `valueexplain` 必须使用 `GetMktValue("1","stkid1")`，且 `extfieldassign` 必须使用 `stkid=stkid1`
