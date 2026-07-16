## 1. 代码定位与数据模型确认

- [x] 1.1 按 `AGENTS.md` 规则从 `macbs-service/database/pdma/split_pdm/macbs-day/` 定位日间清算 `day_gpzydebt_command` 模型，不使用 `MACBS-V3` 作为日间表模型依据。
- [x] 1.2 定位 `day_gpzydebt_command.market`、`settdate`、`deadline`、`createdate` 字段在日间模型和 `full/gauss/fs_cbs_day` 脚本中的字段类型。
- [x] 1.3 确认 `day_gpzydebt_command` 物理主键为 `sno`，并区分其与 `sno + gpzysno + createdate` 业务匹配键的关系。
- [x] 1.4 定位 `node_gpzydebt_intrrepayplan.market`、`settdate`、`deadline`、`createdate` 字段在日终模型和 DAO 中的字段名、类型和访问成员。
- [x] 1.5 定位 `node_gpzydebt_intrrepayplan`、`node_gpzydebt` 的已生成 DAO/cache manager 文件和主键访问方式；如还息计划表缺少 cache manager，先补齐生成文件。
- [x] 1.6 确认 `node_gpzydebt.status` 已了结状态常量或字典值，避免硬编码含义不清的状态判断。
- [x] 1.7 确认 `kcps_stream` 在现有代码中的物理库查询用法，复用本仓库已有连接、错误处理和字段读取模式。
- [x] 1.8 确认 `CDaySettdetailClear` 的七阶段边界：`Before()` 重做恢复，`Cache()` 读取日间指令并缓存日终内存库数据，`Clear()` 校验和生成待写计划，`Write()` 批量写入。
- [x] 1.9 确认 `day_gpzydebt_command` 位于日间 nodex 物理库，并确认读取前切换数据源、读取后恢复数据源的本模块既有写法。

## 2. 新增 gpzy_intrrepay scope

- [x] 2.1 在 `day_cbs_adapter_scope` 中新增股票质押批量还息 scope 常量，建议值为 `4`，并添加业务含义注释。
- [x] 2.2 在 `CDaySettdetailClear` 中新增股票质押批量还息处理所需的数据结构、市场字段、缓存索引和私有方法声明。
- [x] 2.3 在 `Clear()` 中按 `IsInDayclearAdapterScope()` 调用新 scope 的处理方法，保持未配置 scope 时无行为变化。
- [x] 2.4 为新 scope 的关键判断、分市场过滤和业务处理补充明确业务注释。

## 3. 日间指令读取与过滤

- [x] 3.1 在 `Cache()` 阶段切换到 nodex 数据源后使用 `kcps_stream` 读取物理库 `day_gpzydebt_command`，不通过 `phydbManager`。
- [x] 3.2 读取字段中包含 `market`，并将读取结果映射为内部指令结构，包含生成/滚动计划需要的字段、有效性判断字段和定位错误所需的 `sno/gpzysno/createdate/market`。
- [x] 3.3 按日间模型把 `settdate`、`deadline`、`createdate` 作为字符串字段读取，并显式转换为日终 `kdt_date`。
- [x] 3.4 在读取 `day_gpzydebt_command` 的 SQL 中直接追加 `settbody = GetSettbody()` 条件，不再用代码层过滤和统计结算主体忽略数。
- [x] 3.5 在读取 `day_gpzydebt_command` 的 SQL 中直接追加 `market in markets` 条件，不再用代码层过滤和统计市场忽略数。
- [x] 3.6 不在统一读取过滤阶段用 `createdate == GetBusidate()` 或 `status == '1'` 排除全部其他指令。
- [x] 3.7 在计划处理阶段对当日新增和历史指令统一判断 `status == '1'`，无效状态指令只计入忽略，不生成或滚动计划。
- [x] 3.8 对读取数量、候选数量、当日新增数量、历史有效滚动数量、无效状态忽略数量和错误数量输出流程日志，移除结算主体、市场和合约不存在过滤计数占位符。
- [x] 3.9 读取 `day_gpzydebt_command` 完成后恢复日终数据源，避免影响后续 `node_gpzydebt` 和 `node_gpzydebt_intrrepayplan` 缓存。

## 4. 合约和计划缓存

- [x] 4.1 使用 `node_gpzydebt` cache manager 查询指令对应的合约记录，不将常规读取路径落到 `MemdbManager`。
- [x] 4.2 `node_gpzydebt` 在 `Cache()` 中缓存时，按照 `busidate=T-1` 上一业务日进行过滤。
- [x] 4.3 `GetGpzyDebt()` 查询合约时按上一业务日 `busidate=T-1` 查找，未传入 `dealpoint` 时也仅在 T-1 日合约缓存中匹配。
- [x] 4.4 对 `gpzysno` 不存在于上一业务日 `node_gpzydebt` 合约缓存的指令，在代码层过滤并忽略，不报错、不生成或滚动计划，且不维护单独流程日志计数。
- [x] 4.5 对合约状态已了结的指令报错，错误信息包含 `sno/gpzysno/createdate/market` 和合约状态。
- [x] 4.6 在 `Cache()` 阶段使用 `node_gpzydebt_intrrepayplan` cache manager 仅缓存 `busidate=T-1` 的还息计划数据。
- [x] 4.7 缓存 `node_gpzydebt_intrrepayplan` 时按任务参数 `markets` 过滤 `market`，避免处理其他市场计划。
- [x] 4.8 移除依赖缓存 T 日计划的重复检查逻辑，T 日重做重复由 `Before()` 删除和 cache manager 插入索引处理。

