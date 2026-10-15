from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def manifest_paths(root, kind='public'):
    root = root.resolve()
    manifest = json.loads((root / 'assets/bundle-files.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 'paper-bundle-files-v1':
        raise ValueError('Unsupported bundle file manifest')
    names = manifest['runtime'] + (manifest['public_additions'] if kind == 'public' else [])
    if len(names) != len(set(names)):
        raise ValueError('Duplicate bundle file entry')
    result = []
    for name in names:
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name or not relative.parts:
            raise ValueError('Unsafe bundle path')
        if relative.parts[0] not in {'scripts', 'references', 'assets', 'tests', '.agents', 'agents'} and name not in {'README.md', 'SKILL.md', 'LICENSE', '.gitignore', 'requirements.txt', 'requirements-corpus.txt'}:
            raise ValueError('Bundle path is outside supported public source folders')
        path = root / name
        if not path.is_file() or not path.resolve().is_relative_to(root) or any(parent.is_symlink() for parent in [path, *path.parents] if parent != root and parent.is_relative_to(root)):
            raise ValueError('Bundle contains missing, symlinked or external file')
        result.append(path)
    return sorted(result)


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, arguments):
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True)
    if result.returncode:
        raise ValueError('Git inspection failed; raw output suppressed')
    return result.stdout


def materialize_bundle(root, destination):
    import paper_fulltext_fetcher as helper

    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for path in manifest_paths(root):
        relative = path.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        expected = checksum(path)
        if checksum(target) != expected or checksum(path) != expected:
            raise ValueError('Bundle source changed during copying')
        hashes[relative.as_posix()] = expected
    findings = helper.privacy_findings(destination)
    if findings:
        raise ValueError('Public bundle privacy scan failed; ' + str(len(findings)) + ' findings, values suppressed')
    return hashes


def stage_bundle(root, destination):
    if destination.exists():
        raise FileExistsError('Bundle output already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.paper-bundle-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'candidate'
        hashes = materialize_bundle(root, staged)
        staged.rename(destination)
    return hashes


def check(root, index=False, history=False):
    import paper_fulltext_fetcher as helper

    allowed = {path.relative_to(root).as_posix() for path in manifest_paths(root)}
    findings = []
    with tempfile.TemporaryDirectory(prefix='paper-release-check-') as temporary:
        hashes = stage_bundle(root, Path(temporary) / 'candidate')
        if index:
            staged = git(root, ['ls-files', '--stage', '-z']).decode('utf-8').split('\0')
            indexed = Path(temporary) / 'index'
            indexed.mkdir()
            for entry in filter(None, staged):
                metadata, name = entry.split('\t', 1)
                mode, object_id, stage = metadata.split()
                if mode not in {'100644', '100755'} or stage != '0' or name not in allowed:
                    findings.append({'kind': 'unapproved_index_entry', 'path': name})
                    continue
                target = indexed / name
                target.parent.mkdir(parents=True, exist_ok=True)
                body = git(root, ['cat-file', 'blob', object_id])
                target.write_bytes(body)
                if body.replace(b'\r\n', b'\n') != (root / name).read_bytes().replace(b'\r\n', b'\n'):
                    findings.append({'kind': 'index_worktree_mismatch', 'path': name})
            indexed_names = {entry.split('\t', 1)[1] for entry in staged if entry}
            for name in sorted(allowed - indexed_names):
                findings.append({'kind': 'approved_public_file_not_staged', 'path': name})
            findings.extend(helper.privacy_findings(indexed))
        history_blobs = 0
        if history:
            historical = Path(temporary) / 'history'
            historical.mkdir()
            for entry in git(root, ['rev-list', '--objects', '--all']).decode('utf-8').splitlines():
                parts = entry.split(' ', 1)
                if len(parts) != 2 or git(root, ['cat-file', '-t', parts[0]]).strip() != b'blob':
                    continue
                object_id, name = parts
                relative = PurePosixPath(name)
                if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                    findings.append({'kind': 'unsafe_historical_path', 'object': object_id})
                    continue
                folder = historical / object_id
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(git(root, ['cat-file', 'blob', object_id]))
                history_blobs += 1
                findings.extend({**finding, 'object': object_id} for finding in helper.privacy_findings(folder))
        return {'created_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed' if not findings else 'failed', 'public_file_count': len(hashes), 'public_file_sha256': hashes, 'index_checked': index, 'history_checked': history, 'historical_blobs_checked': history_blobs, 'findings': findings, 'matched_secret_values_printed': False, 'limitations': 'Heuristic source and secret scanning, not proof of absent private information. Human review of the selected public files and licenses remains necessary.'}


def main():
    parser = argparse.ArgumentParser(description='Allowlisted runtime/public bundles and privacy-aware Git publication checks')
    parser.add_argument('command', choices=('check', 'build'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--index', action='store_true')
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if args.command == 'build':
            if not args.output_dir:
                raise ValueError('A new --output-dir is required')
            hashes = stage_bundle(root, args.output_dir.resolve())
            result = {'status': 'passed', 'files': len(hashes), 'sha256': hashes, 'contains_research_data': False}
        else:
            result = check(root, args.index, args.history)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
        print(json.dumps({key: value for key, value in result.items() if key not in {'public_file_sha256', 'sha256'}}, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'passed' else 3
    except (ValueError, OSError) as error:
        print(type(error).__name__ + ': publication check stopped; inspect source selection, no secret values emitted')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
