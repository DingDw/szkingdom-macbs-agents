# KDOP 接口参考

> 平台：`http://jzdevops.szkingdom.com:8080`（部署地址可配）
> 网关前缀：`/gateway/`
> 鉴权：`Authorization: Bearer-<JWT>` + 会话 Cookie
> 核实时间：2026-10-28（登录页/平台前端静态 JS 实测；标注「待登录核实」的需要账号权限确认返回结构）

## 1. 寻址规则（来自平台 `util/gateway-url.js`）

前端 JS 里的 `service-issue/xxx`、`serviceId-core/xxx`、`gateway/...` 最终都拼成：

```
/gateway/<service>/<service>/<接口路径>
```

| 前端写法 | 实际地址 |
| --- | --- |
| `service-core/global/search/listResult` | `/gateway/core/core/global/search/listResult` |
| `serviceId-issue/apps/project/index` | `/gateway/issue/issue/apps/project/index` |
| `gateway/issue/issue/issue/searchIssue` | 原样 |

本 skill 的 `normalize_path()` 会自动做这个转换，并修正 Git Bash 对 `/` 开头参数的路径改写。

## 2. 登录与身份

| 用途 | 端点 | 方法 | 说明 |
| --- | --- | --- | --- |
| 登录页 | `/login.html` | GET | 表单：`#loginName`、`#loginPassword`、`#validateCode`(可选)；按钮 `#loginButton` / `.login-btn` |
| 当前用户 | `/gateway/core/core/user/security/getLoginUserInfo` | POST | `code=200` 且 `data.token` 存在即成功；`data` 含 `userId`、`userName`、`email`、`orgCode`、`token` |
| 图形验证码 | `/gateway/core/core/user/security/getImageRandomCode` | GET | 前端用法：`?time=<随机数>` 刷新 |
| 登出 | `/gateway/core/core/user/security/logout` | POST | 前端登出按钮调用 |

- 密码由登录页前端 JS（3DES/ECB）加密后提交，**不要自己拼登录请求**；填表单点按钮最稳。
- 内部登录接口在前端是 `ajaxLogin`（`login.js` 里 `getNodeUrl(data,"gateway/core/core/user/security/ajaxLogin")`），
  但走页面表单可以同时拿到 Cookie 和 token，不需要自己实现加密。
- 未登录访问任意网关接口会返回**登录页 HTML（HTTP 200）**，不是 401/403，因此判定依据是「响应不是 JSON」。

## 3. 项目

| 用途 | 端点 | 参数 | 说明 |
| --- | --- | --- | --- |
| 有权限的产品/项目目录 | `/gateway/core/core/product/catalog/getPermitProductAndProjectCatalog` | 无 | 平台顶栏项目切换器数据源；返回产品→项目目录树（待登录核实具体字段） |
| 有权限的项目集 | `/gateway/core/core/project/set/getPermitAll` | 无 | 项目集维度（可选） |
| 模块授权 | `/gateway/core/core/authorizeCode/isAllow` | `moduleName` | 判断当前账号是否开通某模块 |

`kdop_core projects` 优先用项目目录接口；失败时退回用「全平台版本列表」的 `parentId/parentName` 反推。

## 4. 版本

```
POST /gateway/issue/issue/issue/getIssueVersionList
Content-Type: application/x-www-form-urlencoded

objectId=<项目ID>
```

- **必须用 `objectId`**；传 `projectId` 会 500。
- 返回**全平台**版本（三万条量级），要按 `parentId == 项目ID` 过滤。
- 行字段：`objectId`、`objectName`、`parentId`、`beginDate`、`planEndDate`、`endDate`（毫秒时间戳）、`status`。
- 不再返回 `issueReleaseFull` / `doneBugFull` 等聚合统计，统计必须自己按需求/缺陷算。

## 5. 需求与缺陷

