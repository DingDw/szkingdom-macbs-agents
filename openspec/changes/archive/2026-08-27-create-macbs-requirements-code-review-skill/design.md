## Context

The requested skill will automate a recurring MACBS review workflow: collect all KDOP stories and development tasks for a specified version, resolve their linked code commits, analyze the relevant local repository changes, and produce a story-grouped HTML review report. The current workspace contains `macbs-base` and `macbs-service` as child directories. KDOP data is available through internal HTTP form APIs on `jzdevops.szkingdom.com:8080`, with a user-supplied cookie, `projectId`, and `versionId` required for every run.

The skill must follow the MACBS repository rules already defined for this workspace. End-of-day clearing remains the default analysis perspective, but day-clearing requirements must use the day-clearing database and module rules when the KDOP metadata, story title, module, or changed paths indicate day-clearing scope.

## Goals / Non-Goals

**Goals:**

- Create a concise, discoverable Codex skill named `macbs-requirements-code-review`.
- Preserve the confirmed KDOP API workflow and required runtime inputs.
- Aggregate output by story, with child development tasks nested under each story.
- Analyze code attached directly to a story and code attached to its development tasks.
- Deeply review only `macbs-base` and `macbs-service`, while recording out-of-scope repositories.
- Generate an HTML report with navigable local file links, key diff hunks, collapsible full diffs, change-logic explanations, and review findings.
- Treat KDOP cookies as sensitive values that are never persisted or printed.

**Non-Goals:**

- Do not review `macbs-web` or other repositories beyond recording their linked commits as out of scope.
- Do not follow `linkIssue` relationships when collecting commits.
- Do not execute business builds or database scripts as part of the default review.
- Do not create a production service; this is a Codex skill with optional helper scripts.

## Decisions

1. **Use a skill with helper scripts rather than a prose-only skill.**

   The KDOP requests, pagination, git commit resolution, diff extraction, and HTML generation are deterministic and easy to regress if reimplemented ad hoc. The skill should keep `SKILL.md` focused on workflow and include scripts for KDOP collection and report assembly. Alternative considered: put all logic in `SKILL.md`; rejected because it would be too verbose and less reliable.

2. **Require `cookie`, `projectId`, and `versionId` at runtime.**

   These values vary per request and include sensitive authentication material. The skill should accept them from explicit user input or environment variables, redact the cookie from diagnostics, and stop when required inputs are missing. Alternative considered: embedding an example cookie; rejected for security reasons.

3. **Fully paginate every KDOP list endpoint.**

   Both the issue-list and commit-list APIs are paginated. The implementation should continue until `hasNextPage` is false or until `pageNum/pages` and `total/pageSize/list.length` prove completion. Alternative considered: read only page 1 with `size=100`; rejected because large versions or heavily linked issues would silently lose data.

4. **Group by story and collect commits from both story and development-task issues.**

   KDOP issue type `2` is story and `42` is development task. Development tasks belong under stories through `parentId`, but commits may be attached either to the story or the development task. The report should group tasks under their parent story and de-duplicate commits by repository plus resolved hash while preserving all source issues. Alternative considered: report every issue independently; rejected because it fragments review context.

5. **Deeply analyze only `macbs-base` and `macbs-service`.**

   Repository IDs are fixed for this workflow: `162364` maps to `./macbs-base`, and `162363` maps to `./macbs-service`. Other repositories, including `163321` for `macbs-web`, should be listed but not code-reviewed. Alternative considered: infer paths from `repoRootPath`; rejected because the user explicitly scoped review to these two local repositories.

6. **Resolve commits with `revision` first, then `commitId`, with automatic fetch allowed.**

   KDOP returns both fields. `revision` is the 40-character Git SHA candidate and should be tried first. If the commit is missing locally, the script may run `git fetch` in the matching repository and retry before falling back to `commitId`. Alternative considered: only use `commitId`; rejected because it may be KDOP-specific or not a local Git hash.

7. **Show key hunks by default and complete diffs in collapsible sections.**

   The report must be readable for large versions but still allow inspection of exact changes. Key hunks should prioritize business logic, SQL/configuration, public interfaces, and changed control flow. Full diffs should be collapsible, with binary and oversized files summarized. Alternative considered: full diff only; rejected because it creates noisy reports.

8. **Use safe HTML rendering for KDOP descriptions.**

   KDOP `description` is HTML, while `description_`, `upgradeCont`, and `custom_73` may contain text variants. The report should prefer sanitized `description` for demand description, fall back to `description_`, prefer `upgradeCont` for upgrade content, and fall back to `custom_73`. Scripts, inline event handlers, iframes, and unsafe tags must be removed; ordinary links may remain.

9. **Apply MACBS review rules according to detected scope.**

   Default review emphasizes end-of-day clearing. If the story title, module, metadata, or changed paths indicate day-clearing, the skill must analyze with day-clearing rules, including `fs_cbs_day` database scripts and the day-clearing model path. For database DDL, the review should check PDMA synchronization expectations.

## Risks / Trade-offs

- **KDOP API response shape changes** -> Keep the KDOP parsing script defensive, fail with clear field-level diagnostics, and include raw response samples only when redacted.
- **Local commits are unavailable after fetch** -> Continue report generation, mark the commit as unresolved, and include repository, branch, `revision`, `commitId`, and source issue metadata.
- **Story parent is missing from the version list** -> Create a placeholder story group from the child task parent ID and attempt detail lookup by ID; mark parent metadata as incomplete if lookup fails.
- **Large diffs reduce report usability** -> Summarize generated, binary, or oversized files and keep full diffs behind collapsible sections.
- **Automated review misses business intent** -> Include a `待确认` severity and explicitly list assumptions, missing requirement content, unresolved commits, and cases where code behavior cannot be proven from the diff.
- **Cookie leakage** -> Never persist the cookie, never echo it, and redact authentication headers from all diagnostics.