## 5. 还息计划滚动与生成

- [x] 5.1 对 `createdate == GetBusidate()` 且 `status == '1'` 的当日新增有效指令，新生成 T 日 `node_gpzydebt_intrrepayplan` 记录。
- [x] 5.2 对 `createdate == GetBusidate()` 且 `status != '1'` 的当日新增无效指令，忽略且不生成计划。
- [x] 5.3 当日新增计划同步日间指令除 `status` 以外的计划要素，并将计划 `status` 设置为 `0` 扣收中。
- [x] 5.4 当日新增计划的 `market` 必须使用日间指令 `market`。
- [x] 5.5 对 `createdate != GetBusidate()` 的历史指令，仅在日间指令状态有效时进入滚动处理。
- [x] 5.6 历史有效指令使用 `node_gpzydebt_intrrepayplan` cache manager 按 `sno + gpzysno + createdate + busidate=上一业务日` 查找 T-1 计划。
- [x] 5.7 历史有效指令存在 T-1 计划时复制生成 T 日计划，仅修改 `busidate` 为当前业务日，并将 `deadline` 更新为日间指令值。
- [x] 5.8 历史滚动生成的 T 日计划 `market` 必须与日间指令 `market` 保持一致。
- [x] 5.9 历史有效指令不存在 T-1 计划时应报错，错误信息包含 `sno/gpzysno/createdate/market` 和上一业务日。
- [x] 5.10 确保所有计划处理均按指令级别 `sno + gpzysno + createdate` 执行，不按 `gpzysno` 聚合。

## 6. 写入与重做处理

- [x] 6.1 在 `Write()` 中通过 cache manager 批量写入新生成的 `node_gpzydebt_intrrepayplan` 记录。
- [x] 6.2 在 `Before()` 中增加重做恢复处理，删除 `busidate=当日` 且 `market` 属于任务 `markets` 的 `node_gpzydebt_intrrepayplan` 记录，避免重复生成。
- [x] 6.3 如重做恢复删除使用 `MemdbManager`，需限制在 `Before()` 恢复删除路径并补充业务注释。
- [x] 6.4 为计划写入数量、当日新增数量、历史滚动数量、无效状态忽略数量和错误数量输出流程日志，并移除无用忽略计数占位符。
- [x] 6.5 删除不再使用的结算主体忽略、市场忽略、合约不存在忽略和总忽略计数成员及其日志参数。

## 7. 国信 patch 脚本

- [x] 7.1 在 `macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_comm/2.data/sys_param_define.sql` 更新 `paramid=62029` 默认值为 `1,2,4`。
- [x] 7.2 在 SQL 注释中说明该配置用于国信启用 624001 股票质押批量还息计划 scope。
- [x] 7.3 使用 `rg` 检查 `62029`、`PARAMID_DAY_CBS_ADAPTER_SCOPE` 和国信 patch 中同名配置，避免遗漏或重复冲突。

## 8. 验证

- [ ] 8.1 构造或复用测试数据验证未配置 scope 时不读取日间指令、不写还息计划。
- [ ] 8.2 验证 `markets` 只包含单市场时，读取 SQL 只返回该市场指令，且只删除和缓存该市场还息计划。
- [ ] 8.3 验证 `markets` 包含多个逗号分隔市场时，读取 SQL 能返回多个市场指令且不返回其他市场。
- [ ] 8.4 验证 `createdate == GetBusidate()` 且 `status == '1'` 的当日新增有效指令能生成 T 日计划，计划 `market` 正确、`status=0` 且不复制日间指令 `status`。
- [ ] 8.5 验证 `createdate == GetBusidate()` 且 `status != '1'` 的当日新增无效指令被忽略且不生成计划。
- [ ] 8.6 验证 `createdate != GetBusidate()` 的历史有效指令存在 T-1 计划时，T 日计划只调整 `busidate` 和 `deadline`，并保留正确 `market`。
- [ ] 8.7 验证合约不存在指令被过滤且不报错，合约已了结、历史有效指令缺少 T-1 计划两类错误场景正常报错。
- [ ] 8.9 验证读取 `day_gpzydebt_command` 时切换到 nodex 数据源，并在读取完成后恢复日终数据源。
- [x] 8.8 用户明确要求构建时执行目标级构建 `cbs_day_clear_adapter`；如未执行构建，在交付说明中明确原因。
