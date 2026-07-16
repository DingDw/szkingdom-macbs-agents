# cbs_fund_cost 模块知识库

> 模块路径：`lbm_pro/macbs/cbs_fund_cost/`  
> 模块定位：资金扣收模块，包含资金扣收数据生成、资金扣收处理、二次扣收、扣收交割流水生成和调用订单扣收等入口。

## 1. 模块入口

| 类型 | 文件 | 说明 |
|---|---|---|
| 构建入口 | `lbm_pro/macbs/cbs_fund_cost/CMakeLists.txt` | 构建 `cbs_fund_cost` 动态库，声明 include 目录、链接库和产物复制规则 |
| 导出入口 | `lbm_pro/macbs/cbs_fund_cost/export.cpp` | 通过 `MACBS_CLEAR_LBM_API` 绑定导出函数、具体类和执行方法 |
| 运行配置 | `bin64/conf/frame.xml` | 通过 `func_id` 映射到动态库和导出函数 |

## 2. 导出函数索引

| func_id | 导出函数 | 具体类 | 执行方法 | 业务含义 |
|---|---|---|---|---|
| 632001 | `DoFundcostsumRestore` | `CFundCostRestore` | `DoClear` | 重做资金扣收数据 |
| 632003 | `DoFundcostsumCalcrange` | `CFundcostsumCalcRange` | `DoClear` | 分段资金扣收数据 |
| 632005 | `DoFundcostsum` | `CFundcostsum` | `DoClear` | 生成资金扣收数据 |
| 632002 | `DoFundcostclearRestore` | `CFundcostclearRestore` | `DoClear` | 重做资金扣收处理 |
| 632004 | `DoFundcostclearCalcrange` | `CFundcostclearCalcrange` | `DoClear` | 分段资金扣收处理 |
| 632006 | `DoFundcostclear` | `CFundcostclear` | `DoClear` | 资金扣收处理 |
| 632008 | `DoFundcostpost` | `CFundcostpost` | `DoClear` | 调用订单扣收 |

## 3. 功能链路

```text
632001 重做资金扣收数据
632003 分段资金扣收数据
632005 生成资金扣收数据
    ↓
632002 重做资金扣收处理
632004 分段资金扣收处理
632006 资金扣收处理
    ↓
632008 调用订单扣收
```

核心数据流：

```text
node_debtdetail + comm_fund_cost_cfg
        ↓
node_fund_cost_detail
        ↓
node_fund_cost_sum
        ↓
node_debtdetail + node_settdetail + node_settdetailsub
```

## 4. 632005 生成资金扣收数据

### 4.1 阶段顺序

```text
GetBusiParam
  ↓
Before
  ↓
Cache
  ↓
Clear
  ├─ costpoint != SECOND: GenerateDetail → GenerateSum
  └─ costpoint == SECOND: GenSecondCostDetail → UpdateSecondCostSum
  ↓
Write
```

### 4.2 GetBusiParam

读取执行范围和控制参数：

```text
beginfundunit
endfundunit
costpoint，默认一次扣收
ipocostorder
calculateruleid
```

如果 `calculateruleid != 0`，会调用资产计算父类流程，为后续资金余额、资金可用计算准备数据。

### 4.3 Cache

一次扣收加载：

```text
node_debtdetail
comm_fund_cost_cfg
node_fundunit
node_fundbookkeeping
node_fundacct
```

资金簿记关注科目：

```text
F100201 当前资金余额
F100212 当前资金可用
F123103 融券卖出资金
F123104 融券卖出资金已用
```

二次扣收额外加载：

```text
node_fund_cost_sum
node_fund_cost_detail
```

二次扣收只处理第一次扣收中：

```text
costpoint = FIRST
costmode in (COST_MODE_COST_MAX, COST_MODE_COST)
```

也就是：

```text
1 有多少扣多少
2 足额扣收，不足不处理
```

### 4.4 Clear 一次扣收

一次扣收执行：

```text
GenerateDetail
  ↓
GenerateSum
```

#### 4.4.1 GenerateDetail 筛选负债明细

遍历 `node_debtdetail`，先计算：

