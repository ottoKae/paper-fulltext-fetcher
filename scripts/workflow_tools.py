from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import paper_fulltext_fetcher as helper
from campus_support import CHANNELS, STOP_STATUSES, RouteLedger, domain, local_endpoint, write_exclusive


def output_root(config_path):
    config = helper.load_config(config_path)
    return helper.resolve_local_path(config.get("project", {}).get("output_root", "outputs/acquisition"), config_path.resolve().parent)


def invoke(command, arguments):
    args = helper.build_parser().parse_args([command, *[str(value) for value in arguments]])
    with contextlib.redirect_stdout(io.StringIO()):
        return args.function(args)


def browser_call(config, action, hosts, target=None, label=None):
    endpoint = local_endpoint(config.get("browser", {}).get("cdp_endpoint", ""))
    node = shutil.which("node")
    if not node:
        raise ValueError("Node.js with built-in WebSocket is required for optional CDP assistance")
    options = {"endpoint": endpoint, "action": action, "hosts": hosts, "target": target, "label": label}
    try:
        result = subprocess.run([node, str(Path(__file__).with_name("browser_bridge.mjs")), json.dumps(options)], capture_output=True, text=True, encoding="utf-8", timeout=50)
    except subprocess.TimeoutExpired:
        return {"status": "browser_timeout"}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "browser_error", "reason": "bridge_did_not_return_json"}


def probe(args):
    if not args.allow_browser:
        raise ValueError("Explicit --allow-browser consent is required; this command only inspects an existing session")
    result = browser_call(helper.load_config(args.config), "inspect" if args.target else "probe", [domain(host) for host in args.allow_host], args.target)
    if args.output:
        write_exclusive(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"connected_not_authenticated", "observed_not_downloaded"} else (3 if result["status"] == "challenge_or_block" else 2)


def route(args):
    ledger = RouteLedger(output_root(args.config) / "access")
    if args.action == "recover":
        ledger.recover(args.host, args.channel, args.evidence, args.user_confirmed)
    elif args.action == "stop":
        if not args.reason or not args.evidence or not args.evidence.is_file():
            raise ValueError("A reason and saved evidence file are required")
        ledger.record(args.host, args.channel, args.reason, evidence_sha256=helper.sha256_file(args.evidence))
    print(json.dumps(ledger.state(args.host, args.channel), indent=2))
    return 0


def strong_identity(path, record):
    text, detail = helper.pdf_text(path, max_pages=2)
    valid, identity = helper.pdf_identity(text, record)
    return valid, {**identity, "parse_detail": detail}


def stable_pdfs(directory, previous, minimum_bytes):
    current = {}
    ready = []
    for path in sorted(directory.glob("*")):
        if not path.is_file() or path.is_symlink() or path.suffix.casefold() != ".pdf":
            continue
        stat = path.stat()
        fingerprint = (stat.st_size, stat.st_mtime_ns)
        current[path] = fingerprint
        if previous.get(path) == fingerprint and stat.st_size >= minimum_bytes:
            ready.append(path)
    return current, ready


