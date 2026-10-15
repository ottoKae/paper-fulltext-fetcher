from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from corpus_tool import synthetic_text_pdf


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    checks = {}
    environment = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}

    def call(label, script, arguments, expected=(0,)):
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts' / script), *map(str, arguments)]
        completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=environment)
        (output / (label + '.stdout.log')).write_text(completed.stdout, encoding='utf-8')
        (output / (label + '.stderr.log')).write_text(completed.stderr, encoding='utf-8')
        commands.append({'label': label, 'command': command, 'exit_code': completed.returncode})
        (output / 'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2), encoding='utf-8')
        if completed.returncode not in expected:
            raise RuntimeError('Unexpected CLI result at ' + label)
        return completed

    workspace = output / 'workspace'
    workspace.mkdir()
    records = [{'record_id': 'example-' + str(number), 'title': 'Synthetic satellite mapping example ' + str(number), 'doi': '10.5555/reuse-' + str(number), 'year': '2025', 'publisher': 'Example Publisher', 'expected_filename': 'example-' + str(number) + ('.pdf' if number == 1 else '.xml')} for number in range(1, 6)]
    bibliography = workspace / 'bibliography.csv'
    with bibliography.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    call('init', 'paper_fulltext_fetcher.py', ['init', '--workspace', workspace, '--input', 'bibliography.csv'])
    config = workspace / 'acquisition.local.toml'
    source_pdf = workspace / 'manual_pdf_inbox/example-1.pdf'
    source_pdf.write_bytes(synthetic_text_pdf(records[0]['title'] + ' ' + records[0]['doi']) + b'\n%' + b'synthetic-padding ' * 800)
    original_pdf_hash = digest(source_pdf)
    call('receive-preview', 'workflow_tools.py', ['browser-receive', '--config', config, '--record-id', 'example-1', '--wait-seconds', '3', '--poll-seconds', '0.1'])
    call('receive', 'workflow_tools.py', ['browser-receive', '--config', config, '--record-id', 'example-1', '--inbox', source_pdf.parent, '--wait-seconds', '3', '--poll-seconds', '0.1', '--execute'])
    checks['original_inbox_preserved'] = digest(source_pdf) == original_pdf_hash

    def xml(record):
        paragraphs = ''.join('<p>Satellite observation ' + str(number) + ' describes a synthetic plantation measurement and preserves traceable reference data.</p>' for number in range(120))
        return ('<article><front><article-meta><article-id pub-id-type="doi">' + record['doi'] + '</article-id><title-group><article-title>' + record['title'] + '</article-title></title-group></article-meta></front><body><sec><title>Methods</title>' + paragraphs + '</sec></body></article>').encode('utf-8')

    (workspace / 'papers_xml/example-2.xml').write_bytes(xml(records[1]))
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlsplit(self.path).path
            requests.append(route)
            self.send_response(403 if route == '/blocked.xml' else 200)
            self.end_headers()
            self.wfile.write(b'Access denied' if route == '/blocked.xml' else xml(records[2] if route == '/good.xml' else records[1]))

        def log_message(self, *arguments):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    environment.update({'HTTP_PROXY': 'http://127.0.0.1:' + str(server.server_port), 'http_proxy': 'http://127.0.0.1:' + str(server.server_port), 'HTTPS_PROXY': 'http://127.0.0.1:' + str(server.server_port), 'https_proxy': 'http://127.0.0.1:' + str(server.server_port), 'NO_PROXY': '', 'no_proxy': ''})
    sources = workspace / 'approved.csv'
    selected = [{**record, 'candidate_url': 'http://repository.example.edu' + route, 'approved': 'true', 'approval_scope': 'open_access', 'report_role': 'primary', 'source_version': 'fulltext_xml', 'license_evidence': 'Synthetic fixture owned by this test'} for record, route in zip(records[2:], ['/good.xml', '/wrong.xml', '/blocked.xml'])]
    with sources.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(selected[0]))
        writer.writeheader()
        writer.writerows(selected)
    batch = workspace / 'runs/reuse-01'
    arguments = ['batch', '--config', config, '--output-dir', batch, '--approved-sources', sources, '--allow-host', 'repository.example.edu', '--delay', '60', '--no-tables']
    try:
        for label, changes in [('missing-scope', {'approval_scope': ''}), ('related-report', {'report_role': 'related'}), ('signed-url', {'candidate_url': selected[0]['candidate_url'] + '?' + 'X-Amz-' + 'Signature=' + 'synthetic-signature'}), ('wrong-metadata', {'doi': '10.5555/not-target'})]:
            variant = workspace / (label + '.csv')
            with variant.open('x', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(selected[0]))
                writer.writeheader()
                writer.writerow({**selected[0], **changes})
            invalid_arguments = list(arguments)
            invalid_arguments[invalid_arguments.index(sources)] = variant
            call(label + '-rejected', 'workflow_tools.py', invalid_arguments, expected=(2,))
            checks[label + '_rejected_before_network_or_writes'] = not requests and not batch.exists()
        call('batch-preview', 'workflow_tools.py', arguments)
        checks['preview_no_network_or_batch_directory'] = not requests and not batch.exists()
        call('batch', 'workflow_tools.py', [*arguments, '--execute'])
        first_summary = json.loads((batch / 'attempts/001/summary.json').read_text(encoding='utf-8'))
        first_snapshot = batch / 'attempts/001/library'
        before = {path.relative_to(first_snapshot).as_posix(): digest(path) for path in first_snapshot.rglob('*') if path.is_file()}
        checks['three_verified_fulltexts_two_missing'] = first_summary['fulltexts'] == 3 and first_summary['missing'] == 2
        checks['actual_good_wrong_and_blocked_requests_only_once'] = requests == ['/good.xml', '/wrong.xml', '/blocked.xml']
        checks['incorrect_paper_not_imported'] = not (workspace / 'papers_xml/example-4.xml').exists()
        call('resume', 'workflow_tools.py', [*arguments, '--execute', '--resume'])
        checks['resume_no_network_retries'] = requests == ['/good.xml', '/wrong.xml', '/blocked.xml']
        checks['old_snapshot_unchanged'] = all(digest(first_snapshot / path) == checksum for path, checksum in before.items())
        second_snapshot = batch / 'attempts/002/library'
        call('archive-verify', 'workflow_tools.py', ['archive-verify', '--snapshot', second_snapshot])
        call('search', 'workflow_tools.py', ['library-search', '--snapshot', second_snapshot, '--query', 'satellite', '--limit', '3'])
        with sqlite3.connect(second_snapshot / 'search.sqlite') as connection:
            checks['real_fts_search_returns_records'] = connection.execute("SELECT count(*) FROM chunks WHERE chunks MATCH 'satellite'").fetchone()[0] > 0
        manifest = json.loads((second_snapshot / 'manifest.json').read_text(encoding='utf-8'))
        checks['all_documents_converted_and_colocated'] = len(manifest['documents']) == 3 and all(row['structure_status'] == 'verified' and len({Path(entry['path']).parent for entry in row['files'].values()}) == 1 for row in manifest['documents'])
        checks['old_quality_warnings_retained'] = all(next(row for row in manifest['documents'] if row['record_id'] == old['record_id'])['quality_class'] == old['quality_class'] for old in json.loads((first_snapshot / 'manifest.json').read_text(encoding='utf-8'))['documents'])
        source_entry = manifest['documents'][0]['files']['source']
        with (second_snapshot / source_entry['path']).open('ab') as stream:
            stream.write(b'changed')
        call('tamper-rejected', 'workflow_tools.py', ['archive-verify', '--snapshot', second_snapshot], expected=(2,))
        checks['tampered_snapshot_rejected'] = True
        original_bibliography = bibliography.read_bytes()
        bibliography.write_bytes(original_bibliography + b'\n')
        call('changed-input-rejected', 'workflow_tools.py', [*arguments, '--execute', '--resume'], expected=(2,))
        bibliography.write_bytes(original_bibliography)
        checks['changed_frozen_input_rejected'] = True
        lock = workspace / 'outputs/acquisition/workflow-batch.lock'
        lock.write_text('Synthetic active operation; no automatic lock removal', encoding='utf-8')
        try:
            call('lock-rejected', 'workflow_tools.py', [*arguments, '--execute', '--resume'], expected=(2,))
            checks['active_workspace_lock_not_cleared'] = lock.exists()
        finally:
            lock.unlink()
        call('install', 'install_skills.py', ['--destination', output / 'installed-skills', '--execute'])
        call('package', 'release_tools.py', ['build', '--output-dir', output / 'public-package'])
        checks['package_no_private_data_or_environments'] = not any(path.suffix in {'.pdf', '.xml', '.jsonl', '.sqlite', '.log'} or '.venv' in path.parts for path in (output / 'public-package').rglob('*') if path.is_file())
        fixture = output / 'allowlist-fixture'
        shutil.copytree(output / 'public-package', fixture)
        (fixture / 'scripts/local_notes.py').write_text('PRIVATE_FIXTURE_ONLY = True\n', encoding='utf-8')
        (fixture / '.agents/skills/paper-corpus/agents/local_notes.txt').write_text('Synthetic private note; must not be installed', encoding='utf-8')
        call('install-filtered', fixture / 'scripts/install_skills.py', ['--destination', output / 'installed-filtered', '--execute'])
        checks['unlisted_runtime_and_agent_files_not_installed'] = not list((output / 'installed-filtered').rglob('local_notes.*'))
        with (fixture / 'README.md').open('a', encoding='utf-8') as stream:
            stream.write('\nSynthetic contact: ' + 'fixture' + '@' + 'private.invalid\n')
        call('private-package-rejected', fixture / 'scripts/release_tools.py', ['build', '--root', fixture, '--output-dir', output / 'rejected-private-package'], expected=(2,))
        checks['private_content_in_allowlisted_file_stops_packaging'] = not (output / 'rejected-private-package').exists()
    finally:
        server.shutdown()
        server.server_close()
        artifact = {'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed' if checks and all(checks.values()) and len(checks) == 20 else 'failed', 'checks': checks, 'expected': {'verified_fulltexts': 3, 'missing': 2, 'external_network_requests': 0, 'checks': 20}, 'commands': commands, 'environment': {'python': sys.version.split()[0], 'docling': version('docling-slim'), 'docling_core': version('docling-core'), 'model_cache_offline_required': True}, 'input_sha256': {'verifier': digest(Path(__file__)), 'bibliography': digest(bibliography), 'approved_sources': digest(sources), 'original_pdf': original_pdf_hash}, 'actual_loopback_requests': requests, 'output_sha256': {'first_library_manifest': digest(first_snapshot / 'manifest.json')} if 'first_snapshot' in locals() and (first_snapshot / 'manifest.json').exists() else {}, 'reproduction_command': [sys.executable, str(Path(__file__)), '--output', str(output.parent / (output.name + '-repeat-new'))], 'limitations': 'Synthetic local HTTP proxy, real CLI and local Docling with previously downloaded model weights in offline mode. No institution login, publisher entitlement, browser automation or future external-source availability is verified. Run IDs, timestamps and loopback port vary; semantic counts and preserved hashes are the reproducible checks.'}
        (output / 'verification.json').write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': artifact['status'], 'passed': sum(checks.values()), 'checks': len(checks)}))
    return 0 if artifact['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    destination = options.output.resolve()
    if destination.exists():
        parser.error('Output directory already exists; use a new verification run')
    try:
        raise SystemExit(main(destination))
    except Exception as error:
        artifact_path = destination / 'verification.json'
        if not artifact_path.exists():
            artifact_path.write_text(json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'failed', 'error_type': type(error).__name__, 'expected': {'verified_fulltexts': 3, 'missing': 2}, 'actual': 'Stopped before full workflow verification; inspect synthetic CLI logs', 'commands': json.loads((destination / 'commands.json').read_text(encoding='utf-8')) if (destination / 'commands.json').exists() else [], 'environment': {'python': sys.version.split()[0], 'docling': version('docling-slim'), 'docling_core': version('docling-core')}, 'input_sha256': {'verifier': digest(Path(__file__))}, 'output': str(destination), 'reproduction_command': [sys.executable, str(Path(__file__)), '--output', str(destination.parent / (destination.name + '-repeat-new'))]}, ensure_ascii=False, indent=2), encoding='utf-8')
        raise
