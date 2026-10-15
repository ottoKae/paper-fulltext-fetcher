from __future__ import annotations

import csv
import json
import os
import platform
import re
import shutil
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .chunks import build_chunks, docling_parts, jats_parts, write_chunks
from .common import (
    RuntimePaths,
    append_csv_row,
    append_jsonl,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    config_sha256,
    load_registry,
    read_csv,
    redact_error,
    relative_posix,
    selection_ids,
    sha256_file,
    utc_now,
)
from .jats import prepare_jats


MANIFEST_FIELDS = [
    "run_id",
    "study_id",
    "source_sha256",
    "source_format",
    "source_relpath",
    "conversion_source_relpath",
    "conversion_source_sha256",
    "jats_preparation",
    "parser",
    "profile",
    "config_sha256",
    "docling_version",
    "docling_core_version",
    "python_version",
    "started_utc",
    "finished_utc",
    "duration_seconds",
    "status",
    "error_class",
    "error_message",
    "page_count",
    "text_items",
    "table_items",
    "picture_items",
    "chunk_count",
    "ocr_used",
    "ocr_page_count",
    "table_mode",
    "table_extraction",
    "total_chars",
    "json_relpath",
    "json_sha256",
    "md_relpath",
    "md_sha256",
    "chunks_relpath",
    "chunks_sha256",
    "source_map_relpath",
    "source_map_sha256",
    "retry_level",
]


_WORKER_CONTEXT: dict[str, Any] = {}


def package_version(name: str, *aliases: str) -> str:
    for candidate in (name, *aliases):
        try:
            return version(candidate)
        except PackageNotFoundError:
            continue
    return "not-installed"


def corpus_settings(runtime: RuntimePaths) -> dict[str, Any]:
    values = runtime.config.get("corpus") or {}
    pdf_backend = str(values.get("pdf_backend", "default"))
    if pdf_backend not in {"default", "pypdfium2"}:
        raise ValueError("corpus.pdf_backend must be default or pypdfium2")
    languages = values.get("ocr_languages", ["english"])
    if isinstance(languages, str):
        languages = [languages]
    return {
        "pdf_backend": pdf_backend,
        "ocr_languages": [str(value) for value in languages if str(value).strip()] or ["english"],
        "target_chars": int(values.get("target_chars", 2800)),
        "max_chars": int(values.get("max_chars", 3600)),
    }


def profile_spec(
    profile: str,
    *,
    threads: int,
    artifacts_path: Path | None,
    settings: dict[str, Any],
    no_tables: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if profile not in {"benchmark", "base", "force-ocr", "accurate"}:
        raise ValueError(f"unsupported conversion profile: {profile}")
    pdf_backend = settings.get("pdf_backend", "default")
    if pdf_backend not in {"default", "pypdfium2"}:
        raise ValueError("unsupported PDF backend")
    public = {
        "profile": profile,
        "pipeline": "standard",
        "pdf_backend": pdf_backend,
        "device": "cpu",
        "threads": threads,
        "do_ocr": True,
        "ocr_engine": "rapidocr",
        "ocr_languages": settings["ocr_languages"],
        "force_full_page_ocr": profile == "force-ocr",
        "do_table_structure": not no_tables,
        "table_mode": "accurate" if profile == "accurate" else "fast",
        "table_extraction": "disabled" if no_tables else "enabled",
        "generate_images": False,
        "enable_remote_services": False,
        "allow_external_plugins": False,
        "jats_format_selection": "explicit_validated_jats",
        "document_timeout": 1200,
        "artifacts_configured": artifacts_path is not None,
        "chunker": {
            "name": "deterministic_provenance_v1",
            "target_chars": settings["target_chars"],
            "max_chars": settings["max_chars"],
        },
        "docling_version": package_version("docling", "docling-slim"),
        "docling_core_version": package_version("docling-core"),
    }
    private = dict(public)
    private["artifacts_path"] = str(artifacts_path.resolve()) if artifacts_path else None
    return public, private


def make_converter(spec: dict[str, Any]) -> Any:
    try:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ModuleNotFoundError as error:
        raise RuntimeError("Docling corpus dependencies are missing; run bootstrap.ps1 -Corpus") from error

    options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=bool(spec["do_table_structure"]),
        generate_page_images=False,
        generate_picture_images=False,
        generate_table_images=False,
        enable_remote_services=False,
        allow_external_plugins=False,
        document_timeout=int(spec["document_timeout"]),
        accelerator_options=AcceleratorOptions(
            device=AcceleratorDevice.CPU,
            num_threads=int(spec["threads"]),
        ),
        ocr_options=RapidOcrOptions(
            lang=list(spec["ocr_languages"]),
            force_full_page_ocr=bool(spec["force_full_page_ocr"]),
        ),
    )
    if spec["do_table_structure"]:
        options.table_structure_options.mode = (
            TableFormerMode.ACCURATE if spec["table_mode"] == "accurate" else TableFormerMode.FAST
        )
    if spec.get("artifacts_path"):
        options.artifacts_path = Path(spec["artifacts_path"])
    pdf_format = PdfFormatOption(pipeline_options=options)
    if spec.get("pdf_backend", "default") == "pypdfium2":
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

        pdf_format = PdfFormatOption(pipeline_options=options, backend=PyPdfiumDocumentBackend)
    elif spec.get("pdf_backend", "default") != "default":
        raise ValueError("unsupported PDF backend")
    return DocumentConverter(format_options={InputFormat.PDF: pdf_format})


