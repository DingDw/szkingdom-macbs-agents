#!/usr/bin/env python3
"""Prepare MACBS config-data shell scripts for schema-based remote execution.

Run this tool on the remote MACBS configuration-data checkout. It creates
temporary execution copies for the standard schema and every configured broker
schema found under the selected full/patch mode, writes db_config_temp.ini,
creates temporary shell scripts that read db_config_temp.ini, and optionally
runs the generated temporary shell scripts. It never rewrites SQL and never
runs the config_diff data check automatically.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


CONFIG_TEMP_NAME = "db_config_temp.ini"
TEMP_SH_NAME = "fs_cbs_comm_temp.sh"
ORIGINAL_SH_NAME = "fs_cbs_comm.sh"

DB_IP = "10.201.69.44"
DB_PORT = "30100"
DB_PASSWORD = "SZtest30"
DB_NAME = "macbs_db"
STANDARD_EXTRA_DIR = "金证股份"
CONFIG_DIFF_TABLE = "config_diff"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "broker_schema_config.json"


@dataclass
class ExecutionGroup:
    name: str
    db_user: str
    source_dirs: list[Path]


@dataclass
class PreparedScript:
    group: str
    source_dir: Path
    work_dir: Path
    temp_script: Path
    db_user: str
    run_log: Path


@dataclass
class GroupRunResult:
    group: str
    returncode: int
    run_log: Path
    scripts: list[Path]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare all MACBS full/patch standard and broker fs_cbs_comm scripts with schema-specific db_config_temp.ini.",
    )
    parser.add_argument("--repo-root", required=True, help="Remote git checkout root, e.g. /home/ddw/ddw_config.")
    parser.add_argument("--mode", required=True, choices=("full", "patch"), help="Script mode to prepare.")
    parser.add_argument(
        "--broker-config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Broker/schema mapping JSON. Defaults to ../config/broker_schema_config.json beside this script.",
    )
    parser.add_argument(
        "--work-root",
        help="Temporary work root. Defaults to <repo-root>/.macbs_config_work/<timestamp>.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned temporary scripts without writing files.")
    parser.add_argument("--run", action="store_true", help="Run generated temporary shell scripts after preparation.")
    parser.add_argument(
        "--post-task-only",
        action="store_true",
        help="Only regenerate ddw_config.config_diff. Requires --work-root and does not prepare or run shell scripts.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Concurrent execution groups for --run. 0 means all groups in parallel.",
    )
    return parser.parse_args()


def load_broker_config(path: str) -> dict:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise SystemExit(f"broker config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config.get("broker_suffixes"), dict):
        raise SystemExit("broker config must contain object: broker_suffixes")
    if not isinstance(config.get("non_broker_dirs"), list):
        raise SystemExit("broker config must contain list: non_broker_dirs")
    if not config.get("db_user_prefix"):
        raise SystemExit("broker config must contain db_user_prefix")
    overlap = sorted(set(config["broker_suffixes"].keys()) & set(config["non_broker_dirs"]))
    if overlap:
        joined = "、".join(overlap)
        raise SystemExit(f"broker config has directories in both broker_suffixes and non_broker_dirs: {joined}")
    return config


def validate_args(args: argparse.Namespace) -> None:
    if args.run and args.dry_run:
        raise SystemExit("--run cannot be used with --dry-run")
    if args.post_task_only and (args.run or args.dry_run):
        raise SystemExit("--post-task-only cannot be used with --run or --dry-run")
    if args.post_task_only and not args.work_root:
        raise SystemExit("--post-task-only requires --work-root")
    if args.jobs < 0:
        raise SystemExit("--jobs must be greater than or equal to 0")


def mode_root(repo_root: Path, mode: str) -> Path:
    root = repo_root / "database" / "script" / mode
    if not root.is_dir():
        raise SystemExit(f"mode directory not found: {root}")
    return root


def scan_unknown_broker_dirs(root: Path, config: dict) -> None:
    configured = set(config["broker_suffixes"].keys())
    non_broker = set(config["non_broker_dirs"])
    unknown = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name not in configured and path.name not in non_broker
    )
    if unknown:
        joined = "、".join(unknown)
        raise SystemExit(
            f"found unconfigured broker directories under {root}: {joined}. "
            "Update broker_schema_config.json and create the corresponding schema before execution."
        )


def existing_broker_dirs(root: Path, config: dict) -> list[str]:
    return [broker for broker in config["broker_suffixes"].keys() if (root / broker).is_dir()]


def execution_groups(repo_root: Path, mode: str, config: dict) -> list[ExecutionGroup]:
    root = mode_root(repo_root, mode)
    scan_unknown_broker_dirs(root, config)

    db_user_prefix = config["db_user_prefix"]
    standard_source_dirs = [root / "gauss" / "fs_cbs"]
    standard_extra_dir = root / STANDARD_EXTRA_DIR / "gauss" / "fs_cbs"
    if (standard_extra_dir / ORIGINAL_SH_NAME).is_file():
        standard_source_dirs.append(standard_extra_dir)

    groups = [
        ExecutionGroup(
            name="standard",
            db_user=db_user_prefix,
            source_dirs=standard_source_dirs,
        )
    ]

    for broker in existing_broker_dirs(root, config):
        suffix = config["broker_suffixes"][broker]
        groups.append(
            ExecutionGroup(
                name=f"broker_{broker}",
                db_user=f"{db_user_prefix}_{suffix}",
                source_dirs=[
                    root / "gauss" / "fs_cbs",
                    root / broker / "gauss" / "fs_cbs",
                ],
            )
        )
    return groups


def ensure_source_dirs_exist(groups: list[ExecutionGroup]) -> None:
    missing: list[str] = []
    for group in groups:
        for directory in group.source_dirs:
            script = directory / ORIGINAL_SH_NAME
            if not directory.is_dir():
                missing.append(f"[{group.name}] directory not found: {directory}")
            elif not script.is_file():
                missing.append(f"[{group.name}] script not found: {script}")
    if missing:
        raise SystemExit("\n".join(missing))


def make_work_root(repo_root: Path, work_root_arg: str | None) -> Path:
    if work_root_arg:
        return Path(work_root_arg).expanduser().resolve()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return repo_root / ".macbs_config_work" / stamp


def read_text_with_encoding(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8", "gb18030", "latin1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin1"), "latin1"


def write_text_with_encoding(path: Path, text: str, encoding: str) -> None:
    path.write_bytes(text.encode(encoding, errors="replace"))


def config_text(db_user: str) -> str:
    return (
        "[COMM]\n"
        f"DB_IP={DB_IP}\n"
        f"DB_PORT={DB_PORT}\n"
        f"DB_USER={db_user}\n"
        f"DB_PASSWORD={DB_PASSWORD}\n"
        f"DB_NAME={DB_NAME}\n"
    )


def write_temp_config(script_dir: Path, db_user: str) -> Path:
    config_path = script_dir / CONFIG_TEMP_NAME
    with config_path.open("w", encoding="utf-8", newline="\n") as config_file:
        config_file.write(config_text(db_user))
    return config_path


def write_temp_shell(script_dir: Path) -> Path:
    source = script_dir / ORIGINAL_SH_NAME
    text, encoding = read_text_with_encoding(source)
    rewritten = text.replace("db_config.ini", CONFIG_TEMP_NAME)
    temp_script = script_dir / TEMP_SH_NAME
    write_text_with_encoding(temp_script, rewritten, encoding)
    mode = temp_script.stat().st_mode
    temp_script.chmod(mode | 0o111)
    return temp_script


def copy_script_dir(source_dir: Path, work_root: Path, repo_root: Path, group_name: str) -> Path:
    relative = source_dir.relative_to(repo_root)
    destination = work_root / group_name / relative
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, destination)
    return destination


def prepare_scripts(args: argparse.Namespace) -> list[PreparedScript]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    config = load_broker_config(args.broker_config)
    groups = execution_groups(repo_root, args.mode, config)
    ensure_source_dirs_exist(groups)

    work_root = make_work_root(repo_root, args.work_root)
    prepared: list[PreparedScript] = []

    for group in groups:
        for source_dir in group.source_dirs:
            relative = source_dir.relative_to(repo_root)
            work_dir = work_root / group.name / relative
            temp_script = work_dir / TEMP_SH_NAME
            run_log = work_root / group.name / "run.log"
            if not args.dry_run and not args.post_task_only:
                work_dir = copy_script_dir(source_dir, work_root, repo_root, group.name)
                write_temp_config(work_dir, group.db_user)
                temp_script = write_temp_shell(work_dir)
            prepared.append(
                PreparedScript(
                    group=group.name,
                    source_dir=source_dir,
                    work_dir=work_dir,
                    temp_script=temp_script,
                    db_user=group.db_user,
                    run_log=run_log,
                )
            )
    return prepared


def group_prepared_scripts(prepared: list[PreparedScript]) -> dict[str, list[PreparedScript]]:
    grouped: dict[str, list[PreparedScript]] = {}
    for item in prepared:
        grouped.setdefault(item.group, []).append(item)
    return grouped


def run_group(group: str, scripts: list[PreparedScript]) -> GroupRunResult:
    run_log = scripts[0].run_log
    run_log.parent.mkdir(parents=True, exist_ok=True)
    with run_log.open("w", encoding="utf-8", newline="\n") as log_file:
        log_file.write(f"START group={group} scripts={len(scripts)}\n")
        for item in scripts:
            log_file.write(f"RUN {item.temp_script}\n")
            log_file.flush()
            result = subprocess.run(
                ["bash", item.temp_script.name],
                cwd=item.work_dir,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            if result.returncode != 0:
                log_file.write(f"FAIL {item.temp_script} returncode={result.returncode}\n")
                return GroupRunResult(
                    group=group,
                    returncode=result.returncode,
                    run_log=run_log,
                    scripts=[script.temp_script for script in scripts],
                )
            log_file.write(f"DONE {item.temp_script}\n")
            log_file.flush()
        log_file.write(f"DONE group={group}\n")
    return GroupRunResult(group=group, returncode=0, run_log=run_log, scripts=[item.temp_script for item in scripts])


def run_prepared(prepared: list[PreparedScript], jobs: int) -> None:
    grouped = group_prepared_scripts(prepared)
    max_workers = len(grouped) if jobs == 0 else min(jobs, len(grouped))
    print(f"RUN groups in parallel: groups={len(grouped)} jobs={max_workers}")

    failures: list[GroupRunResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_group, group, scripts): group
            for group, scripts in grouped.items()
        }
        for future in concurrent.futures.as_completed(futures):
            group = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                print(f"FAIL group={group} error={exc}")
                raise
            if result.returncode == 0:
                print(f"DONE group={result.group} log={result.run_log}")
            else:
                print(f"FAIL group={result.group} returncode={result.returncode} log={result.run_log}")
                failures.append(result)

    if failures:
        details = "\n".join(
            f"[{failure.group}] returncode={failure.returncode} log={failure.run_log}"
            for failure in failures
        )
        raise SystemExit(f"one or more execution groups failed:\n{details}")


def work_root_from_prepared(prepared: list[PreparedScript]) -> Path:
    if not prepared:
        raise SystemExit("no prepared scripts")
    return prepared[0].run_log.parent.parent


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def broker_targets_from_prepared(prepared: list[PreparedScript]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in prepared:
        if not item.group.startswith("broker_") or item.group in seen:
            continue
        seen.add(item.group)
        targets.append((item.group[len("broker_") :], item.db_user))
    return targets


def config_diff_sql(mode: str, run_id: str, standard_schema: str, brokers: list[tuple[str, str]]) -> str:
    broker_values = ",\n        ".join(
        f"({sql_literal(broker_name)}, {sql_literal(broker_schema)})"
        for broker_name, broker_schema in brokers
    )
    if not broker_values:
        broker_values = "('__NO_BROKER__', '__NO_BROKER_SCHEMA__')"

    return f"""\\set ON_ERROR_STOP on
