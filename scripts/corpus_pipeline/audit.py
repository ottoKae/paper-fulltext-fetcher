from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import CHUNK_SCHEMA_VERSION
from .common import (
    RuntimePaths,
    atomic_write_csv,
    atomic_write_json,
    latest_success,
    load_registry,
    read_csv,
    sha256_file,
    utc_now,
)


def verify_manifest_row(runtime: RuntimePaths, record: dict[str, str], row: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    source = runtime.workspace / record["source_relpath"]
    if not source.is_file():
        reasons.append("source_missing")
    elif sha256_file(source) != record["source_sha256"]:
        reasons.append("source_hash_mismatch")
    for path_key, hash_key in (
        ("json_relpath", "json_sha256"),
        ("md_relpath", "md_sha256"),
        ("chunks_relpath", "chunks_sha256"),
    ):
        relative = row.get(path_key, "")
        target = runtime.workspace / relative if relative else None
        if target is None or not target.is_file():
            reasons.append(f"{path_key}_missing")
        elif sha256_file(target) != row.get(hash_key, ""):
            reasons.append(f"{path_key}_hash_mismatch")
    chunks_relative = row.get("chunks_relpath", "")
    chunks_path = runtime.workspace / chunks_relative if chunks_relative else None
    if chunks_path and chunks_path.is_file():
        chunk_count = 0
        try:
            with chunks_path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    chunk_count += 1
                    if value.get("schema_version") != CHUNK_SCHEMA_VERSION:
                        reasons.append("chunk_schema_mismatch")
                        break
                    if value.get("study_id") != record["study_id"]:
                        reasons.append("chunk_study_id_mismatch")
                        break
                    if value.get("source_sha256") != record["source_sha256"]:
                        reasons.append("chunk_source_hash_mismatch")
                        break
                    if record["source_format"] == "pdf" and value.get("locator_type") not in {"page", "page_bbox"}:
                        reasons.append("pdf_locator_invalid")
                        break
                    if record["source_format"] == "xml" and value.get("locator_type") != "xpath":
                        reasons.append("xml_locator_invalid")
                        break
            if chunk_count == 0:
                reasons.append("chunks_empty")
        except (OSError, json.JSONDecodeError):
            reasons.append("chunks_invalid_jsonl")
    return sorted(set(reasons))


def run_verify(runtime: RuntimePaths, profile: str) -> tuple[int, dict[str, Any]]:
    registry = load_registry(runtime.registry)
    manifest_path = runtime.corpus_root / "manifests" / "conversion_manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError("conversion manifest was not found")
    manifests = read_csv(manifest_path)
    selected = latest_success(manifests, profile)
    rows: list[dict[str, Any]] = []
    for record in registry:
        manifest = selected.get(record["study_id"])
        if not manifest:
            rows.append({"study_id": record["study_id"], "profile": profile, "status": "missing", "reasons": "no_successful_conversion"})
            continue
        reasons = verify_manifest_row(runtime, record, manifest)
        rows.append(
            {
                "study_id": record["study_id"],
                "profile": profile,
                "status": "valid" if not reasons else "invalid",
                "reasons": "|".join(reasons),
            }
        )
    counts = Counter(str(row["status"]) for row in rows)
    output = runtime.corpus_root / "verification"
    atomic_write_csv(output / f"verification_{profile}.csv", rows, ["study_id", "profile", "status", "reasons"])
    summary = {
        "created_utc": utc_now(),
        "profile": profile,
        "registry_records": len(registry),
        "valid": counts["valid"],
        "invalid": counts["invalid"],
        "missing": counts["missing"],
        "ready": counts["valid"] == len(registry),
    }
    atomic_write_json(output / f"verification_{profile}_summary.json", summary)
    return (0 if summary["ready"] else 2), summary


def corpus_status(runtime: RuntimePaths) -> dict[str, Any]:
    registry = load_registry(runtime.registry)
    manifest_path = runtime.corpus_root / "manifests" / "conversion_manifest.csv"
    manifests = read_csv(manifest_path) if manifest_path.is_file() else []
    profiles: dict[str, dict[str, int]] = {}
    for profile in sorted({row.get("profile", "") for row in manifests if row.get("profile")}):
        latest = latest_success(manifests, profile)
        profiles[profile] = {
            "successful_studies": len(latest),
            "remaining_studies": max(0, len(registry) - len(latest)),
            "failure_events": sum(row.get("profile") == profile and row.get("status") == "failure" for row in manifests),
        }
    return {
        "checked_utc": utc_now(),
        "registry_records": len(registry),
        "pdf_records": sum(row["source_format"] == "pdf" for row in registry),
        "xml_records": sum(row["source_format"] == "xml" for row in registry),
        "manifest_events": len(manifests),
        "profiles": profiles,
    }
