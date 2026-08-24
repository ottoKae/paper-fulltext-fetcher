from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from . import CHUNK_SCHEMA_VERSION
from .common import atomic_write_text, clean_text
from .jats import REFERENCE_HEADING


def approximate_tokens(text: str) -> int:
    latin_words = len(re.findall(r"\b[A-Za-z0-9][A-Za-z0-9._/-]*\b", text))
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    punctuation = len(re.findall(r"[^\w\s]", text, flags=re.UNICODE))
    return max(1, math.ceil(latin_words * 1.3 + cjk * 0.75 + punctuation * 0.2))


def split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) == 1:
        paragraphs = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(paragraph[start : start + max_chars] for start in range(0, len(paragraph), max_chars))
        elif not current:
            current = paragraph
        elif len(current) + len(paragraph) + 2 <= max_chars:
            current += "\n\n" + paragraph
        else:
            pieces.append(current)
            current = paragraph
    if current:
        pieces.append(current)
    return pieces or [text[:max_chars]]


def build_chunks(
    parts: Iterable[dict[str, Any]],
    *,
    study_id: str,
    source_format: str,
    source_sha256: str,
    docling_json_sha256: str,
    target_chars: int = 2800,
    max_chars: int = 3600,
) -> list[dict[str, Any]]:
    if target_chars < 200 or max_chars < target_chars:
        raise ValueError("chunk sizes must satisfy 200 <= target_chars <= max_chars")
    chunks: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    pending_chars = 0

    def flush() -> None:
        nonlocal pending, pending_chars
        if not pending:
            return
        text = "\n\n".join(str(part.get("text") or "") for part in pending).strip()
        if not text:
            pending = []
            pending_chars = 0
            return
        pages = sorted(
            {
                int(prov["page_no"])
                for part in pending
                for prov in part.get("provenance", [])
                if prov.get("page_no")
            }
        )
        boxes = [
            prov
            for part in pending
            for prov in part.get("provenance", [])
            if prov.get("bbox")
        ]
        source_ids = [str(part["source_item_id"]) for part in pending if part.get("source_item_id")]
        section_path = str(pending[-1].get("section_path") or "")
        if source_format == "pdf":
            locator_type = "page_bbox" if boxes else "page"
            if not pages:
                locator_value = "page_unresolved"
            elif len(pages) == 1:
                locator_value = f"p.{pages[0]}"
            else:
                locator_value = f"pp.{pages[0]}-{pages[-1]}"
        else:
            locator_type = "xpath"
            if not source_ids:
                locator_value = f"chunk-{len(chunks) + 1:04d}"
            elif len(source_ids) == 1:
                locator_value = source_ids[0]
            else:
                locator_value = f"{source_ids[0]} … {source_ids[-1]}"
        chunks.append(
            {
                "schema_version": CHUNK_SCHEMA_VERSION,
                "chunk_id": f"{study_id}-C{len(chunks) + 1:04d}",
                "study_id": study_id,
                "source_format": source_format,
                "section_path": section_path,
                "item_labels": sorted({str(part.get("label") or "other") for part in pending}),
                "locator_type": locator_type,
                "locator_value": locator_value,
                "page_start": pages[0] if pages else None,
                "page_end": pages[-1] if pages else None,
                "bbox": boxes,
                "text": text,
                "token_count": approximate_tokens(text),
                "token_count_method": "deterministic_approx_v1",
                "source_item_ids": source_ids,
                "is_reference_section": any(bool(part.get("is_reference")) for part in pending),
                "extraction_eligible": not any(bool(part.get("is_reference")) for part in pending),
                "source_sha256": source_sha256,
                "docling_json_sha256": docling_json_sha256,
            }
        )
        pending = []
        pending_chars = 0

    for part in parts:
        text = clean_text(str(part.get("text") or ""))
        if not text:
            continue
        for piece in split_long_text(text, max_chars):
            if pending and pending_chars + len(piece) + 2 > max_chars:
                flush()
            item = dict(part)
            item["text"] = piece
            pending.append(item)
            pending_chars += len(piece) + 2
            if pending_chars >= target_chars:
                flush()
    flush()
    return chunks


def _label_value(item: Any) -> str:
    label = getattr(item, "label", "other")
    return getattr(label, "value", str(label)).lower()


def _item_text(item: Any, document: Any) -> str:
    label = _label_value(item)
    if label == "table" and hasattr(item, "export_to_markdown"):
        try:
            return clean_text(item.export_to_markdown(doc=document))
        except Exception:
            return ""
    text = getattr(item, "text", None)
    if text:
        return clean_text(str(text))
    if label == "picture" and hasattr(item, "caption_text"):
        try:
            return clean_text(item.caption_text(document))
        except Exception:
            return ""
    return ""


def docling_parts(document: Any) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    headings: list[str] = []
    reference_mode = False
    for item, level in document.iterate_items(with_groups=False, traverse_pictures=True):
        label = _label_value(item)
        text = _item_text(item, document)
        if not text:
            continue
        if label in {"section_header", "title"}:
            if label == "title":
                headings = [text]
            else:
                heading_level = max(1, int(level))
                headings = headings[: max(0, heading_level - 1)] + [text]
            reference_mode = bool(REFERENCE_HEADING.match(text.strip()))
        provenance: list[dict[str, Any]] = []
        for prov in getattr(item, "prov", []) or []:
            bbox = getattr(prov, "bbox", None)
            bbox_value = bbox.model_dump(mode="json") if bbox is not None else None
            provenance.append({"page_no": getattr(prov, "page_no", None), "bbox": bbox_value})
        parts.append(
            {
                "source_item_id": str(getattr(item, "self_ref", "")),
                "label": label,
                "text": text,
                "provenance": provenance,
                "section_path": " > ".join(headings),
                "is_reference": reference_mode,
            }
        )
    return parts


def jats_parts(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_item_id": row.get("xpath", ""),
            "label": row.get("label", "xml"),
            "text": row.get("text", ""),
            "provenance": [],
            "section_path": row.get("section_path", ""),
            "is_reference": bool(row.get("is_reference")),
        }
        for row in rows
    ]


def write_chunks(path: Path, chunks: list[dict[str, Any]]) -> None:
    atomic_write_text(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in chunks))
