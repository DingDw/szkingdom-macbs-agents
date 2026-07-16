# HK_TZXX 与 SZHK_TZXX 写入 comm_hk_rightinfo 处理逻辑

> 适用范围：`cbs_preclear` 公共信息预处理中的 `HK_TZXX`、`SZHK_TZXX` 通知信息文件处理。

## 1. 分析对象

本文说明两类港股通通知信息文件在预处理阶段的业务含义和写表逻辑：

| 文件 | 接口规范 | 代码处理类 | 入口分派 |
|---|---|---|---|
| `HK_TZXX` | `港股通结算数据接口规范（结算参与机构版V1.16）`，`hk_tzxx` 第 24-30 页 | `CHktzxxHandler` | `SHJS` + `HK_TZXX` |
| `SZHK_TZXX` | `深圳市场港股通结算数据接口规范（Ver 1.02）`，`SZHK_TZXX` 第 25-34 页 | `CSzhktzxxHandler` | `SZJS` + `SZHK_TZXX` |

运行入口为 `CPreClearComm`，导出函数是 `DoPreClearComm`，用于公共信息预处理。`CPreClearCommHandlerFactory` 根据接口和文件标识创建具体 handler。

关键代码：

- `macbs-base/lbm_pro/macbs/cbs_preclear/preclear_comm/handler/base/preclear_comm_handler_factory.h`
- `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/SHJS/hktzxx_handler.h`
- `macbs-base/lbm_pro/macbs/cbs_preclear/preclear/handler/SZJS/szhktzxx_handler.h`
- `macbs-base/library/macbs/dao/tables/tables_base/comm_hk_rightinfo_memdb_base.h`

## 2. 目标表定位

`comm_hk_rightinfo` 是港股通公司行为通知归一表。`HK_TZXX` 和 `SZHK_TZXX` 中与后续清算识别相关的权益登记、公司收购、分拆合并、公开配售、供股信息，会转换为该表记录。

表主键：

| 主键字段 | 说明 |
|---|---|
| `market` | 港股通市场，沪港通写 `MKT_SHANGHAIH`，深港通写 `MKT_SHENZHENH` |
| `tzlb` | 通知类别 |
| `stkcode` | 通知维度下用于匹配的证券代码 |
| `qylb` | 权益类别，源字段为空时写单空格 |
| `lx2` | 类型2/状态维度，源字段为空时写单空格 |

处理时先按该主键 `GetByKey` 查询：已存在则更新，不存在则插入。最终在 `Write()` 阶段批量写入内存库。

## 3. 原始接口关键字段

### 3.1 HK_TZXX 关键字段

上海 `hk_tzxx` 是 DBF 文件，字段主要为字符型。代码中多数数值字段通过 `atoi/atof` 转换。

| 字段 | 规范含义 | 在代码中的主要用途 |
|---|---|---|
| `SCDM` | 市场代码，港股通为 `05` | 不直接写 `comm_hk_rightinfo`，目标市场固定写 `MKT_SHANGHAIH` |
| `TZLB` | 通知类别 | 决定处理分支，并写入 `comm_hk_rightinfo.tzlb` |
| `TZRQ` | 通知日期 | 写入 `comm_hk_rightinfo.tzrq` |
| `ZQDM` | 证券代码 | 通常写入/参与 `stkid`；多数类别也作为 `stkcode` |
| `ZQLB` | 证券类别 | 当前转换逻辑不写入 `comm_hk_rightinfo` |
| `LTLX` | 流通类型 | 写入 `comm_hk_rightinfo.circtype` |
| `QYLB` | 权益类别 | 写入主键字段 `qylb` |
| `RQ1/RQ2/RQ3` | 日期1/日期2/日期3，不同 `tzlb` 下含义不同 | 写入 `rq1/rq2/rq3` |
| `JG1/JG2` | 价格1/价格2 | 写入 `jg1/jg2` |
| `BL1/BL2` | 比率1/比率2 | 写入 `bl1/bl2`；`H05` 时用于汇率 |
| `SL1/SL2` | 数量1/数量2 | 写入 `sl1/sl2` |
| `LX1` | 类型1 | 写入 `lx1` |
| `LX2` | 类型2 | 写入主键字段 `lx2`；对部分类别有 `UPD -> ADD` 归并 |
| `FZDM1` | 辅助代码1 | 写入 `fzdm1`；`H10` 下是临时代码 |
| `FZDM2` | 辅助代码2 | 写入 `fzdm2`；不同类别下含义不同 |
| `FJSM1/FJSM2` | 附加说明1/2 | 写入 `fjsm1/fjsm2` |
| `BZ/WBHL/JE1/JE2/JE3/BY` | 币种、汇率、金额、备用 | 当前 `comm_hk_rightinfo` 转换不直接写入 |

