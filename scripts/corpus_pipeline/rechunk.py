from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from .chunks import build_chunks, docling_parts, jats_parts, write_chunks
from .common import (
    RuntimePaths,
    atomic_write_csv,
    atomic_write_json,
    config_sha256,
    latest_success,
    load_registry,
    read_csv,
    redact_error,
    relative_posix,
    sha256_file,
    utc_now,
)
from .engine import corpus_settings


CHUNK_MANIFEST_FIELDS = [
    "run_id",
    "study_id",
    "profile",
    "source_sha256",
    "docling_json_sha256",
    "chunk_config_sha256",
    "chunks_relpath",
    "chunks_sha256",
    "chunk_count",
    "status",
    "error_class",
    "error_message",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def run_rechunk(
    runtime: RuntimePaths,
    *,
    profile: str,
    study_id: str | None,
    target_chars: int | None,
    max_chars: int | None,
) -> tuple[int, dict[str, Any]]:
    settings = corpus_settings(runtime)
    target = int(target_chars or settings["target_chars"])
    maximum = int(max_chars or settings["max_chars"])
    chunk_spec = {
        "name": "deterministic_provenance_v1",
        "target_chars": target,
        "max_chars": maximum,
    }
    chunk_digest = config_sha256(chunk_spec)
    run_id = f"rechunk-{uuid4().hex}"
    output_dir = runtime.corpus_root / "chunk_sets" / chunk_digest[:8] / run_id
    registry = load_registry(runtime.registry)
    if study_id:
        registry = [row for row in registry if row["study_id"] == study_id]
        if not registry:
            raise ValueError("requested study ID was not found in the registry")
    conversion_manifest = runtime.corpus_root / "manifests" / "conversion_manifest.csv"
    if not conversion_manifest.is_file():
        raise FileNotFoundError("conversion manifest was not found")
    selected = latest_success(read_csv(conversion_manifest), profile)
    output_dir.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, Any]] = []
    for record in registry:
        manifest = selected.get(record["study_id"])
        row: dict[str, Any] = {
            "run_id": run_id,
            "study_id": record["study_id"],
            "profile": profile,
            "source_sha256": record["source_sha256"],
            "chunk_config_sha256": chunk_digest,
        }
        try:
            if not manifest:
                raise ValueError("no successful conversion for this profile")
            if manifest.get("source_sha256") != record["source_sha256"]:
                raise ValueError("conversion source does not match the current registry")
            if sha256_file(runtime.workspace / record["source_relpath"]) != record["source_sha256"]:
                raise ValueError("registered source hash mismatch")
            json_path = runtime.workspace / manifest["json_relpath"]
            json_digest = sha256_file(json_path)
            if json_digest != manifest["json_sha256"]:
                raise ValueError("Docling JSON hash mismatch")
            if record["source_format"] == "xml":
                source_map = runtime.workspace / manifest.get("source_map_relpath", "")
                if not source_map.is_file():
                    raise FileNotFoundError("XML XPath source map is missing")
                if sha256_file(source_map) != manifest.get("source_map_sha256"):
                    raise ValueError("XML XPath source map hash mismatch")
                parts = jats_parts(_read_jsonl(source_map))
            else:
                try:
                    from docling_core.types.doc import DoclingDocument
                except ModuleNotFoundError as error:
                    raise RuntimeError("docling-core is missing; run bootstrap.ps1 -Corpus") from error
                document = DoclingDocument.load_from_json(json_path)
                parts = docling_parts(document)
            chunks = build_chunks(
                parts,
                study_id=record["study_id"],
                source_format=record["source_format"],
                source_sha256=record["source_sha256"],
                docling_json_sha256=json_digest,
                target_chars=target,
                max_chars=maximum,
            )
            target_path = output_dir / f"{record['study_id']}.jsonl"
            write_chunks(target_path, chunks)
            row.update(
                {
                    "docling_json_sha256": json_digest,
                    "chunks_relpath": relative_posix(target_path, runtime.workspace),
                    "chunks_sha256": sha256_file(target_path),
                    "chunk_count": len(chunks),
                    "status": "success",
                    "error_class": "",
                    "error_message": "",
                }
            )
        except BaseException as error:
            row.update(
                {
                    "status": "failure",
                    "error_class": type(error).__name__,
                    "error_message": redact_error(str(error)),
                }
            )
        rows.append(row)
    manifest_path = runtime.corpus_root / "manifests" / f"chunk_manifest_{chunk_digest[:8]}.csv"
    atomic_write_csv(output_dir / "manifest.csv", rows, CHUNK_MANIFEST_FIELDS)
    atomic_write_csv(manifest_path, rows, CHUNK_MANIFEST_FIELDS)
    counts = Counter(str(row["status"]) for row in rows)
    summary = {
        "run_id": run_id,
        "created_utc": utc_now(),
        "profile": profile,
        "chunk_config": chunk_spec,
        "chunk_config_sha256": chunk_digest,
        "requested": len(registry),
        "success": counts["success"],
        "failure": counts["failure"],
    }
    atomic_write_json(output_dir / "summary.json", summary)
    return (2 if counts["failure"] else 0), summary
