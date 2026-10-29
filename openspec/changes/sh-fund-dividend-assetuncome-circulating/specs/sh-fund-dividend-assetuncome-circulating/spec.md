## ADDED Requirements

### Requirement: 上海基金红利权补偿按流通份额计算

系统必须只按当日 `sh_zqye` 中流通份额（`ltlx='0'`、`zqlb='JJ'` 且 `qylb` 为空的持仓记录）计算上海基金红利权的资产补偿金额，不得将限售份额的市值损失计入补偿。

#### Scenario: 存在流通持仓时按流通份额补偿

- **WHEN** 当日 `sh_zqye` 存在 `qylb=HL`、`zqlb=JJ` 的红利权记录，且存在相同 `zqzh+zqdm+xwh`、`ltlx='0'`、`zqlb='JJ'`、`qylb` 为空的持仓记录
- **THEN** 系统必须使用该持仓记录的 `ye1` 作为补偿份额，生成 `matchqty=ye1`、`matchprice=comm_rightinfo.rightsamt`、`assetamt=round(ye1*rightsamt,2)` 的 `node_assetuncome` 记录

#### Scenario: 限售份额不产生补偿

- **WHEN** 红利权对应的持仓只有 `ltlx<>'0'` 的限售份额，或不存在 `qylb` 为空的持仓记录
- **THEN** 系统不得生成补偿记录，并必须记录跳过原因日志

#### Scenario: 排除红利权记录自身

- **WHEN** 红利权记录的 `ltlx` 恰好等于 `'0'`
- **THEN** 系统必须只把 `qylb` 为空（IS NULL）的记录作为流通份额来源，不得使用 `qylb='HL'` 的红利权记录自身 `ye1` 计算补偿

#### Scenario: 同一账户证券席位命中多条流通持仓记录

- **WHEN** 当日 `sh_zqye` 中相同 `zqzh+zqdm+xwh` 存在多条 `ltlx='0'`、`zqlb='JJ'` 的持仓记录
- **THEN** 系统必须取第一条记录的 `ye1` 计算补偿，并记录告警日志

### Requirement: 红利权补偿按业务日结转

系统必须按业务日结转未到账的红利权补偿记录：以上一业务日的 `busitype=014001` 记录判断红利权是否为存量，存量记录复制生成当天记录且不重算金额。

#### Scenario: 首次出现的红利权生成补偿记录

- **WHEN** 上一业务日的 `node_assetuncome` 中不存在 `secuid+stkcode+busitype(014001)+remark(${gpnf}_${ltlx})` 匹配的记录
- **THEN** 系统必须按流通份额新生成一条记录，`busidate=当前业务日期`、`archivedate=下一业务日`、`busitype=014001`、`remark=${gpnf}_${ltlx}`

#### Scenario: 存量红利权复制上一业务日记录

- **WHEN** 上一业务日存在 `secuid+stkcode+busitype(014001)+remark(${gpnf}_${ltlx})` 匹配的记录
- **THEN** 系统必须复制该记录生成当天记录，保持 `assetamt`、`matchqty`、`matchprice`、`assettype`、`dealkind`、`winbusitype` 等业务字段不变，仅设置 `busidate=当前业务日期`、`archivedate=下一业务日` 并重新生成补偿流水号

#### Scenario: 同一分红事件重复出现只处理一次

- **WHEN** 同一业务日的 `sh_zqye` 中同一个 `zqzh+zqdm+gpnf+ltlx` 出现多条红利权记录
- **THEN** 系统必须只生成一条当天补偿记录

#### Scenario: 上一业务日无历史记录

- **WHEN** 上一业务日不存在任何 `busitype=014001` 的结转记录
- **THEN** 系统必须将当日全部红利权记录按首次出现口径计算并生成记录

### Requirement: 红利权补偿到账后停止结转

系统必须在红利权记录不再发放时停止生成当天补偿记录，由现有归档配置按 `archivedate` 清理上一业务日记录。

#### Scenario: 红利权记录消失

- **WHEN** 当日 `sh_zqye` 中不再存在某笔红利权记录
- **THEN** 系统不得生成该笔分红的当天补偿记录，且上一业务日记录的 `archivedate` 为当天，由归档任务删除

#### Scenario: 结转记录归档口径

- **WHEN** 生成红利权补偿记录
- **THEN** 记录的 `archivedate` 必须为下一业务日，沿用现有 `delete from node_assetuncome where archivedate=@busidate` 归档配置，不新增 `status` 字段

### Requirement: 结转依据数据必须加载到内存库

系统必须在日终数据汇总执行前，将上一业务日 `busitype=014001` 的 `node_assetuncome` 记录加载到内存库，保证存量判定可以读到上一业务日记录。

#### Scenario: 上一业务日存在结转记录

- **WHEN** 数据汇总资产补偿任务需要读取上一业务日补偿记录
- **THEN** 内存库必须已按国信日终加载分组（`00`、`60`）加载 `busidate = 上一业务日 AND busitype = '014001'` 的 `node_assetuncome` 记录

### Requirement: 结转记录识别键

系统必须使用 `secuid`（`zqzh`）、`stkcode`（`zqdm`）、`busitype=014001` 和 `remark=${gpnf}_${ltlx}` 作为结转记录的业务识别键，比对范围限定为上一业务日。

#### Scenario: 识别键限定上一业务日

- **WHEN** 判定红利权记录是否为首次出现
- **THEN** 系统必须只匹配 `node_assetuncome.busidate = 上一业务日` 且 `busitype = 014001` 的记录，不得匹配其他业务日或其他业务类别的记录

#### Scenario: 匹配不使用截止日期

- **WHEN** 查找流通持仓或匹配结转记录
- **THEN** 系统不得将 `sh_zqye.jzrq` 作为匹配条件
