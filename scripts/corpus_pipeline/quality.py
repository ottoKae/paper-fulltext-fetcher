from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .common import (
    RuntimePaths,
    atomic_write_csv,
    atomic_write_json,
    latest_success,
    load_registry,
    read_csv,
    utc_now,
)


QUALITY_FIELDS = [
    "study_id",
    "profile",
    "config_sha256",
    "source_format",
    "source_relpath",
    "json_relpath",
    "page_count_docling",
    "page_count_source",
    "page_count_match",
    "total_chars",
    "chars_per_page",
    "low_text_pages",
    "low_text_page_ratio",
    "replacement_chars",
    "replacement_ratio",
    "printable_ratio",
    "repeated_line_ratio",
    "section_headers",
    "table_items",
    "picture_items",
    "title_token_coverage",
    "doi_found",
    "identity_warning",
    "quality_class",
    "ocr_recommended",
    "quality_reasons",
]


def normalize_doi(value: str) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    return text.rstrip(" .;,)")


def title_tokens(value: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def line_repeat_ratio(text: str) -> float:
    lines = [re.sub(r"\s+", " ", line).strip().casefold() for line in text.splitlines()]
    lines = [line for line in lines if len(line) >= 30]
    if not lines:
        return 0.0
    counts = Counter(lines)
    repeats = sum(count - 1 for count in counts.values() if count > 1)
    return repeats / len(lines)


def default_thresholds(runtime: RuntimePaths) -> dict[str, float]:
    values = runtime.config.get("corpus_quality") or {}
    return {
        "min_total_chars": float(values.get("min_total_chars", 3000)),
        "low_page_chars": float(values.get("low_page_chars", 100)),
        "max_low_text_page_ratio": float(values.get("max_low_text_page_ratio", 0.35)),
        "max_replacement_ratio": float(values.get("max_replacement_ratio", 0.005)),
        "min_printable_ratio": float(values.get("min_printable_ratio", 0.98)),
        "max_repeated_line_ratio": float(values.get("max_repeated_line_ratio", 0.15)),
        "min_title_token_coverage": float(values.get("min_title_token_coverage", 0.45)),
    }


def source_page_count(path: Path) -> int:
    try:
        import pypdfium2
    except ModuleNotFoundError as error:
        raise RuntimeError("pypdfium2 is missing; run bootstrap.ps1 -Corpus") from error
    document = pypdfium2.PdfDocument(str(path))
    try:
        return len(document)
    finally:
        document.close()


def assess_document(
    data: dict[str, Any],
    record: dict[str, str],
    manifest: dict[str, str],
    thresholds: dict[str, float],
    page_counter: Callable[[Path], int],
    workspace: Path,
) -> dict[str, Any]:
    texts = data.get("texts", [])
    text_values = [str(item.get("text") or "") for item in texts]
    full_text = "\n".join(text_values)
    total_chars = len(full_text)
    page_chars: dict[int, int] = Counter()
    for item in texts:
        value = str(item.get("text") or "")
        pages = {prov.get("page_no") for prov in item.get("prov", []) if prov.get("page_no")}
        if pages:
            share = max(1, len(value) // len(pages))
            for page in pages:
                page_chars[int(page)] += share
    docling_pages = int(manifest.get("page_count") or 0)
    if record["source_format"] == "pdf":
        source_pages = page_counter(workspace / record["source_relpath"])
        page_match = source_pages == docling_pages
        low_pages = sum(
            page_chars.get(page, 0) < thresholds["low_page_chars"]
            for page in range(1, source_pages + 1)
        )
        low_ratio = low_pages / max(source_pages, 1)
        chars_per_page = total_chars / max(source_pages, 1)
    else:
        source_pages = 0
        page_match = True
        low_pages = 0
        low_ratio = 0.0
        chars_per_page = 0.0
    replacement = full_text.count("\ufffd")
    replacement_ratio = replacement / max(total_chars, 1)
    printable = sum(character.isprintable() or character in "\n\t" for character in full_text)
    printable_ratio = printable / max(total_chars, 1)
    repeated_ratio = line_repeat_ratio(full_text)
    labels = Counter(str(item.get("label") or "") for item in texts)
    expected_title_tokens = title_tokens(record.get("title", ""))
    observed_title_tokens = title_tokens(full_text[:30000])
    title_coverage = len(expected_title_tokens & observed_title_tokens) / max(len(expected_title_tokens), 1)
    doi = normalize_doi(record.get("doi", ""))
    doi_found = bool(doi) and doi in full_text.casefold().replace("https://doi.org/", "")
    identity_warning = title_coverage < thresholds["min_title_token_coverage"] and (not doi or not doi_found)
    reasons: list[str] = []
    if not page_match:
        reasons.append("page_count_mismatch")
    if total_chars < thresholds["min_total_chars"]:
        reasons.append("very_low_total_text")
    if low_ratio > thresholds["max_low_text_page_ratio"]:
        reasons.append("many_low_text_pages")
    if replacement_ratio > thresholds["max_replacement_ratio"]:
        reasons.append("replacement_character_rate")
    if printable_ratio < thresholds["min_printable_ratio"]:
        reasons.append("low_printable_ratio")
    if repeated_ratio > thresholds["max_repeated_line_ratio"]:
        reasons.append("repeated_text")
    if identity_warning:
        reasons.append("identity_text_warning")
    retry_reasons = {
        "page_count_mismatch",
        "very_low_total_text",
        "many_low_text_pages",
        "replacement_character_rate",
        "low_printable_ratio",
        "repeated_text",
    }
    ocr_recommended = record["source_format"] == "pdf" and bool(retry_reasons & set(reasons))
    quality_class = "A_ready" if not reasons else ("C_retry_required" if ocr_recommended else "B_usable_with_warnings")
    return {
        "study_id": record["study_id"],
        "profile": manifest["profile"],
        "config_sha256": manifest["config_sha256"],
        "source_format": record["source_format"],
        "source_relpath": record["source_relpath"],
        "json_relpath": manifest["json_relpath"],
        "page_count_docling": docling_pages,
        "page_count_source": source_pages,
        "page_count_match": str(page_match).lower(),
        "total_chars": total_chars,
        "chars_per_page": round(chars_per_page, 1),
        "low_text_pages": low_pages,
        "low_text_page_ratio": round(low_ratio, 4),
        "replacement_chars": replacement,
        "replacement_ratio": round(replacement_ratio, 6),
        "printable_ratio": round(printable_ratio, 6),
        "repeated_line_ratio": round(repeated_ratio, 6),
        "section_headers": labels.get("section_header", 0),
        "table_items": len(data.get("tables", [])),
        "picture_items": len(data.get("pictures", [])),
        "title_token_coverage": round(title_coverage, 4),
        "doi_found": str(doi_found).lower(),
        "identity_warning": str(identity_warning).lower(),
        "quality_class": quality_class,
        "ocr_recommended": str(ocr_recommended).lower(),
        "quality_reasons": "|".join(reasons),
    }


def run_quality(runtime: RuntimePaths, profile: str) -> tuple[int, dict[str, Any]]:
    registry = load_registry(runtime.registry)
    manifest_path = runtime.corpus_root / "manifests" / "conversion_manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError("conversion manifest was not found; run corpus convert first")
    manifests = read_csv(manifest_path)
    by_study = latest_success(manifests, profile)
    thresholds = default_thresholds(runtime)
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for record in registry:
        manifest = by_study.get(record["study_id"])
        if not manifest:
            missing.append(record["study_id"])
            continue
        json_path = runtime.workspace / manifest["json_relpath"]
        if not json_path.is_file():
            missing.append(record["study_id"])
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        rows.append(
            assess_document(data, record, manifest, thresholds, source_page_count, runtime.workspace)
        )
    quality_dir = runtime.corpus_root / "quality"
    atomic_write_csv(quality_dir / f"quality_{profile}.csv", rows, QUALITY_FIELDS)
    retry = [
        {
            "study_id": row["study_id"],
            "source_format": row["source_format"],
            "quality_reasons": row["quality_reasons"],
        }
        for row in rows
        if row["ocr_recommended"] == "true"
    ]
    atomic_write_csv(
        quality_dir / f"retry_ocr_{profile}.csv",
        retry,
        ["study_id", "source_format", "quality_reasons"],
    )
    summary = {
        "created_utc": utc_now(),
        "profile": profile,
        "registry_records": len(registry),
        "assessed": len(rows),
        "missing_conversion": len(missing),
        "quality_counts": dict(Counter(str(row["quality_class"]) for row in rows)),
        "ocr_recommended": len(retry),
        "thresholds": thresholds,
    }
    atomic_write_json(quality_dir / f"quality_{profile}_summary.json", summary)
    return (2 if missing else 0), summary