def convert_validated_jats(converter: Any, source: Path) -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import InputDocument

    options = converter.format_to_options[InputFormat.XML_JATS]
    document = InputDocument(
        path_or_stream=source,
        format=InputFormat.XML_JATS,
        backend=options.backend,
        backend_options=options.backend_options_for_input(source),
    )
    pipeline = options.pipeline_cls(options.pipeline_options)
    return pipeline.execute(document, raises_on_error=False)


def benchmark_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    pdfs = sorted(
        (row for row in records if row["source_format"] == "pdf"),
        key=lambda row: (int(row["source_bytes"]), row["study_id"]),
    )
    xmls = sorted((row for row in records if row["source_format"] == "xml"), key=lambda row: row["study_id"])
    chosen: list[dict[str, str]] = []
    if pdfs:
        for position in (0.05, 0.25, 0.50, 0.75, 0.95):
            chosen.append(pdfs[min(len(pdfs) - 1, round((len(pdfs) - 1) * position))])
    if xmls:
        chosen.extend([xmls[0], xmls[-1]])
    seen: set[str] = set()
    return [row for row in chosen if not (row["study_id"] in seen or seen.add(row["study_id"]))]


def choose_records(
    records: list[dict[str, str]],
    profile: str,
    selection: Path | None,
    limit: int | None,
) -> list[dict[str, str]]:
    by_id = {row["study_id"]: row for row in records}
    if selection:
        ids = selection_ids(selection)
        missing = [study_id for study_id in ids if study_id not in by_id]
        if missing:
            raise ValueError(f"selection contains unknown study IDs: {missing[:10]}")
        chosen = [by_id[study_id] for study_id in ids]
    elif profile == "benchmark":
        chosen = benchmark_records(records)
    elif profile in {"force-ocr", "accurate"}:
        raise ValueError(f"profile {profile} requires --selection or --from-retry")
    else:
        chosen = records
    if limit is not None and limit < 1:
        raise ValueError("--limit must be at least 1")
    return chosen[:limit] if limit is not None else chosen


def output_directories(runtime: RuntimePaths, profile: str, config8: str, run_id: str) -> dict[str, Path]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", run_id):
        raise ValueError("run ID must be a safe single path component of at most 96 characters")
    root = runtime.corpus_root / "derived" / profile / config8 / run_id
    return {
        "root": root,
        "json": root / "docling_json",
        "markdown": root / "markdown",
        "chunks": root / "chunks",
        "jats": root / "jats",
        "source_maps": root / "source_maps",
    }