DROP TABLE IF EXISTS {standard_schema}.{CONFIG_DIFF_TABLE};

CREATE TABLE {standard_schema}.{CONFIG_DIFF_TABLE} (
    run_id varchar(32),
    mode varchar(16),
    broker_name varchar(64),
    standard_schema varchar(64),
    broker_schema varchar(64),
    table_name varchar(128),
    diff_type varchar(32),
    standard_rows bigint,
    broker_rows bigint,
    detail varchar(1024),
    created_at timestamp default current_timestamp
);

DO $$
DECLARE
    v_run_id text := {sql_literal(run_id)};
    v_mode text := {sql_literal(mode)};
    v_standard_schema text := {sql_literal(standard_schema)};
    v_standard_count bigint;
    v_broker_count bigint;
    v_has_diff boolean;
    v_standard_signature text;
    v_broker_signature text;
    v_broker_schema text;
    broker record;
    tbl record;
BEGIN
    FOR broker IN
        SELECT broker_name, broker_schema
        FROM (VALUES
        {broker_values}
        ) AS b(broker_name, broker_schema)
        WHERE broker_schema <> '__NO_BROKER_SCHEMA__'
    LOOP
        v_broker_schema := broker.broker_schema;

        FOR tbl IN
            SELECT
                coalesce(s.table_name, b.table_name) AS table_name,
                s.table_name IS NOT NULL AS standard_exists,
                b.table_name IS NOT NULL AS broker_exists
            FROM (
                SELECT tablename AS table_name
                FROM pg_tables
                WHERE schemaname = v_standard_schema
                  AND tablename <> {sql_literal(CONFIG_DIFF_TABLE)}
            ) s
            FULL JOIN (
                SELECT tablename AS table_name
                FROM pg_tables
                WHERE schemaname = v_broker_schema
            ) b ON s.table_name = b.table_name
            ORDER BY coalesce(s.table_name, b.table_name)
        LOOP
            v_standard_count := NULL;
            v_broker_count := NULL;

            IF NOT tbl.standard_exists THEN
                EXECUTE 'SELECT count(*) FROM ' || quote_ident(v_broker_schema) || '.' || quote_ident(tbl.table_name)
                    INTO v_broker_count;
                INSERT INTO {standard_schema}.{CONFIG_DIFF_TABLE}
                    (run_id, mode, broker_name, standard_schema, broker_schema, table_name, diff_type, standard_rows, broker_rows, detail)
                VALUES
                    (v_run_id, v_mode, broker.broker_name, v_standard_schema, v_broker_schema, tbl.table_name,
                     'only_in_broker', NULL, v_broker_count, 'table exists only in broker schema');
                CONTINUE;
            END IF;

            IF NOT tbl.broker_exists THEN
                EXECUTE 'SELECT count(*) FROM ' || quote_ident(v_standard_schema) || '.' || quote_ident(tbl.table_name)
                    INTO v_standard_count;
                INSERT INTO {standard_schema}.{CONFIG_DIFF_TABLE}
                    (run_id, mode, broker_name, standard_schema, broker_schema, table_name, diff_type, standard_rows, broker_rows, detail)
                VALUES
                    (v_run_id, v_mode, broker.broker_name, v_standard_schema, v_broker_schema, tbl.table_name,
                     'only_in_standard', v_standard_count, NULL, 'table exists only in standard schema');
                CONTINUE;
            END IF;

            SELECT string_agg(
                       column_name || ':' || data_type || ':' ||
                       coalesce(character_maximum_length::text, '') || ':' ||
                       coalesce(numeric_precision::text, '') || ':' ||
                       coalesce(numeric_scale::text, '') || ':' ||
                       is_nullable,
                       ',' ORDER BY ordinal_position
                   )
              INTO v_standard_signature
              FROM information_schema.columns
             WHERE table_schema = v_standard_schema
               AND table_name = tbl.table_name;

            SELECT string_agg(
                       column_name || ':' || data_type || ':' ||
                       coalesce(character_maximum_length::text, '') || ':' ||
                       coalesce(numeric_precision::text, '') || ':' ||
                       coalesce(numeric_scale::text, '') || ':' ||
                       is_nullable,
                       ',' ORDER BY ordinal_position
                   )
              INTO v_broker_signature
              FROM information_schema.columns
             WHERE table_schema = v_broker_schema
               AND table_name = tbl.table_name;

            EXECUTE 'SELECT count(*) FROM ' || quote_ident(v_standard_schema) || '.' || quote_ident(tbl.table_name)
                INTO v_standard_count;
            EXECUTE 'SELECT count(*) FROM ' || quote_ident(v_broker_schema) || '.' || quote_ident(tbl.table_name)
                INTO v_broker_count;

            IF coalesce(v_standard_signature, '') <> coalesce(v_broker_signature, '') THEN
                INSERT INTO {standard_schema}.{CONFIG_DIFF_TABLE}
                    (run_id, mode, broker_name, standard_schema, broker_schema, table_name, diff_type, standard_rows, broker_rows, detail)
                VALUES
                    (v_run_id, v_mode, broker.broker_name, v_standard_schema, v_broker_schema, tbl.table_name,
                     'structure_diff', v_standard_count, v_broker_count, 'column definition/order differs');
                CONTINUE;
            END IF;

            IF v_standard_count <> v_broker_count THEN
                INSERT INTO {standard_schema}.{CONFIG_DIFF_TABLE}
                    (run_id, mode, broker_name, standard_schema, broker_schema, table_name, diff_type, standard_rows, broker_rows, detail)
                VALUES
                    (v_run_id, v_mode, broker.broker_name, v_standard_schema, v_broker_schema, tbl.table_name,
                     'data_diff', v_standard_count, v_broker_count, 'row count differs');
                CONTINUE;
            END IF;

            BEGIN
                EXECUTE
                    'SELECT EXISTS (' ||
                    'SELECT 1 FROM (' ||
                    '(SELECT * FROM ' || quote_ident(v_standard_schema) || '.' || quote_ident(tbl.table_name) ||
                    ' EXCEPT SELECT * FROM ' || quote_ident(v_broker_schema) || '.' || quote_ident(tbl.table_name) || ')' ||
                    ' UNION ALL ' ||
                    '(SELECT * FROM ' || quote_ident(v_broker_schema) || '.' || quote_ident(tbl.table_name) ||
                    ' EXCEPT SELECT * FROM ' || quote_ident(v_standard_schema) || '.' || quote_ident(tbl.table_name) || ')' ||
                    ') d LIMIT 1)'
                    INTO v_has_diff;

                IF v_has_diff THEN
                    INSERT INTO {standard_schema}.{CONFIG_DIFF_TABLE}
                        (run_id, mode, broker_name, standard_schema, broker_schema, table_name, diff_type, standard_rows, broker_rows, detail)
                    VALUES
                        (v_run_id, v_mode, broker.broker_name, v_standard_schema, v_broker_schema, tbl.table_name,
                         'data_diff', v_standard_count, v_broker_count, 'row content differs');
                END IF;
            EXCEPTION WHEN OTHERS THEN
                INSERT INTO {standard_schema}.{CONFIG_DIFF_TABLE}
                    (run_id, mode, broker_name, standard_schema, broker_schema, table_name, diff_type, standard_rows, broker_rows, detail)
                VALUES
                    (v_run_id, v_mode, broker.broker_name, v_standard_schema, v_broker_schema, tbl.table_name,
                     'compare_error', v_standard_count, v_broker_count, SQLERRM);
            END;
        END LOOP;
    END LOOP;
