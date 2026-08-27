## ADDED Requirements

### Requirement: 合并生成模式由 periodflag 控制
系统 MUST 支持 `comm_busidefine.periodflag = '2'` 作为周期流水合并生成模式，并保持 `0` 和 `1` 的既有含义不变。

#### Scenario: 业务配置为合并生成
- **WHEN** 某业务类型配置 `periodflag = '2'`
- **THEN** 周期流水生成 MUST 先基于当日来源交割流水生成普通周期流水，再对这些周期流水执行合并生成评估。
- **AND** 新生成的有效普通周期流水 MUST 按既有保留期规则设置 `archivedate`，并将 `updatedate` 初始化为 0。

#### Scenario: 业务未配置为合并生成
- **WHEN** 某业务类型配置 `periodflag = '0'` 或 `periodflag = '1'`
- **THEN** 系统 MUST 保持该业务类型既有的不生成或普通生成行为。

### Requirement: 合并周期流水生命周期必须明确
系统 SHALL 使用 `node_perioddetail.mergebusiflowid` 存储合并关系，并 MUST 保证被合并替代的源流水与有效合并流水处于互斥状态。

#### Scenario: 多笔源周期流水被合并
- **WHEN** 同一合并分组内存在多笔源周期流水
- **THEN** 系统 MUST 插入一笔合并周期流水，且该记录满足 `status = 正常`、`archivedate = 按当前业务日期和默认周期流水保留期计算的归档日期`、`updatedate = 0`、`mergebusiflowid` 为空。
- **AND** 系统 MUST 将分组内每笔源周期流水更新为 `status = 关闭`、`archivedate = 当前业务日期`、`updatedate = 当前业务日期`、`mergebusiflowid = 合并周期流水号`。

#### Scenario: 合并分组内只有一笔源周期流水
- **WHEN** 合并分组内只有一笔源周期流水
- **THEN** 系统 MUST NOT 为该分组额外生成合并周期流水。
- **AND** 如果该源周期流水本身状态正常，则它 MUST 继续作为有效周期流水保留。

### Requirement: 合并源必须排除已关闭历史周期流水
系统 SHALL 只从正常历史周期流水和当前执行生成的周期流水中选择合并源。

#### Scenario: 为合并生成业务选择合并源
- **WHEN** `generate_perioddetail` 处理 `periodflag = '2'` 的业务类型
- **THEN** 历史合并源 MUST 限定为 `createdate < 当前业务日期` 且 `status = 正常` 的记录。
- **AND** 当日合并源 MUST 限定为本次 `generate_perioddetail` 生成的普通周期流水。

#### Scenario: 存在已关闭历史记录
- **WHEN** 历史周期流水的 `status = 关闭`
- **THEN** 系统 MUST 将这些记录排除在合并源之外，不受其 `mergebusiflowid` 是否为空影响。

#### Scenario: 历史合并流水未被消费
- **WHEN** 旧合并周期流水仍为 `status = 正常`
- **THEN** 系统 MUST 在下一轮滚动合并评估中包含该旧合并周期流水。

### Requirement: 周期配对候选必须使用历史创建日期
系统 SHALL 基于 `createdate < 当前业务日期` 加载周期配对候选，而不是基于周期流水状态或合并关系标记过滤候选。

#### Scenario: 加载周期配对候选
- **WHEN** 周期配对加载候选 `node_perioddetail` 记录
- **THEN** 候选记录 MUST 满足 `createdate < 当前业务日期`。
- **AND** 候选记录 MUST NOT 因 `status` 为正常或关闭而被单独过滤。
- **AND** 候选记录 MUST NOT 因 `mergebusiflowid` 为空或非空而被单独过滤。

#### Scenario: 当日已关闭周期流水继续参与配对
- **WHEN** 同一笔历史周期流水已在当前业务日期被交割流水 A 周期配对并关闭
- **AND** 后续交割流水 B 按周期配对规则仍应匹配该周期流水
- **THEN** 系统 MUST 允许该 `createdate < 当前业务日期` 的周期流水继续作为候选参与交割流水 B 的周期配对。

#### Scenario: 按已引用流水号精确查询周期流水
- **WHEN** 后续处理按已记录的 `busiflowid` 精确查询周期流水
- **THEN** 查询 MUST 能查到该精确记录，不得套用周期配对候选过滤条件导致记录不可见。

### Requirement: 合并 key 必须从周期配对引用规则推导
系统 SHALL 根据周期配对引用规则和强制安全维度，为 `periodflag = '2'` 的目标业务类型推导合并 key。

#### Scenario: 多条周期配对规则指向同一源业务类型
- **WHEN** 多条 `comm_busidefine_refrule` 记录以周期配对 reftype 指向同一个合并生成业务类型
- **THEN** 合并 key MUST 取所有规则中目标周期流水侧字段的并集。

#### Scenario: 引用规则包含不等条件字段
- **WHEN** 周期配对引用规则中存在涉及目标周期流水侧字段的 `<>` 比较
- **THEN** 该目标侧字段 MUST 参与合并 key。

