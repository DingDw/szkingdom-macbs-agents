# KDOP 概念定义

> 平台：KDOP / jzdevops（研发管理平台）。本文只描述**平台无关的通用概念**，具体部署地址、项目、版本由配置提供。

## 1. 平台分层

```
浏览器 SPA（index.html + 各业务应用 iframe）
        │  统一网关
        ▼
网关 /gateway/<服务>/<服务>/<接口>     例：/gateway/issue/issue/issue/searchIssue
        │
        ▼
业务服务：core（用户/项目/全局检索）、issue（需求/缺陷/版本/流程）、test、pipeline …
```

平台前端在 JS 里用简写 `service-core/xxx`、`serviceId-issue/xxx`，等价于
`/gateway/core/core/xxx`、`/gateway/issue/issue/xxx`（见 `references/api.md` 寻址规则）。

## 2. 身份与鉴权

| 概念 | 说明 |
| --- | --- |
| 登录账号 | 工号（`userId`） |
| token | `data.token`，形如 `Bearer-eyJhbGci...`，是 JWT；`exp` 即过期时间 |
| 会话 Cookie | `websessionid` / `K-JSESSIONID` / `ktsessionid` 等，需与 token 一起带 |
| 登录校验 | `getLoginUserInfo` 返回 `code=200` 且 `data.token` 非空即视为已登录 |
| 滑动续期 | 平台会在部分响应里下发新 `data.token`；及时落盘即可长期免登录 |

**推论**：裸 HTTP 不带 token+Cookie 会拿到登录页 HTML（HTTP 200，不是 401），
所以「返回非 JSON」必须当作登录态失效处理，而不是当成接口错误。

## 3. 核心业务对象

| 概念 | 主键 | 关键字段 | 说明 |
| --- | --- | --- | --- |
| 项目 project | `projectId` | `objectName` / `projectName` | 归属容器；权限按项目授予 |
| 版本 version | `objectId`(UUID) | `objectName`、`parentId`、`beginDate`、`planEndDate`、`status` | 交付批次，如 `FS2.5_macbs_1.7.9.0` |
| 需求（故事）story | `id`(UUID) | `issueNum`、`title`、`issueTypeName`、`statusName`、`assigneeName` | `appId=1` 的工作项；以 `issueTypeName` 含「故事」界定 |
| 缺陷 bug | `id` | `issueNum`、`statusName`、`bugGradesName` | `appId=2` |
| 提交 commit | `revision` | `message`、`repoType`、`repoName`、`commitTime` | 代码域记录，通过全局检索获取 |
| 需求编号 | 文本 | `FS-CBS-\d+` | 业务需求号，通常出现在需求标题与提交信息中 |

### 版本 ↔ 需求：多对多
一个需求可属于多个版本（`versionIdName` 是逗号分隔多值）。因此：
- 按版本过滤必须用 `versionId`（UUID）；用 `versionIdName` 只做单值匹配，会漏掉跨多版本的需求。
- 汇总多版本时要按需求 `id` 合并，并记录命中了哪些版本。

### 需求 ↔ 提交：弱关联（关键字）
平台**没有**需求到提交的外键。真正的关联链是：

```
需求标题里的 FS-CBS-xxxx  ←→  提交信息里的 FS-CBS-xxxx
```

所以「某需求的提交」= 用编号在提交信息里检索的**证据**，不是权威关系。
追溯报告必须标注来源（KDOP 代码检索 / 本地 git）并提示人工复核。

## 4. 状态机

需求/故事（`statusName`，`status` 为空，判断时只看 `statusName`）：

```
开放 → 已受理 → 已分配 → 开发中 → 评审中 → 待测试 → 测试中 → 已解决 → 已关闭
                                                    ↑                │
                                                    └──── 重新打开 ←──┘
```

缺陷（`statusName`，`status` 为数字码）：

```
新建 → 激活 → 修复 → 关闭
              └→ 拒绝修复 / 丢弃
```

## 5. 统计口径（默认，可按团队习惯调整）

| 指标 | 口径 |
| --- | --- |
| 总故事数 | `issueTypeName` 含「故事」的记录数 |
| 开发完成 | 状态 ∈ {待测试, 测试中, 已解决, 已关闭} |
| 测试完成 | 状态 ∈ {已解决, 已关闭} |
| 需求完成率 | (开发完成率 + 测试完成率) / 2 |
| 缺陷修复 | 状态 ∈ {修复, 拒绝修复, 关闭, 丢弃} |
| 缺陷关闭 | 状态 ∈ {关闭, 丢弃} |

## 6. 字段字典（常用）

| 字段 | 含义 |
| --- | --- |
| `id` / `issueNum` | 工作项内部 ID / 业务编号 |
| `issueTypeName` | 类型名：故事、任务、子任务、缺陷… |
| `statusName` | 状态名（需求只有这个可用） |
| `versionId` / `versionIdName` | 版本 UUID / 版本名（可能逗号分隔多值） |
| `assigneeName` / `developersName` / `testerName` | 经办人 / 开发 / 测试 |
| `moduleName` / `productModuleName` | 所属模块 |
| `custom_589` | 计划开发完成日期（毫秒时间戳） |
| `custom_469` | 计划测试完成日期 |
| `custom_96` | 开发完成日期 |
| `custom_564` | 计划转测日期 |
| `custom_83Name` | 开发人员 |

## 7. 抽象边界（本 skill 的分层）

```
认证层   ensure_session / browser_login        ← 只关心「有没有可用 token」
传输层   api / call                           ← 只关心「把表单参数发出去、拿回 data」
业务层   projects / versions / requirements / issue / search_commits
追溯层   trace_version                        ← 组合业务层 + 本地 git，产出证据报告
```

扩展新接口时优先走 `api` 直调验证，稳定后再固化为一个业务方法或端点覆盖。
