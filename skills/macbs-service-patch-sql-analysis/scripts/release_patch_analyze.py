import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(".").resolve()
ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
OUT = ANALYSIS_ROOT / "output/json"
PATCH = ROOT / "database/script/patch"
OFFICIAL_BRANCHES = [
    "release/FS-CBS-1.7.0.0",
    "release/FS-CBS-1.7.1.0",
    "release/FS-CBS-1.7.2.0",
    "release/FS-CBS-1.7.2.1",
    "release/FS-CBS-1.7.3.0",
    "release/FS-CBS-1.7.3.1",
    "release/FS-CBS-1.7.4.0",
    "release/FS-CBS-1.7.4.1",
    "release/FS-CBS-1.7.5.0",
    "release/FS-CBS-1.7.5.1",
    "release/FS-CBS-1.7.6.0",
]
BRANCHES = [
    *OFFICIAL_BRANCHES,
    "release/FS-CBS-1.7.6.0-upd001",
]
STABLE_CHANGE_IDS = False
STABLE_SQL_HASH_LENGTH = 16
EXPECTED = {
    BRANCHES[0]: ["common", "gauss", "goldendb", "oceanbase", "东方财富", "中信建投", "中信建投poc", "中金财富", "华兴证券", "国信证券", "国投证券", "申万宏源poc", "金证股份"],
    BRANCHES[1]: ["gauss", "oceanbase", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券"],
    BRANCHES[2]: ["gauss", "oceanbase", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "国投证券poc", "日间清算适配", "银河证券"],
    BRANCHES[3]: ["gauss", "东方财富", "中金财富", "国投证券", "日间清算适配", "银河证券"],
    BRANCHES[4]: ["gauss", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "广发证券", "日间清算适配", "银河证券"],
    BRANCHES[5]: ["gauss", "东方财富", "中信建投", "中金财富", "国信证券", "国投证券", "广发证券", "银河证券"],
    BRANCHES[6]: ["gauss", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "广发证券", "日间清算适配", "银河证券"],
    BRANCHES[7]: ["gauss", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "广发证券", "银河证券"],
    BRANCHES[8]: ["gauss", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "广发证券", "日间清算适配", "银河证券"],
    BRANCHES[9]: ["gauss", "oceanbase", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "广发证券", "日间清算适配", "银河证券"],
    BRANCHES[10]: ["gauss", "oceanbase", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "广发证券", "日间清算适配", "金证股份", "银河证券"],
    BRANCHES[11]: ["gauss", "oceanbase", "东方财富", "中信建投", "中金财富", "华兴证券", "国信证券", "国投证券", "广发证券", "日间清算适配", "金证股份", "银河证券"],
}
EXPECTED["release/FS-CBS-1.7.6.0-upd002"] = EXPECTED["release/FS-CBS-1.7.6.0"]
TARGETS = ["comm_busidefine", "comm_subjectdefine", "comm_bookkeepingrule", "sys_param_define", "comm_busidefine_refrule"]
IDENT = r'[A-Za-z_][\w$]*|"[^"]+"|`[^`]+`'


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze release patch SQL changes.")
    parser.add_argument("repo", nargs="?", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--branch", action="append", dest="branches", help="Analyze only the specified branch; repeat for multiple branches")
    parser.add_argument("--output-json-dir", help="Analysis JSON output directory")
    parser.add_argument("--stable-change-ids", action="store_true", help="Use directory/file/short-SQL-SHA256 change IDs")
    return parser.parse_args()


def run(*args):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, encoding="utf-8", errors="replace", capture_output=True).stdout.strip()


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_sql(path):
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            return raw.decode(encoding), encoding, hashlib.sha256(raw).hexdigest()
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace"), "utf-8-replace", hashlib.sha256(raw).hexdigest()


def stable_change_id(path, raw_sql):
    normalized_sql = raw_sql.replace("\r\n", "\n").replace("\r", "\n")
    sql_sha256 = hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest()[:STABLE_SQL_HASH_LENGTH]
    directory = path.parent.relative_to(PATCH).as_posix()
    return f"{directory}/{path.name}/{sql_sha256}"


def line_at(text, pos):
    return text.count("\n", 0, pos) + 1


def split_sql(text):
    chunks, comments = [], []
    start = 0
    i = 0
    state = "normal"
    dollar = None
    while i < len(text):
        if state == "normal":
            if text.startswith("--", i):
                j = text.find("\n", i)
                j = len(text) if j < 0 else j
                comments.append((i, j, "line"))
                i = j
                continue
            if text.startswith("/*", i):
                j = text.find("*/", i + 2)
                j = len(text) - 2 if j < 0 else j
                comments.append((i, j + 2, "block"))
                i = j + 2
                continue
            if text[i] == "'": state = "single"
            elif text[i] == '"': state = "double"
            elif text[i] == "`": state = "backtick"
            elif text[i] == "$":
                m = re.match(r"\$[A-Za-z_0-9]*\$", text[i:])
                if m:
                    dollar = m.group(0); state = "dollar"; i += len(dollar) - 1
            elif text[i] == ";":
                chunks.append((start, i + 1)); start = i + 1
        elif state == "single":
            if text[i] == "'":
                if i + 1 < len(text) and text[i + 1] == "'": i += 1
                else: state = "normal"
            elif text[i] == "\\": i += 1
        elif state == "double":
            if text[i] == '"':
                if i + 1 < len(text) and text[i + 1] == '"': i += 1
                else: state = "normal"
        elif state == "backtick" and text[i] == "`": state = "normal"
        elif state == "dollar" and text.startswith(dollar, i):
            i += len(dollar) - 1; state = "normal"; dollar = None
        i += 1
    if text[start:].strip(): chunks.append((start, len(text)))
    return chunks, comments


def comment_obj(text, a, b, kind, association):
    raw = text[a:b]
    body = raw[2:-2] if kind == "block" else raw[2:]
    return {"kind": kind, "line_start": line_at(text, a), "line_end": line_at(text, max(a, b - 1)), "raw": raw, "text": body.strip(), "association": association}


def clean_ident(value):
    return value.strip('`"').split(".")[-1].strip('`"').lower()


def table_from(sql, keyword):
    m = re.search(keyword + rf"\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?((?:{IDENT})(?:\s*\.\s*(?:{IDENT}))?)", sql, re.I | re.S)
    return clean_ident(m.group(1).replace(" ", "")) if m else None


def ddl_info(sql):
    s = re.sub(r"(?:--[^\n]*|/\*.*?\*/)", " ", sql, flags=re.S).strip()
    u = s.upper()
    operation, obj = "unknown_ddl", "unknown"
    table = column = constraint = index = None
    if re.search(r"\bCREATE\s+TABLE\b", u): operation, obj, table = "create_table", "table", table_from(s, r"CREATE\s+TABLE")
    elif re.search(r"\bDROP\s+TABLE\b", u): operation, obj, table = "drop_table", "table", table_from(s, r"DROP\s+TABLE")
    elif re.search(r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b", u):
        operation, obj = "create_index", "index"
        m = re.search(rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?({IDENT})\s+ON\s+((?:{IDENT})(?:\s*\.\s*(?:{IDENT}))?)", s, re.I)
        if m: index, table = clean_ident(m.group(1)), clean_ident(m.group(2).replace(" ", ""))
    elif re.search(r"\bDROP\s+INDEX\b", u): operation, obj = "drop_index", "index"
    elif re.search(r"\bALTER\s+TABLE\b", u):
        table = table_from(s, r"ALTER\s+TABLE")
        alter = re.search(rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?((?:{IDENT})(?:\s*\.\s*(?:{IDENT}))?)\s+(.*)", s, re.I | re.S)
        action_sql = alter.group(2) if alter else s
        action_upper = action_sql.upper()
        tests = [(r"\bADD\s+CONSTRAINT\b", "add_constraint", "constraint"), (r"\bDROP\s+CONSTRAINT\b", "drop_constraint", "constraint"), (r"\bADD\s+(?:COLUMN\s+)?", "add_column", "column"), (r"\bDROP\s+(?:COLUMN\s+)?", "drop_column", "column"), (r"\bRENAME\s+COLUMN\b", "rename_column", "column"), (r"\bALTER\s+COLUMN\b|\bMODIFY\b|\bCHANGE\b", "alter_column", "column"), (r"\bRENAME\s+TO\b", "rename_table", "table")]
        for pat, op, typ in tests:
            if re.search(pat, action_upper): operation, obj = op, typ; break
        m = re.search(rf"(?:ADD|DROP|ALTER|MODIFY|CHANGE|RENAME)\s+(?:COLUMN\s+)?(?:IF\s+(?:NOT\s+)?EXISTS\s+)?({IDENT})", action_sql, re.I)
        if m and obj == "column": column = clean_ident(m.group(1))
    elif re.search(r"\bCOMMENT\s+ON\s+TABLE\b", u): operation, obj, table = "comment_table", "table", table_from(s, r"COMMENT\s+ON\s+TABLE")
    elif re.search(r"\bCOMMENT\s+ON\s+COLUMN\b", u):
        operation, obj = "comment_column", "column"
        m = re.search(rf"COMMENT\s+ON\s+COLUMN\s+((?:{IDENT})\s*\.\s*({IDENT}))", s, re.I)
        if m: table, column = clean_ident(m.group(1).rsplit(".", 1)[0]), clean_ident(m.group(2))
    return operation, obj, table, column, constraint, index


def renamed_column_after(sql):
    statement = re.sub(r"(?:--[^\n]*|/\*.*?\*/)", " ", sql, flags=re.S)
    match = re.search(rf"\bRENAME\s+COLUMN\s+(?:{IDENT})\s+TO\s+({IDENT})", statement, re.I | re.S)
    return clean_ident(match.group(1)) if match else None


def column_type_from_tail(tail):
    if not tail:
        return None
    depth = 0
    state = "normal"
    index = 0
    while index < len(tail):
        char = tail[index]
        if state == "normal":
            if char == "'": state = "single"
            elif char == '"': state = "double"
            elif char == "`": state = "backtick"
            elif char == "(": depth += 1
            elif char == ")": depth = max(0, depth - 1)
            elif depth == 0 and char in ",;": break
            elif depth == 0:
                suffix = tail[index:]
                if re.match(r"\s+(?:USING|DEFAULT|NOT\s+NULL|NULL|COMMENT|COLLATE|FIRST|AFTER)\b", suffix, re.I): break
        elif state == "single" and char == "'":
            if index + 1 < len(tail) and tail[index + 1] == "'": index += 1
            else: state = "normal"
        elif state == "double" and char == '"': state = "normal"
        elif state == "backtick" and char == "`": state = "normal"
        index += 1
    return tail[:index].strip() or None


def add_column_definition(sql):
    statement = re.sub(r"(?:--[^\n]*|/\*.*?\*/)", " ", sql, flags=re.S)
    match = re.search(rf"\bADD\s+(?:COLUMN\s+)?(?:IF\s+(?:NOT\s+)?EXISTS\s+)?(?:{IDENT})\s+(.+)", statement, re.I | re.S)
    return column_type_from_tail(match.group(1).strip()) if match else None


def alter_column_definition(sql):
    statement = re.sub(r"(?:--[^\n]*|/\*.*?\*/)", " ", sql, flags=re.S)
    patterns = [
        rf"\bMODIFY\s+(?:COLUMN\s+)?(?:{IDENT})\s+(.+)",
        rf"\bCHANGE\s+(?:COLUMN\s+)?(?:{IDENT})\s+(?:{IDENT})\s+(.+)",
        rf"\bALTER\s+COLUMN\s+(?:{IDENT})\s+(?:SET\s+DATA\s+TYPE|TYPE)\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, statement, re.I | re.S)
        if match:
            return column_type_from_tail(match.group(1).strip())
    return None


def ddl_comment_text(sql):
    match = re.search(r"\bCOMMENT\s+ON\s+(?:TABLE|COLUMN)\s+.+?\s+IS\s+'((?:''|[^'])*)'", sql, re.I | re.S)
    return match.group(1).replace("''", "'") if match else None


def dml_targets(sql):
    stripped = re.sub(r"(?:--[^\n]*|/\*.*?\*/|'(?:''|[^'])*')", " ", sql, flags=re.S)
    found = []
    patterns = {
        "insert": r"\bINSERT\s+INTO\s+", "update": r"\bUPDATE\s+", "delete": r"\bDELETE\s+FROM\s+",
        "merge": r"\bMERGE\s+INTO\s+", "replace": r"\bREPLACE\s+INTO\s+", "truncate": r"\bTRUNCATE\s+(?:TABLE\s+)?"
    }
    for op, prefix in patterns.items():
        for m in re.finditer(prefix + rf"((?:{IDENT})(?:\s*\.\s*(?:{IDENT}))?)", stripped, re.I):
            qualified = re.sub(r"\s+", "", m.group(1))
            target = clean_ident(qualified)
            if target in TARGETS and (op, target, qualified) not in found: found.append((op, target, qualified))
    return found


def classify(directory, category):
    rel = directory.relative_to(PATCH).as_posix(); p = rel.split("/"); db = None; scope = "unknown"; customer = None; warning = None; offset = 0
    if p and p[0].lower() in ("gauss", "oceanbase"): db = p[0].lower(); scope = "standard"; offset = 0
    elif len(p) > 1 and p[1].lower() in ("gauss", "oceanbase"): customer, db, scope, offset = p[0], p[1].lower(), "customer", 1
    else: warning = "Path does not match known standard/customer database layout"
    return {"relative_path": rel, "database": db, "scope": scope, "customer": customer, "system": p[offset + 1] if len(p) > offset + 1 else None, "module": p[offset + 2] if len(p) > offset + 2 else None, "category": category, "classification_warning": warning, "files": [], "scanned_files": 0, "matched_files": 0}


def analyze_file(path, category, counters):
    text, encoding, sha = read_sql(path); chunks, comment_ranges = split_sql(text)
    changes, attached = [], set()
    for a, b in chunks:
        raw = text[a:b]
        if not raw.strip(): continue
        matches = []
        if category == "table":
            if re.search(r"\b(?:CREATE|ALTER|DROP|RENAME|COMMENT)\b|\bDO\s+\$", raw, re.I): matches = [ddl_info(raw)]
        else: matches = dml_targets(raw)
        if not matches: continue
        statement_comments = []
        for ci, (ca, cb, kind) in enumerate(comment_ranges):
            if ca >= a and cb <= b:
                statement_comments.append(comment_obj(text, ca, cb, kind, "inline_statement")); attached.add(ci)
        for match in matches:
            if category == "table":
                op, obj, table, column, constraint, index = match; counters["table"] += 1
                definition_after = alter_column_definition(raw) if op == "alter_column" else add_column_definition(raw) if op == "add_column" else None
                column_after = renamed_column_after(raw) if op == "rename_column" else None
                comment_text = ddl_comment_text(raw)
                description = "；".join(value for value in (definition_after, comment_text) if value)
                change = {"change_id": f"table-{counters['table']:06d}", "change_category": "table", "operation": op, "object_type": obj, "table_name": table, "column_name": column, "column_name_after": column_after, "constraint_name": constraint, "index_name": index, "definition_before": None, "definition_after": definition_after, "description": description or None}
                if op.startswith("comment_"):
                    change["description"] = comment_text
            else:
                op, target, qualified = match; counters["data"] += 1
                affected = []
                if op == "update":
                    m = re.search(r"\bSET\s+(.*?)(?:\bWHERE\b|$)", raw, re.I | re.S)
                    if m: affected = [clean_ident(x) for x in re.findall(rf"({IDENT})\s*=", m.group(1))]
                change = {"change_id": f"data-{counters['data']:06d}", "change_category": "data", "operation": op, "target_table": target, "qualified_target_table": qualified, "key_conditions": [], "affected_columns": affected, "insert_columns": [], "insert_values": []}
            change.update({"line_start": line_at(text, a), "line_end": line_at(text, max(a, b - 1)), "raw_sql": raw, "comments": statement_comments, "parse_warnings": []})
            if STABLE_CHANGE_IDS:
                change["change_id"] = stable_change_id(path, raw)
            changes.append(change)
    if not changes: return None
    file_comments = [comment_obj(text, a, b, kind, "file") for i, (a, b, kind) in enumerate(comment_ranges) if i not in attached]
    return {"path": path.relative_to(ROOT).as_posix(), "encoding": encoding, "content_sha256": sha, "file_comments": file_comments, "changes": changes}


def analyze_branch(branch):
    ref = "origin/" + branch
    run("git", "switch", "--detach", ref)
    commit = run("git", "rev-parse", "HEAD")
    status = run("git", "status", "--short", "--branch")
    actual = sorted(p.name for p in PATCH.iterdir() if p.is_dir()) if PATCH.exists() else []
    # Explicit extra branches may not have a maintained directory baseline.
    expected = EXPECTED.get(branch, [])
    counters = {"table": 0, "data": 0}; directories = []; warnings = []
    if not PATCH.exists(): warnings.append("Patch root does not exist")
    candidates = set()
    if PATCH.exists():
        for path in PATCH.rglob("*.sql"):
            parts = path.parts
            indexes = [i for i, value in enumerate(parts) if value in ("1.table", "2.data")]
            if indexes: candidates.add(Path(*parts[:indexes[-1] + 1]))
    candidates = sorted(candidates, key=lambda x: x.as_posix())
    scanned = 0
    for directory in candidates:
        category = "table" if "1.table" in directory.parts else "data"
        obj = classify(directory, category)
        files = sorted(directory.rglob("*.sql"), key=lambda x: x.as_posix())
        obj["scanned_files"] = len(files); scanned += len(files)
        for path in files:
            result = analyze_file(path, category, counters)
            if result: obj["files"].append(result)
        obj["matched_files"] = len(obj["files"])
        directories.append(obj)
        if obj["classification_warning"]: warnings.append(f"{obj['relative_path']}: {obj['classification_warning']}")
    by_table = {t: 0 for t in TARGETS}; by_dir = {}
    for d in directories:
        count = sum(len(f["changes"]) for f in d["files"]); by_dir[d["relative_path"]] = count
        for f in d["files"]:
            for c in f["changes"]:
                if c["change_category"] == "data": by_table[c["target_table"]] += 1
    result = {
        "schema_version": "1.0", "generated_at": now(), "branch": {"name": branch, "ref": ref, "commit": commit, "checkout_status": status}, "patch_root": "database/script/patch",
        "scan_policy": {"cross_branch_diff": False, "cross_branch_deduplication": False, "table_path_segment": "1.table", "data_path_segment": "2.data", "target_data_tables": TARGETS, "change_id_strategy": f"directory/file/sql_sha256_{STABLE_SQL_HASH_LENGTH}" if STABLE_CHANGE_IDS else "sequential_by_category"},
        "directory_validation": {"expected_top_level": expected, "actual_top_level": actual, "missing_expected": sorted(set(expected) - set(actual)), "unexpected_actual": sorted(set(actual) - set(expected))},
        "directories": directories,
        "summary": {"table_directory_count": sum(d["category"] == "table" for d in directories), "data_directory_count": sum(d["category"] == "data" for d in directories), "scanned_sql_file_count": scanned, "table_change_count": counters["table"], "data_change_count": counters["data"], "data_change_count_by_table": by_table, "change_count_by_directory": by_dir, "warning_count": len(warnings)},
        "warnings": warnings,
    }
    change_ids = [c["change_id"] for d in directories for f in d["files"] for c in f["changes"]]
    if len(change_ids) != len(set(change_ids)):
        raise ValueError(f"Duplicate change_id generated for {branch}")
    folder = OUT / branch.replace("/", "_"); folder.mkdir(parents=True, exist_ok=True)
    target = folder / "analysis.json"; target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(target.read_text(encoding="utf-8"))
    return result, target.relative_to(OUT).as_posix()


def main():
    global ROOT, OUT, PATCH, STABLE_CHANGE_IDS
    args = parse_args()
    ROOT = Path(args.repo).resolve()
    OUT = Path(args.output_json_dir).resolve() if args.output_json_dir else ANALYSIS_ROOT / "output/json"
    PATCH = ROOT / "database/script/patch"
    STABLE_CHANGE_IDS = args.stable_change_ids
    branches = args.branches or BRANCHES
    requested_extra_branches = [branch for branch in branches if branch not in OFFICIAL_BRANCHES]
    OUT.mkdir(parents=True, exist_ok=True)
    original_branch = run("git", "branch", "--show-current") or None
    original_commit = run("git", "rev-parse", "HEAD")
    detached = original_branch is None
    records = []; restored = False
    try:
        for branch in branches:
            try:
                result, path = analyze_branch(branch)
                s = result["summary"]
                records.append({"name": branch, "ref": "origin/" + branch, "commit": result["branch"]["commit"], "result_file": path, "table_change_count": s["table_change_count"], "data_change_count": s["data_change_count"], "warning_count": s["warning_count"], "status": "completed"})
                print(f"{branch}: table={s['table_change_count']} data={s['data_change_count']} warnings={s['warning_count']}", flush=True)
            except Exception as exc:
                records.append({"name": branch, "ref": "origin/" + branch, "status": "failed", "error": str(exc)})
                raise
    finally:
        try:
            if detached: run("git", "switch", "--detach", original_commit)
            else: run("git", "switch", original_branch)
            restored = run("git", "rev-parse", "HEAD") == original_commit
        finally:
            totals = {"completed_branch_count": sum(r["status"] == "completed" for r in records), "failed_branch_count": sum(r["status"] == "failed" for r in records), "table_change_count": sum(r.get("table_change_count", 0) for r in records), "data_change_count": sum(r.get("data_change_count", 0) for r in records), "warning_count": sum(r.get("warning_count", 0) for r in records)}
            index = {"schema_version": "1.0", "generated_at": now(), "branch_order": branches, "requested_extra_branches": requested_extra_branches, "branches": records, "totals": totals, "original_checkout": {"branch": original_branch, "commit": original_commit, "detached": detached, "restored": restored}, "change_id_strategy": f"directory/file/sql_sha256_{STABLE_SQL_HASH_LENGTH}" if STABLE_CHANGE_IDS else "sequential_by_category"}
            target = OUT / "index.json"; target.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"); json.loads(target.read_text(encoding="utf-8"))
    if not restored: raise RuntimeError("Original checkout was not restored")


if __name__ == "__main__": main()
