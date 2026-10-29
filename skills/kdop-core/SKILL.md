---
name: kdop-core
description: "通用 KDOP（jzdevops 研发管理平台）访问与需求追溯 skill：自动登录后按项目/版本抓取需求（故事）、缺陷、提交，并能回答「某版本有哪些需求」「某需求关联了哪些代码提交」。当用户提到 KDOP、jzdevops、版本需求清单、需求完成率、缺陷清单、需求编号 FS-CBS-xxx 的提交/代码变动、版本交付盘点、需求追溯时使用。"
description_zh: "KDOP 通用访问与需求追溯（登录/概念/常用方法/版本→需求→提交）"
description_en: "Generic KDOP client: silent login, versions/stories/defects/commits, requirement-to-commit traceability"
allowed-tools: Bash,Read,Glob,Grep
---

# KDOP 通用访问与需求追溯

本 skill 是从具体项目里抽出来的**通用层**：只封装 KDOP 的认证、传输、通用概念和追溯方法，
不绑定任何项目、版本或仓库。项目/版本/仓库都由参数或配置提供。

四条能力：

| 能力 | 命令 | 回答的问题 |
| --- | --- | --- |
| 认证 | `login` / `whoami` / `config` | 我是谁、登录态还有效吗 |
| 通用查询 | `projects` / `versions` / `requirements` / `issue` / `api` | 项目有哪些版本、版本下有哪些需求、某需求详情 |
| 提交检索 | `commits` | 关键字（需求编号/issueNum）命中了哪些提交 |
| 追溯 | `trace` | 某版本的需求清单 + 每条需求的提交证据 |

## 一、先理解登录模型（否则容易误判「需要人工登录」）

| 阶段 | 做什么 | 需要人工吗 |
| --- | --- | --- |
| 首次配置 | `config set` 写账号到 `~/.kdop/config.json` | 需要一次（用户自己填） |
| 首次登录 | 无头 Chrome 打开登录页填表提交，取 Bearer token + Cookie 存 `~/.kdop/session.json` | 不需要，全自动 |
| 日常调用 | 直接用 token + Cookie 发 HTTP，不起浏览器 | 不需要 |
| token 过期 | 自动重登一次并重试原请求 | 不需要 |

**不要**提示用户「请先登录 KDOP」。只有 `config` 里没有账号时才需要用户提供账号密码。
登录态与会话文件与旧 `kdop` skill 兼容，可直接复用、无需二次登录。

## 二、概念速查（完整定义见 `references/concepts.md`）

| 概念 | 标识 | 说明 |
| --- | --- | --- |
| 项目 project | `projectId` | 需求/版本的归属容器，一个项目下多个版本 |
| 版本 version | `objectId`(UUID) / `objectName` | 交付批次，如 `FS2.5_macbs_1.7.9.0`；需求与版本是多对多 |
| 需求/故事 story | `id`(UUID) / `issueNum` | `appId=1` 下的工作项，只统计 `issueTypeName` 含「故事」的 |
| 缺陷 bug | `id` / `issueNum` | `appId=2` |
| 提交 commit | `revision` / `message` | 代码域记录；与需求**没有强外键**，靠提交信息里的编号弱关联 |
| 需求编号 | `FS-CBS-\d+` | 业务需求号，通常出现在需求标题和提交信息里 |

关键推论：**需求 ↔ 提交是关键字匹配，不是外键关联。** 追溯结果要标注证据来源并提示人工复核。

## 三、命令

```bash
SKILL=<kdop-core skill 目录>
"$SKILL/scripts/kdop_core.sh"  ...    # Windows 用 scripts\kdop_core.cmd
```

```bash
# 配置（仅首次；--base-url 换部署时才需要）
kdop_core config set --username <工号> --password <密码> \
                     --project-id <项目ID> --base-url http://jzdevops.szkingdom.com:8080
kdop_core config show           # 密码打码，显示 session 是否有效
kdop_core login / whoami / logout

# 项目与版本
kdop_core projects                          # 有权限的项目（失败时加 --from-versions 反推）
kdop_core versions --match "1\.7\.9"        # 本项目版本；--all-projects 全平台
kdop_core versions --match "1\.7" --json --out versions.json

# 需求清单
kdop_core requirements --version FS2.5_macbs_1.7.9.0 --format md
kdop_core requirements --version V1 --version V2 --out stories.json
kdop_core requirements --version FS2.5_macbs_1.7.9.0 --summary     # 完成率
kdop_core requirements --version FS2.5_macbs_1.7.9.0 --app-id 2 --summary   # 缺陷修复率

# 单条需求
kdop_core issue <issueId>

# 提交检索（两条独立通道）
kdop_core commits --keyword FS-CBS-24123              # KDOP 代码域全局检索
kdop_core commits --keyword FS-CBS-24123 --local      # 本地 git 仓库提交信息检索

# 追溯：版本 → 需求 → 提交
kdop_core trace --version FS2.5_macbs_1.7.9.0 --format md --out trace.json
kdop_core trace --version FS2.5_macbs_1.7.9.0 --no-kdop-commits   # 只走本地 git（快）

# 兜底：任意网关接口 / 接口发现（无需登录）
kdop_core api gateway/issue/issue/issue/searchIssue --data appId=1 --data page=1 --data size=5
kdop_core discover --keyword commit
```