```text
unpaidamt = debtamt - lastpaidamt - paidamt - paidamtday
```

过滤场景包括：

```text
非当前业务日期跳过
日间取消的股权激励扣税跳过
销户资产单元跳过
限售股所得税按公参判断是否生成
外部扣收数据余额或可用不足时跳过并回写结果
```

按 `busitype` 查找 `comm_fund_cost_cfg`。未找到配置时，记录业务类别，最后统一抛错。

#### 4.4.2 GenerateDetail 生成 node_fund_cost_detail 基础字段

来自 `node_debtdetail`：

```text
busidate
fundunit
fundacct
curcode
orgid
brhid
coreid
settunit
settbody
busitype
debtsno
cleardate
market
stkcode
costpoint
```

`extfundunit` 的处理：

```text
从 fundunit 中截掉 fundacct 前缀得到
```

默认金额：

```text
m_dbFundAmt  = node_debtdetail.unpaidamt
m_dbCostunit = 0.01
m_dbToufzamt = node_debtdetail.lastfrzamt
```

#### 4.4.3 GenerateDetail 写入配置字段

来自 `comm_fund_cost_cfg`：

```text
m_nCostpriority  = costpriority
m_cAdvfrzflag    = advfrzflag
m_cPrefrzamtflag = prefrzamtflag
```

扣收模式取值：

```text
if node_debtdetail.costmode 非空:
    m_cCostmode = node_debtdetail.costmode
else:
    m_cCostmode = comm_fund_cost_cfg.costmode
```

#### 4.4.4 GenerateDetail handler 补充业务字段

按 `busitype` 选择 handler。

常见补充逻辑：

```text
默认扣收:
    m_dbTocostamt = unpaidamt

默认冻结 / 税类 / IPO预冻结:
    m_dbTofrzamt = unpaidamt

IPO缴款:
    m_dbTocostamt = unpaidamt
    m_dbToufzamt 可能从 S72003 持仓簿记取
    m_dbCostunit 可能从配号表价格取

港股通组合费:
    m_dbTocostamt = unpaidamt
    按市场设置 m_nSortBusitypeNo

财富规划 / 投顾:
    m_dbTocostamt = unpaidamt
    可能回写外部收费结果
```

#### 4.4.5 GenerateDetail 优先级处理

第一层分组：

```text
group by fundunit + 原始 costpriority
```

组内调用 handler 的 `DoSort()`。

常见排序因子：

```text
原始 costpriority
业务内部排序号 sortBusitypeNo
cleardate
fundAmt
stkcode
sortNo
```

第二层按资产单元整体排序：

```text
costpriority asc
sortBusitypeNo asc
```

最终重写优先级：

```text
m_nCostpriority = 原始 costpriority * 1000000 + 资产单元内顺序号
```

该最终值决定 `632006` 的实际扣收顺序。

#### 4.4.6 GenerateDetail 保存原始待解冻金额快照

写入明细前：

```text
m_szRemark = to_string(m_dbToufzamt)
```

含义：

```text
m_szRemark 保存原始待解冻金额快照。
```

后续交割流水用它还原：

```text
dbUfzedAmt = ToDouble(m_szRemark)
```

这里不是直接使用 `m_dbUfzamt`。

#### 4.4.7 GenerateSum 生成 node_fund_cost_sum

汇总维度：

```text
busidate + fundunit + curcode
```

来自 `node_fund_cost_detail`：

```text
busidate
fundunit
fundacct
extfundunit
settunit
curcode
coreid
```

来自 `node_fundunit`：

```text
orgid
```

资金余额：

```text
m_dbFundbal = F100201.endbal
m_dbFundavl = F100212.endbal
```

信用账户修正：

```text
m_dbFundavl = min(F100201.endbal, F100212.endbal)
              - (F123103.endbal - F123104.endbal)
```

汇总待占用金额：

```text
m_dbTofrzamt += detail.m_dbTocostamt
              + detail.m_dbTofrzamt
              - detail.m_dbToufzamt
```

初始化结果字段：

```text
m_dbCostamt       = 0
m_dbFrzamt        = 0
m_dbSecondcostamt = 0
m_dbSecondfrzamt  = 0
m_dbFundnight     = 0
```