### 3.2 SZHK_TZXX 关键字段

深圳 `SZHK_TZXX` 与上海类似，但数值字段在 DAO 中多为数值型，并新增 `ZT` 参数状态。

| 字段 | 规范含义 | 在代码中的主要用途 |
|---|---|---|
| `SCDM` | 市场代码，港股通为 `05` | 不直接写 `comm_hk_rightinfo`，目标市场固定写 `MKT_SHENZHENH` |
| `TZLB` | 通知类别 | 决定处理分支，并写入 `comm_hk_rightinfo.tzlb` |
| `FSRQ` | 通知发送日期 | 写入 `comm_hk_rightinfo.tzrq` |
| `ZQDM` | 证券代码 | 通常作为 `stkcode` 和 `stkid` 来源 |
| `GFXZ` | 股份性质 | 当前转换逻辑不写入 `comm_hk_rightinfo` |
| `SSZT` | 上市状态 | 写入 `comm_hk_rightinfo.circtype` |
| `QYLB` | 权益类别 | 写入主键字段 `qylb` |
| `QYBH` | 权益编号 | 当前转换逻辑不写入 `comm_hk_rightinfo` |
| `RQ1/RQ2/RQ3` | 日期1/日期2/日期3，不同 `tzlb` 下含义不同 | 写入 `rq1/rq2/rq3` |
| `JG1/JG2` | 价格1/价格2 | 写入 `jg1/jg2` |
| `BL1/BL2` | 比率1/比率2 | 写入 `bl1/bl2`；`H05` 时用于汇率 |
| `SL1/SL2` | 数量1/数量2 | 写入 `sl1/sl2` |
| `LX1` | 类型1 | 写入 `lx1` |
| `LX2` | 类型2 | 写入主键字段 `lx2`，当前不做状态归并 |
| `FZDM1` | 辅助代码1 | 写入 `fzdm1`；`H10` 下是临时代码 |
| `FZDM2` | 辅助代码2 | 写入 `fzdm2`；`H13/H14` 下是派发证券代码 |
| `FJSM1/FJSM2` | 附加说明1/2 | 写入 `fjsm1/fjsm2` |
| `ZT` | 参数状态，`Y` 生效，`N` 终止/取消 | 写入 `comm_hk_rightinfo.zt` |
| `BZ/HL/JE1/JE2/JE3/BY` | 币种、汇率、金额、备用 | 当前 `comm_hk_rightinfo` 转换不直接写入；`H05` 分支使用 `BL1/BL2` 写汇率 |

## 4. 按通知类别的业务含义和处理逻辑

### 4.1 `H01` 权益登记

规范含义：

- 上海：`H01` 为港股通权益登记通知信息。`QYLB=HL` 表示红利，`QYLB=S` 表示送股/派发权证。`RQ1` 为权益登记日，`RQ2` 为香港结算发放日，`RQ3` 在红利股票选择权业务中表示选择权申报截止日。
- 深圳：`H01` 为权益登记。`QYLB` 参照权益类别表，常见如红利、送股/派送权证等。`RQ1/RQ2/RQ3` 含义与上海类似，`RQ3` 只在含选择权红利时有业务意义。

关键字段含义：

| 字段 | 业务含义 |
|---|---|
| `ZQDM` | 权益登记涉及的证券代码 |
| `QYLB` | 权益类别，如红利、送股/派发证券 |
| `RQ1` | 权益登记日 |
| `RQ2` | 香港结算发放日 |
| `RQ3` | 红利股票选择权申报截止日，非选择权场景无意义或为空 |
| `JG1/JG2` | 红利登记时的每股红利价格，分别对应境内税前/税后 |
| `BL1/BL2` | 送股/派发权证配比；含红利股票选择权时 `BL1` 可表示以股代息价格 |
| `LX1` | 上海规范中可表示零碎股利现金发放标志 |
| `LX2` | 红利股票选择权标志，`Y` 表示含选择权，`N` 表示不含选择权 |
| `FZDM1` | 公司行为代码 |
| `FZDM2` | 上海为权益代码，深圳为派发证券代码 |

写入逻辑：

- 上海和深圳都写入 `comm_hk_rightinfo`。
- 主键中 `stkcode` 通常取 `ZQDM`，`qylb` 取 `QYLB`，`lx2` 取 `LX2`。
- 价格、比率、日期、辅助代码、附加说明按通用字段映射写入。

