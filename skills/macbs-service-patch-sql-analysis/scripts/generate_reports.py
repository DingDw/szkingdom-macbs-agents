import datetime as dt
import argparse
import json
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ANALYSIS_ROOT / "output"
OUTPUT_ROOT = DEFAULT_OUTPUT_ROOT
JSON_ROOT = OUTPUT_ROOT / "json"
HTML_PATH = OUTPUT_ROOT / "release-patch-change-analysis.html"
REPORT_JSON_PATH = OUTPUT_ROOT / "release-patch-change-analysis.json"
MIGRATION_ADJUSTMENTS_PATH = OUTPUT_ROOT / "release-patch-change-analysis-adjustments.json"
STATIC_HTML_PATH = OUTPUT_ROOT / "release-patch-change-analysis-static.html"
XLSX_PATH = OUTPUT_ROOT / "release-patch-change-analysis.xlsx"
ASSET_ROOT = OUTPUT_ROOT
REPORT_ASSETS = [
    "release-patch-change-analysis-server.js",
    "build-static.js",
    "start.bat",
    "build.bat",
    "README.md",
]
EXCEL_CELL_LIMIT = 32767
HTML_TEMPLATE_PATH = None


def parse_args():
    parser = argparse.ArgumentParser(description="Generate patch SQL reports from analysis JSON.")
    parser.add_argument("repo", nargs="?", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--html-template", help="Existing editable report HTML used as the output template")
    parser.add_argument("--migration-source", help="Explicit report JSON used as the migration-adjustment source; omitted means no adjustments are imported")
    parser.add_argument("--remap-migration-branch", action="append", default=[], help="Branch whose adjustments are matched by exact SQL content instead of change id")
    parser.add_argument("--analysis-json-dir", help="Analysis JSON directory containing index.json")
    parser.add_argument("--output-dir", help="Report output directory")
    return parser.parse_args()


def load_reports():
    index = json.loads((JSON_ROOT / "index.json").read_text(encoding="utf-8"))
    reports = []
    for branch in index["branches"]:
        if branch.get("status") != "completed":
            continue
        report = json.loads((JSON_ROOT / branch["result_file"]).read_text(encoding="utf-8"))
        reports.append(report)
    return index, reports


def comments_text(change):
    return "\n".join(item.get("raw", "") for item in change.get("comments", []))


def warnings_text(change):
    return "\n".join(change.get("parse_warnings", []))


IDENTIFIER = r'(?:"[^"]+"|`[^`]+`|[A-Za-z_][\w$]*)'
INSERT_DISPLAY_KEYS = {
    "comm_busidefine": ["busitype"],
    "comm_bookkeepingrule": ["templateid", "busitype", "sno"],
    "comm_subjectdefine": ["subjectcode"],
    "sys_param_define": ["sysid", "paramid"],
    "comm_busidefine_refrule": ["busitype", "reftype", "reftargetbusitype"],
}


def remove_sql_comments(sql):
    result = []
    index = 0
    state = "normal"
    while index < len(sql):
        char = sql[index]
        if state == "normal":
            if sql.startswith("--", index):
                end = sql.find("\n", index)
                if end < 0:
                    break
                result.append(" " * (end - index))
                index = end
                continue
            if sql.startswith("/*", index):
                end = sql.find("*/", index + 2)
                end = len(sql) - 2 if end < 0 else end
                comment = sql[index:end + 2]
                result.append("".join("\n" if value == "\n" else " " for value in comment))
                index = end + 2
                continue
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "`":
                state = "backtick"
        elif state == "single" and char == "'":
            if index + 1 < len(sql) and sql[index + 1] == "'":
                result.append(char)
                index += 1
                char = sql[index]
            else:
                state = "normal"
        elif state == "double" and char == '"':
            state = "normal"
        elif state == "backtick" and char == "`":
            state = "normal"
        result.append(char)
        index += 1
    return "".join(result)


def split_top_level(text):
    parts = []
    start = 0
    depth = 0
    state = "normal"
    index = 0
    while index < len(text):
        char = text[index]
        if state == "normal":
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "`":
                state = "backtick"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
        elif state == "single" and char == "'":
            if index + 1 < len(text) and text[index + 1] == "'":
                index += 1
            else:
                state = "normal"
        elif state == "double" and char == '"':
            state = "normal"
        elif state == "backtick" and char == "`":
            state = "normal"
        index += 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def clause_after_keyword(sql, keyword, end_keywords=()):
    match = re.search(rf"\b{re.escape(keyword)}\b", sql, re.I)
    if not match:
        return None
    start = match.end()
    depth = 0
    state = "normal"
    index = start
    while index < len(sql):
        char = sql[index]
        if state == "normal":
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "`":
                state = "backtick"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif depth == 0 and char == ";":
                return sql[start:index]
            elif depth == 0:
                for end_keyword in end_keywords:
                    end_match = re.match(rf"\b{re.escape(end_keyword)}\b", sql[index:], re.I)
                    if end_match:
                        return sql[start:index]
        elif state == "single" and char == "'":
            if index + 1 < len(sql) and sql[index + 1] == "'":
                index += 1
            else:
                state = "normal"
        elif state == "double" and char == '"':
            state = "normal"
        elif state == "backtick" and char == "`":
            state = "normal"
        index += 1
    return sql[start:]


def matching_parenthesis(text, start):
    depth = 0
    state = "normal"
    index = start
    while index < len(text):
        char = text[index]
        if state == "normal":
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "`":
                state = "backtick"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        elif state == "single" and char == "'":
            if index + 1 < len(text) and text[index + 1] == "'":
                index += 1
            else:
                state = "normal"
        elif state == "double" and char == '"':
            state = "normal"
        elif state == "backtick" and char == "`":
            state = "normal"
        index += 1
    return None


def clean_identifier(value):
    return value.strip().split(".")[-1].strip().strip('`"')


def renamed_column_after(change):
    if change.get("column_name_after"):
        return change["column_name_after"]
    if change.get("operation") != "rename_column":
        return None
    sql = remove_sql_comments(change.get("raw_sql", ""))
    match = re.search(rf"\bRENAME\s+COLUMN\s+(?:{IDENTIFIER})\s+TO\s+({IDENTIFIER})", sql, re.I | re.S)
    return clean_identifier(match.group(1)) if match else None


def clean_sql_value(value):
    value = value.strip().rstrip(";")
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def contains_chinese(value):
    return bool(re.search(r"[\u3400-\u9fff]", value or ""))


def where_pairs(sql):
    match = re.search(r"\bWHERE\b(.*?)(?:\bRETURNING\b|;|$)", sql, re.I | re.S)
    if not match:
        return []
    clause = match.group(1)
    condition = re.compile(
        rf"((?:{IDENTIFIER})(?:\s*\.\s*(?:{IDENTIFIER}))?)\s*"
        r"(NOT\s+LIKE|NOT\s+IN|IN|IS\s+NOT|IS|LIKE|<>|!=|>=|<=|=|>|<)\s*"
        r"(\((?:[^()']|'(?:''|[^'])*')*\)|'(?:''|[^'])*'|[^\s;)]+)",
        re.I | re.S,
    )
    result = []
    previous_end = 0
    for item in condition.finditer(clause):
        connectors = list(re.finditer(r"\b(AND|OR)\b", clause[previous_end:item.start()], re.I))
        connector = connectors[-1].group(1) if connectors else ""
        result.append((clean_identifier(item.group(1)), re.sub(r"\s+", " ", item.group(2).upper()), clean_sql_value(item.group(3)), connector))
        previous_end = item.end()
    return result


def where_presentation(sql, connectors_at_line_end=False):
    match = re.search(r"\bWHERE\b(.*?)(?:\bRETURNING\b|;|$)", sql, re.I | re.S)
    if not match:
        return [], "", []
    clause = match.group(1)
    fields = []
    descriptions = []
    chinese_pairs = []
    tuple_condition = re.search(
        rf"\(\s*((?:{IDENTIFIER})(?:\s*,\s*(?:{IDENTIFIER}))+?)\s*\)\s*(NOT\s+IN|IN)\s*\(",
        clause,
        re.I | re.S,
    )
    if tuple_condition:
        columns = [clean_identifier(column) for column in split_top_level(tuple_condition.group(1))]
        fields.extend(columns)
        outer_start = tuple_condition.end() - 1
        outer_end = matching_parenthesis(clause, outer_start)
        if outer_end is not None:
            body = clause[outer_start + 1:outer_end]
            rows = []
            index = 0
            while index < len(body):
                if body[index] == "(":
                    end = matching_parenthesis(body, index)
                    if end is None:
                        break
                    values = [clean_sql_value(value) for value in split_top_level(body[index + 1:end])]
                    rows.append(list(zip(columns, values)))
                    index = end
                index += 1
            row_text = [pair_text(row) for row in rows]
            descriptions.extend(row_text if len(row_text) <= 1 else [f"第{index}行: {value}" for index, value in enumerate(row_text, 1)])
            chinese_pairs.extend((field, value) for row in rows for field, value in row if contains_chinese(value))
    simple_conditions = where_pairs(sql)
    fields.extend(field for field, _, _, _ in simple_conditions)
    if simple_conditions:
        if connectors_at_line_end:
            lines = []
            for index, (field, operator, value, _) in enumerate(simple_conditions):
                next_connector = simple_conditions[index + 1][3] if index + 1 < len(simple_conditions) else ""
                lines.append(f"{field} {operator} {value}")
                if next_connector:
                    lines.append(next_connector)
            descriptions.append("\n".join(lines))
        else:
            descriptions.append("\n".join(f"{connector + ' ' if connector else ''}{field} {operator} {value}" for field, operator, value, connector in simple_conditions))
        chinese_pairs.extend((field, value) for field, _, value, _ in simple_conditions if contains_chinese(value))
    return list(dict.fromkeys(fields)), "\n".join(descriptions), chinese_pairs


def assignment_pairs(sql):
    clause = clause_after_keyword(sql, "SET", ("WHERE", "RETURNING"))
    if clause is None:
        return []
    result = []
    for assignment in split_top_level(clause):
        pair = re.match(rf"\s*((?:{IDENTIFIER})(?:\s*\.\s*(?:{IDENTIFIER}))?)\s*=\s*(.*)\s*$", assignment, re.I | re.S)
        if pair:
            result.append((clean_identifier(pair.group(1)), clean_sql_value(pair.group(2))))
    return result


def insert_rows(sql):
    match = re.search(rf"\bINSERT\s+INTO\s+(?:{IDENTIFIER})(?:\s*\.\s*(?:{IDENTIFIER}))?\s*\((.*?)\)\s*VALUES\b", sql, re.I | re.S)
    if not match:
        return [], []
    columns = [clean_identifier(column) for column in split_top_level(match.group(1))]
    values_text = sql[match.end():]
    rows = []
    index = 0
    while index < len(values_text):
        if values_text[index] == "'":
            index += 1
            while index < len(values_text):
                if values_text[index] == "'":
                    if index + 1 < len(values_text) and values_text[index + 1] == "'":
                        index += 2
                        continue
                    break
                index += 1
        elif values_text[index] == "(":
            end = matching_parenthesis(values_text, index)
            if end is None:
                break
            values = [clean_sql_value(value) for value in split_top_level(values_text[index + 1:end])]
            rows.append(list(zip(columns, values)))
            index = end
        elif re.match(r"\b(?:ON\s+CONFLICT|ON\s+DUPLICATE|RETURNING)\b", values_text[index:], re.I):
            break
        index += 1
    return columns, rows


def insert_select_keys(sql, display_keys):
    match = re.search(r"\bSELECT\s+\*\s+FROM\s*\(\s*SELECT\s+(.*?)\bFROM\b", sql, re.I | re.S)
    if not match:
        return []
    projections = split_top_level(match.group(1))
    result = []
    for key in display_keys:
        for projection in projections:
            alias = re.search(rf"\bAS\s+({IDENTIFIER})\s*$", projection, re.I | re.S)
            projected_name = clean_identifier(alias.group(1)) if alias else clean_identifier(projection)
            if projected_name.lower() == key.lower():
                result.append((key, re.sub(r"\s+", " ", projection).strip()))
                break
    return result if len(result) == len(display_keys) else []


def pair_text(pairs, include_operator=False):
    if include_operator:
        return "; ".join(f"{field} {operator} {value}" for field, operator, value in pairs)
    return "; ".join(f"{field}={value}" for field, value in pairs)


def insert_description(rows):
    return "\n".join(pair_text(row) for row in rows if row)


def data_presentation(change):
    sql = remove_sql_comments(change.get("raw_sql", ""))
    operation = (change.get("operation") or "").lower()
    fields = list(change.get("affected_columns", []))
    description = change.get("description") or ""
    chinese_pairs = []
    chinese_rows = []
    description_rows = []
    value_columns = []
    value_rows = []
    impact_fields = ""
    if operation == "delete":
        fields, description, chinese_pairs = where_presentation(sql, connectors_at_line_end=True)
    elif operation == "insert":
        columns, rows = insert_rows(sql)
        value_columns = columns
        value_rows = [[value for _, value in row] for row in rows]
        condition_fields, condition_description, condition_chinese_pairs = where_presentation(sql)
        display_keys = INSERT_DISPLAY_KEYS.get((change.get("target_table") or "").lower(), columns)
        fields = [key for key in display_keys if key.lower() in {column.lower() for column in columns}] or condition_fields
        if rows:
            selected_rows = [[pair for pair in row if pair[0].lower() in {key.lower() for key in display_keys}] for row in rows]
            impact_fields = "\n".join(", ".join(f"{field} = {value}" for field, value in row) for row in selected_rows if row)
            description_rows = [row for row in selected_rows if row]
            description = insert_description(description_rows)
            chinese_rows = [[(field, value) for field, value in row if contains_chinese(value)] for row in rows]
            chinese_rows = [row for row in chinese_rows if row]
            chinese_pairs = [pair for row in chinese_rows for pair in row]
        elif not columns:
            selected_keys = insert_select_keys(sql, display_keys)
            if selected_keys:
                fields = display_keys
                impact_fields = ", ".join(f"{field} = {value}" for field, value in selected_keys)
                description_rows = [selected_keys]
                description = insert_description(description_rows)
        elif condition_fields:
            description = condition_description
            chinese_pairs = condition_chinese_pairs
    elif operation == "update":
        assignments = assignment_pairs(sql)
        fields = [f"{field} = {value}" for field, value in assignments]
        _, description, _ = where_presentation(sql, connectors_at_line_end=True)
        chinese_pairs = [(field, value) for field, value in assignments if contains_chinese(value)]
    comments = comments_text(change)
    display_comment_rows = []
    if not comments.strip() and chinese_rows:
        display_comment_rows = chinese_rows
        comments = "\n".join(pair_text(row) for row in chinese_rows)
    elif not comments.strip() and chinese_pairs:
        comments = pair_text(chinese_pairs)
    return {"fields": fields, "description": description, "description_rows": description_rows, "comments": comments, "comment_rows": display_comment_rows, "value_columns": value_columns, "value_rows": value_rows, "impact_fields": impact_fields}


def load_migration_adjustments(source_path=REPORT_JSON_PATH, excluded_branches=()):
    if source_path is None or not source_path.exists():
        return {}
    existing = json.loads(source_path.read_text(encoding="utf-8"))
    return {
        (report["branch"]["name"], change["id"]): change.get("migration_adjustment", "无")
        for report in existing
        if report["branch"]["name"] not in excluded_branches
        for directory in report.get("directories", [])
        for source in directory.get("files", [])
        for change in source.get("changes", [])
        if change.get("id")
    }


def load_migration_metadata(source_path=REPORT_JSON_PATH, excluded_branches=()):
    if source_path is None or not source_path.exists():
        return {}
    existing = json.loads(source_path.read_text(encoding="utf-8"))
    return {
        (report["branch"]["name"], change["id"]): {
            "migration_sql_updated": True,
            "migration_original_sql": change.get("migration_original_sql"),
            "migration_updated_sql": change.get("migration_updated_sql"),
            "migration_match_similarity": change.get("migration_match_similarity"),
        }
        for report in existing
        if report["branch"]["name"] not in excluded_branches
        for directory in report.get("directories", [])
        for source in directory.get("files", [])
        for change in source.get("changes", [])
        if change.get("id") and change.get("migration_sql_updated")
    }


def normalized_sql(sql):
    return "\n".join(line.rstrip() for line in (sql or "").replace("\r\n", "\n").replace("\r", "\n").strip().split("\n"))


def migration_content_key(directory_path, source_path, change):
    return (
        directory_path,
        source_path,
        change.get("category"),
        change.get("operation"),
        change.get("object_type"),
        change.get("table"),
        change.get("target_table"),
        change.get("column"),
        change.get("column_after"),
        change.get("constraint"),
        change.get("index"),
        normalized_sql(change.get("raw_sql")),
    )


def remap_migration_adjustments(compact, source_path, branches):
    if not branches:
        return {"source_nondefault": 0, "matched": 0, "exact_matched": 0, "similarity_matched": 0, "unmatched": 0, "ambiguous": 0, "unmatched_examples": []}
    existing = json.loads(source_path.read_text(encoding="utf-8"))
    source_records = defaultdict(list)
    for report in existing:
        branch = report["branch"]["name"]
        if branch not in branches:
            continue
        for directory in report.get("directories", []):
            for source in directory.get("files", []):
                for change in source.get("changes", []):
                    adjustment = change.get("migration_adjustment", "无")
                    if not adjustment or adjustment == "无":
                        continue
                    key = (branch, migration_content_key(directory["path"], source["path"], change))
                    source_records[key].append((change.get("id"), adjustment, change.get("raw_sql", "")))

    targets = defaultdict(list)
    loose_targets = defaultdict(list)
    for report in compact:
        branch = report["branch"]["name"]
        if branch not in branches:
            continue
        for directory in report.get("directories", []):
            for source in directory.get("files", []):
                for change in source.get("changes", []):
                    key = (branch, migration_content_key(directory["path"], source["path"], change))
                    targets[key].append(change)
                    loose_targets[(branch, key[1][:-1])].append(change)

    exact_matched = similarity_matched = ambiguous = 0
    assigned_targets = set()
    unmatched_examples = []
    for key, records in source_records.items():
        candidates = targets.get(key, [])
        if len(records) == 1 and len(candidates) == 1:
            candidates[0]["migration_adjustment"] = records[0][1]
            assigned_targets.add(id(candidates[0]))
            exact_matched += 1
        elif records and candidates:
            ambiguous += len(records)
        else:
            branch, signature = key
            similar_candidates = [change for change in loose_targets.get((branch, signature[:-1]), []) if id(change) not in assigned_targets]
            ranked = sorted(
                ((SequenceMatcher(None, signature[-1], normalized_sql(change.get("raw_sql"))).ratio(), change) for change in similar_candidates),
                key=lambda item: item[0],
                reverse=True,
            )
            top_score = ranked[0][0] if ranked else 0
            next_score = ranked[1][0] if len(ranked) > 1 else 0
            if len(records) == 1 and ranked and top_score >= 0.95 and (len(ranked) == 1 or top_score - next_score >= 0.05):
                target = ranked[0][1]
                target["migration_adjustment"] = records[0][1]
                target["migration_sql_updated"] = True
                target["migration_original_sql"] = records[0][2]
                target["migration_updated_sql"] = target.get("raw_sql", "")
                target["migration_match_similarity"] = round(top_score, 4)
                assigned_targets.add(id(target))
                similarity_matched += 1
            else:
                unmatched_examples.append({"branch": branch, "id": records[0][0], "directory": signature[0], "file": signature[1], "top_similarity": round(top_score, 4)})
    source_nondefault = sum(len(records) for records in source_records.values())
    matched = exact_matched + similarity_matched
    return {
        "source_nondefault": source_nondefault,
        "matched": matched,
        "exact_matched": exact_matched,
        "similarity_matched": similarity_matched,
        "unmatched": source_nondefault - matched - ambiguous,
        "ambiguous": ambiguous,
        "unmatched_examples": unmatched_examples[:10],
    }


def compact_reports(reports, migration_adjustments, migration_metadata=None):
    migration_metadata = migration_metadata or {}
    result = []
    for report in reports:
        directories = []
        for directory in report["directories"]:
            files = []
            for source in directory["files"]:
                changes = []
                for change in source["changes"]:
                    presentation = data_presentation(change) if change.get("change_category") == "data" else None
                    column_after = renamed_column_after(change)
                    migration_key = (report["branch"]["name"], change.get("change_id"))
                    metadata = migration_metadata.get(migration_key, {})
                    changes.append({
                        "id": change.get("change_id"),
                        "category": change.get("change_category"),
                        "operation": change.get("operation"),
                        "object_type": change.get("object_type"),
                        "table": change.get("table_name") or change.get("target_table"),
                        "target_table": change.get("target_table"),
                        "qualified_target_table": change.get("qualified_target_table"),
                        "column": change.get("column_name"),
                        "column_after": column_after,
                        "constraint": change.get("constraint_name"),
                        "index": change.get("index_name"),
                        "description": change.get("description"),
                        "affected_columns": change.get("affected_columns", []),
                        "display_fields": presentation["fields"] if presentation else [],
                        "display_value_columns": presentation["value_columns"] if presentation else [],
                        "display_value_rows": presentation["value_rows"] if presentation else [],
                        "display_impact_fields": presentation["impact_fields"] if presentation else "",
                        "display_description": presentation["description"] if presentation else change.get("description"),
                        "display_description_rows": presentation["description_rows"] if presentation else [],
                        "line_start": change.get("line_start"),
                        "line_end": change.get("line_end"),
                        "comments": presentation["comments"] if presentation else comments_text(change),
                        "display_comment_rows": presentation["comment_rows"] if presentation else [],
                        "raw_sql": change.get("raw_sql", ""),
                        "warnings": warnings_text(change),
                        "migration_adjustment": migration_adjustments.get(migration_key, "无"),
                        "migration_sql_updated": metadata.get("migration_sql_updated", False),
                        "migration_original_sql": metadata.get("migration_original_sql"),
                        "migration_updated_sql": metadata.get("migration_updated_sql"),
                        "migration_match_similarity": metadata.get("migration_match_similarity"),
                    })
                if changes:
                    files.append({"path": Path(source["path"]).name, "encoding": source["encoding"], "changes": changes})
            if files:
                directories.append({
                    "path": directory["relative_path"],
                    "database": directory.get("database"),
                    "scope": directory.get("scope"),
                    "customer": directory.get("customer"),
                    "system": directory.get("system"),
                    "module": directory.get("module"),
                    "category": directory["category"],
                    "files": files,
                })
        result.append({
            "branch": report["branch"],
            "scan_policy": report.get("scan_policy", {}),
            "summary": report["summary"],
            "directories": directories,
            "warnings": report.get("warnings", []),
        })
    return result


def write_migration_adjustments(compact):
    adjustments = []
    for report in compact:
        for directory in report.get("directories", []):
            for source in directory.get("files", []):
                for change in source.get("changes", []):
                    adjustment = change.get("migration_adjustment", "无")
                    sql_updated = bool(change.get("migration_sql_updated"))
                    if not change.get("id") or (adjustment in (None, "", "无") and not sql_updated):
                        continue
                    item = {
                        "branch": report["branch"]["name"],
                        "change_id": change["id"],
                        "migration_adjustment": adjustment or "无",
                    }
                    if sql_updated:
                        item.update({
                            "migration_sql_updated": True,
                            "migration_original_sql": change.get("migration_original_sql"),
                            "migration_updated_sql": change.get("migration_updated_sql"),
                            "migration_match_similarity": change.get("migration_match_similarity"),
                        })
                    adjustments.append(item)
    document = {"schema_version": "1.0", "updated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "adjustments": adjustments}
    MIGRATION_ADJUSTMENTS_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(MIGRATION_ADJUSTMENTS_PATH.read_text(encoding="utf-8"))
    return len(adjustments)


def clear_embedded_migration_adjustments(compact):
    for report in compact:
        for directory in report.get("directories", []):
            for source in directory.get("files", []):
                for change in source.get("changes", []):
                    change["migration_adjustment"] = "无"
                    change.pop("migration_sql_updated", None)
                    change.pop("migration_original_sql", None)
                    change.pop("migration_updated_sql", None)
                    change.pop("migration_match_similarity", None)


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Release Patch SQL 变更分析</title>
<style>
:root{--ink:#17211b;--muted:#667269;--paper:#f3f0e8;--panel:#fffdf8;--line:#d9d4c8;--green:#164b3b;--green2:#26715a;--rust:#a4432f;--gold:#bb8a31;--blue:#315f78;--shadow:0 12px 30px rgba(41,51,44,.09)}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(115deg,#ebe6da 0,#f8f6ef 45%,#e6eee9 100%);color:var(--ink);font:14px/1.55 "Segoe UI","Microsoft YaHei",sans-serif}button,input{font:inherit}
.masthead{padding:30px 34px 22px;background:var(--green);color:#fff;position:relative;overflow:hidden}.masthead:after{content:"SQL";position:absolute;right:30px;top:-37px;font:900 150px Georgia,serif;color:rgba(255,255,255,.055);letter-spacing:-12px}.eyebrow{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#c6dbd3}.masthead h1{margin:6px 0 5px;font:700 30px/1.2 Georgia,"Microsoft YaHei",serif}.masthead p{margin:0;color:#d9e7e1}
.tabs{display:flex;gap:7px;padding:13px 24px;background:#123c30;overflow:auto;position:sticky;top:0;z-index:20}.tab{border:1px solid rgba(255,255,255,.2);background:transparent;color:#d6e5df;padding:8px 14px;border-radius:2px;white-space:nowrap;cursor:pointer}.tab.active{background:#fff9ec;color:#173d32;border-color:#fff9ec;font-weight:700}
.toolbar{position:sticky;top:59px;z-index:15;display:flex;gap:12px;align-items:center;padding:12px 24px;background:rgba(243,240,232,.94);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}.search{flex:1;max-width:720px;border:1px solid #b9b4a8;background:#fff;padding:10px 13px;border-radius:3px;outline:none}.search:focus{border-color:var(--green2);box-shadow:0 0 0 3px rgba(38,113,90,.12)}.count{color:var(--muted);white-space:nowrap}
main{padding:22px 24px 60px;max-width:1800px;margin:auto}.branch-head{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:18px}.branch-head h2{margin:0;font:700 25px Georgia,"Microsoft YaHei",serif}.commit{font:12px Consolas,monospace;color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:10px;margin:14px 0 25px}.card{background:var(--panel);border:1px solid var(--line);border-top:4px solid var(--green2);padding:14px 16px;box-shadow:var(--shadow)}.card.data{border-top-color:var(--rust)}.card .n{font:700 25px Georgia,serif}.card .label{color:var(--muted);font-size:12px}
.section-title{display:flex;align-items:center;gap:10px;margin:27px 0 10px;font:700 19px Georgia,"Microsoft YaHei",serif}.section-title:after{content:"";height:1px;background:var(--line);flex:1}.section-mark{width:9px;height:9px;background:var(--blue);transform:rotate(45deg)}.section-mark.data{background:var(--rust)}
details.group{background:var(--panel);border:1px solid var(--line);margin:0 0 9px;box-shadow:0 4px 14px rgba(41,51,44,.05)}details.group>summary{list-style:none;cursor:pointer;padding:12px 14px;display:flex;gap:12px;align-items:center}details.group>summary::-webkit-details-marker{display:none}details.group>summary:before{content:"+";width:20px;height:20px;border:1px solid #aaa;display:grid;place-items:center;font-weight:700}details[open].group>summary:before{content:"−"}.path{font-family:Consolas,"Microsoft YaHei",monospace;font-weight:700}.meta{color:var(--muted);font-size:12px}.pill{margin-left:auto;background:#e8eee9;color:var(--green);padding:3px 8px;border-radius:20px;font-weight:700;font-size:12px}.target>summary{border-left:5px solid var(--rust)}.subgroup{margin:0 12px 10px;border:1px solid #e4ded2}.subgroup>summary{padding:9px 11px!important;background:#faf6ed}
 .table-wrap{overflow:auto;border-top:1px solid var(--line)}table{width:1350px;min-width:100%;border-collapse:collapse;table-layout:fixed}th{position:sticky;top:0;background:#e8e5dc;color:#35423a;text-align:left;padding:8px 13px 8px 8px;border-bottom:1px solid #cbc5b8;font-size:12px}th .column-resizer{position:absolute;top:0;right:-3px;width:7px;height:100%;cursor:col-resize;z-index:2}th .column-resizer:after{content:"";position:absolute;top:20%;bottom:20%;left:3px;width:1px;background:#b7b0a3}th .column-resizer:hover:after,body.resizing th .column-resizer:after{background:var(--green2)}body.resizing{cursor:col-resize;user-select:none}td{vertical-align:top;padding:8px;border-bottom:1px solid #ebe6dc;overflow-wrap:anywhere;word-break:break-word}tr:hover td{background:#fff9e9}.op{display:inline-block;padding:3px 7px;border:1px solid transparent;border-radius:3px;background:#e5e8e6;color:#45524b;font:700 12px Consolas,monospace}.op-create,.op-insert,.op-add{background:#dcefe5;border-color:#a9d3bb;color:#185b3d}.op-update,.op-alter,.op-modify{background:#fff0c9;border-color:#dfc573;color:#76530b}.op-delete,.op-drop,.op-truncate{background:#f6ddd8;border-color:#dfa79c;color:#8b2f20}.op-rename,.op-replace{background:#e8e0f5;border-color:#c6b4e2;color:#60418a}.op-comment{background:#e4edf6;border-color:#b6cce0;color:#315f78}.op-index{background:#dcecef;border-color:#acd0d6;color:#1e6570}.op-constraint{background:#eee4d8;border-color:#d5bda2;color:#72502e}.op-merge{background:#e1e8f7;border-color:#b5c4e2;color:#354f86}.file{font:12px Consolas,"Microsoft YaHei",monospace;word-break:break-all}.desc{display:block;color:#5f4a25;white-space:pre-wrap;overflow-wrap:anywhere}.sql-source{margin-bottom:5px;color:var(--muted);font:12px/1.45 Consolas,"Microsoft YaHei",monospace;word-break:break-all}.sql-toggle summary{cursor:pointer;color:var(--green2);font-weight:700}.sql-toggle pre{white-space:pre-wrap;word-break:break-word;max-height:420px;overflow:auto;background:#18231e;color:#e7eee9;padding:12px;border-radius:2px;font:12px/1.55 Consolas,"Microsoft YaHei",monospace}.comments{display:block;white-space:pre-wrap;color:#785c27;overflow-wrap:anywhere}.comment-table{width:100%;min-width:0;table-layout:auto;border-collapse:collapse;color:#5f4a25;font-size:12px}.comment-table th{position:static;padding:4px 6px;border:1px solid #d5cab8;background:#f1eadc;color:#6c5936;white-space:nowrap}.comment-table td{padding:4px 6px;border:1px solid #ded5c4;background:#fffaf0}.comment-table tr:hover td{background:#fff7e7}.empty{padding:50px;text-align:center;color:var(--muted)}.hidden{display:none!important}.footer{padding:18px 24px;color:var(--muted);border-top:1px solid var(--line);background:#ece8de;font-size:12px}
 .insert-data-button{border:1px solid #8fb9a8;background:#e5f1eb;color:#185b3d;padding:5px 9px;border-radius:3px;cursor:pointer;font-weight:700}.insert-data-button:hover{background:#d6e9df}.data-modal{position:fixed;inset:0;z-index:100;display:none;align-items:center;justify-content:center;padding:28px;background:rgba(18,33,26,.58)}.data-modal.open{display:flex}.data-modal-panel{display:flex;flex-direction:column;width:min(1500px,96vw);max-height:90vh;background:var(--panel);border:1px solid #bbb3a5;box-shadow:0 25px 70px rgba(0,0,0,.3)}.data-modal-head{display:flex;align-items:center;gap:15px;padding:13px 16px;background:var(--green);color:#fff}.data-modal-title{font-weight:700}.data-modal-meta{color:#c9ddd5;font-size:12px}.data-modal-close{margin-left:auto;border:1px solid rgba(255,255,255,.45);background:transparent;color:#fff;padding:4px 10px;cursor:pointer}.data-modal-body{overflow:auto;padding:14px}.insert-data-table{width:max-content;min-width:100%;table-layout:auto;border-collapse:collapse}.insert-data-table th{position:sticky;top:0;padding:7px 9px;border:1px solid #c9c2b6;background:#e8e5dc;white-space:nowrap}.insert-data-table tbody th{top:auto;left:0;z-index:1;background:#f1eadc}.insert-data-table thead th:first-child{left:0;z-index:3}.insert-data-table td{padding:7px 9px;border:1px solid #ded8cd;background:#fff;white-space:pre;min-width:100px;max-width:none;overflow-wrap:normal;word-break:normal}.insert-data-table tr:hover td{background:#fff9e9}
 .update-field-preview{display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.update-field-preview.truncated{cursor:help}.field-tooltip{position:fixed;z-index:120;display:none;max-width:min(720px,80vw);max-height:60vh;overflow:auto;padding:10px 12px;border:1px solid #8d978f;border-radius:3px;background:#17231e;color:#eef4f0;box-shadow:0 12px 35px rgba(0,0,0,.3);white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 Consolas,"Microsoft YaHei",monospace;pointer-events:none}.field-tooltip.open{display:block}
@media(max-width:760px){.masthead{padding:23px 18px}.masthead h1{font-size:24px}.tabs,.toolbar{padding-left:12px;padding-right:12px}.toolbar{top:57px}.cards{grid-template-columns:1fr 1fr}main{padding:17px 12px 45px}.branch-head{display:block}.commit{margin-top:6px;word-break:break-all}.meta{display:none}}
</style>
</head>
<body>
<header class="masthead"><div class="eyebrow">Database Change Ledger</div><h1>Release Patch SQL 变更分析</h1><p>按正式分支、Patch 目录和配置目标表组织的可追溯报告</p></header>
<nav class="tabs" id="tabs"></nav>
<div class="toolbar"><input id="search" class="search" placeholder="搜索目录、文件、表、字段、说明或 SQL…"><span id="visibleCount" class="count"></span></div>
<main id="app"></main>
<div id="dataModal" class="data-modal" role="dialog" aria-modal="true" aria-labelledby="dataModalTitle"><div class="data-modal-panel"><div class="data-modal-head"><span id="dataModalTitle" class="data-modal-title">INSERT 数据</span><span id="dataModalMeta" class="data-modal-meta"></span><button id="dataModalClose" class="data-modal-close" type="button">关闭</button></div><div id="dataModalBody" class="data-modal-body"></div></div></div>
<div id="fieldTooltip" class="field-tooltip"></div>
<footer class="footer">数据来源：output/json · 生成时间：__GENERATED_AT__</footer>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
const reports=JSON.parse(document.getElementById('report-data').textContent);let active=0;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const flatDir=d=>d.files.flatMap(f=>f.changes.map(c=>({...c,file:f.path,encoding:f.encoding,directory:d.path,meta:d})));
function operationClass(operation){const value=String(operation??'').toLowerCase();if(value==='insert'||value.startsWith('create_')||value.startsWith('add_'))return value.includes('index')?'op-index':value.includes('constraint')?'op-constraint':value==='insert'?'op-insert':value.startsWith('create_')?'op-create':'op-add';if(value==='update'||value.startsWith('alter_')||value.startsWith('modify_'))return value==='update'?'op-update':value.startsWith('modify_')?'op-modify':'op-alter';if(value==='delete'||value==='truncate'||value.startsWith('drop_'))return value==='delete'?'op-delete':value==='truncate'?'op-truncate':value.includes('index')?'op-index':value.includes('constraint')?'op-constraint':'op-drop';if(value.startsWith('rename_'))return 'op-rename';if(value.startsWith('comment_'))return 'op-comment';if(value==='replace')return 'op-replace';if(value==='merge')return 'op-merge';return ''}
function pairRowsTable(records){const fields=[...new Set(records.flatMap(record=>record.map(([field])=>field)))];const rows=records.map(record=>{const values=Object.fromEntries(record);return `<tr>${fields.map(field=>`<td>${esc(values[field]??'')}</td>`).join('')}</tr>`}).join('');return `<table class="comment-table"><thead><tr>${fields.map(field=>`<th>${esc(field)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`}
function commentsCell(c){if(c.display_comment_rows?.length)return pairRowsTable(c.display_comment_rows);return `<span class="comments">${esc(c.comments)}</span>`}
function descriptionCell(c){if(c.operation==='insert'&&c.display_description_rows?.length)return pairRowsTable(c.display_description_rows);return `<span class="desc">${esc(c.display_description??c.description)}</span>`}
function fieldsCell(c){if(c.operation==='insert'&&c.display_value_columns?.length)return `<button type="button" class="insert-data-button" data-change-id="${esc(c.id)}">查看插入数据 · ${c.display_value_rows.length} 行 × ${c.display_value_columns.length} 列</button>`;const value=c.operation==='rename_column'&&c.column_after?`${c.column} -> ${c.column_after}`:c.column||c.display_fields?.join('\n')||c.affected_columns?.join(', ')||'';if(c.operation==='update')return `<span class="update-field-preview" data-full="${esc(value)}">${esc(value)}</span>`;return esc(value)}
function row(c){const source=`<div class="sql-source">${esc(c.file)} · 行 ${esc(c.line_start)}-${esc(c.line_end)}</div>`;const cols=[`<span class="op ${operationClass(c.operation)}">${esc(c.operation)}</span>`,esc(c.table),fieldsCell(c),descriptionCell(c),commentsCell(c),`${source}<details class="sql-toggle"><summary>查看 SQL</summary><pre>${esc(c.raw_sql)}</pre></details>`];return `<tr class="change-row">${cols.map(x=>`<td>${x}</td>`).join('')}</tr>`}
function table(rows){const headers=['操作','表/目标表','字段/影响字段','说明','注释','原始 SQL'];return `<div class="table-wrap"><table><colgroup><col style="width:110px"><col style="width:180px"><col style="width:260px"><col style="width:300px"><col style="width:240px"><col style="width:260px"></colgroup><thead><tr>${headers.map(x=>`<th>${x}<span class="column-resizer" title="拖动调整列宽"></span></th>`).join('')}</tr></thead><tbody>${rows.map(row).join('')}</tbody></table></div>`}
function dirGroup(d){const rows=flatDir(d);return `<details class="group"><summary><span class="path">${esc(d.path)}</span><span class="meta">${esc([d.customer,d.database,d.system,d.module].filter(Boolean).join(' / '))}</span><span class="pill">${rows.length}</span></summary>${table(rows)}</details>`}
function dataGroups(dirs,targets){return targets.map(target=>{const matches=dirs.map(d=>({d,rows:flatDir(d).filter(c=>c.target_table===target)})).filter(x=>x.rows.length);if(!matches.length)return '';const total=matches.reduce((n,x)=>n+x.rows.length,0);return `<details class="group target"><summary><span class="path">${esc(target)}</span><span class="meta">目标配置表 · ${matches.length} 个目录</span><span class="pill">${total}</span></summary>${matches.map(x=>`<details class="group subgroup"><summary><span class="path">${esc(x.d.path)}</span><span class="meta">${esc([x.d.customer,x.d.database,x.d.system,x.d.module].filter(Boolean).join(' / '))}</span><span class="pill">${x.rows.length}</span></summary>${table(x.rows)}</details>`).join('')}</details>`}).join('')}
function markTruncatedUpdateFields(){document.querySelectorAll('.update-field-preview').forEach(preview=>preview.classList.toggle('truncated',preview.scrollWidth>preview.clientWidth))}
function enableColumnResize(){document.querySelectorAll('.column-resizer').forEach(handle=>handle.addEventListener('mousedown',event=>{event.preventDefault();const th=handle.parentElement,table=th.closest('table'),columns=[...table.querySelectorAll('col')],index=[...th.parentElement.children].indexOf(th),column=columns[index],startX=event.clientX,startWidth=th.getBoundingClientRect().width,startTableWidth=table.getBoundingClientRect().width;document.body.classList.add('resizing');const move=moveEvent=>{const delta=moveEvent.clientX-startX,newWidth=Math.max(70,startWidth+delta);column.style.width=`${newWidth}px`;table.style.width=`${Math.max(420,startTableWidth+newWidth-startWidth)}px`};const stop=()=>{document.body.classList.remove('resizing');document.removeEventListener('mousemove',move);document.removeEventListener('mouseup',stop);markTruncatedUpdateFields()};document.addEventListener('mousemove',move);document.addEventListener('mouseup',stop)}))}
function render(i){active=i;document.querySelectorAll('.tab').forEach((x,n)=>x.classList.toggle('active',n===i));const r=reports[i],s=r.summary,tableDirs=r.directories.filter(d=>d.category==='table'),dataDirs=r.directories.filter(d=>d.category==='data');document.getElementById('app').innerHTML=`<div class="branch-head"><div><h2>${esc(r.branch.name)}</h2><div class="commit">${esc(r.branch.ref)} · ${esc(r.branch.commit)}</div></div></div><div class="cards"><div class="card"><div class="n">${s.table_change_count.toLocaleString()}</div><div class="label">表结构变更</div></div><div class="card data"><div class="n">${s.data_change_count.toLocaleString()}</div><div class="label">配置数据变更</div></div><div class="card"><div class="n">${s.scanned_sql_file_count.toLocaleString()}</div><div class="label">扫描 SQL 文件</div></div><div class="card"><div class="n">${s.warning_count.toLocaleString()}</div><div class="label">解析警告</div></div></div><h3 class="section-title"><span class="section-mark"></span>表结构变更 · 按目录</h3>${tableDirs.map(dirGroup).join('')||'<div class="empty">无表结构变更</div>'}<h3 class="section-title"><span class="section-mark data"></span>配置数据变更 · 按目标表</h3>${dataGroups(dataDirs,['comm_busidefine','comm_subjectdefine','comm_bookkeepingrule','sys_param_define','comm_busidefine_refrule'])||'<div class="empty">无目标配置表变更</div>'}`;enableColumnResize();markTruncatedUpdateFields();filter();}
function filter(){const q=document.getElementById('search').value.trim().toLowerCase();let shown=0,total=0;document.querySelectorAll('.change-row').forEach(row=>{total++;const ok=!q||row.textContent.toLowerCase().includes(q);row.classList.toggle('hidden',!ok);if(ok)shown++});document.querySelectorAll('details.group').forEach(g=>{const any=g.querySelector('.change-row:not(.hidden)');g.classList.toggle('hidden',!any)});document.getElementById('visibleCount').textContent=q?`显示 ${shown.toLocaleString()} / ${total.toLocaleString()} 条`:`共 ${total.toLocaleString()} 条`;}
function showInsertData(changeId){const change=reports[active].directories.flatMap(flatDir).find(item=>item.id===changeId);if(!change)return;const fields=change.display_value_columns,records=change.display_value_rows;document.getElementById('dataModalTitle').textContent=`${change.table} · INSERT 数据`;document.getElementById('dataModalMeta').textContent=`${records.length} 条数据 × ${fields.length} 个字段`;document.getElementById('dataModalBody').innerHTML=`<table class="insert-data-table"><thead><tr><th>字段</th>${records.map((_,index)=>`<th>数据 ${index+1}</th>`).join('')}</tr></thead><tbody>${fields.map((field,fieldIndex)=>`<tr><th>${esc(field)}</th>${records.map(values=>`<td>${esc(values[fieldIndex]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table>`;document.getElementById('dataModal').classList.add('open');document.body.style.overflow='hidden'}
function closeInsertData(){document.getElementById('dataModal').classList.remove('open');document.body.style.overflow=''}
function positionFieldTooltip(event){const tooltip=document.getElementById('fieldTooltip'),gap=14;let left=event.clientX+gap,top=event.clientY+gap;const box=tooltip.getBoundingClientRect();if(left+box.width>innerWidth-8)left=Math.max(8,event.clientX-box.width-gap);if(top+box.height>innerHeight-8)top=Math.max(8,event.clientY-box.height-gap);tooltip.style.left=`${left}px`;tooltip.style.top=`${top}px`}
document.getElementById('tabs').innerHTML=reports.map((r,i)=>`<button class="tab" data-i="${i}">${esc(r.branch.name.replace('release/',''))}</button>`).join('');document.getElementById('tabs').addEventListener('click',e=>{const b=e.target.closest('.tab');if(b){document.getElementById('search').value='';render(Number(b.dataset.i));scrollTo(0,0)}});document.getElementById('app').addEventListener('click',e=>{const button=e.target.closest('.insert-data-button');if(button)showInsertData(button.dataset.changeId)});document.getElementById('app').addEventListener('toggle',()=>requestAnimationFrame(markTruncatedUpdateFields),true);document.getElementById('app').addEventListener('mouseover',e=>{const preview=e.target.closest('.update-field-preview');if(!preview)return;preview.classList.toggle('truncated',preview.scrollWidth>preview.clientWidth);if(!preview.classList.contains('truncated'))return;const tooltip=document.getElementById('fieldTooltip');tooltip.textContent=preview.dataset.full;tooltip.classList.add('open');positionFieldTooltip(e)});document.getElementById('app').addEventListener('mousemove',e=>{if(document.getElementById('fieldTooltip').classList.contains('open'))positionFieldTooltip(e)});document.getElementById('app').addEventListener('mouseout',e=>{const preview=e.target.closest('.update-field-preview');if(preview&&!preview.contains(e.relatedTarget))document.getElementById('fieldTooltip').classList.remove('open')});document.getElementById('dataModalClose').addEventListener('click',closeInsertData);document.getElementById('dataModal').addEventListener('click',e=>{if(e.target.id==='dataModal')closeInsertData()});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeInsertData()});window.addEventListener('resize',markTruncatedUpdateFields);document.getElementById('search').addEventListener('input',filter);render(0);
</script>
</body></html>'''


def write_web_report(compact):
    REPORT_JSON_PATH.write_text(
        json.dumps(compact, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8"))

    template_path = HTML_TEMPLATE_PATH or HTML_PATH
    if not template_path.is_file():
        raise FileNotFoundError(
            f"Editable HTML template not found: {template_path}. "
            "Pass --html-template with an existing report HTML."
        )
    document = template_path.read_text(encoding="utf-8")
    document = document.replace(
        "dataGroups(dataDirs,['comm_busidefine','comm_subjectdefine','comm_bookkeepingrule','sys_param_define','comm_busidefine_refrule'])",
        "dataGroups(dataDirs,r.scan_policy?.target_data_tables||[])"
    )
    generated_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    document = re.sub(r"生成时间：[^<]+", f"生成时间：{generated_at}", document, count=1)
    HTML_PATH.write_text(document, encoding="utf-8")


def excel_text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))
    if len(value) > EXCEL_CELL_LIMIT:
        marker = "\n[Excel 单元格长度限制，完整内容请查看 HTML 或 JSON]"
        value = value[:EXCEL_CELL_LIMIT - len(marker)] + marker
    return value


def column_name(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def xml_cell(row, column, value, style=8):
    ref = f"{column_name(column)}{row}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}" s="{style}" t="n"><v>{value}</v></c>'
    text = escape(excel_text(value))
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def detail_values(directory, source, change):
    category = "表结构" if change["change_category"] == "table" else "配置数据"
    presentation = data_presentation(change) if change["change_category"] == "data" else None
    column_name = change.get("column_name")
    column_after = renamed_column_after(change)
    if change.get("operation") == "rename_column" and column_after:
        column_name = f"{column_name} -> {column_after}"
    return [
        category,
        directory["relative_path"],
        change.get("target_table") or "",
        directory.get("scope"),
        directory.get("customer"),
        directory.get("database"),
        directory.get("system"),
        directory.get("module"),
        Path(source["path"]).name,
        source.get("encoding"),
        f'{change.get("line_start", "")}-{change.get("line_end", "")}',
        change.get("change_id"),
        change.get("operation"),
        change.get("object_type"),
        change.get("table_name") or change.get("target_table"),
        column_name,
        change.get("constraint_name"),
        change.get("index_name"),
        presentation["description"] if presentation else change.get("description"),
        (presentation["impact_fields"] or presentation["fields"]) if presentation else change.get("affected_columns", []),
        presentation["comments"] if presentation else comments_text(change),
        change.get("raw_sql", ""),
        warnings_text(change),
    ]


def grouped_changes(report):
    table_groups = []
    data_groups = defaultdict(lambda: defaultdict(list))
    for directory in report["directories"]:
        entries = []
        for source in directory["files"]:
            for change in source["changes"]:
                entry = (directory, source, change)
                if directory["category"] == "table":
                    entries.append(entry)
                else:
                    data_groups[change["target_table"]][directory["relative_path"]].append(entry)
        if entries:
            table_groups.append((directory["relative_path"], entries))
    return table_groups, data_groups


CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>__SHEETS__</Types>'''
ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="4"><font><sz val="10"/><name val="Microsoft YaHei"/></font><font><b/><sz val="16"/><color rgb="FFFFFFFF"/><name val="Microsoft YaHei"/></font><font><b/><color rgb="FFFFFFFF"/><name val="Microsoft YaHei"/></font><font><b/><color rgb="FF23392E"/><name val="Microsoft YaHei"/></font></fonts><fills count="7"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF164B3B"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF315F78"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFA4432F"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9B970"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE9E4D8"/></patternFill></fill></fills><borders count="2"><border/><border><left style="thin"><color rgb="FFD6D0C3"/></left><right style="thin"><color rgb="FFD6D0C3"/></right><top style="thin"><color rgb="FFD6D0C3"/></top><bottom style="thin"><color rgb="FFD6D0C3"/></bottom></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="9"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="3" fillId="6" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''


def write_sheet(archive, number, report):
    headers = ["大项", "目录", "目标配置表", "范围", "客户/专项", "数据库", "系统", "模块", "源文件", "编码", "行号", "变更ID", "操作", "对象类型", "表名", "字段名", "约束名", "索引名", "说明", "字段/影响字段", "SQL注释", "原始SQL", "解析警告"]
    table_groups, data_groups = grouped_changes(report)
    with archive.open(f"xl/worksheets/sheet{number}.xml", "w") as out:
        def emit(value):
            out.write(value.encode("utf-8"))
        emit('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')
        emit('<sheetPr><outlinePr summaryBelow="0"/></sheetPr><sheetViews><sheetView workbookViewId="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15" outlineLevelRow="1"/>')
        widths = [12, 44, 28, 12, 16, 12, 15, 20, 52, 11, 12, 18, 18, 15, 26, 22, 20, 20, 35, 25, 42, 75, 30]
        emit('<cols>' + ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1)) + '</cols><sheetData>')
        row = 1
        emit(f'<row r="{row}" ht="28" customHeight="1">{xml_cell(row, 1, report["branch"]["name"], 1)}</row>')
        row += 1
        summary = report["summary"]
        summary_text = f'提交: {report["branch"]["commit"]}    表结构变更: {summary["table_change_count"]}    配置数据变更: {summary["data_change_count"]}    扫描文件: {summary["scanned_sql_file_count"]}    警告: {summary["warning_count"]}'
        emit(f'<row r="{row}" ht="23" customHeight="1">{xml_cell(row, 1, summary_text, 2)}</row>')
        row += 1
        emit(f'<row r="{row}"></row>'); row += 1
        emit(f'<row r="{row}" ht="30" customHeight="1">' + ''.join(xml_cell(row, i, value, 3) for i, value in enumerate(headers, 1)) + '</row>')
        for directory, entries in table_groups:
            row += 1
            emit(f'<row r="{row}" ht="22" customHeight="1">{xml_cell(row, 1, f"表结构目录 | {directory} | {len(entries)} 条", 4)}</row>')
            for directory_obj, source, change in entries:
                row += 1
                values = detail_values(directory_obj, source, change)
                emit(f'<row r="{row}" outlineLevel="1">' + ''.join(xml_cell(row, i, value, 7 if i in (19, 20, 21, 22, 23) else 8) for i, value in enumerate(values, 1)) + '</row>')
        target_order = report["scan_policy"]["target_data_tables"]
        for target in target_order:
            directories = data_groups.get(target, {})
            if not directories:
                continue
            total = sum(len(entries) for entries in directories.values())
            row += 1
            emit(f'<row r="{row}" ht="23" customHeight="1">{xml_cell(row, 1, f"目标配置表 | {target} | {total} 条", 5)}</row>')
            for directory, entries in directories.items():
                row += 1
                emit(f'<row r="{row}" ht="21" customHeight="1" outlineLevel="1">{xml_cell(row, 1, f"目录 | {directory} | {len(entries)} 条", 6)}</row>')
                for directory_obj, source, change in entries:
                    row += 1
                    values = detail_values(directory_obj, source, change)
                    emit(f'<row r="{row}" outlineLevel="1">' + ''.join(xml_cell(row, i, value, 7 if i in (19, 20, 21, 22, 23) else 8) for i, value in enumerate(values, 1)) + '</row>')
        emit('</sheetData><mergeCells count="2"><mergeCell ref="A1:W1"/><mergeCell ref="A2:W2"/></mergeCells><pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/></worksheet>')


def write_xlsx(reports):
    sheet_names = [report["branch"]["name"].replace("release/", "")[:31] for report in reports]
    sheet_overrides = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(reports) + 1))
    workbook_sheets = "".join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheet_names, 1))
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{workbook_sheets}</sheets><calcPr calcId="191029"/></workbook>'''
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(1, len(reports) + 1):
        rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
    rels.append(f'<Relationship Id="rId{len(reports) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    with zipfile.ZipFile(XLSX_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES.replace("__SHEETS__", sheet_overrides))
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        archive.writestr("xl/styles.xml", STYLES)
        for number, report in enumerate(reports, 1):
            write_sheet(archive, number, report)


def validate_outputs(reports):
    html = HTML_PATH.read_text(encoding="utf-8")
    html_reports = json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8"))
    if '<script id="report-data"' in html or "const DATA_URL='release-patch-change-analysis.json'" not in html:
        raise ValueError("HTML must load the standalone report JSON")
    if "迁移调整" not in html or "saveMigrationAdjustment" not in html:
        raise ValueError("HTML migration adjustment editor is missing")
    if "ADJUSTMENTS_URL='release-patch-change-analysis-adjustments.json'" not in html or "saveMigrationAdjustments" not in html:
        raise ValueError("HTML independent migration-adjustment storage is missing")
    if "jumpToChange" not in html or "migration-jump-button" not in html:
        raise ValueError("HTML migration summary jump support is missing")
    if "migration_sql_updated" not in html or "SQL 发生变化" not in html or "查看 SQL 差异" not in html or "showSqlDiff" not in html or "lineDiff" not in html:
        raise ValueError("HTML updated-SQL comparison support is missing")
    report_changes = [
        change
        for report in html_reports
        for directory in report["directories"]
        for source in directory["files"]
        for change in source["changes"]
    ]
    embedded_adjustments = [change for change in report_changes if change.get("migration_adjustment") not in (None, "", "无")]
    if embedded_adjustments:
        raise ValueError("Report JSON must not embed migration adjustments")
    marker_fields = {"migration_sql_updated", "migration_original_sql", "migration_updated_sql", "migration_match_similarity"}
    if any(marker_fields.intersection(change) for change in report_changes):
        raise ValueError("Report JSON must not embed migration marker fields")
    adjustment_count = 0
    updated_sql_adjustments = []
    if MIGRATION_ADJUSTMENTS_PATH.exists():
        adjustment_document = json.loads(MIGRATION_ADJUSTMENTS_PATH.read_text(encoding="utf-8"))
        if adjustment_document.get("schema_version") != "1.0" or not isinstance(adjustment_document.get("adjustments"), list):
            raise ValueError("Independent migration-adjustment JSON is invalid")
        adjustment_count = len(adjustment_document["adjustments"])
        updated_sql_adjustments = [item for item in adjustment_document["adjustments"] if item.get("migration_sql_updated")]
        for item in updated_sql_adjustments:
            if not item.get("migration_original_sql") or not item.get("migration_updated_sql"):
                raise ValueError(f'Updated SQL comparison is incomplete: {item.get("change_id")}')
            if normalized_sql(item["migration_original_sql"]) == normalized_sql(item["migration_updated_sql"]):
                raise ValueError(f'Updated SQL comparison contains identical SQL: {item.get("change_id")}')
    for asset in REPORT_ASSETS:
        if not (OUTPUT_ROOT / asset).is_file():
            raise ValueError(f"Missing web report asset: {asset}")
    html_counts = [sum(len(source["changes"]) for directory in report["directories"] for source in directory["files"]) for report in html_reports]
    expected_counts = [report["summary"]["table_change_count"] + report["summary"]["data_change_count"] for report in reports]
    if html_counts != expected_counts:
        raise ValueError(f"HTML detail counts mismatch: {html_counts} != {expected_counts}")
    if any("/" in source["path"] or "\\" in source["path"] for report in html_reports for directory in report["directories"] for source in directory["files"]):
        raise ValueError("HTML source-file fields must contain file names only")
    data_display = defaultdict(lambda: {"total": 0, "fields": 0, "description": 0, "comments": 0})
    unresolved = []
    for report in html_reports:
        for directory in report["directories"]:
            if directory["category"] != "data":
                continue
            for source in directory["files"]:
                for change in source["changes"]:
                    operation = change["operation"]
                    metrics = data_display[operation]
                    metrics["total"] += 1
                    metrics["fields"] += bool(change.get("display_fields"))
                    metrics["description"] += bool(change.get("display_description"))
                    metrics["comments"] += bool(change.get("comments"))
                    if operation in ("delete", "insert") and (not change.get("display_fields") or not change.get("display_description")):
                        unresolved.append(f'{source["path"]}:{change["line_start"]}-{change["line_end"]}')
                    if operation == "insert":
                        expected_keys = INSERT_DISPLAY_KEYS.get((change.get("target_table") or "").lower())
                        if expected_keys and change.get("display_fields") != expected_keys:
                            unresolved.append(f'{source["path"]}:{change["line_start"]}-{change["line_end"]}: insert keys {change.get("display_fields")} != {expected_keys}')
                        if re.search(r"第\d+行", change.get("display_description") or ""):
                            unresolved.append(f'{source["path"]}:{change["line_start"]}-{change["line_end"]}: insert description contains row labels')
                        expected_description = insert_description(change.get("display_description_rows", []))
                        if change.get("display_description") != expected_description:
                            unresolved.append(f'{source["path"]}:{change["line_start"]}-{change["line_end"]}: insert description rows were merged or deduplicated')
                    if operation == "update":
                        if re.search(r"\bWHERE\b", change.get("raw_sql") or "", re.I) and not change.get("display_description"):
                            unresolved.append(f'{source["path"]}:{change["line_start"]}-{change["line_end"]}: update WHERE values missing')
                        if not change.get("display_fields") or any("=" not in value for value in change["display_fields"]):
                            unresolved.append(f'{source["path"]}:{change["line_start"]}-{change["line_end"]}: update SET field/value pairs missing')
    if unresolved:
        raise ValueError(f"Data display extraction failed for {len(unresolved)} changes; examples: {unresolved[:10]}")

    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(XLSX_PATH) as archive:
        if archive.testzip() is not None:
            raise ValueError("XLSX ZIP validation failed")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet_names = [sheet.attrib["name"] for sheet in workbook.find("m:sheets", namespace)]
        expected_names = [report["branch"]["name"].replace("release/", "")[:31] for report in reports]
        if sheet_names != expected_names:
            raise ValueError(f"XLSX sheet names mismatch: {sheet_names} != {expected_names}")
        xlsx_counts = []
        for number in range(1, len(reports) + 1):
            sheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{number}.xml"))
            detail_rows = [row for row in sheet.findall(".//m:row", namespace) if row.attrib.get("outlineLevel") == "1" and len(row.findall("m:c", namespace)) == 23]
            xlsx_counts.append(len(detail_rows))
            for row in detail_rows:
                file_name = "".join(row.findall("m:c", namespace)[8].itertext())
                if "/" in file_name or "\\" in file_name:
                    raise ValueError("XLSX source-file fields must contain file names only")
        if xlsx_counts != expected_counts:
            raise ValueError(f"XLSX detail counts mismatch: {xlsx_counts} != {expected_counts}")
    return {"html_detail_counts": html_counts, "xlsx_detail_counts": xlsx_counts, "sheet_names": sheet_names, "updated_sql_comparison_count": len(updated_sql_adjustments), "independent_migration_adjustment_count": adjustment_count, "data_display": data_display}


def main():
    global ROOT, OUTPUT_ROOT, JSON_ROOT, HTML_PATH, REPORT_JSON_PATH, MIGRATION_ADJUSTMENTS_PATH, STATIC_HTML_PATH, XLSX_PATH, ASSET_ROOT, HTML_TEMPLATE_PATH
    args = parse_args()
    ROOT = Path(args.repo).resolve()
    OUTPUT_ROOT = Path(args.output_dir).resolve() if args.output_dir else DEFAULT_OUTPUT_ROOT
    JSON_ROOT = Path(args.analysis_json_dir).resolve() if args.analysis_json_dir else OUTPUT_ROOT / "json"
    HTML_PATH = OUTPUT_ROOT / "release-patch-change-analysis.html"
    REPORT_JSON_PATH = OUTPUT_ROOT / "release-patch-change-analysis.json"
    MIGRATION_ADJUSTMENTS_PATH = OUTPUT_ROOT / "release-patch-change-analysis-adjustments.json"
    STATIC_HTML_PATH = OUTPUT_ROOT / "release-patch-change-analysis-static.html"
    XLSX_PATH = OUTPUT_ROOT / "release-patch-change-analysis.xlsx"
    ASSET_ROOT = OUTPUT_ROOT
    HTML_TEMPLATE_PATH = Path(args.html_template).resolve() if args.html_template else None
    migration_source = Path(args.migration_source).resolve() if args.migration_source else None
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ROOT != DEFAULT_OUTPUT_ROOT:
        for asset in REPORT_ASSETS:
            source = DEFAULT_OUTPUT_ROOT / asset
            if source.is_file():
                shutil.copy2(source, OUTPUT_ROOT / asset)
    index, reports = load_reports()
    remap_branches = set(args.remap_migration_branch)
    if remap_branches and migration_source is None:
        raise ValueError("--remap-migration-branch requires an explicit --migration-source")
    migration_adjustments = load_migration_adjustments(migration_source, remap_branches)
    migration_metadata = load_migration_metadata(migration_source, remap_branches)
    compact = compact_reports(reports, migration_adjustments, migration_metadata)
    remap_stats = remap_migration_adjustments(compact, migration_source, remap_branches)
    imported_adjustments = sum(
        change.get("migration_adjustment", "无") != "无"
        for report in compact
        for directory in report.get("directories", [])
        for source in directory.get("files", [])
        for change in source.get("changes", [])
    )
    if migration_source is not None:
        imported_adjustments = write_migration_adjustments(compact)
    clear_embedded_migration_adjustments(compact)
    write_web_report(compact)
    write_xlsx(reports)
    validation = validate_outputs(reports)
    print(json.dumps({
        "branches": len(reports),
        "table_changes": index["totals"]["table_change_count"],
        "data_changes": index["totals"]["data_change_count"],
        "html": str(HTML_PATH.relative_to(ROOT)),
        "json": str(REPORT_JSON_PATH.relative_to(ROOT)),
        "static_html": str(STATIC_HTML_PATH.relative_to(ROOT)),
        "xlsx": str(XLSX_PATH.relative_to(ROOT)),
        "migration_source": str(migration_source) if migration_source else None,
        "migration_adjustments_json": str(MIGRATION_ADJUSTMENTS_PATH.relative_to(ROOT)),
        "imported_migration_adjustments": imported_adjustments,
        "migration_remap": remap_stats,
        "validation": validation,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
