from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is required
    tomllib = None


REGISTRY_FIELDS = [
    "study_id",
    "record_id",
    "excel_row",
    "title",
    "doi",
    "year",
    "source_title",
    "publisher",
    "authors",
    "source_format",
    "source_relpath",
    "source_bytes",
    "source_sha256",
    "acquisition_status",
    "acquisition_validation",
]

SUCCESS_ACQUISITION_STATUSES = {"valid_pdf", "visual_approved_pdf", "valid_xml"}


@dataclass(frozen=True)
class RuntimePaths:
    config_path: Path
    workspace: Path
    config: dict[str, Any]
    pdf_dir: Path
    xml_dir: Path
    acquisition_output: Path
    audit_records: Path
    corpus_root: Path
    registry: Path
    runs_root: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def config_sha256(value: Any) -> str:
    return sha256_text(canonical_json(value))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def atomic_write_text(path: Path, value: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as stream:
            stream.write(value)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def atomic_write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(materialized)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def append_csv_row(path: Path, row: dict[str, Any], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)
        stream.flush()
        os.fsync(stream.fileno())


def resolve_path(value: str | Path, base: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def relative_posix(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError as error:
        raise ValueError("corpus sources and outputs must stay inside the configured workspace") from error


def load_config(path: Path) -> dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("Python 3.11 or newer is required")
    if not path.is_file():
        raise FileNotFoundError("acquisition config was not found")
    with path.open("rb") as stream:
        return tomllib.load(stream)


def runtime_paths(config_path: Path) -> RuntimePaths:
    config_path = config_path.resolve()
    workspace = config_path.parent
    config = load_config(config_path)
    project = config.get("project") or {}
    corpus = config.get("corpus") or {}
    pdf_dir = resolve_path(project.get("pdf_dir", "papers_pdf"), workspace)
    xml_dir = resolve_path(project.get("xml_dir", "papers_xml"), workspace)
    acquisition_output = resolve_path(project.get("output_root", "outputs/acquisition"), workspace)
    corpus_root = resolve_path(corpus.get("root", "corpus"), workspace)
    runs_root = resolve_path(corpus.get("runs_root", "outputs/corpus"), workspace)
    registry = resolve_path(corpus.get("registry", "corpus/registry.csv"), workspace)
    for path in (pdf_dir, xml_dir, acquisition_output, corpus_root, runs_root, registry.parent):
        relative_posix(path, workspace)
    return RuntimePaths(
        config_path=config_path,
        workspace=workspace,
        config=config,
        pdf_dir=pdf_dir,
        xml_dir=xml_dir,
        acquisition_output=acquisition_output,
        audit_records=acquisition_output / "audit" / "records.csv",
        corpus_root=corpus_root,
        registry=registry,
        runs_root=runs_root,
    )


def safe_study_id(value: str, row: dict[str, str]) -> str:
    candidate = str(value or "").strip()
    if candidate and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", candidate):
        return candidate
    basis = str(row.get("doi") or "").strip().casefold()
    if not basis:
        basis = "|".join(
            [str(row.get("title") or "").strip().casefold(), str(row.get("year") or "").strip()]
        )
    return f"paper-{sha256_text(basis)[:12]}"


def load_registry(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError("corpus registry was not found; run corpus register first")
    rows = read_csv(path)
    if not rows:
        raise ValueError("corpus registry is empty")
    missing = [field for field in REGISTRY_FIELDS if field not in rows[0]]
    if missing:
        raise ValueError(f"corpus registry is missing required fields: {missing}")
    ids = [row["study_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("corpus registry contains duplicate study_id values")
    return rows


def selection_ids(path: Path) -> list[str]:
    rows = read_csv(path)
    if not rows or "study_id" not in rows[0]:
        raise ValueError("selection CSV must contain a study_id column")
    values = [row["study_id"].strip() for row in rows if row.get("study_id", "").strip()]
    if len(values) != len(set(values)):
        raise ValueError("selection CSV contains duplicate study IDs")
    return values


def clean_text(value: str) -> str:
    text = value.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def redact_error(value: str, limit: int = 2000) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"(?i)[A-Z]:\\Users\\[^\\\s]+(?:\\[^\s]*)?", "<local-path>", text)
    posix_home_pattern = r"/" + r"home/[^/\s]+(?:/[^\s]*)?"
    text = re.sub(posix_home_pattern, "<local-path>", text)
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "<email>", text, flags=re.I)
    text = re.sub(r"(?i)(api[_-]?key|token|password|authorization)=([^\s&]+)", r"\1=<redacted>", text)
    return text[:limit]


def latest_success(rows: list[dict[str, str]], profile: str) -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("profile") == profile and row.get("status") in {"success", "partial_success"}:
            selected[row["study_id"]] = row
    return selected
