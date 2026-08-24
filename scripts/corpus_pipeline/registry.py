from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from . import CORPUS_SCHEMA_VERSION
from .common import (
    REGISTRY_FIELDS,
    SUCCESS_ACQUISITION_STATUSES,
    RuntimePaths,
    atomic_write_csv,
    atomic_write_json,
    read_csv,
    relative_posix,
    safe_study_id,
    sha256_file,
    utc_now,
)


def build_registry(runtime: RuntimePaths, audit_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not audit_path.is_file():
        raise FileNotFoundError("acquisition audit records were not found; run audit first")
    audit_rows = read_csv(audit_path)
    if not audit_rows:
        raise ValueError("acquisition audit contains no records")

    registry: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_hashes: dict[str, str] = {}
    for row_number, row in enumerate(audit_rows, start=2):
        status = str(row.get("status") or "").strip()
        if status not in SUCCESS_ACQUISITION_STATUSES:
            continue
        source_format = "xml" if status == "valid_xml" else "pdf"
        filename = str(row.get("fulltext_file") or "").strip()
        source = (runtime.xml_dir if source_format == "xml" else runtime.pdf_dir) / filename
        study_id = safe_study_id(str(row.get("record_id") or ""), row)
        if not filename:
            errors.append({"row": str(row_number), "study_id": study_id, "reason": "missing_fulltext_file"})
            continue
        if not source.is_file():
            errors.append({"row": str(row_number), "study_id": study_id, "reason": "source_file_missing"})
            continue
        digest = sha256_file(source)
        recorded_digest = str(row.get("sha256") or "").strip().casefold()
        if recorded_digest and recorded_digest != digest:
            errors.append({"row": str(row_number), "study_id": study_id, "reason": "source_hash_mismatch"})
            continue
        if study_id in seen_ids:
            errors.append({"row": str(row_number), "study_id": study_id, "reason": "duplicate_study_id"})
            continue
        if digest in seen_hashes:
            errors.append({"row": str(row_number), "study_id": study_id, "reason": "duplicate_source_content"})
            continue
        seen_ids.add(study_id)
        seen_hashes[digest] = study_id
        registry.append(
            {
                "study_id": study_id,
                "record_id": str(row.get("record_id") or study_id),
                "excel_row": str(row.get("excel_row") or ""),
                "title": str(row.get("title") or ""),
                "doi": str(row.get("doi") or ""),
                "year": str(row.get("year") or ""),
                "source_title": str(row.get("source_title") or ""),
                "publisher": str(row.get("publisher") or "Unclassified"),
                "authors": str(row.get("authors") or ""),
                "source_format": source_format,
                "source_relpath": relative_posix(source, runtime.workspace),
                "source_bytes": source.stat().st_size,
                "source_sha256": digest,
                "acquisition_status": status,
                "acquisition_validation": str(row.get("validation") or ""),
            }
        )

    registry.sort(key=lambda item: (str(item["excel_row"]), str(item["study_id"])))
    format_counts = Counter(str(row["source_format"]) for row in registry)
    summary = {
        "created_utc": utc_now(),
        "schema_version": CORPUS_SCHEMA_VERSION,
        "audit_records": len(audit_rows),
        "registered_records": len(registry),
        "skipped_unavailable_records": len(audit_rows) - len(registry) - len(errors),
        "pdf_records": format_counts["pdf"],
        "xml_records": format_counts["xml"],
        "errors": len(errors),
        "error_counts": dict(Counter(item["reason"] for item in errors)),
        "audit_sha256": sha256_file(audit_path),
        "registry_ready": bool(registry) and not errors,
        "error_records": errors,
    }
    return registry, summary


def write_registry(runtime: RuntimePaths, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    atomic_write_csv(runtime.registry, rows, REGISTRY_FIELDS)
    atomic_write_json(runtime.registry.with_name("registry_summary.json"), summary)