### 4.5 Clear 二次扣收

二次扣收执行：

```text
GenSecondCostDetail
  ↓
UpdateSecondCostSum
```

#### 4.5.1 GenSecondCostDetail 生成二次扣收明细

来源：

```text
第一次 node_fund_cost_detail
```

条件：

```text
costpoint = FIRST
costmode in (COST_MODE_COST_MAX, COST_MODE_COST)
存在未扣完或未冻完金额
```

差额：

```text
secondToCostamt = first.m_dbTocostamt - first.m_dbCostamt
secondToFrzamt  = first.m_dbTofrzamt  - first.m_dbFrzamt
```

二次明细继承字段：

```text
busidate
settbody
orgid
brhid
coreid
settunit
fundunit
fundacct
extfundunit
curcode
costpriority
costunit
busitype
costmode
cleardate
debtsno
```

二次明细重置字段：

```text
m_dbTocostamt = secondToCostamt
m_dbTofrzamt  = secondToFrzamt
m_dbToufzamt  = 0
m_dbFrzamt    = 0
m_dbUfzamt    = 0
m_dbCostamt   = 0
m_cAdvfrzflag = 空
m_cCostpoint  = SECOND
```

关键差异：

```text
二次明细 m_szRemark = 第一次明细 m_szRemark
二次明细 m_dbToufzamt = 0
二次明细 m_dbUfzamt = 0
```

因此二次扣收时：

```text
m_szRemark 仍表示第一次明细的原始待解冻金额。
m_dbUfzamt 表示二次明细自身实际已解冻金额，通常为 0。
```

#### 4.5.2 UpdateSecondCostSum 刷新汇总资金

不重新生成 `node_fund_cost_sum`，只刷新已有汇总的：

```text
m_dbFundbal
m_dbFundavl
```

取值逻辑仍然是：

```text
m_dbFundbal = F100201.endbal
m_dbFundavl = F100212.endbal
信用账户再按 F123103/F123104 修正
```

### 4.6 Write

写入内存库：

```text
node_fund_cost_detail BatchInsert
node_fund_cost_sum BatchInsert
node_fund_cost_sum BatchUpdate
```

写入物理库：

```text
一次扣收:
    node_fund_cost_sum BatchInsert

二次扣收:
    node_fund_cost_sum BatchUpdate
```

## 5. 632006 资金扣收处理

### 5.1 阶段顺序

```text
GetBusiParam
  ↓
Cache
  ↓
Clear
  ├─ 遍历 node_fund_cost_sum
  ├─ 获取并排序 node_fund_cost_detail
  ├─ 提前解冻预处理
  ├─ 逐笔 CalFundcostDetail
  ├─ 逐笔 CalDebtdetail
  ├─ 逐笔 CreateSettdetail
  └─ 更新 node_fund_cost_sum
  ↓
Write
```

### 5.2 GetBusiParam

读取范围和控制参数：

```text
beginfundunit
endfundunit
costpoint
otcfrzflag
```

读取公参：

```text
60110 组合费/存托服务费是否扣透支并余额蓝补
信用扣收维保比例
信用扣收维保保护业务类别
H股登记过户费处理模式
```

### 5.3 Cache

核心加载：

```text
node_fund_cost_sum
node_fund_cost_detail
node_debtdetail
comm_fund_cost_cfg
node_fundunit
node_fundacct
node_fundbookkeeping
intf_fundcost_result
```

`node_fund_cost_detail` 按扣收时点过滤：

```text
一次扣收:
    costpoint != SECOND

二次扣收:
    costpoint = SECOND
```

夜盘/OTC冻结：

```text
if otcfrzflag = 1:
    dbFundnight = fundnight + otcfrz
else:
    dbFundnight = fundnight
```

### 5.4 Clear 遍历 node_fund_cost_sum

每条汇总初始化资金池：

```text
dbFundbal = node_fund_cost_sum.m_dbFundbal
dbFundavl = node_fund_cost_sum.m_dbFundavl - dbFundnight
```

读取同一汇总维度下的明细：

```text
busidate + fundunit + curcode
```