### 4.2 `H05` 结算汇兑比率

规范含义：

- `H05` 为港股通结算汇兑比率通知。
- `RQ1` 为适用日期。
- `BL1` 为结算买入汇兑比率。
- `BL2` 为结算卖出汇兑比率。

处理逻辑：

- 不写入 `comm_hk_rightinfo`。
- 用于刷新 `comm_exchangerate`。
- 若公参 `PARAMID_HK_RATE_SXBZ` 即 `67232` 配置为 `2`，表示使用 `hk_jsmx/szhk_sjsmx` 刷汇率，不使用 `tzxx` 刷汇率；当前记录计为忽略。
- 上海写汇率时：
  - `market = MKT_SHANGHAIH`
  - `curcode = HKD`
  - `bcurcode = RMB`
  - `buyprice = BL1`
  - `sellprice = BL2`
  - `currate = (BL1 + BL2) / 2`
  - `rateunit = 1`
- 深圳写汇率时：
  - `market = MKT_SHENZHENH`
  - `curcode = HKD`
  - `bcurcode = RMB`
  - `buyprice = BL1`
  - `sellprice = BL2`
  - `currate = BL1`
  - `rateunit = 1`

### 4.3 `H07` 现金收购

规范含义：

- `H07` 为现金收购通知。
- `RQ1` 为股权登记日，`RQ2` 为申报起始日，`RQ3` 为申报截止日。
- `JG1` 为每股收购价格。
- `BZ` 为收购币种。
- `LX1` 为收购类型，如有条件收购、无条件收购、强制收购。
- `FZDM1` 为公司行为代码。

写入逻辑：

- 写入 `comm_hk_rightinfo`，后续公司收购处理可按通知类别和证券代码匹配。
- 上海若 `LX2=UPD`，主键 `lx2` 改写为 `ADD`，即变更通知覆盖首次发布记录。
- 深圳不做 `LX2` 归并，`ZT` 写入目标表状态。

### 4.4 `H08` 股份收购

规范含义：

- `H08` 为股份收购通知。
- `BL1` 表示股份支付比例。
- `BL2` 表示保证配额比例。
- `FZDM2` 对股份收购有关键意义，表示支付证券代码。

写入逻辑：

- 写入 `comm_hk_rightinfo`。
- 上海若 `LX2=UPD`，主键 `lx2` 改写为 `ADD`。
- 若 `FZDM2` 为空，代码写 warning，因为后续股份收购识别需要支付证券代码。

### 4.5 `H09` 现金和股份收购

规范含义：

- `H09` 为现金加股份收购通知，同时包含现金收购和股份收购相关字段。
- `JG1/BZ` 用于现金对价。
- `BL1/BL2` 用于股份支付和保证配额。
- `FZDM2` 表示支付证券代码。

写入逻辑：

- 写入 `comm_hk_rightinfo`。
- 上海若 `LX2=UPD`，主键 `lx2` 改写为 `ADD`。
- 若 `FZDM2` 为空，代码写 warning。

### 4.6 `H10` 股份分拆合并

规范含义：

- `H10` 为股份分拆合并通知。
- `ZQDM` 为原交易证券代码。
- `FZDM1` 为临时交易证券代码。
- `FZDM2` 为新交易证券代码。
- `RQ1` 为第一次转换日期，即原证券代码转换至临时代码日期。
- `RQ2` 为第二次转换日期，即临时代码第一次转换至新证券代码日期。
- `RQ3` 为第三次转换日期，即临时代码第二次转换至新证券代码日期。
- `SL1/SL2` 为第一次转换比例分子/分母。
- `BL1/BL2` 为后续转换比例。

写入逻辑：

- 写入 `comm_hk_rightinfo`。
- 上海若 `LX2=UPD`，主键 `lx2` 改写为 `ADD`，因此同一分拆合并通知保留 `ADD` 和 `DEL` 两类记录，`UPD` 覆盖 `ADD`。
- 写入后补充证券模板校验：
  - 上海校验 `MKT_SHANGHAIH + fzdm1`。
  - 深圳校验 `MKT_SHENZHENH + fzdm1`。
- 若临时代码找不到证券模板，代码记录错误/未找到信息。

### 4.7 `H13` 公开配售/要约出售

规范含义：