def save_document_json(document: Any, path: Path) -> None:
    try:
        from docling_core.types.doc import ImageRefMode
    except ModuleNotFoundError as error:
        raise RuntimeError("docling-core is missing; run bootstrap.ps1 -Corpus") from error
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp.json", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        document.save_as_json(temporary, image_mode=ImageRefMode.PLACEHOLDER, indent=2)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def successful_resume(row: dict[str, str], expected: dict[str, str], workspace: Path) -> bool:
    if row.get("status") not in {"success", "partial_success"}:
        return False
    if row.get("source_sha256") != expected["source_sha256"]:
        return False
    if row.get("config_sha256") != expected["config_sha256"]:
        return False
    required_outputs = [
        ("json_relpath", "json_sha256"),
        ("md_relpath", "md_sha256"),
        ("chunks_relpath", "chunks_sha256"),
    ]
    if row.get("source_format") == "xml":
        required_outputs.extend([
            ("conversion_source_relpath", "conversion_source_sha256"),
            ("source_map_relpath", "source_map_sha256"),
        ])
    for path_key, hash_key in required_outputs:
        relpath = row.get(path_key, "")
        if not relpath:
            return False
        path = workspace / relpath
        if not path.is_file() or sha256_file(path) != row.get(hash_key):
            return False
    return True


def init_worker(spec: dict[str, Any], workspace: str, directories: dict[str, str]) -> None:
    _WORKER_CONTEXT.clear()
    _WORKER_CONTEXT.update(
        {
            "spec": spec,
            "workspace": Path(workspace),
            "directories": {key: Path(value) for key, value in directories.items()},
            "converter": make_converter(spec),
        }
    )


def convert_record_worker(
    index: int,
    record: dict[str, str],
    run_id: str,
    profile: str,
    config_digest: str,
) -> tuple[int, dict[str, Any]]:
    try:
        from docling.datamodel.base_models import ConversionStatus
        from docling_core.types.doc import ImageRefMode
    except ModuleNotFoundError as error:
        raise RuntimeError("Docling corpus dependencies are missing; run bootstrap.ps1 -Corpus") from error

    spec = _WORKER_CONTEXT["spec"]
    workspace: Path = _WORKER_CONTEXT["workspace"]
    directories: dict[str, Path] = _WORKER_CONTEXT["directories"]
    converter = _WORKER_CONTEXT["converter"]
    study_id = record["study_id"]
    source = workspace / record["source_relpath"]
    conversion_source = source
    jats_preparation = "not_applicable"
    source_map_path: Path | None = None
    jats_rows: list[dict[str, Any]] = []
    started = utc_now()
    start_clock = time.perf_counter()
    row: dict[str, Any] = {
        "run_id": run_id,
        "study_id": study_id,
        "source_sha256": record["source_sha256"],
        "source_format": record["source_format"],
        "source_relpath": record["source_relpath"],
        "profile": profile,
        "config_sha256": config_digest,
        "docling_version": spec["docling_version"],
        "docling_core_version": spec["docling_core_version"],
        "python_version": platform.python_version(),
        "started_utc": started,
        "ocr_used": "forced_full_page" if spec["force_full_page_ocr"] else "auto_if_needed",
        "table_mode": spec["table_mode"],
        "table_extraction": spec["table_extraction"],
        "retry_level": 1 if profile == "force-ocr" else 0,
        "parser": "docling+jats_xpath" if record["source_format"] == "xml" else "docling",
    }
    try:
        if not source.is_file() or sha256_file(source) != record["source_sha256"]:
            raise ValueError("source file is missing or changed since corpus registration")
        if record["source_format"] == "xml":
            source_map_path = directories["source_maps"] / f"{study_id}.jsonl"
            conversion_source, jats_preparation, jats_rows = prepare_jats(
                source,
                directories["jats"] / f"{study_id}.nxml",
                source_map_path,
            )
        row["conversion_source_relpath"] = relative_posix(conversion_source, workspace)
        row["conversion_source_sha256"] = sha256_file(conversion_source)
        row["jats_preparation"] = jats_preparation
        result = (
            convert_validated_jats(converter, conversion_source)
            if record["source_format"] == "xml"
            else converter.convert(conversion_source, raises_on_error=False)
        )
        if result.status not in {ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS}:
            raise RuntimeError(f"Docling conversion status: {result.status}")
        document = result.document
        json_path = directories["json"] / f"{study_id}.json"
        markdown_path = directories["markdown"] / f"{study_id}.md"
        chunks_path = directories["chunks"] / f"{study_id}.jsonl"
        save_document_json(document, json_path)
        json_digest = sha256_file(json_path)
        markdown = document.export_to_markdown(
            image_mode=ImageRefMode.PLACEHOLDER,
            page_break_placeholder="\n\n<!-- page break -->\n\n",
        )
        atomic_write_text(markdown_path, markdown + ("\n" if markdown and not markdown.endswith("\n") else ""))
        parts = jats_parts(jats_rows) if record["source_format"] == "xml" else docling_parts(document)
        chunks = build_chunks(
            parts,
            study_id=study_id,
            source_format=record["source_format"],
            source_sha256=record["source_sha256"],
            docling_json_sha256=json_digest,
            target_chars=int(spec["chunker"]["target_chars"]),
            max_chars=int(spec["chunker"]["max_chars"]),
        )
        write_chunks(chunks_path, chunks)
        total_chars = sum(len(getattr(item, "text", "") or "") for item in document.texts)
        result_errors = " | ".join(redact_error(str(error)) for error in result.errors)
        row.update(
            {
                "status": getattr(result.status, "value", str(result.status)).lower(),
                "error_class": "",
                "error_message": result_errors[:2000],
                "page_count": len(document.pages),
                "text_items": len(document.texts),
                "table_items": len(document.tables),
                "picture_items": len(document.pictures),
                "chunk_count": len(chunks),
                "ocr_page_count": len(document.pages) if spec["force_full_page_ocr"] else "",
                "total_chars": total_chars,
                "json_relpath": relative_posix(json_path, workspace),
                "json_sha256": json_digest,
                "md_relpath": relative_posix(markdown_path, workspace),
                "md_sha256": sha256_file(markdown_path),
                "chunks_relpath": relative_posix(chunks_path, workspace),
                "chunks_sha256": sha256_file(chunks_path),
                "source_map_relpath": relative_posix(source_map_path, workspace) if source_map_path else "",
                "source_map_sha256": sha256_file(source_map_path) if source_map_path else "",
            }
        )
    except BaseException as error:
        row.update(
            {
                "status": "failure",
                "error_class": type(error).__name__,
                "error_message": redact_error(str(error)),
                "conversion_source_relpath": row.get("conversion_source_relpath", ""),
                "jats_preparation": jats_preparation,
            }
        )
    row["finished_utc"] = utc_now()
    row["duration_seconds"] = round(time.perf_counter() - start_clock, 3)
    return index, row