END $$;
"""


def run_config_diff_post_task(prepared: list[PreparedScript], mode: str) -> None:
    brokers = broker_targets_from_prepared(prepared)
    work_root = work_root_from_prepared(prepared)
    run_id = work_root.name
    standard_schema = prepared[0].db_user
    sql_path = work_root / "config_diff.sql"
    log_path = work_root / "config_diff.log"

    with sql_path.open("w", encoding="utf-8", newline="\n") as sql_file:
        sql_file.write(config_diff_sql(mode, run_id, standard_schema, brokers))
    print(f"RUN post-task config_diff brokers={len(brokers)} sql={sql_path} log={log_path}")

    with log_path.open("w", encoding="utf-8", newline="\n") as log_file:
        result = subprocess.run(
            [
                "gsql",
                "-h",
                DB_IP,
                "-p",
                DB_PORT,
                "-d",
                DB_NAME,
                "-U",
                standard_schema,
                "-W",
                DB_PASSWORD,
                "-f",
                str(sql_path),
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    if result.returncode != 0 or "ERROR" in log_text:
        raise SystemExit(f"config_diff post-task failed: returncode={result.returncode} log={log_path}")
    print(f"DONE post-task config_diff log={log_path}")


def print_post_task_prompt(args: argparse.Namespace, prepared: list[PreparedScript]) -> None:
    work_root = work_root_from_prepared(prepared)
    command = (
        "python3 .macbs_config_tools/prepare_config_run.py "
        f"--repo-root {args.repo_root} "
        f"--broker-config {args.broker_config} "
        f"--mode {args.mode} "
        f"--post-task-only --work-root {work_root}"
    )
    print("POST-TASK PENDING: config_diff data check was not run automatically because it can take a long time.")
    print("Ask the user whether to run the data check before executing the following command:")
    print(command)


def print_summary(prepared: list[PreparedScript], dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "PREPARED"
    print(f"{mode} scripts:")
    for item in prepared:
        print(f"- group:  {item.group}")
        print(f"  source: {item.source_dir}")
        print(f"  work:   {item.work_dir}")
        print(f"  temp:   {item.temp_script}")
        print(f"  config: {CONFIG_TEMP_NAME}")
        print(f"  DB_USER={item.db_user}")
        print(f"  runlog: {item.run_log}")
        print("  sql:    not rewritten")
    print(
        f"post-task(optional): recreate {prepared[0].db_user}.{CONFIG_DIFF_TABLE} only after the user confirms it"
    )


def main() -> int:
    args = parse_args()
    validate_args(args)
    prepared = prepare_scripts(args)
    print_summary(prepared, args.dry_run)
    if args.post_task_only:
        run_config_diff_post_task(prepared, args.mode)
        return 0
    if args.run:
        run_prepared(prepared, args.jobs)
        print_post_task_prompt(args, prepared)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