- 上海：`H13` 为公开配售通知。
- 深圳：`H13` 为公开配售/要约出售通知。
- `RQ1` 为权益登记日，`RQ3` 为申报截止日。
- `JG1` 为每股公开配售或要约出售价格。
- `BL1/BL2` 为转换比例分母/分子。
- `FZDM1` 为公司行为代码。
- 上海规范中`ZQDM`为正股代码，`FZDM2` 为权益代码；深圳规范中 `ZQDM` 为公开配售权/要约出售权代码，`FZDM2` 为正股代码。
- 深圳规范特别说明：有效申报认购后，上市公司可能同时额外派发红股、权证等证券，因此可能多条通知对应不同派发证券。

写入逻辑：

- 写入 `comm_hk_rightinfo`。
- 深圳：
  - 主键 `stkcode = ZQDM`。
  - `fzdm2 = FZDM2`。
  - 若 `FZDM2` 为空，会尝试用 `H01 + QYLB=HG + FZDM2=当前 ZQDM` 的记录反查，并用查到记录的 `ZQDM` 补 `fzdm2`。
  - 证券模板校验使用 `MKT_SHENZHENH + stkcode`。
- 上海：
  - 主键 `stkcode` 先取源 `FZDM2`。
  - `fzdm2`，覆盖为源 `ZQDM`。
  - 证券模板校验使用 `MKT_SHANGHAIH + stkcode`。

### 4.8 `H14` 供股

规范含义：

- `H14` 为供股通知。
- `RQ1` 为权益登记日，`RQ3` 为供股申报截止日。
- `JG1` 为每股供股价格。
- `BL1/BL2` 为供股比例分母/分子。
- `FZDM1` 为公司行为代码。
- 深圳规范中 `ZQDM` 为供股权代码，`FZDM2` 为派发证券代码。

写入逻辑：

- 写入 `comm_hk_rightinfo`。
- 目标字段和校验逻辑与 `H13` 基本一致。
- 深圳保留 `stkcode = ZQDM`，并在必要时通过 `H01` 补 `fzdm2`。
- 上海使用换代码逻辑：主键 `stkcode = FZDM2`，目标 `fzdm2 = ZQDM`。

### 4.9 其他通知类别

规范中还存在 `H06` 投票公告、`H12` 投票议案，深圳还存在 `H15` 证券注销。

当前 `HK_TZXX`/`SZHK_TZXX` 转换为 `comm_hk_rightinfo` 的代码不处理这些类别。它们不会进入权益信息写入分支。

## 5. comm_hk_rightinfo 字段赋值逻辑

### 5.1 主键字段

| 目标字段 | HK_TZXX 赋值 | SZHK_TZXX 赋值 | 说明 |
|---|---|---|---|
| `market` | 固定 `MKT_SHANGHAIH` | 固定 `MKT_SHENZHENH` | 区分沪港通、深港通 |
| `tzlb` | `TZLB` | `TZLB` | 通知类别 |
| `stkcode` | 默认 `ZQDM`；`H13/H14` 改取 `FZDM2` | `ZQDM`，为空时写单空格 | 后续匹配的核心证券代码 |
| `qylb` | `QYLB`，为空写单空格 | `QYLB`，为空写单空格 | 权益类别 |
| `lx2` | `LX2`，为空写单空格；`H10/H07/H08/H09` 且 `LX2=UPD` 时写 `ADD` | `LX2`，为空写单空格 | 上海用来归并通知状态，深圳基本原样保留 |

### 5.2 通用字段