排序：

```text
m_nCostpriority asc
```

### 5.5 Clear 提前解冻预处理

在逐笔扣收前，先扫描本汇总下所有明细。

如果：

```text
node_fund_cost_detail.m_cAdvfrzflag == FLAG_YES
```

执行：

```text
node_fund_cost_detail.m_dbUfzamt
    = node_fund_cost_detail.m_dbToufzamt

dbFundavl += node_fund_cost_detail.m_dbUfzamt
```

这里的含义要明确区分：

```text
第一步:
    把 node_fund_cost_detail.m_dbToufzamt
    更新到 node_fund_cost_detail.m_dbUfzamt

第二步:
    把 node_fund_cost_detail.m_dbUfzamt
    加回当前汇总资金池 dbFundavl
```

提前解冻释放出来的可用资金，会参与后续所有明细按优先级扣收。

### 5.6 Clear 逐笔 CalFundcostDetail

每笔先清零结果：

```text
detail.m_dbCostamt = 0
detail.m_dbFrzamt = 0
detail.m_dbCostprefrzamt = 0
```

如果当前明细不是提前解冻：

```text
detail.m_dbUfzamt = detail.m_dbToufzamt
dbFundavl += detail.m_dbUfzamt
```

所以：

```text
advfrzflag = YES:
    m_dbToufzamt → m_dbUfzamt 发生在逐笔扣收前

advfrzflag = NO:
    m_dbToufzamt → m_dbUfzamt 发生在当前明细计算时
```

一级预冻结处理：

```text
if prefrzamtflag = YES and F500131余额 > 0:
    dbFundavl += F500131余额
```

然后修正有效余额：

```text
dbFundbal = min(dbFundbal, dbFundavl)
```

扣收模式计算：

```text
0 全额扣收:
    costamt = tocostamt
    frzamt  = tofrzamt

1 有多少扣多少:
    costamt = min(tocostamt, 按 costunit 裁剪后的 fundbal)
    frzamt  = min(tofrzamt,  按 costunit 裁剪后的 fundavl)

2 足额扣收，不足不处理:
    fundbal >= tocostamt 才 costamt = tocostamt
    fundavl >= tofrzamt  才 frzamt  = tofrzamt

3 足额扣收，不足有多少冻结多少:
    fundbal >= tocostamt:
        costamt = tocostamt
    else:
        frzamt = min(tocostamt, 按 costunit 裁剪后的 fundavl)

4 有多少扣多少，不足全额冻结:
    fundbal >= tocostamt:
        costamt = tocostamt
    else:
        costamt = 按 costunit 裁剪后的 fundbal
        frzamt  = tocostamt - costamt

5 全额冻结:
    frzamt = tocostamt

6 有多少扣多少，不足仅蓝补余额:
    金额计算同 4
    后续流水走蓝补拆分

7 足额扣收，不足全额冻结:
    fundbal >= tocostamt:
        costamt = tocostamt
    else:
        frzamt = tocostamt
```

信用维保保护触发条件：

```text
启用维保参数
资金账号是信用账户
存在两融负债
业务类别在保护清单内
costmode != 0
```

满足时裁剪：

```text
detail.m_dbCostamt
```

一级预冻结使用额：

```text
如果 prefrzamtflag = YES
且 detail.m_dbCostamt > 原始未加预冻结的可用:
    计算 detail.m_dbCostprefrzamt
```

### 5.7 Clear 逐笔滚动资金池

每笔计算完成后：

汇总实扣：

```text
dbCostamt += detail.m_dbCostamt
```

汇总实冻净额：

```text
dbFrzamt += detail.m_dbFrzamt - detail.m_dbUfzamt
```

余额滚动：

```text
dbFundbal -= detail.m_dbCostamt
```

可用滚动：

```text
if detail.m_cAdvfrzflag != FLAG_YES:
    dbFundavl += detail.m_dbUfzamt

dbFundavl -= detail.m_dbCostamt
dbFundavl -= detail.m_dbFrzamt
```

因为提前解冻明细的 `m_dbUfzamt` 已经在预处理阶段加过，所以这里不能重复加。

如果：