def audit(config_path, directory):
    minimum_bytes = int(helper.load_config(config_path).get("identity", {}).get("minimum_pdf_bytes", 10000))
    invoke("audit", ["--config", config_path, "--output-dir", directory, "--minimum-pdf-bytes", minimum_bytes])
    with (directory / "records.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(helper.csv.DictReader(stream))


def receive(args):
    config = helper.load_config(args.config)
    base = args.config.resolve().parent
    value = args.inbox or config.get("browser", {}).get("downloads_dir") or config.get("project", {}).get("manual_inbox")
    if not value:
        raise ValueError("Configure the actual browser download directory or provide --inbox")
    inbox = helper.resolve_local_path(Path(value).expanduser(), base).resolve()
    if not inbox.is_dir() or not 0 <= args.wait_seconds <= 300 or not 0.1 <= args.poll_seconds <= 10:
        raise ValueError("Existing inbox and bounded wait/poll intervals required")
    input_path = helper.resolve_local_path(config["project"]["input"], base)
    records = helper.load_records(input_path, config["project"].get("sheet"), config.get("columns"))
    if len({record["record_id"] for record in records}) != len(records) or len({record["expected_filename"].casefold() for record in records}) != len(records):
        raise ValueError("Resolve duplicate IDs or destination filenames before acquisition")
    matches = [record for record in records if record["record_id"] == args.record_id]
    if len(matches) != 1:
        raise ValueError("Select exactly one known record ID")
    record = matches[0]
    if args.target and (not args.allow_browser or not args.allow_host or not args.label):
        raise ValueError("Browser click requires explicit consent, allowed hosts and observed PDF control label")
    if not args.execute:
        print(json.dumps({"mode": "dry_run", "record_id": args.record_id, "inbox_exists": True, "browser_click": bool(args.target), "wait_seconds": args.wait_seconds, "network_requested": False}))
        return 0
    root = output_root(args.config)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "browser-receive.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write("One receiver per workspace. Remove only after confirming an interrupted receiver has stopped.\n")
    directory = root / "browser-runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8])
    result = {"record_id": args.record_id, "status": "started", "started_utc": helper.utcnow()}
    ledger = RouteLedger(root / "access")
    route_host = None
    route_started = False
    try:
        write_exclusive(directory / "started.json", {**result, "input_sha256": helper.sha256_file(input_path), "config_sha256": helper.sha256_file(args.config), "helper_version": helper.VERSION, "tool_sha256": {name: helper.sha256_file(Path(__file__).with_name(name)) for name in ("workflow_tools.py", "browser_bridge.mjs", "campus_support.py", "paper_fulltext_fetcher.py")}})
        before_rows = audit(args.config, directory / "audit-before")
        existing = next(row for row in before_rows if row["record_id"] == args.record_id)
        if existing["status"] in helper.SUCCESS_STATUSES:
            result.update(status="already_present", sha256=existing["sha256"])
            return 0
        wanted = directory / "wanted.csv"
        helper.write_csv(wanted, [record])
        minimum_bytes = int(config.get("identity", {}).get("minimum_pdf_bytes", 10000))
        has_saved_pdf = False
        if args.target:
            observed_files, _ = stable_pdfs(inbox, {}, minimum_bytes)
            time.sleep(args.poll_seconds)
            _, candidates = stable_pdfs(inbox, observed_files, minimum_bytes)
            has_saved_pdf = any(candidate.stat().st_size <= args.max_bytes and helper.validate_pdf(candidate, record, minimum_bytes)[0] and strong_identity(candidate, record)[0] for candidate in candidates)
        if args.target and not has_saved_pdf:
            hosts = [domain(host) for host in args.allow_host]
            observed = browser_call(config, "inspect", hosts, args.target)
            write_exclusive(directory / "browser-inspect.json", observed)
            route_host = observed.get("target", {}).get("host")
            if observed["status"] == "challenge_or_block":
                result["status"] = "challenge_or_block"
                if route_host:
                    ledger.record(route_host, "browser", "challenge_or_block", record_id=args.record_id)
                return 3
            if observed["status"] != "observed_not_downloaded":
                result["status"] = observed["status"]
                return 2
            state = observed["before"]
            front = state.get("title", "") + " " + state.get("text", "")
            coverage, matched = helper.title_score(front, record["title"])
            if not (record["doi"] and record["doi"] in front.casefold() or coverage >= 0.95 and matched >= 5):
                raise ValueError("Visible article does not match the selected record; no click performed")
            ledger.begin(route_host, "browser")
            route_started = True
            clicked = browser_call(config, "click", hosts, args.target, args.label)
            write_exclusive(directory / "browser-click.json", clicked)
            if clicked["status"] == "challenge_or_block":
                result["status"] = "challenge_or_block"
                return 3
            if not clicked.get("click", {}).get("clicked"):
                result["status"] = "manual_required"
                return 2
        deadline = time.monotonic() + args.wait_seconds
        previous = {}
        inspected = {}
        while True:
            current, candidates = stable_pdfs(inbox, previous, minimum_bytes)
            for candidate in candidates:
                if inspected.get(candidate) == current[candidate]:
                    continue
                inspected[candidate] = current[candidate]
                if candidate.stat().st_size > args.max_bytes:
                    continue
                valid, detail, _ = helper.validate_pdf(candidate, record, minimum_bytes)
                identity_valid, identity = strong_identity(candidate, record) if valid else (False, {})
                if not identity_valid:
                    continue
                staged = directory / "inbox"
                staged.mkdir(exist_ok=False)
                source_hash = helper.sha256_file(candidate)
                shutil.copyfile(candidate, staged / record["expected_filename"])
                if helper.sha256_file(staged / record["expected_filename"]) != source_hash or helper.sha256_file(candidate) != source_hash:
                    raise ValueError("Source changed during staging; not imported")
                write_exclusive(directory / "source.json", {"record_id": args.record_id, "sha256": source_hash, "bytes": candidate.stat().st_size, "identity": identity, "validation": detail, "source_location": "configured_download_directory"})
                arguments = ["--config", args.config, "--remaining", wanted, "--inbox", staged, "--log-dir", directory / "import-plan", "--minimum-pdf-bytes", minimum_bytes]
                if invoke("import", [*arguments, "--dry-run"]) != 0:
                    raise ValueError("Import dry-run failed")
                arguments[arguments.index(directory / "import-plan")] = directory / "import"
                if invoke("import", arguments) != 0:
                    raise ValueError("Import failed")
                after = audit(args.config, directory / "audit-after")
                verified = next(row for row in after if row["record_id"] == args.record_id)
                if verified["status"] != "valid_pdf" or verified["sha256"] != source_hash:
                    raise ValueError("Final audit did not confirm the received PDF")
                shutil.copytree(directory / "audit-after", root / "audit", dirs_exist_ok=True)
                result.update(status="valid_pdf", sha256=source_hash, output_file=verified["fulltext_file"])
                return 0
            if time.monotonic() >= deadline:
                result["status"] = "watch_timeout"
                return 2
            previous = current
            time.sleep(min(args.poll_seconds, max(0, deadline - time.monotonic())))
    except BaseException as error:
        result.update(status="local_execution_error", error_type=type(error).__name__)
        raise
    finally:
        if route_started:
            ledger.record(route_host, "browser", result["status"], record_id=args.record_id)
        result["finished_utc"] = helper.utcnow()
        write_exclusive(directory / "finished.json", result)
        lock.unlink(missing_ok=True)
        print(json.dumps({**result, "receipt": directory.relative_to(base).as_posix() if directory.is_relative_to(base) else directory.name}, ensure_ascii=False))


def search_register(args):
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    runs = manifest.get("searches", [])
    if not runs:
        raise ValueError("Manifest must contain one or more searches")
    prepared = []
    for entry in runs:
        for key in ("database", "platform", "query", "fields", "filters", "searched_at", "export_file", "reported_hits", "truncated"):
            if key not in entry:
                raise ValueError("Missing search field: " + key)
        when = datetime.fromisoformat(entry["searched_at"])
        if when.tzinfo is None or type(entry["truncated"]) is not bool or type(entry["reported_hits"]) is not int or entry["reported_hits"] < 0:
            raise ValueError("Use a timezone-aware search time, boolean truncation and nonnegative hit count")
        source = helper.resolve_local_path(entry["export_file"], args.manifest.resolve().parent)
        _, rows, _ = helper.read_table(source, entry.get("sheet"))
        records = [helper.canonical_record(row, index + 2, entry.get("columns")) for index, row in enumerate(rows)]
        if any(not record["title"] and not record["doi"] for record in records):
            raise ValueError("Export records require a title or DOI")
        if len(records) > entry["reported_hits"] or len(records) < entry["reported_hits"] and not entry["truncated"]:
            raise ValueError("Export count disagrees with hit count/truncation declaration")
        prepared.append((entry, source, records, helper.sha256_file(source)))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    aggregated = []
    seen_dois = {}
    provenance = []
    searches = []
    for index, (entry, source, records, source_hash) in enumerate(prepared, 1):
        raw = args.output_dir / "raw" / (f"search-{index:03d}" + source.suffix.lower())
        raw.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, raw)
        if helper.sha256_file(raw) != source_hash or helper.sha256_file(source) != source_hash:
            raise ValueError("Search export changed during registration")
        search_id = f"search-{index:03d}-{source_hash[:12]}"
        searches.append({**{key: value for key, value in entry.items() if key != "export_file"}, "search_id": search_id, "export_file": raw.relative_to(args.output_dir).as_posix(), "export_sha256": source_hash, "exported_records": len(records)})
        for row_number, record in enumerate(records, 1):
            identifier = seen_dois.get(record["doi"]) if record["doi"] else None
            duplicate = bool(identifier)
            if not identifier:
                identifier = helper.stable_record_id(record["title"], record["doi"], record["year"]) if record["doi"] else f"{search_id}-row-{row_number:06d}"
                aggregated.append({**record, "record_id": identifier, "expected_filename": identifier + ".pdf"})
                if record["doi"]:
                    seen_dois[record["doi"]] = identifier
            provenance.append({"record_id": identifier, "search_id": search_id, "source_row": row_number, "source_record_id": record["record_id"], "duplicate_exact_doi": duplicate, "source_metadata": record})
    helper.write_csv(args.output_dir / "bibliography.csv", aggregated)
    write_exclusive(args.output_dir / "search_runs.json", {"helper_version": helper.VERSION, "searches": searches, "input_manifest_sha256": helper.sha256_file(args.manifest), "exact_doi_dedup_only": True})
    write_exclusive(args.output_dir / "provenance.json", provenance)
    print(json.dumps({"searches": len(searches), "exported_rows": len(provenance), "unique_records": len(aggregated), "unperformed_network_search": True}))
    return 0


