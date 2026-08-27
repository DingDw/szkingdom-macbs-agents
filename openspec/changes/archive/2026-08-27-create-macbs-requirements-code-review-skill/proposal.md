## Why

MACBS version requirements currently require manual cross-checking between KDOP stories, linked development tasks, commits, local repository diffs, and MACBS-specific review rules. Creating a dedicated Codex skill will make this review repeatable, preserve the confirmed KDOP API workflow, and produce a navigable HTML report for version-level requirement code analysis.

## What Changes

- Add a new `macbs-requirements-code-review` Codex skill for reviewing code changes associated with a specified MACBS KDOP version.
- Define a KDOP collection workflow that requires the user to provide a current cookie, `projectId`, and `versionId`, then fully paginates story/development-task and commit-list APIs.
- Aggregate report content by story, including child development tasks and commits attached either to the story or to its development tasks.
- Limit deep code analysis to `macbs-base` and `macbs-service` repositories under the current workspace; record other repositories as out of review scope.
- Analyze each KDOP-linked commit individually, using `revision` first and `commitId` as fallback, with automatic `git fetch` allowed when commits are missing locally.
- Generate an HTML report containing requirement details, upgrade content, task metadata, linked commits, local file links, key diff hunks, collapsible full diffs, change-logic explanations, and code review findings.
- Apply MACBS-specific review criteria for end-of-day and day-clearing changes, including repository layout, database script placement, cache/write layering, flow configuration, customer customization, comments, magic values, and PDMA/DDL synchronization where relevant.

## Capabilities

### New Capabilities
- `macbs-requirements-code-review`: Review KDOP version stories and development tasks for MACBS by collecting linked commits, analyzing local `macbs-base` and `macbs-service` changes, and producing a story-grouped HTML code review report.

### Modified Capabilities

## Impact

- Adds a new personal Codex skill under the user's skill directory when implemented.
- May include reusable scripts for KDOP API calls, git commit/diff collection, and HTML report generation.
- Uses network access to `jzdevops.szkingdom.com:8080` and local git operations, including `git fetch`.
- Reads local repositories at `./macbs-base` and `./macbs-service` relative to the current workspace.
- Treats KDOP cookies as sensitive runtime input that must not be persisted or printed in reports, logs, or examples.
