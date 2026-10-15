from __future__ import annotations

import html
import json
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

import paper_fulltext_fetcher as helper
from campus_support import write_exclusive
from corpus_pipeline.common import latest_success, read_csv, runtime_paths, safe_study_id, utc_now


def local_file(root, relative):
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts or not value.parts:
        raise ValueError('Expected a relative file within its workspace')
    target = root / value
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink() or not target.is_file():
        raise ValueError('Source missing, linked outside workspace, or not a regular file')
    return target


def copy_checked(source, destination, checksum):
    if helper.sha256_file(source) != checksum:
        raise ValueError('Source hash changed before copying')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as reader, destination.open('xb') as writer:
        shutil.copyfileobj(reader, writer)
    if helper.sha256_file(destination) != checksum or helper.sha256_file(source) != checksum:
        raise ValueError('Source or copied file hash changed')


def build_library(config, audit_path, output, profile='base', sources=None, previous=None):
    runtime = runtime_paths(config)
    output = output.resolve()
    if output == runtime.workspace or not output.is_relative_to(runtime.workspace):
        raise ValueError('Library output must be a new child of the private workspace')
    previous_documents = {}
    if previous:
        verify_library(previous)
        previous_documents = {row['record_id']: row for row in json.loads((previous / 'manifest.json').read_text(encoding='utf-8'))['documents']}
    audit = read_csv(audit_path)
    ids = [row['record_id'] for row in audit]
    if not audit or len(ids) != len(set(ids)):
        raise ValueError('Nonempty audit with unique record IDs required')
    conversions_path = runtime.corpus_root / 'manifests/conversion_manifest.csv'
    conversions = latest_success(read_csv(conversions_path), profile) if conversions_path.exists() else {}
    quality_path = runtime.corpus_root / 'quality' / ('quality_' + profile + '.csv')
    qualities = read_csv(quality_path) if quality_path.exists() else []
    source_metadata = {}
    for row in read_csv(sources) if sources else []:
        if row.get('report_role', 'primary') != 'primary':
            raise ValueError('Related reports require separate records, not replacement of candidate originals')
        source_metadata[row['record_id']] = row
    output.mkdir(parents=True, exist_ok=False)
    provenance = output / 'provenance'
    provenance.mkdir()
    inputs = {}
    for name, source in [('audit.csv', audit_path), ('conversion_manifest.csv', conversions_path), ('quality.csv', quality_path)]:
        if source.is_file():
            checksum = helper.sha256_file(source)
            copy_checked(source, provenance / name, checksum)
            inputs[name] = checksum
    if previous:
        checksum = helper.sha256_file(previous / 'manifest.json')
        copy_checked(previous / 'manifest.json', provenance / 'previous_manifest.json', checksum)
        inputs['previous_manifest.json'] = checksum
    documents = []
    missing = []
    seen_hashes = set()
    with sqlite3.connect(output / 'search.sqlite') as connection:
        connection.execute('CREATE VIRTUAL TABLE chunks USING fts5(record_id UNINDEXED, title, doi, text, locator UNINDEXED, source UNINDEXED, markdown UNINDEXED, quality UNINDEXED)')
        for row in audit:
            if row['status'] not in helper.SUCCESS_STATUSES:
                missing.append(row)
                continue
            identifier = row['record_id']
            study_id = safe_study_id(identifier, row)
            source_format = 'xml' if row['status'] == 'valid_xml' else 'pdf'
            source_root = runtime.xml_dir if source_format == 'xml' else runtime.pdf_dir
            original = local_file(source_root, row['fulltext_file'])
            if row['sha256'] in seen_hashes:
                raise ValueError('Duplicate original content needs identity review, not double counting')
            seen_hashes.add(row['sha256'])
            directory = output / 'papers' / study_id
            files = {}

            def archive_file(name, source, checksum):
                target = directory / name
                copy_checked(source, target, checksum)
                entry = {'path': target.relative_to(output).as_posix(), 'sha256': checksum}
                return entry

            files['source'] = archive_file('source.' + source_format, original, row['sha256'])
            conversion = conversions.get(study_id)
            quality = None
            structure_status = 'awaiting_structure'
            chunks = []
            if conversion and conversion['source_sha256'] == row['sha256']:
                for name, key, hash_key in [('fulltext.md', 'md_relpath', 'md_sha256'), ('docling.json', 'json_relpath', 'json_sha256'), ('chunks.jsonl', 'chunks_relpath', 'chunks_sha256'), ('source_map.json', 'source_map_relpath', 'source_map_sha256')]:
                    if conversion.get(key):
                        files[{'fulltext.md': 'markdown', 'docling.json': 'docling_json', 'chunks.jsonl': 'chunks', 'source_map.json': 'source_map'}[name]] = archive_file(name, local_file(runtime.workspace, conversion[key]), conversion[hash_key])
                matches = [value for value in qualities if value['study_id'] == study_id and value['config_sha256'] == conversion['config_sha256'] and value['json_relpath'] == conversion['json_relpath']]
                if len(matches) != 1:
                    raise ValueError('Successful conversion needs exactly one matching quality assessment')
                quality = matches[0]
                chunks = [json.loads(line) for line in (output / files['chunks']['path']).read_text(encoding='utf-8').splitlines() if line.strip()]
                structure_status = 'verified'
                if source_format == 'pdf' and quality.get('page_count_match') != 'true':
                    structure_status = 'incomplete_pages'
            selected_quality = quality['quality_class'] if quality else 'not_assessed'
            old = previous_documents.get(identifier)
            retained_warning = bool(old and old['files']['source']['sha256'] == row['sha256'] and old['quality_class'] not in {'A_ready', 'not_assessed'})
            if retained_warning:
                ranks = {'not_assessed': 0, 'A_ready': 0, 'B_search_only': 1, 'C_retry_required': 2}
                selected_quality = max((selected_quality, old['quality_class']), key=lambda value: ranks.get(value, 3))
            metadata = source_metadata.get(identifier, {})
            document = {
                **{key: row.get(key, '') for key in ('record_id', 'title', 'doi', 'year', 'publisher', 'authors')},
                'study_id': study_id, 'source_format': source_format, 'source_sha256': row['sha256'],
                'source_version': metadata.get('source_version') or (old or {}).get('source_version', 'unknown_not_assumed'),
                'license_evidence': metadata.get('license_evidence') or (old or {}).get('license_evidence', 'not_recorded_not_assumed'),
                'source_url_redacted': helper.redact_url(metadata.get('candidate_url', '')),
                'report_role': 'primary', 'formal_inclusion': 'not_assessed', 'structure_status': structure_status,
                'quality_class': selected_quality, 'machine_quality': quality, 'prior_warning_retained': retained_warning,
                'prior_quality': old['quality_class'] if old else None, 'conversion': conversion if 'docling_json' in files else None,
                'chunk_count': len(chunks), 'files': files,
            }
            for chunk in chunks:
                if chunk.get('study_id') != study_id or chunk.get('source_sha256') != row['sha256'] or chunk.get('docling_json_sha256') != files['docling_json']['sha256'] or not chunk.get('locator_value'):
                    raise ValueError('Chunk identity, hash or locator mismatch')
                connection.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)', (identifier, row['title'], row['doi'], chunk.get('text', ''), str(chunk['locator_value']), files['source']['path'], files['markdown']['path'], selected_quality))
            write_exclusive(directory / 'metadata.json', document)
            documents.append(document)
    summary = {'candidates': len(audit), 'fulltexts': len(documents), 'missing': len(missing), 'structured': sum(row['structure_status'] == 'verified' for row in documents), 'chunks': sum(row['chunk_count'] for row in documents), 'quality': dict(Counter(row['quality_class'] for row in documents)), 'formal_inclusions_assessed': 0}
    helper.write_csv(output / 'missing.csv', missing, list(audit[0]))
    helper.write_csv(output / 'index.csv', [{key: row[key] for key in ('record_id', 'title', 'doi', 'source_version', 'structure_status', 'quality_class', 'chunk_count')} for row in documents], ['record_id', 'title', 'doi', 'source_version', 'structure_status', 'quality_class', 'chunk_count'])
    write_exclusive(output / 'summary.json', summary)
    lines = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Paper library</title><h1>Local paper library</h1><p>Retrieval and parsing are not review inclusion. Quality warnings require original-page checks.</p><input id="filter" placeholder="Title, DOI, ID"><table><thead><tr><th>ID / title</th><th>Files</th><th>Version / quality</th></tr></thead><tbody>']
    for document in documents:
        links = ' | '.join('<a href="' + html.escape(entry['path'], quote=True) + '">' + html.escape(name) + '</a>' for name, entry in document['files'].items())
        lines.append('<tr><td>' + html.escape(document['record_id'] + ' ' + document['title'] + ' ' + document['doi']) + '</td><td>' + links + '</td><td>' + html.escape(document['source_version'] + ' / ' + document['quality_class']) + '</td></tr>')
    lines.append('</tbody></table><script>document.getElementById("filter").addEventListener("input",function(){const value=this.value.toLowerCase();document.querySelectorAll("tbody tr").forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(value))});</script></html>')
    (output / 'index.html').write_text('\n'.join(lines), encoding='utf-8')
    artifacts = {name: helper.sha256_file(output / name) for name in ('summary.json', 'index.csv', 'index.html', 'missing.csv', 'search.sqlite')}
    write_exclusive(output / 'manifest.json', {'schema': 'paper-library-v1', 'created_utc': utc_now(), 'summary': summary, 'inputs': inputs, 'artifacts': artifacts, 'documents': documents})
    verify_library(output)
    return summary


