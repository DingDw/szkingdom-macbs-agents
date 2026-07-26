---
name: spec-kdop-filler
description: Fill KDOP requirement fields from a specified OpenSpec spec change and collect the related file list for an FS-CBS-XXX requirement by searching commit messages in both macbs-base and macbs-service. Use when the user asks to generate KDOP text, fill KDOP requirement analysis fields, summarize a spec change into 需求描述/需求分析/实现概要/影响范围/测试要点, or produce 文件清单 from MACBS commits whose messages contain a KDOP requirement number.
---

# Spec KDOP Filler

## Overview

Generate paste-ready KDOP content for MACBS requirements. Base the requirement sections on the specified OpenSpec change, and base the file list only on commits in `macbs-base` and `macbs-service` whose commit messages contain the specified `FS-CBS-XXX` requirement number.

## Inputs

Require these inputs:

- OpenSpec change identifier or path, such as `add-clear-check` or `openspec/changes/add-clear-check`.
- KDOP requirement number in `FS-CBS-XXX` format for commit search.

If either input is missing and cannot be inferred from the user's message, ask for it before producing final KDOP content.

## Workflow

1. Locate the OpenSpec change.
   - Prefer an explicit path from the user.
   - Otherwise search likely `openspec/changes/<change-id>` locations under the current repo and parent workspace.
   - Read the change's `proposal.md`, `design.md`, `tasks.md`, and delta specs under `specs/` when present.
   - Treat checked tasks, implementation notes, spec deltas, and design decisions as the source for implementation details.

2. Draft the five KDOP requirement sections from the spec change.
   - `需求描述`: State the business requirement and target behavior. Prefer user-visible behavior over internal implementation.
   - `需求分析`: Explain the current gap, business rules, constraints, and why the change is needed.
   - `实现概要`: Summarize the chosen implementation approach, major modules, flows, tables, parameters, or scripts. Mention whether it is a single function number or three-stage processing when the spec establishes that.
   - `影响范围`: List affected repositories, modules, function numbers, database objects, flow configuration, parameters, and deployment scripts that are supported by the change evidence.
   - `测试要点`: Cover normal path, boundary cases, regression risks, database/script validation, clearing stage behavior, and any customer-specific or day-end/daytime distinction in the spec.

3. Locate both repositories for commit evidence.
   - Search for `macbs-base` and `macbs-service` as sibling or child directories of the current workspace when paths are not explicit.
   - Use `git -C <repo>` so repository context is unambiguous.
   - If a repository cannot be found, state that clearly in the evidence notes and continue with the repository that is available.

4. Search commits by KDOP requirement number.
   - Use commit message search, not source text search, as the primary evidence:

```powershell
git -C <repo-path> log --all --regexp-ignore-case --grep="<FS-CBS-XXX>" --name-only --pretty=format:"commit %H%nsubject %s"
```

   - Collect the commit hash, subject, and changed file paths.
   - Deduplicate file paths within each repository while preserving repository ownership.
   - Exclude blank lines and commit metadata from the final `文件清单`.
   - If matching commits exist but contain no file names because of command options or merge commits, rerun with `--stat` or inspect each commit with `git show --name-only --pretty=format:`.

5. Cross-check only when needed.
   - Use `rg "<FS-CBS-XXX>"` to find related local notes, SQL comments, or task references only as supplemental context.
   - Do not add files to `文件清单` from `rg` unless they are also present in matching commit file lists, or explicitly label them as supplemental non-commit evidence.

## Output Format

Produce concise Chinese content using exactly these labels and blank lines:

```text
需求描述：
<content>

需求分析：
<content>

实现概要：
<content>

影响范围：
<content>

测试要点：
<content>

文件清单：
macbs-base：
- <path>

macbs-service：
- <path>
```

If no matching commits are found for one repository, write `未找到提交注释包含 <FS-CBS-XXX> 的提交。` under that repository.

## Quality Rules

- Do not invent KDOP facts. If the spec change does not establish a detail, either omit it or mark it as `未在 spec change 中明确`.
- Prefer day-end clearing (`日终清算`) context unless the user or spec explicitly involves daytime clearing (`日间清算`).
- Preserve customer-specific scope when the spec or file paths show a customer directory.
- Keep the final answer directly pasteable into KDOP; avoid long process narration unless the user asks for evidence.
- When reporting uncertainty, include the exact missing input, missing file, or repository path that caused it.