#### Scenario: 引用规则包含常量条件
- **WHEN** 周期配对引用规则中存在常量条件
- **THEN** 常量 MUST NOT 作为合并 key 字段。
- **AND** 常量 MUST 仍可作为规则适用过滤条件或校验约束使用。

#### Scenario: 追加安全维度
- **WHEN** 系统构建合并 key
- **THEN** 除引用规则推导字段外，key MUST 包含 `busitype`、`fundacct`、`fundunit`、`settunit`、`market`、`secuid`、`stkholdunit`、`curcode`、`stkid`、`mainseat`、`trdseat`。

#### Scenario: key 字段为空
- **WHEN** `market`、`secuid`、`stkholdunit`、`stkid`、`mainseat`、`trdseat` 等合并 key 字段为空或 null
- **THEN** 系统 MUST 以一致方式处理这些空值，并仍允许对应分组被合并。

### Requirement: 合并周期流水必须按配置汇总数值字段
系统 SHALL 仅对已配置的主表和子表字段执行汇总，生成合并周期流水。

#### Scenario: 汇总周期流水主表字段
- **WHEN** 多笔源周期流水被合并
- **THEN** 合并周期流水的 `matchamt` MUST 等于源流水 `matchamt` 之和。
- **AND** 合并周期流水的 `matchqty` MUST 等于源流水 `matchqty` 之和。
- **AND** 除合并生命周期字段覆盖项外，其他主表字段 MUST 从一笔源周期流水代表记录复制。

#### Scenario: 汇总周期流水子表字段
- **WHEN** 源 `node_perioddetailsub` 记录被合并
- **THEN** 子表汇总 MUST 按 `fieldname + fieldflag` 分组。
- **AND** 当 `subtype = '1'`、`fieldname` 以 `amt` 结尾、`fieldname` 以 `qty` 结尾，或 `fieldname` 以 `fee_` 开头时，对应记录 MUST 汇总求和。

#### Scenario: 保留非汇总周期流水子表字段
- **WHEN** 源 `node_perioddetailsub` 记录不满足汇总规则
- **THEN** 合并周期流水子表 MUST 从一笔源记录保留这些字段作为代表数据。

### Requirement: 重做恢复必须遵守清算阶段职责
系统 SHALL 区分周期配对重做和周期流水生成重做，按阶段职责恢复周期流水状态。

#### Scenario: 周期配对重做恢复当天关闭记录
- **WHEN** 当前业务日期执行周期配对重做
- **THEN** 所有 `updatedate = 当前业务日期` 且 `status = 关闭` 的周期流水 MUST 恢复为 `status = 正常`、`archivedate = 按周期流水 createdate 和默认保留期重新计算的有效归档日期`、`updatedate = 当前业务日期`、`mergebusiflowid` 为空。
- **AND** 受影响的周期流水子表记录 MUST 恢复为同一有效归档日期，并将 `updatedate` 设置为当前业务日期。

#### Scenario: 周期流水生成重做恢复合并关闭记录
- **WHEN** 当前业务日期重做 `generate_perioddetail`
- **THEN** 仅 `updatedate = 当前业务日期`、`status = 关闭` 且 `mergebusiflowid` 非空的周期流水 MUST 在重新生成前恢复为正常状态。
- **AND** 恢复后的周期流水及其子表 MUST 使用按周期流水 createdate 和默认保留期重新计算的有效归档日期，并将 `updatedate` 设置为当前业务日期。
- **AND** 当前业务日期生成的周期流水及其子表记录 MUST 在重新生成前删除。

### Requirement: 历史合并工程脚本必须支持安全 dry-run
系统 SHALL 提供用于历史周期流水合并准备的 patch 工程脚本，并 MUST 支持正式执行前的 dry-run 校验。

#### Scenario: 执行 dry-run 模式
- **WHEN** 历史合并工程脚本以 dry-run 模式执行
- **THEN** 脚本 MUST 输出受影响的 `periodflag = '2'` 业务类型、合并 key 字段、源记录数、预计合并后记录数、单笔分组数量、最大分组笔数、预计生成的合并流水号、流水号长度检查、主键冲突检查、异常状态检查。

#### Scenario: 生成历史合并记录
- **WHEN** 历史合并工程脚本执行正式合并
- **THEN** 新生成的历史合并周期流水 MUST 使用 `select max(busidate) from sys_config` 作为 `createdate`。
- **AND** 生成的合并流水号 MUST 使用源流水最小 `createdate` 拼接 `M` 和序号。
- **AND** 生成的合并流水号 MUST 不超过 `node_perioddetail.busiflowid` 字段长度，且 MUST 不与既有流水号冲突。

### Requirement: 数据模型和持久化配置必须包含合并字段
系统 SHALL 保持周期流水表结构、生成访问对象、归档配置、迁移配置与新增合并字段一致。

#### Scenario: 持久化包含合并字段的周期流水
- **WHEN** 包含 `mergebusiflowid` 的周期流水被插入、更新、归档、迁移或通过生成访问层查询
- **THEN** `node_perioddetail`、`his_node_perioddetail`、PDM 模型定义、生成的 DAO/cache/memdb 结构、归档配置、迁移配置 MUST 全部一致包含 `mergebusiflowid` 字段。