```
POST /gateway/issue/issue/issue/searchIssue
Content-Type: application/x-www-form-urlencoded;charset=UTF-8

field=<逗号分隔字段>
&appId=1|2
&page=1
&size=500
&projectId=<项目ID>
&versionId=<版本UUID>          # 推荐
&versionIdName=<版本名>        # 单值精确匹配，跨多版本会漏
&extraQueryField=
&extraQueryFilterOptions=[]
```

- `appId=1` 需求/工作项，`appId=2` 缺陷。
- 分页 `page` + `size`（`rows` 会 400），`size=500` 实测可用。
- 返回 `{"code":200,"data":{"total":N,"pageSize":n,"list":[...]}}`。
- `field` 必须显式列字段；`custom_*` 通配不稳定。

需求详情接口在不同部署里可能不同（默认 `/gateway/issue/issue/issue/getIssueDetail`），
本 skill 取不到时自动退回 `searchIssue` 单条查询。

## 6. 提交（代码域全局检索）

```
POST /gateway/core/core/global/search/listResult
Content-Type: application/x-www-form-urlencoded

module=4
&keyword=<关键字>
&projectId=<项目ID>     # 可选，平台按项目过滤
```

- 端点与模块号来自平台前端 `index/src/global-search.js`（顶栏全局搜索的「代码」tab）。
- `module`：1=需求 2=缺陷 3=用例 4=代码/提交；5~7 为其他工作项类型。
- 代码结果行在前端被当作 commit 使用，字段含 `id`、`projectId`、`revision`、`message`、`repoType`
  （前端 `select` 时把整行作为 `repoCommitData` 传给代码页）。
- 返回结构为 `{"code":200,"data":[...]}`（列表直接在 `data`，不是 `data.list`；实现里两种都兼容）。
- 局限：这是**关键字检索**，不保证「提交 ↔ 需求」的外键关系；检索粒度由平台分词/模糊规则决定。

## 7. 其他可用端点（前端已出现，按需扩展）

| 用途 | 端点 |
| --- | --- |
| 菜单树（含各业务应用 openUrl） | `/gateway/core/core/menu/list` |
| 未读消息数 / 消息体 | `/gateway/core/core/user/message/getNotReadTotal`、`/getSubject`、`/messageDetail` |
| 全局搜索历史 | `/gateway/core/core/global/search/listHistory`、`/clearHistory` |
| 交付流水线信息 | `/gateway/issue/issue/pipeline/info/getInfo` |
| 上线校验 | `/gateway/pipeline/pipeline/cicd/checkOnLine` |

接口升级后重新发现：`kdop_core discover --keyword <关键字>`（不需要登录态）。

## 8. 请求头模板

```
Authorization: Bearer-eyJhbGciOi...
Cookie: websessionid=...; K-JSESSIONID=...; ktsessionid=Bearer-eyJ...
Content-Type: application/x-www-form-urlencoded;charset=UTF-8
Accept: application/json, text/plain, */*
X-Requested-With: XMLHttpRequest
User-Agent: Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36
```

访问内网地址要**绕开系统代理**（实现里对 urllib 使用空 ProxyHandler），否则会被 `http_proxy` 劫持。

## 9. 排查清单

| 现象 | 原因 |
| --- | --- |
| 返回 HTML（登录页），HTTP 200 | 没带 token/Cookie，或 token 过期 |
| `code=500` + 查询异常 | 分页参数写成 `rows`，或 `getIssueVersionList` 用了 `projectId` |
| 版本列表出现其它项目版本 | 未按 `parentId` 过滤，或过滤后为空被兜底成全量 |
| 某版本需求数偏少 | 用了 `versionIdName` 单值匹配，跨多版本的故事被漏 |
| 提交检索为空 | 提交信息里没有该编号；或账号无代码域权限；或需要按项目过滤 |
| 统计全 0 | 新接口不再返回聚合字段，需按状态自行统计 |
| 路径被改写成 `C:/.../gateway/...` | Git Bash 路径转换，用不带前导 `/` 的写法 |
