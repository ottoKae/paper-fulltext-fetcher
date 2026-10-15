from __future__ import annotations

import json
import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import paper_fulltext_fetcher as helper
from campus_support import RouteLedger, write_exclusive
from corpus_pipeline.common import read_csv, runtime_paths
from library_tools import build_library, local_file
from release_tools import manifest_paths

VERSIONS = {'published', 'accepted_manuscript', 'preprint', 'author_copy', 'repository_copy', 'fulltext_xml'}


def approved_sources(path, records, hosts):
    by_id = {row['record_id']: row for row in records}
    selected = helper.approved_rows(path) if path else []
    if path:
        declared = [row for row in read_csv(path) if row.get('approved', '').casefold() == 'true']
        if len(declared) != len(selected):
            raise ValueError('Approved rows require a valid approval_scope; do not silently skip malformed approvals')
    seen = set()
    for row in selected:
        identifier = row['record_id']
        if identifier not in by_id or identifier in seen:
            raise ValueError('Approved sources need one known record per ID; select alternatives in a new reviewed batch')
        seen.add(identifier)
        canonical = helper.canonical_record(row, int(row.get('excel_row') or 2))
        if any(canonical[key] != by_id[identifier][key] for key in ('doi', 'title', 'expected_filename')):
            raise ValueError('Approved metadata or destination differs from the frozen bibliography')
        if row.get('report_role') != 'primary' or row.get('source_version') not in VERSIONS or not row.get('license_evidence', '').strip():
            raise ValueError('Explicit primary-report role, supported source version and lawful-source evidence required')
        parsed = urlsplit(row['candidate_url'])
        if parsed.scheme not in {'http', 'https'} or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('Expected an approved HTTP host without credentials or fragment')
        if any(re.search(r'token|signature|credential|password|api.?key|authorization|^sig$|^auth$|^key$|expires', key, re.I) for key, _ in parse_qsl(parsed.query)):
            raise ValueError('Do not freeze credential-bearing or temporary signed URLs')
    return sorted(selected, key=lambda row: (row.get('publisher', '').casefold(), row['record_id']))


