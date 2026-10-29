## Why

上海基金现金分红在除权日净值会下降单位分红金额，但红利资金要到几个交易日后才到账，导致持仓对应的总市值在到账前存在缺口，需要通过资产补偿补足。

现有实现位于 `macbs-base/lbm_pro/macbs/cbs_data_summary/data_summary/handler/asset_uncome_handler/asset_uncome_handler101.cpp` 的 `GenerateDataByRightInfo()`：直接使用 `sh_zqye` 中 `qylb=HL & zqlb=JJ` 的红利权记录，按 `zqzh+zqdm+gpnf+ltlx` 关联 `comm_rightinfo` 权益信息，生成一条 `busitype=014001` 的 `node_assetuncome` 记录。

新发现的问题：资产补偿只覆盖流通股持仓市值，限售的基金份额不产生资产损失，不应补偿。但红利权记录的 `ltlx` 表示该年分红次数，无法区分该笔红利对应的持仓是流通还是限售，因此按红利权记录直接补偿会把限售份额也计入，导致补偿金额高估。

## What Changes

- 上海基金红利权补偿改为**按日结转**：每条补偿记录的 `archivedate` 取下一业务日，次一业务日由现有归档任务删除；不再新增 `status` 字段，国信对账单仍按 `busidate=当天` 取在途权益。
- 新增/存量判定改为与**上一业务日**的 `node_assetuncome` 记录比对：匹配键为 `secuid(zqzh)` + `stkcode(zqdm)` + `busitype(014001)` + `remark(${gpnf}_${ltlx})`，比对范围限定 `busidate=@lastbusidate`。
- 首次出现的红利权记录：只按当日 `sh_zqye` 中流通份额（`zqzh+zqdm+xwh` 相同、`ltlx='0'`、`zqlb='JJ'` 且 `qylb` 为空（IS NULL）的持仓记录 `ye1`）计算补偿；`匹配qty=ye1`、`matchprice=rightsamt`、`assetamt=round(ye1*rightsamt,2)`。
- 上一业务日已存在匹配记录：复制该记录生成当天记录，业务字段（补偿金额、份额、价格、资产缺失类型、补偿方式、备注等）保持不变，仅重置 `busidate=@busidate`、`archivedate=@nextbusidate` 并重新生成补偿流水号。
- 当日红利权记录不再发放：不再生成当天记录，上一业务日记录的 `archivedate` 已是当天，由归档任务正常删除。
- `busitype` 仍为 `014001`，资产缺失类型/补偿方式仍取 `comm_assetuncomeconfig` 的 `014001` 配置；深圳基金分红（`sz_sjsjg`）与深 B 红利（`sz_sjsgb`）分支保持不变。
- 新增国信 `comm_memdb_load_cfg` 配置：在日终实际使用的加载分组 `00`、`60` 中，按 `busidate=:lastbusidate and busitype='014001'` 将上一业务日补偿记录加载到内存库，保证结转判定有数据可读。
- 不新增表字段、不改归档配置，也不调整国信对账单与 OMS 下场导出的取数口径。

## Capabilities

### New Capabilities
- `sh-fund-dividend-assetuncome-circulating`: 上海基金分红资产补偿按流通份额计算，并按业务日结转未到账红利补偿记录。

### Modified Capabilities

## Impact

- 代码影响：`macbs-base/lbm_pro/macbs/cbs_data_summary/data_summary/handler/asset_uncome_handler/asset_uncome_handler101.h/.cpp`（`Cache()`、`GenerateDataByRightInfo()` 及其拆分函数）。`Write()`、`CAssetUncomeCalcRangeHandler101`、`CAssetUncomeRestoreHandler101` 无需改动。
- 数据影响：`node_assetuncome` 中 `busitype=014001` 的记录由"当日生成、当日归档"变为"当日生成、下一业务日归档"，每天仍保留当天有效记录，跨日记录由结转复制产生。
- 数据库影响：无表结构变更；新增国信 `comm_memdb_load_cfg` 配置（分组 `00`/`60` 加载上一业务日 `014001` 补偿记录），并新增国信节点库一次性存量清理脚本（`node_assetuncome` 旧口径 `014001` 记录），脚本位置 `macbs-service/database/script/patch/国信证券/gauss/fs_cbs/fs_cbs_node/2.data/node_assetuncome.sql`，执行入口 `fs_cbs_node_cleanup.sh`。
- 存量数据：历史已归档数据不修复；`node` 库旧口径残留记录在切换日数据汇总前清理，避免新逻辑将其误判为上一业务日存量而复制旧口径金额。
- 兼容性：只改 `asset_uncome_handler101`（国信分支），不改老 handler `asset_uncome_handler.h/.cpp`；深圳基金分红与深 B 红利补偿逻辑不变。
- 下游影响：国信对账单按 `busidate=当天` 取在途权益，结转记录当天存在，不受影响；OMS 下场导出 `a01-assetuncome` 不带 `busidate` 过滤，结转期间会同时导出上一业务日记录（`archivedate=当天`，当日归档后删除），需确认客户端按主键覆盖处理。
