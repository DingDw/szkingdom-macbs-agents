## 1. 数据模型和配置

- [x] 1.3 在正确的 Gauss 日终 patch 路径中新增 `node_perioddetail.mergebusiflowid` 和 `his_node_perioddetail.mergebusiflowid` 的 DDL。
- [x] 1.5 更新引用 `node_perioddetail` 或 `his_node_perioddetail` 的归档和迁移配置，包括显式列清单和 `select *` 依赖。
- [x] 1.6 确认现有 `periodflag` 字典/配置支持 `0-不生成`、`1-生成`、`2-合并生成`，且不改变 `0`/`1` 既有行为。

## 2. 周期流水生成

- [x] 2.1 调整 `generate_perioddetail` 的缓存加载逻辑，使用具名常量加载 `periodflag = '1'` 和 `periodflag = '2'` 的业务，避免魔法字符值。
- [x] 2.2 保持 `periodflag = '1'` 业务的既有普通周期流水生成行为不变。
- [x] 2.3 对 `periodflag = '2'` 业务，先生成当日普通周期流水和周期流水子表源记录，按既有保留期规则设置有效流水 `archivedate`，再执行合并评估。
- [x] 2.4 实现合并源采集：历史源为 `createdate < 当前业务日期 and status = 正常` 的记录，当日源为本次生成的普通周期流水，排除所有已关闭历史记录。
- [x] 2.5 实现滚动合并：未被消费且仍为正常状态的旧合并周期流水必须参与下一轮合并评估。
- [x] 2.6 确保单笔分组不生成额外合并周期流水。
- [x] 2.7 当同一分组源记录超过一笔时，插入一笔合并 `node_perioddetail`，并将所有源记录更新为关闭状态、当前归档日期、当前更新日期和对应 `mergebusiflowid`。
- [x] 2.8 在合并模式分支、合并源选择、源流水关闭、合并流水插入等关键业务逻辑处增加清晰的业务注释。

## 3. 合并 key 和汇总逻辑

- [x] 3.1 按 `reftype` 和 `reftargetbusitype` 加载 `periodflag = '2'` 业务对应的周期配对 `comm_busidefine_refrule` 记录。
- [x] 3.2 从等值和不等值引用规则表达式中解析目标周期流水侧字段；常量不进入 key，但保留为适用过滤或校验条件。
- [x] 3.3 基于规则目标侧字段并集和安全维度构建合并 key，安全维度包括 `busitype`、`fundacct`、`fundunit`、`settunit`、`market`、`secuid`、`stkholdunit`、`curcode`、`stkid`、`mainseat`、`trdseat`。
- [x] 3.4 对 `market`、`secuid`、`stkholdunit`、`stkid`、`mainseat`、`trdseat` 等可空安全维度统一归一化空值和 null。
- [x] 3.5 实现主表汇总：仅 `matchamt` 和 `matchqty` 求和，其他主表字段从一笔源记录作为代表值复制，再覆盖合并生命周期字段。
- [x] 3.6 实现子表汇总：按 `fieldname + fieldflag` 分组，对 `subtype = '1'`、`fieldname` 以 `amt` 结尾、`fieldname` 以 `qty` 结尾或以字面量 `fee_` 开头的记录求和。
- [x] 3.7 从一笔代表源记录保留非汇总子表字段，并将合并子表记录改写为新合并 `busiflowid`，`archivedate` 继承合并主表保留期归档日期、`updatedate = 0`。
- [x] 3.8 增加合并 key 字段、分组数量、源流水关闭数量、合并流水生成数量的校验或日志输出。

## 4. 重做和候选过滤

- [x] 4.1 在 `cbs_clear_match/clearmatch_restore` 三段式重做前恢复阶段实现周期配对重做恢复：将所有 `updatedate = 当前业务日期 and status = 关闭` 的周期流水恢复为正常状态，`archivedate` 按周期流水 `createdate` 和默认保留期重算，`updatedate = 当前业务日期`，`mergebusiflowid` 为空，禁止放在 `CClearMatch::Before()`。
- [x] 4.2 在 `cbs_clear_match/clearmatch_restore` 三段式重做前恢复阶段同步恢复对应 `node_perioddetailsub` 记录，将 `archivedate` 恢复为主表有效归档日期，`updatedate` 设置为当前业务日期。
- [x] 4.3 实现 `generate_perioddetail` 重做恢复：仅恢复 `updatedate = 当前业务日期`、`status = 关闭` 且 `mergebusiflowid` 非空的记录，按默认保留期恢复有效归档日期并保留当前更新日期，然后删除当日生成的周期流水和子表再重新生成。
- [x] 4.4 调整周期配对候选加载条件为 `createdate < 当前业务日期`，并确保不按 `status` 或 `mergebusiflowid` 过滤。
- [x] 4.5 检查周期配对外其他候选池式读取 `node_perioddetail` 的路径，区分周期配对候选口径与 `generate_perioddetail` 合并源状态过滤口径。
- [x] 4.6 确认按精确 `busiflowid` 查询的路径不会错误套用候选过滤，避免隐藏已被引用的记录。

## 5. 历史合并工程脚本

- [x] 5.1 在合适的 `script/patch/.../工程脚本` 路径下新增历史周期流水合并准备脚本。
- [x] 5.2 实现 dry-run 模式，输出受影响的 `periodflag = '2'` 业务类型、合并 key 字段、源记录数、预计合并后记录数、单笔分组数量、最大分组笔数、预计合并流水号、长度检查、主键冲突检查、异常状态检查。
- [x] 5.3 实现正式执行模式，生成历史合并周期流水，且 `createdate = select max(busidate) from sys_config`。
- [x] 5.4 工程脚本合并流水号按“源流水最小 `createdate` + `M` + 序号”生成，并校验不超过 `node_perioddetail.busiflowid` 长度且不与既有流水号冲突。
- [x] 5.5 将历史源周期流水关闭，设置当前处理日期为 `archivedate` 和 `updatedate`，并将 `mergebusiflowid` 设置为生成的合并流水号。
- [x] 5.6 在工程脚本目录补充脚本前置条件、dry-run 审核步骤、正式执行步骤、回滚/备份要求说明。

## 6. 验证

- [ ] 6.1 验证 `periodflag = '0'` 和 `periodflag = '1'` 业务保持既有行为。
- [ ] 6.2 验证 `periodflag = '2'` 的单笔分组不会额外生成合并周期流水。
- [ ] 6.3 验证当日多笔分组会生成一笔合并周期流水、关闭所有源周期流水，并正确汇总主表和子表字段。
- [ ] 6.4 验证历史正常周期流水、当日新生成周期流水以及未消费的旧合并周期流水可以滚动合并为新的合并周期流水。
- [ ] 6.5 验证已关闭历史周期流水不会作为合并源参与合并。
- [ ] 6.6 验证周期配对只按 `createdate < 当前业务日期` 加载候选，且不按 `status` 或 `mergebusiflowid` 过滤；同一周期流水当日被交割流水 A 关闭后，仍可继续供交割流水 B 配对。
- [ ] 6.7 验证周期配对重做后再重做周期流水生成时，数据可正确恢复和重新生成，不产生重复有效周期流水。
- [ ] 6.8 验证历史合并工程脚本 dry-run 能发现流水号长度冲突、主键冲突和异常源状态。
- [x] 6.9 对修改过的 C++、SQL、模型文件运行定向静态检查或 diagnostics；仅在用户明确要求时执行定向构建。
