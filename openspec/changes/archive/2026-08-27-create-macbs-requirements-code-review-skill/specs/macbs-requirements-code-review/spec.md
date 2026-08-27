## ADDED Requirements

### Requirement: Runtime KDOP Inputs
The skill SHALL require a current KDOP cookie, `projectId`, and `versionId` before collecting KDOP data, and MUST treat the cookie as sensitive runtime input that is not persisted, printed, or included in generated reports.

#### Scenario: Missing KDOP parameter
- **WHEN** the user invokes the skill without a cookie, `projectId`, or `versionId`
- **THEN** the skill stops before making KDOP requests and asks for the missing required input

#### Scenario: Cookie redaction
- **WHEN** the skill logs diagnostics, produces an HTML report, or shows request metadata
- **THEN** the full KDOP cookie is omitted or redacted

### Requirement: Complete KDOP Issue Collection
The skill SHALL call the KDOP issue search API for the specified `projectId` and `versionId` using the confirmed `issueType` filter for stories and development tasks, and MUST fully paginate the response before analysis.

#### Scenario: Multi-page issue list
- **WHEN** the KDOP issue search response indicates additional pages
- **THEN** the skill continues requesting pages until all issues are collected

#### Scenario: Story and development task filter
- **WHEN** the skill requests the KDOP version issue list
- **THEN** the request includes an advanced query for issue types `42,2`

### Requirement: Story-Grouped Issue Model
The skill SHALL group report output by story issue, place development tasks under their parent story using `parentId`, and include commits linked either to the story itself or to its child development tasks.

#### Scenario: Commit linked to story
- **WHEN** a KDOP story has directly linked commits
- **THEN** the story report section includes those commits in addition to child task commits

#### Scenario: Commit linked to development task
- **WHEN** a KDOP development task has linked commits and its `parentId` points to a story
- **THEN** the parent story report section includes the development task and its commits

#### Scenario: Duplicate commit linkage
- **WHEN** the same commit is linked from multiple issues in the same story group
- **THEN** the skill analyzes the commit once and records all source issues that referenced it

### Requirement: KDOP Requirement Detail Collection
The skill SHALL request issue detail data for stories and development tasks, and MUST include story demand description and upgrade content in the report using the configured field priority.

#### Scenario: Demand description exists as HTML
- **WHEN** an issue detail response contains `description`
- **THEN** the report uses sanitized `description` as the demand description

#### Scenario: Upgrade content exists
- **WHEN** an issue detail response contains `upgradeCont`
- **THEN** the report includes `upgradeCont` as the upgrade content

#### Scenario: Primary detail field missing
- **WHEN** `description` or `upgradeCont` is missing
- **THEN** the skill falls back to the configured alternate fields and marks unavailable content as missing

### Requirement: Complete KDOP Commit Collection
The skill SHALL call the KDOP commit-list API for every collected story and development task issue, reuse the supplied cookie, and MUST fully paginate commit responses.

#### Scenario: Multi-page commit list
- **WHEN** the KDOP commit-list response indicates additional pages
- **THEN** the skill continues requesting pages until all linked commits are collected

#### Scenario: No linked commits
- **WHEN** an issue has no linked commits
- **THEN** the report records that no KDOP-linked commit was found for that issue

### Requirement: Repository Scope
The skill SHALL deeply analyze only KDOP repository ID `162364` as `./macbs-base` and repository ID `162363` as `./macbs-service`, relative to the current workspace.

#### Scenario: Supported repository commit
- **WHEN** a linked commit belongs to repository ID `162364` or `162363`
- **THEN** the skill resolves and analyzes the commit in the corresponding local repository

#### Scenario: Unsupported repository commit
- **WHEN** a linked commit belongs to any other repository ID
- **THEN** the report lists the commit as outside the review scope and does not perform code review for it

### Requirement: Commit Resolution
The skill SHALL resolve local Git commits using KDOP `revision` first and `commitId` second, and MUST run `git fetch` in the target repository when the commit is not initially available locally.

#### Scenario: Revision resolves locally
- **WHEN** `git show <revision>` succeeds in the target repository
- **THEN** the skill uses `revision` as the analyzed commit

#### Scenario: Commit missing before fetch
- **WHEN** neither `revision` nor `commitId` resolves locally before fetching
- **THEN** the skill runs `git fetch` in the target repository and retries resolution

#### Scenario: Commit remains unresolved
- **WHEN** the commit cannot be resolved after fetch and fallback attempts
- **THEN** the report marks the commit unresolved and preserves the KDOP commit metadata

### Requirement: Commit-Level Code Analysis
The skill SHALL analyze each resolved KDOP-linked commit individually, including changed files, key diff hunks, full diff content, surrounding code context when needed, and a plain-language explanation of the business logic change.

#### Scenario: Resolved commit with source changes
- **WHEN** a linked commit resolves in `macbs-base` or `macbs-service`
- **THEN** the report includes changed file paths, local file links, key hunks, collapsible full diffs, and change-logic explanations

#### Scenario: Deletion-only hunk
- **WHEN** a diff hunk deletes code that no longer exists in the working tree
- **THEN** the report links to the file or commit diff context and explains that no post-change line target exists

#### Scenario: Binary or oversized file
- **WHEN** a commit changes binary files or files exceeding the configured diff size limit
- **THEN** the report summarizes the file change instead of embedding an unreadable full diff

### Requirement: MACBS-Specific Review Criteria
The skill SHALL review `macbs-base` and `macbs-service` changes against MACBS project rules, including clearing scope, seven-stage processing, function-entry configuration, cache/write layering, database script placement, PDMA synchronization, customer customization, business comments, and magic-value constraints.

#### Scenario: End-of-day clearing change
- **WHEN** the issue metadata and changed paths do not indicate day-clearing scope
- **THEN** the skill applies the default end-of-day clearing review rules

#### Scenario: Day-clearing change
- **WHEN** the issue title, module, metadata, or changed paths indicate day-clearing scope
- **THEN** the skill applies day-clearing review rules and checks day-clearing database/model locations where relevant

#### Scenario: Database DDL change
- **WHEN** a `macbs-service` change modifies database table structure, indexes, partitions, or sequences
- **THEN** the review checks whether the corresponding PDMA model synchronization expectation is satisfied or flags it for confirmation

### Requirement: HTML Review Report
The skill SHALL generate an HTML report grouped by story with requirement metadata, child development tasks, linked commits, repository scope, code changes, review findings, unresolved items, and an overall summary.

#### Scenario: Story report section
- **WHEN** a story is included in the KDOP version list or discovered as a parent of a development task
- **THEN** the report includes story title, issue type, developer, labels, broker name, status, tester, demand description, upgrade content, child tasks, and linked commits

#### Scenario: Review finding severity
- **WHEN** the skill identifies a review issue or uncertainty
- **THEN** the report assigns a severity of `阻断`, `高`, `中`, `低`, or `待确认`

#### Scenario: No findings for story
- **WHEN** the skill finds no issues for a story after analysis
- **THEN** the report states the checked scope rather than only marking the story as passed
