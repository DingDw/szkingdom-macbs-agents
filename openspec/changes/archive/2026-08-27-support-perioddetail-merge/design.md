## Context

当前 `generate_perioddetail` 按每笔交割流水生成一笔 `node_perioddetail`，同类业务长期积累后，周期配对会命中并拼接多笔周期流水号，存在关联流水号超过字段长度并阻断清算的风险。

本变更面向日终清算，基于 `comm_busidefine.periodflag = '2'` 引入周期流水合并生成。周期配对在周期流水生成之前执行；如果周期配对重做，后续周期流水生成一定随之重做，不支持只重做周期配对后直接切日。有效周期流水的 `node_perioddetail.archivedate` 按创建日和保留期计算，关闭流水的 `archivedate` 与 `updatedate` 设置为当前业务日期，切换下一日时会被删除。

## Goals / Non-Goals

**Goals:**

- 支持 `periodflag = '2'` 的业务按周期配对规则反推合并 key，并对历史正常周期流水与当日新生成周期流水进行滚动合并。
- 在 `node_perioddetail` 增加 `mergebusiflowid`，用于记录被合并替代源周期流水所属的合并周期流水。
- 保证被合并替代的源周期流水关闭并归档，切换下一日后仅合并周期流水作为后续有效周期流水保留。
- 明确周期配对候选、周期配对重做恢复、周期流水生成重做恢复的边界。
- 提供历史存量周期流水合并工程脚本，支持 dry-run、流水号冲突检查和字段长度检查。
- 同步数据库模型、DAO/cache/memdb 结构、归档/迁移配置和相关候选加载规则。

**Non-Goals:**

- 不改造日间清算流程。
- 不支持只重做周期配对而不重做后续周期流水生成的执行模式。
- 不改变 `periodflag = '0'` 和 `periodflag = '1'` 的既有业务语义。
- 不把 `mergebusiflowid` 作为周期配对候选过滤条件。
- 不为单笔分组合并生成额外合并周期流水。

## Decisions

### 1. 使用 `mergebusiflowid` 表示源流水被合并替代

新增 `node_perioddetail.mergebusiflowid`，字段长度与 `busiflowid` 保持一致，用于记录源周期流水被哪笔合并周期流水替代。

合并后必须满足以下不变量：

```text
被合并替代的源周期流水：
    status = 关闭
    archivedate = 当前业务日期
    updatedate = 当前业务日期
    mergebusiflowid = 合并流水号

新合并周期流水：
    status = 正常
    archivedate = 按当前业务日期和默认周期流水保留期计算的归档日期
    updatedate = 0
    mergebusiflowid = 空
```

选择该方案而不是复用 `pathid` 或其他业务字段，是因为 `mergebusiflowid` 语义明确、字段长度可控，且能够直接支持重做恢复与历史追溯。

### 2. 周期配对候选只按历史创建日期判断

基于关闭周期流水在切换下一日时一定被删除的前提，周期配对候选统一简化为：

```text
createdate < 当前业务日期
```

候选池扫描不按 `status`、`archivedate` 或 `mergebusiflowid` 过滤。这样可以允许同一笔周期流水在当前业务日期内先被交割流水 A 配对关闭后，继续作为交割流水 B 的周期配对候选，避免 `archiveflag=1` 的前序配对影响当日后续配对。

需要区分三类读取：

- 周期配对候选池扫描：必须使用 `createdate < 当前业务日期`，不得附加 `status` 或 `mergebusiflowid` 过滤。
- `generate_perioddetail` 合并源扫描：仍必须使用历史正常周期流水，避免已关闭历史源被重复合并。
- 按已关联 `busiflowid` 精确查询：不应附加候选过滤条件，避免当天后续处理无法回查已被本日后续阶段关闭但尚未删除的周期流水。

### 3. 合并源范围排除所有已关闭历史流水

`generate_perioddetail` 对 `periodflag = '2'` 的业务先生成当日普通周期流水，再做合并。合并源为：

```text
历史周期流水：
    createdate < 当前业务日期
    and status = 正常

当日周期流水：
    本次 generate_perioddetail 新生成的普通周期流水
```

