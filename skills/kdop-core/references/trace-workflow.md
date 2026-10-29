# 追溯工作流：版本 → 需求 → 提交

面向的问题：
- 「抓取版本 X 的所有需求」
- 「列出某个需求的所有相关代码变动的 commit」

## 1. 总体链路

```
版本名 ──versions(模糊匹配)──► 精确版本名 + versionId
                                   │
                     requirements  │  searchIssue(versionId)  → 只要「故事」
                                   ▼
                              需求清单（编号/标题/状态/经办人）
                                   │
                  requirement_keywords：issueNum、标题里的 FS-CBS-xxx
                                   ▼
        ┌──────────────关键词──────────────┐
        ▼                                  ▼
KDOP 提交检索(module=4)            本地 git log --grep
        │                                  │
        └──────────► 按 hash 去重 ◄────────┘
                          ▼
              需求 → 提交证据（标注来源）+ 覆盖率统计
```

## 2. 判定规则

| 场景 | 处理 |
| --- | --- |
| 版本名不精确 | 先 `versions --match`，把候选给用户确认，**不要猜** |
| 一个需求属于多个版本 | 按需求 `id` 合并，记录命中的版本列表 |
| 标题里没有编号 | 只有 `issueNum` 可查；在报告里说明「无业务需求号」 |
| 编号大小写不一致 | 统一大写比较；git 侧用 `--regexp-ignore-case` |
| 同一编号命中多个需求 | 属正常（一需求多提交 / 编号复用），按需求分别归属 |
| 提交同时命中多个需求编号 | 归到各需求，报告里注明「一次提交关联多个需求」 |
| 只有 KDOP 有、本地没有 | 代码不在本地分支，或本地未拉取；保留 KDOP 证据 |
| 只有本地有、KDOP 没有 | 平台未同步该仓库，或账号无代码域权限；保留 git 证据 |
| 完全没有证据 | 输出到「无提交证据」清单，并给出可能原因，**不要用相似标题凑数** |

## 3. 命令组合

```bash
# 一次性产出（推荐）
kdop_core trace --version FS2.5_macbs_1.7.9.0 --format md --out trace.json

# 只关心本地代码（快，不需要 KDOP 代码域权限）
kdop_core trace --version FS2.5_macbs_1.7.9.0 --no-kdop-commits --repo <仓库1> --repo <仓库2>

# 分步做（需要自定义过滤/统计时）
kdop_core versions --match "1\.7\.9"
kdop_core requirements --version FS2.5_macbs_1.7.9.0 --out stories.json
kdop_core commits --keyword FS-CBS-24123
kdop_core commits --keyword FS-CBS-24123 --local --repo D:/repo/macbs-base
```

配置里固定常用仓库，避免每次传 `--repo`：

```bash
kdop_core config set --username <工号> --password <密码> \
                     --repos D:/repo/macbs-base D:/repo/macbs-service
```

未配置时，回溯层会自动在当前目录及上一级发现 `.git` 目录（深度 2）。

## 4. 报告模板（`--format md` 已内置）

```text
# 需求提交追溯：<版本名>
- 版本ID / 周期 / 需求总数 / 有提交证据数 / 覆盖率
- 证据来源分布：{kdop: N, git: M}
> 提交证据为「提交信息含编号」的弱关联，需人工复核。

## 一、需求清单（编号/标题/状态/经办人/提交数）
## 二、需求 → 提交明细（来源/仓库/提交号/日期/说明/文件数）
## 三、无提交证据的需求
```

## 5. 质量规则

- 每个结论都要能指回原始数据：提交号（或 revision）、仓库、需求编号、检索关键字。
- 统计口径固定写在报告里（完成率 =（开发完成率 + 测试完成率）/ 2），避免读者理解偏差。
- 覆盖率低于预期时，先检查三件事：提交信息是否写编号、版本是否选对、仓库是否已拉取。
- 不把「同一作者、相邻时间、相似标题」当成关联证据。
- 需求编号缺失时标注 `FIXME`，不要编造编号。