def build_parser():
    import batch_pipeline
    import library_tools

    parser = argparse.ArgumentParser(description="Portable campus acquisition and search-evidence helpers")
    commands = parser.add_subparsers(dest="command", required=True)
    batch = commands.add_parser("batch", help="Preview or resume an approved acquisition, local Docling and immutable library batch")
    batch.add_argument("--config", type=Path, required=True)
    batch.add_argument("--output-dir", type=Path, required=True)
    batch.add_argument("--approved-sources", type=Path)
    batch.add_argument("--allow-host", action="append", default=[])
    batch.add_argument("--delay", type=float, default=60)
    batch.add_argument("--limit", type=int, default=10)
    batch.add_argument("--previous-snapshot", type=Path)
    batch.add_argument("--execute", action="store_true")
    batch.add_argument("--resume", action="store_true")
    batch.add_argument("--skip-structure", action="store_true")
    batch.add_argument("--no-tables", action="store_true")
    batch.set_defaults(function=batch_pipeline.run)
    archive = commands.add_parser("archive", help="Copy audited originals and assessed derived files into a new immutable library")
    archive.add_argument("--config", type=Path, required=True)
    archive.add_argument("--audit", type=Path)
    archive.add_argument("--output-dir", type=Path, required=True)
    archive.add_argument("--profile", default="base")
    archive.add_argument("--sources-metadata", type=Path)
    archive.add_argument("--previous-snapshot", type=Path)
    archive.add_argument("--execute", action="store_true")
    archive.set_defaults(function=library_tools.archive)
    archive_verify = commands.add_parser("archive-verify", help="Verify archive hashes, metadata, chunk locators and local search index")
    archive_verify.add_argument("--snapshot", type=Path, required=True)
    archive_verify.set_defaults(function=library_tools.verify)
    search_library = commands.add_parser("library-search", help="Search local SQLite full text and return source locators")
    search_library.add_argument("--snapshot", type=Path, required=True)
    search_library.add_argument("--query", required=True)
    search_library.add_argument("--limit", type=int, default=10)
    search_library.set_defaults(function=library_tools.search)
    browser_probe = commands.add_parser("browser-probe", help="Read an explicitly authorized existing local browser; does not log in")
    browser_probe.add_argument("--config", type=Path, required=True)
    browser_probe.add_argument("--allow-browser", action="store_true")
    browser_probe.add_argument("--allow-host", action="append", required=True)
    browser_probe.add_argument("--target", help="Inspect an already observed article tab without clicking or navigating")
    browser_probe.add_argument("--output", type=Path)
    browser_probe.set_defaults(function=probe)
    receiver = commands.add_parser("browser-receive", help="Receive one matching PDF, import, and audit; optional existing-page click")
    receiver.add_argument("--config", type=Path, required=True)
    receiver.add_argument("--record-id", required=True)
    receiver.add_argument("--inbox", type=Path)
    receiver.add_argument("--execute", action="store_true")
    receiver.add_argument("--wait-seconds", type=float, default=90)
    receiver.add_argument("--poll-seconds", type=float, default=2)
    receiver.add_argument("--max-bytes", type=int, default=100 * 1024 * 1024)
    receiver.add_argument("--target")
    receiver.add_argument("--label")
    receiver.add_argument("--allow-browser", action="store_true")
    receiver.add_argument("--allow-host", action="append", default=[])
    receiver.set_defaults(function=receive)
    routes = commands.add_parser("route", help="Inspect a channel stop or authorize one evidenced recovery probe")
    routes.add_argument("action", choices=("status", "stop", "recover"))
    routes.add_argument("--config", type=Path, required=True)
    routes.add_argument("--host", type=domain, required=True)
    routes.add_argument("--channel", choices=sorted(CHANNELS), required=True)
    routes.add_argument("--reason", choices=sorted(STOP_STATUSES))
    routes.add_argument("--evidence", type=Path)
    routes.add_argument("--user-confirmed", action="store_true")
    routes.set_defaults(function=route)
    search = commands.add_parser("search-register", help="Freeze completed search exports and deduplicate exact DOIs; no network search")
    search.add_argument("--manifest", type=Path, required=True)
    search.add_argument("--output-dir", type=Path, required=True)
    search.set_defaults(function=search_register)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        return args.function(args)
    except KeyboardInterrupt:
        print("Interrupted; existing receipts remain available", file=sys.stderr)
        return 130
    except Exception as error:
        print(helper.redact_error_message(f"{type(error).__name__}: {error}"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