当日普通周期流水生成时继续使用既有归档日期规则：配号业务按 T+1 归档，其他业务按 `GetOffsetNDaysTradeDate(当前业务日期, MKT_SHANGHAIA, PERIODDETAIL_RESERVE_DAYS)` 设置默认保留期归档日期。合并周期流水作为新的有效周期流水，使用默认保留期归档日期，子表归档日期与合并主表保持一致。

所有 `status = 关闭` 的历史周期流水必须排除。旧合并流水如果未被周期配对消费，仍为 `status = 正常`，必须参与新一轮滚动合并。

单笔分组不生成合并流水：

```text
同组源流水数量 = 1：保留原流水
同组源流水数量 > 1：生成合并流水并关闭所有源流水
```

### 4. 合并 key 从周期配对规则反推并追加安全维度

合并 key 来源为：

```text
comm_busidefine_refrule
where reftype = 周期配对
  and reftargetbusitype = 当前 periodflag=2 业务类型
```

规则处理：

- 多条规则时，合并 key 取所有目标周期流水侧字段的并集。
- `<>` 条件中的目标周期流水侧字段也参与 key。
- 常量条件不参与 key。
- 合并 key 为空也允许合并。
- 常量条件不作为 key，但仍应作为规则适用条件参与源数据筛选或校验。

强制追加安全维度：

```text
busitype
fundacct
fundunit
settunit
market
secuid
stkholdunit
curcode
stkid
mainseat
trdseat
```

其中 `market`、`secuid`、`stkholdunit`、`stkid`、`mainseat`、`trdseat` 可能为空。实现时应统一归一化 `NULL` 与空串，避免 SQL 与 C++ 分组结果不一致。

### 5. 主表与子表合并规则

`node_perioddetail` 主表仅汇总：

```text
matchamt
matchqty
```

其他主表字段从随机一条源周期流水作为代表行继承，再覆盖合并流水自身字段：

```text
busiflowid = 新合并流水号
createdate = 当前业务日期
status = 正常
archivedate = GetOffsetNDaysTradeDate(当前业务日期, MKT_SHANGHAIA, PERIODDETAIL_RESERVE_DAYS)
updatedate = 0
mergebusiflowid = 空
matchamt = sum(源流水.matchamt)
matchqty = sum(源流水.matchqty)
```

`node_perioddetailsub` 按 `fieldname + fieldflag` 分组合并。需要汇总的子表记录为：

```text
subtype = '1'
or fieldname like '%amt'
or fieldname like '%qty'
or fieldname like 'fee_%'
```

程序中建议用字符串规则表达为：

```text
subtype == '1'
or fieldname ends with "amt"
or fieldname ends with "qty"
or fieldname starts with "fee_"
```

工程 SQL 中 `fee_` 的下划线需要作为字面量处理，例如使用 `fieldname like 'fee\_%' escape '\'`。

非汇总子表字段从随机代表源数据透传，合并后子表记录的 `busiflowid` 替换为新合并流水号，`createdate` 与合并主表一致，`archivedate` 继承合并主表保留期归档日期，`updatedate = 0`。

### 6. 重做恢复规则按阶段拆分

周期配对重做前，恢复所有当天关闭的周期流水，回到有效保留状态：

```text
恢复范围：
    updatedate = 当前业务日期
    and status = 关闭

恢复动作：
    status = 正常
    archivedate = 按周期流水 createdate 和默认保留期重新计算的有效归档日期
    updatedate = 当前业务日期
    mergebusiflowid = 空
```

对应 `node_perioddetailsub` 同步恢复：

```text
archivedate = 按主表周期流水 createdate 和默认保留期重新计算的有效归档日期
updatedate = 当前业务日期
```

`generate_perioddetail` 自身重做前，只恢复本阶段合并关闭的源流水：

```text
恢复范围：
    updatedate = 当前业务日期
    and status = 关闭
    and mergebusiflowid 非空

恢复动作：
    status = 正常
    archivedate = 按周期流水 createdate 和默认保留期重新计算的有效归档日期
    updatedate = 当前业务日期
    mergebusiflowid = 空
```

恢复后删除 `createdate = 当前业务日期` 的当日周期流水和子表，再重新生成普通周期流水和合并周期流水。