def run_conversion(
    runtime: RuntimePaths,
    *,
    profile: str,
    selection: Path | None,
    limit: int | None,
    workers: int,
    threads: int,
    batch_size: int,
    resume: bool,
    artifacts_path: Path | None,
    run_id: str | None,
    no_tables: bool,
) -> tuple[int, dict[str, Any]]:
    if workers < 1 or workers > 4:
        raise ValueError("workers must be between 1 and 4")
    if threads < 1 or batch_size < 1:
        raise ValueError("threads and batch size must be positive")
    settings = corpus_settings(runtime)
    public_spec, worker_spec = profile_spec(
        profile,
        threads=threads,
        artifacts_path=artifacts_path,
        settings=settings,
        no_tables=no_tables,
    )
    if public_spec["docling_version"] == "not-installed":
        raise RuntimeError("Docling corpus dependencies are missing; run bootstrap.ps1 -Corpus")
    config_digest = config_sha256(public_spec)
    config8 = config_digest[:8]
    run_id = run_id or f"{time.strftime('%Y%m%d_%H%M%S')}_{profile}_{config8}"
    directories = output_directories(runtime, profile, config8, run_id)
    records = choose_records(load_registry(runtime.registry), profile, selection, limit)
    manifest_path = runtime.corpus_root / "manifests" / "conversion_manifest.csv"
    if manifest_path.is_file():
        with manifest_path.open(encoding="utf-8-sig", newline="") as stream:
            if next(csv.reader(stream), []) != MANIFEST_FIELDS:
                raise ValueError("legacy manifest schema: archive and explicitly migrate it before conversion")
    run_dir = runtime.runs_root / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError("corpus run ID already exists; choose a new --run-id")
    directories["root"].mkdir(parents=True, exist_ok=False)
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(runtime.registry, run_dir / "registry.csv")
    shutil.copyfile(runtime.config_path, run_dir / "acquisition.local.toml")
    if selection:
        shutil.copyfile(selection, run_dir / "selection.csv")
    event_path = run_dir / "events.jsonl"
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    existing = read_csv(manifest_path) if manifest_path.is_file() else []
    prior_by_study: dict[str, list[dict[str, str]]] = {}
    for row in existing:
        prior_by_study.setdefault(row.get("study_id", ""), []).append(row)
    atomic_write_json(
        run_dir / "command.json",
        {
            "created_utc": utc_now(),
            "profile": profile,
            "selection_file": selection.name if selection else None,
            "requested_records": len(records),
            "workers": workers,
            "threads_per_worker": threads,
            "batch_size": batch_size,
            "resume": resume,
            "config": public_spec,
            "config_sha256": config_digest,
        },
    )
    atomic_write_json(
        run_dir / "environment.json",
        {
            "created_utc": utc_now(),
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "docling": public_spec["docling_version"],
            "docling_core": public_spec["docling_core_version"],
            "remote_services_enabled": False,
        },
    )
    skipped = 0
    pending: list[tuple[int, dict[str, str]]] = []
    for index, record in enumerate(records, start=1):
        expected = {"source_sha256": record["source_sha256"], "config_sha256": config_digest}
        if resume and any(
            successful_resume(row, expected, runtime.workspace)
            for row in prior_by_study.get(record["study_id"], [])
        ):
            skipped += 1
            append_jsonl(event_path, {"time_utc": utc_now(), "event": "resume_skip", "study_id": record["study_id"]})
            continue
        pending.append((index, record))

    current_rows: list[dict[str, Any]] = []
    if pending:
        serializable_dirs = {key: str(value) for key, value in directories.items()}
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=init_worker,
            initargs=(worker_spec, str(runtime.workspace), serializable_dirs),
        ) as executor:
            futures = {
                executor.submit(convert_record_worker, index, record, run_id, profile, config_digest): (index, record)
                for index, record in pending
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                index, record = futures[future]
                try:
                    returned_index, row = future.result()
                    if returned_index != index:
                        raise RuntimeError("worker returned an unexpected record index")
                except BaseException as error:
                    now = utc_now()
                    row = {
                        "run_id": run_id,
                        "study_id": record["study_id"],
                        "source_sha256": record["source_sha256"],
                        "source_format": record["source_format"],
                        "source_relpath": record["source_relpath"],
                        "profile": profile,
                        "config_sha256": config_digest,
                        "started_utc": now,
                        "finished_utc": now,
                        "duration_seconds": 0,
                        "status": "failure",
                        "error_class": type(error).__name__,
                        "error_message": redact_error(str(error)),
                    }
                current_rows.append(row)
                append_csv_row(manifest_path, row, MANIFEST_FIELDS)
                append_jsonl(
                    event_path,
                    {
                        "time_utc": utc_now(),
                        "event": "record_finished",
                        "study_id": row["study_id"],
                        "status": row["status"],
                        "error_class": row.get("error_class", ""),
                    },
                )
                if completed % batch_size == 0:
                    atomic_write_json(
                        run_dir / "checkpoint.json",
                        {
                            "updated_utc": utc_now(),
                            "completed": completed,
                            "pending": len(pending) - completed,
                            "success": sum(row["status"] in {"success", "partial_success"} for row in current_rows),
                            "failure": sum(row["status"] == "failure" for row in current_rows),
                        },
                    )

    success_rows = [row for row in current_rows if row["status"] in {"success", "partial_success"}]
    failure_rows = [row for row in current_rows if row["status"] == "failure"]
    atomic_write_csv(run_dir / "success.csv", success_rows, MANIFEST_FIELDS)
    atomic_write_csv(run_dir / "failure.csv", failure_rows, MANIFEST_FIELDS)
    atomic_write_csv(
        run_dir / "retry.csv",
        [{"study_id": row["study_id"], "error_class": row.get("error_class", "")} for row in failure_rows],
        ["study_id", "error_class"],
    )
    summary = {
        "finished_utc": utc_now(),
        "run_id": run_id,
        "profile": profile,
        "config_sha256": config_digest,
        "requested": len(records),
        "resume_skipped": skipped,
        "processed": len(current_rows),
        "success": len(success_rows),
        "failure": len(failure_rows),
        "status_counts": dict(Counter(row["status"] for row in current_rows)),
        "remote_services_enabled": False,
    }
    atomic_write_json(run_dir / "summary.json", summary)
    return (2 if failure_rows else 0), summary