约定：**stdout 只输出 JSON/Markdown，进度与统计走 stderr**，可直接被程序消费。

## 四、工作流 A：抓取某版本的所有需求

1. 确认版本名（用户给的名字可能不精确，先模糊匹配）：

```bash
kdop_core versions --match "<用户给的关键字>"
```

2. 拉需求清单并落盘：

```bash
kdop_core requirements --version <精确版本名> --out stories.json --json
```

3. 汇报口径：
   - 只算 `issueTypeName` 含「故事」的记录（`requirements` 已过滤）。
   - 需要完成率时用 `--summary`：开发完成 = `待测试/测试中/已解决/已关闭`；
     测试完成 = `已解决/已关闭`；需求完成率 =（开发完成率 + 测试完成率）/ 2。
   - 版本名未命中时**不要猜**，把 `versions --match` 的候选列表给用户确认。

## 五、工作流 B：列出某需求的所有相关提交

对每个需求构造关键字，然后两条通道并行取证：

| 通道 | 命令 | 数据来源 | 局限 |
| --- | --- | --- | --- |
| KDOP | `commits --keyword <编号>` | 平台「代码」域全局检索（`module=4`） | 依赖编号出现在提交信息；平台需有代码域权限 |
| 本地 git | `commits --keyword <编号> --local` | 本地仓库 `git log --all --grep` | 只覆盖本地已拉取的仓库和分支 |

关键字取值顺序（`requirement_keywords` 已实现）：`issueNum` → 标题里的 `FS-CBS-xxx` → 人工补充（`--keyword-extra`）。

一键产出（含版本概览、需求清单、每条需求的提交明细、无证据需求清单）：

```bash
kdop_core trace --version <版本名> --format md --out trace.json
```

汇报规则：

- 提交证据一律标注来源（`kdop` / `git`），并声明「按提交信息关键字匹配，非平台外键，需人工复核」。
- 找不到提交时，明确写「未找到」+ 可能原因（未提交、编号未写入提交信息、代码不在本地仓库、无代码域权限），
  **不要**用相似编号或标题模糊匹配冒充命中。
- 只要文件清单时：提交记录的 `files` 字段就是该提交的变更文件；跨提交去重时保留仓库归属。

## 六、扩展：接口变了怎么办

平台接口无版本化，升级后路径可能变化。`discover` 会抓平台前端静态 JS 并列出其中的网关路径（不需要登录）：

```bash
kdop_core discover                      # 全部网关接口
kdop_core discover --keyword commit     # 只看含关键字的
```

找到新路径后写回配置即可，不用改代码：

```bash
kdop_core config set --username <工号> --password <密码>   # 保持账号
# 端点覆盖：直接编辑 ~/.kdop/config.json 的 endpoints 段，或用 Python 调用 update_config(endpoints={...})
```

## 七、已知坑（都已在实现里绕开）

1. 版本列表接口只认 `objectId`；传 `projectId` 会 500。
2. 版本列表返回**全平台**数据（三万条量级），必须按 `parentId == 项目ID` 过滤。
3. 按版本拉数据要用 `versionId`（UUID）；`versionIdName` 只做单值匹配，跨多版本的需求会漏。
4. 分页参数是 `page` + `size`（`rows` 会 400），`size` 上限实测 500。
5. `field` 必须显式列字段，`custom_*` 通配在新版不稳定；本 skill 内置字段清单。
6. 内网访问必须绕开系统代理（实现里已禁用 urllib 代理），否则被 `http_proxy` 劫持。
7. 全局检索的 `module`：1=需求 2=缺陷 3=用例 4=代码提交。
8. Git Bash 会把 `/` 开头的参数当路径改写；传接口路径写 `gateway/...`，实现内部也会归一化。

## 八、出错处理

| 退出码 | 含义 | 处理 |
| --- | --- | --- |
| 3 | 登录失败 | 账号密码错/被锁/触发验证码；让用户核对 `config show` |
| 4 | 接口或网络错误 | 检查公司网络/VPN；用 `discover` 或 `api` 复核接口；见 `references/api.md` |
| 5 | 配置缺失 | 未配账号或未配 `projectId` |
| `接口返回非 JSON` | 登录态失效 | 自动重登；仍失败则 `logout` 后 `login` |
| 需要图形验证码 | 未装 OCR | `install.ps1 -Ocr`，或设 `KDOP_CAPTCHA_CMD` |

## 九、参考文档

- `references/concepts.md`：概念定义、字段字典、状态机、关联模型、统计口径。
- `references/api.md`：已核实端点、参数、返回结构、寻址规则、排查清单。
- `references/trace-workflow.md`：追溯工作流细节与报告模板。

## 十、安全说明

- 账号密码明文存于 `~/.kdop/config.json`（仅本机，权限 600；Windows 上 chmod 不生效，属本机信任模型）。
- token 存 `~/.kdop/session.json`，过期自动续期；日志只记登录结果，不记 token。
- 分享 skill 不带任何账号信息；彻底清除用 `config clear`。