def verify_library(snapshot):
    snapshot = snapshot.resolve()
    manifest = json.loads(local_file(snapshot, 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 'paper-library-v1':
        raise ValueError('Unsupported library schema; explicit migration required')
    ids = set()
    total_chunks = 0
    for document in manifest['documents']:
        identifier = document['record_id']
        if identifier in ids:
            raise ValueError('Duplicate archive ID')
        ids.add(identifier)
        parents = set()
        for entry in document['files'].values():
            path = local_file(snapshot, entry['path'])
            if helper.sha256_file(path) != entry['sha256']:
                raise ValueError('Archive file hash mismatch')
            parents.add(path.parent)
        if len(parents) != 1:
            raise ValueError('Original and derived files are not colocated')
        metadata = json.loads(local_file(snapshot, (next(iter(parents)) / 'metadata.json').relative_to(snapshot)).read_text(encoding='utf-8'))
        if metadata != document:
            raise ValueError('Per-paper metadata differs from library manifest')
        if 'chunks' in document['files']:
            chunks = [json.loads(line) for line in local_file(snapshot, document['files']['chunks']['path']).read_text(encoding='utf-8').splitlines() if line.strip()]
            if len(chunks) != document['chunk_count'] or not chunks:
                raise ValueError('Chunk count mismatch or empty parsed text')
            for chunk in chunks:
                if chunk.get('study_id') != document['study_id'] or chunk.get('source_sha256') != document['source_sha256'] or chunk.get('docling_json_sha256') != document['files']['docling_json']['sha256'] or not chunk.get('locator_value'):
                    raise ValueError('Chunk provenance mismatch')
                if document['source_format'] == 'pdf' and not (isinstance(chunk.get('page_start'), int) and isinstance(chunk.get('page_end'), int) and 1 <= chunk['page_start'] <= chunk['page_end'] <= int(document['conversion']['page_count'])):
                    raise ValueError('PDF chunk page out of bounds')
                if document['source_format'] == 'xml' and chunk.get('locator_type') != 'xpath':
                    raise ValueError('XML chunk must use XPath, not invented PDF pages')
            total_chunks += len(chunks)
    for name, checksum in manifest['inputs'].items():
        if helper.sha256_file(local_file(snapshot / 'provenance', name)) != checksum:
            raise ValueError('Frozen archive input changed')
    if set(manifest.get('artifacts', {})) != {'summary.json', 'index.csv', 'index.html', 'missing.csv', 'search.sqlite'}:
        raise ValueError('Archive artifact hash inventory is incomplete')
    for name, checksum in manifest['artifacts'].items():
        if helper.sha256_file(local_file(snapshot, name)) != checksum:
            raise ValueError('Archive index, summary or search database hash mismatch')
    with sqlite3.connect((snapshot / 'search.sqlite').as_uri() + '?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or connection.execute('SELECT count(*) FROM chunks').fetchone()[0] != total_chunks:
            raise ValueError('Search index differs from chunk inventory')
        if connection.execute('SELECT count(*) FROM chunks WHERE quality IS NULL').fetchone()[0]:
            raise ValueError('Missing indexed quality status')
    if len(ids) != manifest['summary']['fulltexts'] or total_chunks != manifest['summary']['chunks']:
        raise ValueError('Archive summary count mismatch')
    return {'status': 'passed', 'documents': len(ids), 'chunks': total_chunks}


def archive(args):
    if not args.execute:
        print(json.dumps({'mode': 'dry_run', 'network_requested': False, 'output_exists': args.output_dir.exists()}))
        return 0
    runtime = runtime_paths(args.config)
    summary = build_library(args.config, args.audit or runtime.audit_records, args.output_dir, args.profile, args.sources_metadata, args.previous_snapshot)
    print(json.dumps(summary))
    return 0


def verify(args):
    print(json.dumps(verify_library(args.snapshot)))
    return 0


def search(args):
    if not 1 <= args.limit <= 100:
        raise ValueError('Limit must be between 1 and 100')
    snapshot = args.snapshot.resolve()
    local_file(snapshot, 'search.sqlite')
    with sqlite3.connect((snapshot / 'search.sqlite').as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute('SELECT record_id,title,doi,locator,source,markdown,quality,snippet(chunks,3,"[","]","...",20) FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?', (args.query, args.limit)).fetchall()
    for row in rows:
        print(json.dumps(dict(zip(('record_id', 'title', 'doi', 'locator', 'source', 'markdown', 'quality', 'snippet'), row)), ensure_ascii=False))
    return 0
