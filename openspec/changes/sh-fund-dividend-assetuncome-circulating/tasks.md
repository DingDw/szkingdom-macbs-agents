## 1. 缓存阶段数据加载

- [x] 1.1 将 `CSumAssetUncome101::Cache()` 中 `sh_zqye` 缓存条件由 `qylb=HL & zqlb=JJ` 调整为 `zqlb=JJ`，并在过滤回调中区分两类记录：红利权记录（`qylb=HL && zqlb=JJ`）与流通持仓记录（`ltlx='0' && zqlb='JJ'` 且 `qylb` 为空，`ISNULL(qylb)`）
- [x] 1.2 新增缓存上一业务日资产补偿记录：`node_assetuncome` 按 `busidate=GetLastBusidate()`、`busitype='014001'` 加载到 `CNode_assetuncomeCacheManager`
- [x] 1.3 以 `secuid|stkcode|remark` 构建上一业务日记录索引，供 `Clear()` 判定新增/存量
- [x] 1.4 确认流通持仓记录不引入额外证券与行情缓存，红利权对应证券仍沿用现有 `comm_stock` / `comm_stkprice` 链路
- [x] 1.5 补充 `Cache()` 日志：红利权记录数、流通持仓数、上一业务日结转记录数
- [x] 1.6 新增国信 `comm_memdb_load_cfg` patch：分组 `00`、`60` 按 `busidate=:lastbusidate and busitype='014001'` 加载上一业务日补偿记录

## 2. 清算处理逻辑

- [x] 2.1 将 `GenerateDataByRightInfo()` 中 `sh_zqye` 分支拆为独立函数（如 `GenerateFundDividendAssetUncome()`），并为其补充业务逻辑说明注释
- [x] 2.2 在 `Cache()` 缓存 `sh_zqye` 时构建当日流通份额映射：`zqzh|zqdm|xwh` → `ye1`，仅接受 `ltlx='0'`、`zqlb='JJ'` 且 `qylb` 为空（`ISNULL(qylb)`）的记录
- [x] 2.3 遍历当日红利权记录，用 `zqzh+zqdm+${gpnf}_${ltlx}` 在上一业务日索引中判定是否已有匹配记录
- [x] 2.4 存在匹配记录时复制该记录：保留业务字段，仅设置 `busidate=当前业务日期`、`archivedate=GetNextBusidate()`，并按当天规则重新生成 `sno`
- [x] 2.5 不存在匹配记录时按新增处理：按 `zqzh+zqdm+xwh` 取流通份额 `ye1`，`ye1<=0` 或找不到流通持仓时跳过并写日志
- [x] 2.6 新增记录金额口径：`matchqty=ye1`、`matchprice=comm_rightinfo.rightsamt`、`assetamt=kcpd_round(ye1*rightsamt,2)`
- [x] 2.7 新增记录其余字段保持现有逻辑：账户配对 `AcctMatch`（业务类别 `013806`）、`assettype`/`dealkind` 取 `comm_assetuncomeconfig` 的 `014001` 配置、`winbusitype` 取 `comm_busitypemapped` 映射、`remark=${gpnf}_${ltlx}`、`busitype=014001`
- [x] 2.8 同一分红事件在当日文件中重复出现时只处理一次（当日已处理集合）
- [x] 2.9 确认 `sz_sjsjg`（`024001`）与 `sz_sjsgb`（`043802`）分支逻辑与 `archivedate=当前业务日期` 保持不变
- [x] 2.10 确认 `Write()` 仍只调用 `BatchInsert(true)`，不引入 `BatchUpdate()`；`CalcRange`、`Restore` 类不改动

## 3. 常量与代码规范

- [x] 3.1 将 `014001`、流通类型 `ltlx='0'`、`remark` 分隔符 `_` 等业务含义值定义为含义明确的宏或匿名命名空间常量
- [x] 3.2 新增变量、函数按项目命名规范（`strKey`、`map...`、`idx`、`fn` 前缀）实现，关键分支补业务注释

## 4. 存量数据处理

- [x] 4.1 确认存量结论：历史已归档文件不修复；`node` 库旧口径 `014001` 残留记录需一次性清理
- [x] 4.2 新增国信节点库清理 SQL `patch/国信证券/gauss/fs_cbs/fs_cbs_node/2.data/node_assetuncome.sql`：`busitype='014001' AND archivedate <= busidate`，头注释标注 FS-CBS-21981、执行时机与预检查 SQL
- [x] 4.3 新增清理执行入口 `patch/国信证券/gauss/fs_cbs/fs_cbs_node_cleanup.sh`，支持按 `db_config.ini` 的 `NODE1..NODE5`/`NODEX` 段执行并输出日志
- [ ] 4.4 切换日执行预检查 SQL 确认残留量，并在 `627009` 数据汇总前执行清理脚本
- [ ] 4.5 若切换日数据汇总已按旧逻辑执行：清理后对当日执行回滚重做，确认当日记录为新口径

## 5. 验证

- [ ] 5.1 首次出现红利权且存在流通持仓：生成 `busidate=当天`、`archivedate=下一业务日` 的 `014001` 记录，金额=流通 `ye1` × `rightsamt`
- [ ] 5.2 同时存在流通与限售份额：只按 `ltlx='0'` 的流通持仓份额补偿，限售份额不计入
- [ ] 5.3 红利权记录自身 `ltlx='0'` 时，因 `qylb='HL'` 不会进入流通份额映射，不会被误当作流通持仓记录
- [ ] 5.4 上一业务日存在匹配记录：当天记录为复制结果，`assetamt`、`matchqty`、`matchprice` 与上一业务日一致
- [ ] 5.5 红利权记录当天不再发放：不生成当天记录，上一业务日记录因 `archivedate=当天` 被归档删除
- [ ] 5.6 同一业务日重复执行：同一 `secuid+stkcode+remark` 只插入一条
- [ ] 5.7 上一业务日无任何 `014001` 记录（首日上线）：按新增口径计算
- [ ] 5.8 无流通持仓或 `ye1<=0`：不生成记录，并可从日志定位跳过原因
- [ ] 5.9 清理脚本幂等性：归档正常时删除 0 行；新口径记录（`archivedate > busidate`）不被删除
- [ ] 5.10 验证内存库加载：分组 `00`、`60` 加载后 `node_assetuncome` 中存在上一业务日 `014001` 记录，且数据汇总可读取
- [x] 5.11 按需执行针对性编译或静态检查；若不执行构建，记录未执行原因
  - 记录：已执行 C++ AST 解析检查（ast-grep 可正常解析 `asset_uncome_handler101.cpp`）与括号配平静态检查；项目规则默认不执行构建，且本次未要求编译，业务级用例需在测试环境执行
