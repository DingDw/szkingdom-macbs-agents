# kdop-core：KDOP 通用访问与需求追溯

一句话：**填一次自己的 KDOP 账号，之后「某版本有哪些需求」「某需求改了哪些代码（commit）」都能一条命令拿到。**

即装即用，无需任何人工登录确认。

---

## 一、安装（3 步）

1. 把整个 `kdop-core` 文件夹放到 skill 目录：
   - WorkBuddy：`%USERPROFILE%\.workbuddy\skills\kdop-core`
   - CodeBuddy：`%USERPROFILE%\.codebuddy\skills\kdop-core`
   - macOS/Linux：`~/.workbuddy/skills/kdop-core`

2. 安装依赖（只需一次；已装过 `kdop` skill 的会直接复用它的 venv）：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
   ```
   ```bash
   bash ./scripts/install.sh
   ```

3. 填账号（只需一次）：

   ```powershell
   .\scripts\kdop_core.cmd config set --username <工号> --password <密码> --project-id <项目ID>
   .\scripts\kdop_core.cmd login
   ```
   ```bash
   ./scripts/kdop_core.sh config set --username <工号> --password <密码> --project-id <项目ID>
   ./scripts/kdop_core.sh login
   ```

看到 `登录成功：<姓名>（<工号>）` 就完成了。之后每天再跑任何命令都不用重新登录。

> 不知道项目 ID？先跑 `kdop_core projects`；如果该接口不可用，用
> `kdop_core versions --all-projects` 看输出里的 `parentId`/`project` 也能对上。

## 二、验证

```powershell
.\scripts\kdop_core.cmd whoami
```

```json
{
  "base_url": "http://jzdevops.szkingdom.com:8080",
  "login_user_id": "1001",
  "user_name": "张三",
  "session_source": "cache",
  "expires_at": "2026-10-29 09:12"
}
```

## 三、用起来

### 需求场景 1：抓取版本的所有需求

```powershell
# 先模糊找版本名
.\scripts\kdop_core.cmd versions --match "1\.7\.9"

# 拉需求清单（JSON 落盘 + Markdown 直读）
.\scripts\kdop_core.cmd requirements --version FS2.5_macbs_1.7.9.0 --out stories.json --format md

# 只要完成率
.\scripts\kdop_core.cmd requirements --version FS2.5_macbs_1.7.9.0 --summary
```

### 需求场景 2：某需求关联的代码提交

```powershell
# 平台侧：按需求编号在 KDOP 代码域检索
.\scripts\kdop_core.cmd commits --keyword FS-CBS-24123

# 本地侧：在已拉取的仓库里按提交信息检索（含变更文件清单）
.\scripts\kdop_core.cmd commits --keyword FS-CBS-24123 --local

# 一步到位：整版本每个需求都配上提交证据
.\scripts\kdop_core.cmd trace --version FS2.5_macbs_1.7.9.0 --format md --out trace.json
```

`trace` 的输出包含：版本概览、需求清单、每条需求的提交明细（来源/仓库/提交号/日期/说明/文件数）、
无提交证据的需求清单与覆盖率。

### 其他

```powershell
.\scripts\kdop_core.cmd projects
.\scripts\kdop_core.cmd issue <需求ID>
.\scripts\kdop_core.cmd api gateway/issue/issue/issue/searchIssue --data appId=1 --data page=1 --data size=5
.\scripts\kdop_core.cmd discover --keyword commit      # 平台升级后重新发现接口
```

## 四、在 AI 助手里用

直接说：

- 「用 KDOP 拉一下 1.7.9.0 的所有需求，按模块列出来」
- 「FS-CBS-24123 关联了哪些 commit，改了哪些文件」
- 「把这个版本每个需求的提交证据整理成报告」

助手会调 `kdop-core`，不需要你解释接口怎么调。

## 五、和 `kdop` skill 的关系

| | `kdop`（旧） | `kdop-core`（本 skill） |
| --- | --- | --- |
| 定位 | 绑定 FS2.5-CBS 清算项目的取数工具 | 通用层：项目/版本/仓库都由参数或配置提供 |
| 登录 | 无头浏览器 + token 缓存 | 相同机制，**复用同一份 `~/.kdop` 配置与登录态** |
| 能力 | 版本/需求/缺陷 + 完成率 | 追加：项目清单、单条需求详情、提交检索、需求→提交追溯、接口发现 |
| 兼容性 | 配置与会话格式一致，两个 skill 可共存 | 互不覆盖；`config set` 只更新传入的键 |

## 六、常见问题

| 问题 | 解决 |
| --- | --- |
| 提示未配置账号 | `config set --username ... --password ...` |
| 提示未配置 projectId | `config set --project-id <ID>`，或命令加 `--project-id` |
| 登录失败 / 账号被锁 | 先在浏览器登录一次 KDOP 确认账号正常，再 `login` |
| 登录页要图形验证码 | `install.ps1 -Ocr` 装依赖 + 装 Tesseract；或设 `KDOP_CAPTCHA_CMD` |
| 版本列表太大 / 很慢 | 用 `--match` 过滤；全平台版本有三万条量级 |
| 提交检索为空 | 提交信息里可能没写需求编号；或账号无代码域权限；本地改用 `--local` |
| 接口变了 | `kdop_core discover` 重新发现，然后覆盖 `~/.kdop/config.json` 的 `endpoints` |
| 换人 / 换账号 | `config clear` 后重新 `config set` |

## 七、安全

- 账号密码只写在使用者自己的 `~/.kdop/config.json`（权限 600；Windows 上 chmod 不生效，属本机信任模型）。
- token 缓存在 `~/.kdop/session.json`，过期自动续期，不落日志。
- skill 包内不含任何账号信息，可直接转发；彻底清除用 `config clear`。
