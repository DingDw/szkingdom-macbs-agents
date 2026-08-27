## 1. 数据模型与数据库脚本

- [x] 1.3 新增公共 Gauss patch DDL，在 `comm_assetuncomeconfig` 表尾增加 `extfieldassign VARCHAR(4000)` 并补充字段注释
- [x] 1.4 新增国信 Gauss patch DML，将 `busitype=013702` 更新为 `valueexplain=GetMktValue("1","stkid1")` 且 `extfieldassign=stkid=stkid1`

## 2. 资产补偿配置校验与缓存

- [x] 2.1 在资产补偿加载配置后校验 `extfieldassign`，仅允许空值或 `stkid=stkid1`，非法配置必须报错阻断并输出业务类别和配置值
- [x] 2.2 在周期流水缓存逻辑中识别配置是否依赖 `stkid1`，并额外缓存非空 `node_perioddetail.stkid1` 对应证券
- [x] 2.3 在交割流水缓存逻辑中识别配置是否依赖 `stkid1`，并额外缓存非空 `node_settdetail.stkid1` 对应证券
- [x] 2.4 确认现有行情缓存链路能覆盖额外缓存的 `stkid1` 证券，并保持现有价格缓存方式不变

## 3. GetMktValue 证券内码来源扩展

- [x] 3.1 将资产补偿表达式函数 `GetMktValue` 的 exprtk 参数签名扩展为兼容一个或两个字符串参数，例如 `S|SS`
- [x] 3.2 为 `GetMktValue` 实现 `operator()(const std::size_t&, parameter_list_t)` 多参数序列回调入口，避免 `S|SS` 触发基类默认实现
- [x] 3.3 在带 `param_seq_index` 的回调入口中统一识别 `GetMktValue("1")`、`GetMktValue("1","stkid")`、`GetMktValue("1","stkid1")`
- [x] 3.4 实现 `GetMktValue("1")` 与 `GetMktValue("1","stkid")` 继续使用 `node_perioddetail.stkid`
- [x] 3.5 实现 `GetMktValue("1","stkid1")` 在 `stkid1` 非空时使用 `node_perioddetail.stkid1` 查证券、行情和证券模板
- [x] 3.6 实现 `GetMktValue("1","stkid1")` 在 `stkid1` 为空时回退 `node_perioddetail.stkid`
- [x] 3.7 对非法 `GetMktValue` 第二参数报错阻断，并在错误信息中包含非法参数和值表达式上下文

## 4. 资产补偿明细证券字段覆盖

- [x] 4.1 为周期流水和交割流水生成逻辑增加共用的 `extfieldassign` 应用函数，只支持 `stkid=stkid1`
- [x] 4.2 在 `GenerateDataByPeriodDetail()` 生成 `node_assetuncome` 时，按非空 `node_perioddetail.stkid1` 推导并覆盖 `market/stkcode`
- [x] 4.3 在 `GenerateDataBySettdetail()` 生成 `node_assetuncome` 时，按非空 `node_settdetail.stkid1` 推导并覆盖 `market/stkcode`，覆盖 `assetmethod=2/3`
- [x] 4.4 当源流水 `stkid1` 为空时保留默认 `market/stkcode` 赋值逻辑，并记录可排查日志

## 5. 验证

- [ ] 5.1 增加或调整资产补偿用例，验证旧配置 `GetMktValue("1")` 仍按默认 `stkid` 计算
- [ ] 5.2 增加国信 `013702` 场景用例，验证 `GetMktValue("1","stkid1")` 按 `stkid1` 证券价格计算补偿金额
- [ ] 5.3 验证 `extfieldassign=stkid=stkid1` 时，周期流水生成的 `node_assetuncome.market/stkcode` 来自 `node_perioddetail.stkid1`
- [ ] 5.4 验证交割流水 `assetmethod=2/3` 配置 `extfieldassign=stkid=stkid1` 时，`node_assetuncome.market/stkcode` 来自 `node_settdetail.stkid1`
- [ ] 5.5 验证 `stkid1` 为空时回退默认证券字段和默认市值证券来源
- [ ] 5.6 验证非法 `extfieldassign` 和非法 `GetMktValue` 第二参数均报错阻断
- [x] 5.7 按需运行针对性编译或静态检查；若不执行构建，记录未执行原因
  - 记录：已执行 PDMA JSON 解析、关键路径 `rg` 静态检查和 Zed diagnostics；按项目规则默认不执行构建，且用户未明确要求构建。