| 目标字段          | HK_TZXX 赋值                      | SZHK_TZXX 赋值                            | 说明                                                               |
| ------------- | ------------------------------- | --------------------------------------- | ---------------------------------------------------------------- |
| `stkid`       | `market + ZQDM`                 | `market + ZQDM`                         | 注意上海 `H13/H14` 的 `stkid` 仍按源 `ZQDM` 拼接，不随主键 `stkcode` 改为 `FZDM2` |
| `tzrq`        | `atoi(TZRQ)`                    | `atoi(FSRQ)`                            | 通知日期/发送日期                                                        |
| `circtype`    | `LTLX` 单字符                      | `SSZT` 单字符                              | 上海保存流通类型；深圳保存上市状态                                                |
| `rq1`         | `atoi(RQ1)`                     | `atoi(RQ1)`                             | 日期1                                                              |
| `rq2`         | `atoi(RQ2)`                     | `atoi(RQ2)`                             | 日期2                                                              |
| `rq3`         | `atoi(RQ3)`                     | `atoi(RQ3)`                             | 日期3                                                              |
| `jg1`         | `atof(JG1)`                     | `JG1`                                   | 价格1                                                              |
| `jg2`         | `atof(JG2)`                     | `JG2`                                   | 价格2                                                              |
| `bl1`         | `atof(BL1)`                     | `BL1`                                   | 比率1                                                              |
| `bl2`         | `atof(BL2)`                     | `BL2`                                   | 比率2                                                              |
| `sl1`         | `atof(SL1)`                     | `SL1`                                   | 数量1                                                              |
| `sl2`         | `atof(SL2)`                     | `SL2`                                   | 数量2                                                              |
| `lx1`         | `LX1`                           | `LX1`                                   | 类型1                                                              |
| `fzdm1`       | `FZDM1`                         | `FZDM1`                                 | 辅助代码1                                                            |
| `fzdm2`       | 默认 `FZDM2`；`H13/H14` 覆盖为 `ZQDM` | 默认 `FZDM2`；`H13/H14` 且为空时可能用 `H01` 反查补值 | 辅助代码2                                                            |
| `fjsm1`       | `FJSM1`                         | `FJSM1`                                 | 附加说明1                                                            |
| `fjsm2`       | `FJSM2`                         | `FJSM2`                                 | 附加说明2                                                            |
| `zt`          | 固定 `"Y"`                        | `ZT`                                    | 上海规范此表没有 `ZT` 字段，代码默认生效                                          |
| `upddate`     | 当前业务日期                          | 当前业务日期                                  | 预处理业务日期                                                          |
| `remark`      | 固定 `"HK_TZXX"`                  | 固定 `"SZHK_TZXX"`                        | 来源标记                                                             |
| `archivedate` | 当前业务日期后 180 天                   | 当前业务日期后 180 天                           | 周期流水归档字段                                                         |

### 5.3 不写入 comm_hk_rightinfo 的源字段

以下源字段在当前转换中不直接写入 `comm_hk_rightinfo`：

| 文件 | 字段 |
|---|---|
| `HK_TZXX` | `SCDM`、`QSBH`、`ZQLB`、`GPNF`、`QYCS`、`ZH1`、`ZH2`、`JE1`、`JE2`、`JE3`、`BZ`、`WBHL`、`BY` |
| `SZHK_TZXX` | `SCDM`、`GFXZ`、`QYBH`、`ZH1`、`ZH2`、`JE1`、`JE2`、`JE3`、`BZ`、`HL`、`BY` |

其中 `BZ/HL/WBHL/JE*` 等字段虽然可能有业务含义，但当前 `comm_hk_rightinfo` 转换没有承载它们。`H05` 汇率分支使用的是 `BL1/BL2` 写 `comm_exchangerate`，不是写 `comm_hk_rightinfo`。

## 6. 写库阶段

`Clear()` 阶段只在缓存中插入或更新 `comm_hk_rightinfo` 记录。真正写入内存库发生在 `Write()` 阶段：

| 文件 | 写入顺序 |
|---|---|
| `HK_TZXX` | 先 `BatchInsert(true)`，再 `BatchUpdate()` |
| `SZHK_TZXX` | 先 `BatchUpdate()`，再 `BatchInsert(true)` |

`BatchInsert(true)` 表示插入时去重/忽略重复主键记录。两个 handler 的顺序不同，但最终语义都是把转换阶段标记为新增或更新的记录落入内存库。

## 7. 关键差异和注意点

1. `H05` 是汇率通知，不是权益通知，不写 `comm_hk_rightinfo`。
2. 上海 `HK_TZXX` 使用 `LX2=ADD/UPD/DEL` 表示通知状态；代码对 `H10/H07/H08/H09` 做 `UPD -> ADD`，让变更通知覆盖首次发布记录。
3. 深圳 `SZHK_TZXX` 使用 `ZT=Y/N` 表示生效/终止，代码写入 `comm_hk_rightinfo.zt`，不做 `UPD -> ADD`。
4. 上海 `H13/H14` 的代码实现和规范字段表述需要结合实际文件理解：当前实现用源 `FZDM2` 作为 `stkcode`，并把源 `ZQDM` 写回目标 `fzdm2`；这和深圳实现明显不同。
5. 深圳 `H13/H14` 可能一项公开配售/供股对应多条派发证券通知，代码保留 `ZQDM` 为权证代码，并用 `FZDM2` 表示派发证券代码；当 `FZDM2` 缺失时尝试用 `H01` 补齐。
6. `comm_hk_rightinfo` 后续主要服务于港股通公司行为清算识别，例如红利/红股、公司收购、分拆合并、公开配售、供股等。字段映射错误会直接影响后续 `hk_zqbd/hk_jsmx`、`szhk_sjsjg/szhk_sjsmx` 的业务类型识别。