```text
detail.m_dbCostamt != 0
or detail.m_dbFrzamt != 0
or detail.m_dbUfzamt != 0
```

更新 `node_fund_cost_detail`。

### 5.8 Clear CalDebtdetail 回写负债

一次扣收：

```text
node_debtdetail.m_dbPaidamt = detail.m_dbCostamt
node_debtdetail.m_dbFrzamt  = detail.m_dbFrzamt
```

二次扣收：

```text
node_debtdetail.m_dbSecondpaidamt = detail.m_dbCostamt
node_debtdetail.m_dbSecondfrzamt  = detail.m_dbFrzamt
```

普通业务：

```text
unpaidamt = debtamt
          - lastpaidamt
          - paidamt
          - paidamtday
          - secondpaidamt
```

预冻结类业务：

```text
unpaidamt = detail.m_dbTofrzamt - detail.m_dbFrzamt
```

了结：

```text
if closemode = CLOSE_MODE_ONCE
or unpaidamt = 0:
    closedate = busidate
```

然后处理：

```text
配号表
行权所得税
垫资明细
交割流水
```

### 5.9 Clear CreateSettdetail 生成交割流水

#### 5.9.1 是否生成流水

不在本模块生成：

```text
busitype in 898207,898208,898209
```

普通业务跳过条件：

```text
detail.m_dbCostamt = 0
detail.m_dbFrzamt  = 0
detail.m_dbUfzamt  = 0
dbUfzedAmt         = 0
```

其中：

```text
dbUfzedAmt = ToDouble(detail.m_szRemark)
```

不是：

```text
detail.m_dbUfzamt
```

#### 5.9.2 m_szRemark 与 m_dbUfzamt 的差异

`m_szRemark`：

```text
生成明细时保存的原始 detail.m_dbToufzamt
用于交割流水恢复原始解冻金额口径
```

`m_dbUfzamt`：

```text
扣收处理阶段计算出的本明细实际已解冻金额
```

明确不同的场景：

```text
场景一：632005 已生成，632006 未处理
    m_szRemark = 原始 m_dbToufzamt
    m_dbUfzamt = 0

场景二：二次扣收明细
    m_szRemark = 第一次明细 m_szRemark
    m_dbToufzamt = 0
    m_dbUfzamt = 0
```

提前解冻一次扣收处理完成后，通常是：

```text
m_szRemark = 原始 m_dbToufzamt
m_dbUfzamt = m_dbToufzamt
```

所以提前解冻本身不必然导致两者不同。

#### 5.9.3 主流水 node_settdetail

关键字段：

```text
busiflowid       = 流水前缀 + 序号
market           = debt.market
secuid           = debt.secuid
mainseat/trdseat = debt，缺失时从 node_secuid 补
fundacct         = node_fundunit.fundacct
fundunit         = debt.fundunit
curcode          = debt.curcode
busitype         = debt.busitype
specialbusitype  = debt.busitype
matchamt         = -detail.m_dbCostamt
priority         = comm_fund_cost_cfg.costpriority
clearflowid      = debt.clearflowid
trdflowid        = debt.sno
refbusiflowid    = debt.extsno
```

历史负债补扣：

```text
if debt.cleardate != debt.busidate
and comm_fund_cost_cfg.bk_busitype 非空:
    settdetail.busitype = bk_busitype
```

扣收时点：

```text
一次扣收:
    pathid = ZJKS
    bookkeepingpoint = KS

二次扣收:
    pathid = ZJKS_SECOND
    bookkeepingpoint = KS_SECOND
```

#### 5.9.4 子流水 node_settdetailsub

实扣金额：

```text
if detail.m_dbCostamt != 0:
    fieldname  = matchamt
    fieldvalue = -detail.m_dbCostamt
```

财富规划、投顾、AXB：

```text
fieldname = feefront
fieldvalue = -detail.m_dbCostamt
settdetail.matchamt = 0
```

冻结/解冻：

```text
if detail.m_dbFrzamt != 0 or dbUfzedAmt != 0:
    fieldname  = frzamt
    fieldvalue = detail.m_dbFrzamt - dbUfzedAmt
```