def run(args):
    runtime = runtime_paths(args.config)
    input_path = helper.resolve_local_path(runtime.config['project']['input'], runtime.workspace)
    records = helper.load_records(input_path, runtime.config['project'].get('sheet'), runtime.config.get('columns'))
    if not records or len(records) != len({row['record_id'] for row in records}) or len(records) != len({row['expected_filename'].casefold() for row in records}):
        raise ValueError('Nonempty bibliography with unique IDs and destination filenames required')
    if not 60 <= args.delay <= 3600 or not 1 <= args.limit <= 1000:
        raise ValueError('Delay must be 60..3600 seconds and request limit 1..1000')
    sources = approved_sources(args.approved_sources, records, set(args.allow_host))
    directory = args.output_dir.resolve()
    if directory == runtime.workspace or not directory.is_relative_to(runtime.workspace):
        raise ValueError('Batch directory must be a child of the private workspace')
    runtime_root = Path(__file__).resolve().parents[1]
    if runtime.workspace == runtime_root or any(runtime.workspace.is_relative_to(runtime_root / name) for name in ('scripts', 'references', 'assets', '.agents')):
        raise ValueError('Do not use the runtime or its source folders as a research workspace')
    if not args.execute:
        print(json.dumps({'mode': 'dry_run', 'candidates': len(records), 'approved_sources': len(sources), 'maximum_requests': args.limit, 'delay_seconds': args.delay, 'network_requested': False, 'writes_performed': False}))
        return 0
    if not args.skip_structure and importlib.util.find_spec('docling') is None:
        raise ValueError('Local Docling is not installed; install corpus dependencies or explicitly use --skip-structure')
    fingerprints = {'bibliography_sha256': helper.sha256_file(input_path), 'config_sha256': helper.sha256_file(args.config), 'sources_sha256': helper.sha256_file(args.approved_sources) if args.approved_sources else None,
        'structure_enabled': not args.skip_structure, 'tables_enabled': not args.no_tables, 'profile': 'base',
        'tools': {path.relative_to(runtime_root).as_posix(): helper.sha256_file(path) for path in manifest_paths(runtime_root, 'runtime') if path.relative_to(runtime_root).parts[0] == 'scripts'}}
    if args.resume:
        started = json.loads(local_file(directory, 'started.json').read_text(encoding='utf-8'))
        if started['frozen_inputs'] != fingerprints:
            raise ValueError('Frozen input, configuration or tool changed; use a new reviewed batch')
    elif directory.exists():
        raise ValueError('Batch already exists; use --resume for unchanged frozen inputs')
    runtime.acquisition_output.mkdir(parents=True, exist_ok=True)
    lock = runtime.acquisition_output / 'workflow-batch.lock'
    if (runtime.acquisition_output / 'browser-receive.lock').exists():
        raise ValueError('A browser receiver is active; do not run concurrent workspace writers')
    with lock.open('x', encoding='utf-8') as stream:
        stream.write('Active batch. After interruption, confirm the process stopped before manually clearing this lock.\n')
    attempt = None
    try:
        if not args.resume:
            directory.mkdir(parents=True, exist_ok=False)
            write_exclusive(directory / 'started.json', {'created_utc': helper.utcnow(), 'frozen_inputs': fingerprints, 'candidate_count': len(records), 'eligibility_decisions_performed': False})
            shutil.copyfile(input_path, directory / ('bibliography.frozen' + input_path.suffix))
            helper.write_csv(directory / 'approved.frozen.csv', sources, list(sources[0]) if sources else ['record_id'])
        attempts_root = directory / 'attempts'
        attempts_root.mkdir(exist_ok=True)
        number = max([int(path.name) for path in attempts_root.iterdir() if path.is_dir() and path.name.isdigit()], default=0) + 1
        attempt = attempts_root / f'{number:03d}'
        attempt.mkdir()
        commands = []

        def execute(label, script, arguments, allowed=(0,)):
            command = [sys.executable, '-X', 'utf8', str(Path(__file__).with_name(script)), *map(str, arguments)]
            write_exclusive(attempt / (label + '.started.json'), {'command': command, 'started_utc': helper.utcnow()})
            with (attempt / (label + '.stdout.log')).open('x', encoding='utf-8') as stdout, (attempt / (label + '.stderr.log')).open('x', encoding='utf-8') as stderr:
                result = subprocess.run(command, stdout=stdout, stderr=stderr)
            receipt = {'command': command, 'exit_code': result.returncode, 'finished_utc': helper.utcnow()}
            write_exclusive(attempt / (label + '.finished.json'), receipt)
            commands.append(receipt)
            if result.returncode not in allowed:
                raise RuntimeError('Batch stopped at ' + label + '; inspect private receipt')

        minimum = str(runtime.config.get('identity', {}).get('minimum_pdf_bytes', 10000))
        execute('audit-before', 'paper_fulltext_fetcher.py', ['audit', '--config', args.config, '--output-dir', attempt / 'audit-before', '--minimum-pdf-bytes', minimum])
        before = {row['record_id']: row for row in read_csv(attempt / 'audit-before/records.csv')}
        ledger = RouteLedger(runtime.acquisition_output / 'access')
        attempted_root = directory / 'transfers'
        attempted_root.mkdir(exist_ok=True)
        prior_attempts = [json.loads(path.read_text(encoding='utf-8')) for path in attempted_root.glob('*.json')]
        attempted_ids = {row['record_id'] for row in prior_attempts}
        last_started = max([datetime.fromisoformat(row['started_utc']).timestamp() for row in prior_attempts], default=0)
        requested = 0
        paused = 0
        for row in sources:
            identifier = row['record_id']
            if before[identifier]['status'] in helper.SUCCESS_STATUSES or identifier in attempted_ids or requested >= args.limit:
                continue
            host = urlsplit(row['candidate_url']).hostname
            if not ledger.state(host, 'http')['attempt_allowed']:
                paused += 1
                continue
            remaining_delay = args.delay - (time.time() - last_started)
            if remaining_delay > 0:
                time.sleep(remaining_delay)
            label = 'fetch-' + str(requested + 1)
            request_path = attempt / (label + '.csv')
            helper.write_csv(request_path, [row])
            arguments = ['fetch-verified', '--config', args.config, '--manifest', request_path, '--allow-host', host, '--timeout', '40', '--delay', str(args.delay), '--limit', '1', '--max-consecutive-failures', '1', '--minimum-pdf-bytes', minimum]
            execute(label + '-preview', 'paper_fulltext_fetcher.py', [*arguments, '--log-dir', attempt / (label + '-preview')])
            last_started = time.time()
            write_exclusive(attempted_root / (hashlib.sha256(identifier.encode()).hexdigest() + '.json'), {'record_id': identifier, 'host': host, 'started_utc': datetime.now(timezone.utc).isoformat(), 'attempted_not_assumed_saved': True})
            execute(label, 'paper_fulltext_fetcher.py', [*arguments, '--log-dir', attempt / label, '--execute'], allowed=(0, 3))
            requested += 1
        execute('audit-after', 'paper_fulltext_fetcher.py', ['audit', '--config', args.config, '--output-dir', attempt / 'audit-after', '--minimum-pdf-bytes', minimum])
        after = read_csv(attempt / 'audit-after/records.csv')
        if {row['record_id'] for row in after} != set(before) or any(row['sha256'] != before[row['record_id']]['sha256'] or row['status'] != before[row['record_id']]['status'] for row in after if before[row['record_id']]['status'] in helper.SUCCESS_STATUSES):
            raise ValueError('Candidate set or previously verified source changed')
        available = [row for row in after if row['status'] in helper.SUCCESS_STATUSES]
        if available and not args.skip_structure:
            for relative in ('manifests/conversion_manifest.csv', 'quality/quality_base.csv', 'registry.csv'):
                path = runtime.registry if relative == 'registry.csv' else runtime.corpus_root / relative
                if path.is_file():
                    target = attempt / 'prior-corpus' / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
            execute('register', 'corpus_tool.py', ['register', '--config', args.config, '--audit', attempt / 'audit-after/records.csv'])
            execute('doctor', 'corpus_tool.py', ['doctor', '--config', args.config])
            conversion_arguments = ['convert', '--config', args.config, '--profile', 'base', '--resume', '--workers', '1', '--threads', '4']
            if args.no_tables:
                conversion_arguments.append('--no-tables')
            execute('convert', 'corpus_tool.py', conversion_arguments, allowed=(0, 2))
            execute('assess', 'corpus_tool.py', ['assess', '--config', args.config, '--profile', 'base'], allowed=(0, 2))
            execute('verify', 'corpus_tool.py', ['verify', '--config', args.config, '--profile', 'base'], allowed=(0, 2))
        prior_libraries = sorted(path for path in attempts_root.glob('*/library') if (path / 'manifest.json').is_file())
        previous = prior_libraries[-1] if prior_libraries else args.previous_snapshot
        summary = build_library(args.config, attempt / 'audit-after/records.csv', attempt / 'library', sources=directory / 'approved.frozen.csv' if sources else None, previous=previous)
        summary.update({'finished_utc': helper.utcnow(), 'requests_this_attempt': requested, 'paused_sources_not_requested': paused, 'new_fulltexts': sum(row['status'] in helper.SUCCESS_STATUSES and before[row['record_id']]['status'] not in helper.SUCCESS_STATUSES for row in after), 'commands': commands, 'complete_acquisition': summary['missing'] == 0, 'complete_structuring': summary['structured'] == summary['fulltexts'], 'eligibility_decisions_performed': False})
        write_exclusive(attempt / 'summary.json', summary)
        print(json.dumps({key: value for key, value in summary.items() if key != 'commands'}, ensure_ascii=False))
        return 0
    except BaseException as error:
        if attempt:
            write_exclusive(attempt / 'interrupted.json', {'finished_utc': helper.utcnow(), 'error_type': type(error).__name__, 'complete': False, 'next_step': 'Inspect receipts and saved files before resuming unchanged inputs; no automatic route or lock recovery'})
        raise
    finally:
        lock.unlink(missing_ok=True)
