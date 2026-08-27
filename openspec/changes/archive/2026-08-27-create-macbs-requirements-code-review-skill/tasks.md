## 1. Skill Structure

- [x] 1.1 Initialize the `macbs-requirements-code-review` skill in the user's Codex skills directory using the skill creator workflow.
- [x] 1.2 Create concise `SKILL.md` frontmatter with a trigger description covering KDOP version requirement review, MACBS clearing code analysis, and HTML code review report generation.
- [x] 1.3 Add only required resource directories, favoring `scripts/` for deterministic KDOP, git, diff, and HTML operations.
- [x] 1.4 Generate or update `agents/openai.yaml` so the skill is discoverable with accurate UI metadata.

## 2. KDOP Collection

- [x] 2.1 Implement runtime input handling for KDOP cookie, `projectId`, and `versionId`, with missing-input checks and cookie redaction.
- [x] 2.2 Implement the KDOP issue-list request to `/gateway/issue/issue/issue/searchIssue` with `issueType` filter `42,2`.
- [x] 2.3 Implement complete pagination for the KDOP issue-list response using `hasNextPage`, `pages`, `pageNum`, `total`, `pageSize`, and list length as available.
- [x] 2.4 Implement issue-detail lookup for stories and development tasks, including `description`, `description_`, `upgradeCont`, and `custom_73` field priority.
- [x] 2.5 Implement the KDOP commit-list request to `/gateway/code/code/code/commit/issue/listByIssueId` for each collected issue.
- [x] 2.6 Implement complete pagination for commit-list responses and preserve unresolved or empty commit results.

## 3. Story Aggregation

- [x] 3.1 Model KDOP issue type `2` as story and issue type `42` as development task.
- [x] 3.2 Group development tasks under parent stories by `parentId`, creating a placeholder parent group and attempting parent detail lookup if a parent story is missing from the version list.
- [x] 3.3 Collect commits attached directly to stories and commits attached to child development tasks.
- [x] 3.4 De-duplicate commits by repository ID and resolved hash while preserving all source issue references.
- [x] 3.5 Ignore `linkIssue` relationships for commit discovery.

## 4. Repository And Commit Analysis

- [x] 4.1 Map repository ID `162364` to `./macbs-base` and repository ID `162363` to `./macbs-service` relative to the current workspace.
- [x] 4.2 Mark commits from all other repository IDs, including `163321`, as outside review scope without deep analysis.
- [x] 4.3 Resolve commits with `revision` first and `commitId` second.
- [x] 4.4 Run `git fetch` in the target repository when a commit is missing locally, then retry resolution.
- [x] 4.5 Extract changed files, key hunks, complete diffs, and surrounding context for each resolved commit.
- [x] 4.6 Summarize binary, generated, or oversized file changes instead of embedding unreadable full diffs.

## 5. MACBS Review Logic

- [x] 5.1 Apply default end-of-day MACBS review rules when issue metadata and paths do not indicate day-clearing scope.
- [x] 5.2 Apply day-clearing review rules when title, module, metadata, or changed paths indicate day-clearing scope.
- [x] 5.3 Review `macbs-base` changes for function entry consistency, seven-stage clearing flow, CacheManager/Memdb usage, Clear/Write separation, comments, and business magic values.
- [x] 5.4 Review `macbs-service` changes for script placement, `full` versus `patch`, `1.table` versus `2.data`, Gauss/default database expectations, day/end clearing path separation, flow configuration, and customer customization.
- [x] 5.5 Check PDMA synchronization expectations for DDL changes and flag missing evidence as `待确认`.

## 6. HTML Report

- [x] 6.1 Generate an HTML report grouped by story with story metadata, demand description, upgrade content, child tasks, linked commits, and repository-scope status.
- [x] 6.2 Sanitize KDOP HTML descriptions by removing unsafe tags, event handlers, scripts, iframes, and unsafe attributes while preserving ordinary links.
- [x] 6.3 Render local file links to changed files and line targets where possible, with explicit handling for deletion-only hunks.
- [x] 6.4 Render key hunks by default and complete diffs inside collapsible sections.
- [x] 6.5 Render code review findings with severities `阻断`, `高`, `中`, `低`, and `待确认`.
- [x] 6.6 Include a top-level summary of unresolved commits, out-of-scope repositories, missing requirement content, and stories with no findings.

## 7. Validation

- [x] 7.1 Validate the skill folder with the skill creator validation script.
- [x] 7.2 Test KDOP parsing and pagination logic against saved redacted response samples.
- [x] 7.3 Test commit resolution behavior for local hit, fetch-then-hit, and unresolved commit cases.
- [x] 7.4 Test HTML generation with at least one story containing a direct commit, one story containing a development-task commit, and one out-of-scope repository commit.
- [x] 7.5 Review generated `SKILL.md` for concision and ensure detailed API and report behavior lives in scripts or references rather than excessive inline prose.