IPO 缴款：

```text
fieldname = matchqty
fieldvalue = 缴款数量
```

特殊业务还会补充：

```text
行权所得税 matchamt
限售股所得税 xsgsds_zrsramt
资金系统解冻 matchamt
```

#### 5.9.5 蓝补模式特殊流水

触发条件：

```text
detail.m_cCostmode = COST_MODE_COST_FRZ_MAX_BLUE
公参 60110 = 1
comm_fund_cost_cfg.correcting_busitype 非空
comm_fund_cost_cfg.reversal_busitype 非空
```

当日负债未偿还：

```text
原流水:
    matchamt = -abs(debt.debtamt)

新增蓝补流水:
    busitype = correcting_busitype
    matchamt = abs(debt.debtamt - debt.paidamt - debt.secondpaidamt)
```

历史负债补扣：

```text
原流水改为红冲:
    busitype = reversal_busitype
    matchamt = -abs(detail.m_dbCostamt)
```

缺少蓝补或红冲配置会抛错。

### 5.10 Clear 更新 node_fund_cost_sum

一个汇总维度下所有明细处理完后：

一次扣收：

```text
node_fund_cost_sum.m_dbCostamt = dbCostamt
node_fund_cost_sum.m_dbFrzamt  = dbFrzamt
node_fund_cost_sum.m_dbFundnight = dbFundnight
```

二次扣收：

```text
node_fund_cost_sum.m_dbSecondcostamt = dbCostamt
node_fund_cost_sum.m_dbSecondfrzamt  = dbFrzamt
node_fund_cost_sum.m_dbFundnight = dbFundnight
```

### 5.11 Write

写入顺序：

```text
1. 更新 node_fund_cost_detail
2. 插入 node_settdetail
3. 插入 node_settdetailsub
4. 更新 node_fund_cost_sum
5. 更新 node_debtdetail
6. 更新 node_logmateno
7. 更新行权所得税相关表
8. 更新质押回购垫资明细
9. 更新财富规划、投顾、H股全流通相关表
```

特殊点：

```text
即使 node_fund_cost_detail 没有更新，
也会先写 node_settdetail / node_settdetailsub。

原因是蓝补场景可能没有实际偿还金额，
但仍需要生成交割流水。
```

## 6. 扣收模式索引

| 模式 | 宏 | 含义 |
|---|---|---|
| `0` | `COST_MODE_COST_ALL` | 全额扣收，必扣 |
| `1` | `COST_MODE_COST_MAX` | 有多少扣多少 |
| `2` | `COST_MODE_COST` | 足额扣收，不足不处理 |
| `3` | `COST_MODE_COST_FRZ` | 足额扣收，不足有多少冻结多少 |
| `4` | `COST_MODE_COST_FRZ_MAX` | 有多少扣多少，不足全额冻结 |
| `5` | `COST_MODE_FRZ_ALL` | 全额冻结 |
| `6` | `COST_MODE_COST_FRZ_MAX_BLUE` | 有多少扣多少，不足仅蓝补余额 |
| `7` | `COST_MODE_COST_FRZ_ALL` | 足额扣收，不足全额冻结 |

## 7. 推荐阅读顺序

1. `lbm_pro/macbs/cbs_fund_cost/export.cpp`：确认功能号、导出函数、具体类和执行方法。
2. `lbm_pro/macbs/cbs_fund_cost/fundcostsum/fundcostsum.cpp`：阅读 `632005` 生成资金扣收数据主流程。
3. `lbm_pro/macbs/cbs_fund_cost/fundcostsum/handler/`：阅读不同业务类别如何补充 `node_fund_cost_detail` 字段和排序逻辑。
4. `lbm_pro/macbs/cbs_fund_cost/fundcostclear/fundcostclear.cpp`：阅读 `632006` 扣收计算、负债回写和交割流水生成。
5. `lbm_pro/macbs/cbs_fund_cost/fundcostsum_restore/`、`fundcostclear_restore/`：阅读重做恢复逻辑。
6. `lbm_pro/macbs/cbs_fund_cost/fundcost_post/`：阅读 `632008` 调用订单扣收逻辑。