### 7. 历史存量工程脚本支持 dry-run

历史存量工程脚本放在 patch 工程脚本目录，按当前 `comm_busidefine_refrule` 和本设计的合并 key 规则执行。

脚本必须支持 dry-run，输出至少包括：

- 涉及的 `periodflag = '2'` 业务类型。
- 每个业务类型的合并 key 字段。
- 合并前记录数、预计合并后记录数、单笔分组数量、最大分组笔数。
- 预计生成的合并流水号。
- `busiflowid` 长度检查与主键冲突检查。
- 异常状态数据检查。

历史合并流水字段规则：

```text
createdate = select max(busidate) from sys_config
```

该 `sys_config.busidate` 一定小于下一次周期配对业务日期，因此不会被下一次周期配对的 `createdate < 当前业务日期` 条件过滤掉。

工程脚本合并流水号规则：

```text
合并源流水的最小 createdate + 'M' + 序号
```

流水号必须不超过 `node_perioddetail.busiflowid` 长度，并且不得与现有周期流水号冲突。

## Risks / Trade-offs

- [Risk] 合并 key 过宽会导致合并效果不足，过窄会导致不同业务含义流水被误合并。→ Mitigation: 从周期配对规则取并集并追加安全维度，dry-run 输出每类业务的 key 与分组结果供确认。
- [Risk] 随机代表行可能导致非汇总字段值不可预测。→ Mitigation: 仅对不参与金额/数量汇总的字段使用代表值；关键可匹配维度已进入合并 key 或安全维度，避免核心业务维度漂移。
- [Risk] 子表 `fieldname like 'fee_%'` 在 SQL 中误匹配。→ Mitigation: 工程 SQL 对 `_` 做转义，程序使用明确前缀判断。
- [Risk] 周期配对候选若按 `status = 正常` 过滤，会导致同一周期流水被交割流水 A 当日关闭后无法继续供交割流水 B 配对。→ Mitigation: 基于关闭流水切日一定删除的前提，周期配对候选统一简化为 `createdate < 当前业务日期`；合并源扫描仍单独保留 `status = 正常` 过滤。
- [Risk] 工程脚本生成流水号超过长度或冲突。→ Mitigation: dry-run 必须做长度和主键冲突检查，执行前要求输出检查结果。
- [Risk] 只重做周期配对而不重做周期流水生成会留下错误恢复状态。→ Mitigation: 将该执行模式列为不支持，并依赖流程编排保证周期配对重做后后续阶段重跑。
- [Risk] 新增字段影响归档、迁移和历史表。→ Mitigation: 同步 PDM、全量脚本、patch、历史表、DAO/cache/memdb、归档和迁移列清单。

## Migration Plan

1. 同步模型和数据库结构：新增 `node_perioddetail.mergebusiflowid` 与 `his_node_perioddetail.mergebusiflowid`，更新 PDM、全量脚本、patch DDL、DAO/cache/memdb 结构。
2. 更新 `comm_busidefine.periodflag` 使用 `0-不生成`、`1-生成`、`2-合并生成` 三态语义；保留 `0`/`1` 兼容行为。
3. 实现 `generate_perioddetail` 合并生成、滚动合并、源流水关闭、子表汇总和重做恢复。
4. 实现周期配对候选按 `createdate < 当前业务日期` 加载，并实现周期配对重做恢复。
5. 检查并改造其他周期配对候选池式读取 `node_perioddetail` 的路径；精确按 `busiflowid` 查询的路径不增加候选过滤。
6. 新增历史存量工程脚本，先执行 dry-run 并确认输出，再执行正式合并。
7. 启用 `periodflag = '2'` 的业务配置，并监控合并前后周期流水数量、最大分组笔数和周期配对关联流水号长度。

Rollback 策略：若上线后需要回退，先停止新增 `periodflag = '2'` 配置，将相关业务恢复为 `periodflag = '1'`；对于已执行历史工程脚本或已生成的合并流水，需依赖执行前备份或归档数据恢复源流水状态。

## Open Questions

None. 当前设计已按确认方案固定关键业务规则；实现阶段只需结合具体 DAO/cache/memdb 生成方式确认落地文件清单。
