#!/usr/bin/env python3
"""Prepare verified scholarly PDF/JATS XML as a searchable, locatable corpus."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from corpus_pipeline.audit import corpus_status, run_verify
from corpus_pipeline.common import (
    atomic_write_json,
    load_registry,
    redact_error,
    runtime_paths,
    utc_now,
)
from corpus_pipeline.engine import make_converter, profile_spec, run_conversion
from corpus_pipeline.quality import run_quality
from corpus_pipeline.rechunk import run_rechunk
from corpus_pipeline.registry import build_registry, write_registry


VERSION = "0.3.1"


def package_version(name: str, *aliases: str) -> str:
    for candidate in (name, *aliases):
        try:
            return version(candidate)
        except PackageNotFoundError:
            continue
    return "not-installed"


def synthetic_text_pdf(text: str) -> bytes:
    """Build a deterministic one-page PDF with a searchable text layer."""
    try:
        escaped = text.encode("ascii").decode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("synthetic PDF text must be ASCII") from error
    escaped = escaped.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT\n/F1 18 Tf\n72 720 Td\n({escaped}) Tj\nET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


def command_register(args: argparse.Namespace) -> int:
    runtime = runtime_paths(args.config)
    audit_path = args.audit.resolve() if args.audit else runtime.audit_records
    registry, summary = build_registry(runtime, audit_path)
    if args.dry_run:
        summary = {**summary, "mode": "dry_run", "written": False}
    elif summary["registry_ready"]:
        write_registry(runtime, registry, summary)
        summary = {**summary, "written": True}
    else:
        summary = {**summary, "written": False}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["registry_ready"] else 2


def command_self_test(args: argparse.Namespace) -> int:
    public, private = profile_spec(
        "base",
        threads=1,
        artifacts_path=None,
        settings={"ocr_languages": ["english"], "target_chars": 1200, "max_chars": 1800},
        no_tables=True,
    )
    pdf_requested = bool(args.pdf)
    pdf_passed: bool | None = None
    with tempfile.TemporaryDirectory(prefix="paper-corpus-self-test-") as temporary:
        source = Path(temporary) / "sample.nxml"
        source.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article SYSTEM "JATS-archive">
<article article-type="research-article" dtd-version="1.3"><front><journal-meta><journal-title-group><journal-title>Example Journal</journal-title></journal-title-group></journal-meta><article-meta><title-group><article-title>Corpus self test</article-title></title-group></article-meta></front>
<body><sec><title>Methods</title><p>Locatable local full text is available.</p></sec></body></article>
""",
            encoding="utf-8",
        )
        converter = make_converter(private)
        result = converter.convert(source, raises_on_error=True)
        markdown = result.document.export_to_markdown()
        if pdf_requested:
            pdf_source = Path(temporary) / "sample.pdf"
            pdf_source.write_bytes(synthetic_text_pdf("Corpus PDF self test"))
            pdf_result = converter.convert(pdf_source, raises_on_error=True)
            pdf_markdown = pdf_result.document.export_to_markdown()
            pdf_passed = len(pdf_result.document.pages) == 1 and "Corpus PDF self test" in pdf_markdown
    jats_passed = "Corpus self test" in markdown and "Locatable local full text" in markdown
    passed = jats_passed and (pdf_passed is True if pdf_requested else True)
    report = {
        "passed": passed,
        "docling_version": public["docling_version"],
        "remote_services_enabled": public["enable_remote_services"],
        "fixtures": {
            "synthetic_jats": jats_passed,
            "synthetic_pdf": pdf_passed if pdf_requested else "not_requested",
        },
        "pdf_model_download_may_be_required": pdf_requested,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


def command_doctor(args: argparse.Namespace) -> int:
    runtime = runtime_paths(args.config)
    modules = {
        "docling": importlib.util.find_spec("docling") is not None,
        "docling_core": importlib.util.find_spec("docling_core") is not None,
        "onnxruntime": importlib.util.find_spec("onnxruntime") is not None,
        "pypdfium2": importlib.util.find_spec("pypdfium2") is not None,
    }
    registry = load_registry(runtime.registry)
    source_bytes = sum(int(row["source_bytes"]) for row in registry)
    disk = shutil.disk_usage(runtime.workspace)
    recommended_free = source_bytes * 3 + 5 * 1024**3
    artifacts = args.artifacts_path.resolve() if args.artifacts_path else None
    blocking: list[str] = []
    if not all(modules.values()):
        blocking.append("corpus_dependencies_missing")
    if disk.free < recommended_free:
        blocking.append("insufficient_recommended_disk_headroom")
    if artifacts is not None and (not artifacts.is_dir() or not any(artifacts.rglob("*"))):
        blocking.append("model_artifacts_path_empty_or_missing")
    report = {
        "checked_utc": utc_now(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "packages": {
            "docling": package_version("docling", "docling-slim"),
            "docling_core": package_version("docling-core"),
            "onnxruntime": package_version("onnxruntime"),
            "pypdfium2": package_version("pypdfium2"),
        },
        "modules_available": modules,
        "registry_records": len(registry),
        "pdf_records": sum(row["source_format"] == "pdf" for row in registry),
        "xml_records": sum(row["source_format"] == "xml" for row in registry),
        "source_bytes": source_bytes,
        "disk_free_bytes": disk.free,
        "recommended_free_bytes": recommended_free,
        "disk_headroom_ok": disk.free >= recommended_free,
        "artifacts_configured": artifacts is not None,
        "artifacts_detected": bool(artifacts and artifacts.is_dir() and any(artifacts.rglob("*"))),
        "remote_services_enabled": False,
        "blocking_errors": blocking,
        "ready": not blocking,
    }
    manifest_dir = runtime.corpus_root / "manifests"
    atomic_write_json(manifest_dir / "preflight.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready"] else 2


def command_convert(args: argparse.Namespace) -> int:
    runtime = runtime_paths(args.config)
    selection = args.selection or args.from_retry
    code, summary = run_conversion(
        runtime,
        profile=args.profile,
        selection=selection.resolve() if selection else None,
        limit=args.limit,
        workers=args.workers,
        threads=args.threads,
        batch_size=args.batch_size,
        resume=args.resume,
        artifacts_path=args.artifacts_path.resolve() if args.artifacts_path else None,
        run_id=args.run_id,
        no_tables=args.no_tables,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return code


def command_chunk(args: argparse.Namespace) -> int:
    runtime = runtime_paths(args.config)
    code, summary = run_rechunk(
        runtime,
        profile=args.profile,
        study_id=args.study_id,
        target_chars=args.target_chars,
        max_chars=args.max_chars,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return code


def command_assess(args: argparse.Namespace) -> int:
    code, summary = run_quality(runtime_paths(args.config), args.profile)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return code


def command_verify(args: argparse.Namespace) -> int:
    code, summary = run_verify(runtime_paths(args.config), args.profile)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return code


def command_status(args: argparse.Namespace) -> int:
    print(json.dumps(corpus_status(runtime_paths(args.config)), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Workflow:\n"
            "  corpus_tool.py register --config my-review/acquisition.local.toml\n"
            "  corpus_tool.py doctor --config my-review/acquisition.local.toml\n"
            "  corpus_tool.py convert --config my-review/acquisition.local.toml --profile benchmark\n"
            "  corpus_tool.py convert --config my-review/acquisition.local.toml --profile base --resume\n"
            "  corpus_tool.py assess --config my-review/acquisition.local.toml --profile base\n"
            "  corpus_tool.py verify --config my-review/acquisition.local.toml --profile base"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    self_test = sub.add_parser("self-test", help="Run local synthetic conversion checks without user documents")
    self_test.add_argument(
        "--pdf",
        action="store_true",
        help="Also convert a one-page synthetic PDF; the first run may download local model weights",
    )
    self_test.set_defaults(function=command_self_test)

    register = sub.add_parser("register", help="Build a stable corpus registry from the latest acquisition audit")
    register.add_argument("--config", type=Path, required=True)
    register.add_argument("--audit", type=Path)
    register.add_argument("--dry-run", action="store_true")
    register.set_defaults(function=command_register)

    doctor = sub.add_parser("doctor", help="Check optional Docling dependencies, registry and disk headroom")
    doctor.add_argument("--config", type=Path, required=True)
    doctor.add_argument("--artifacts-path", type=Path)
    doctor.set_defaults(function=command_doctor)

    convert = sub.add_parser("convert", help="Convert registered PDF/JATS XML into JSON, Markdown and evidence chunks")
    convert.add_argument("--config", type=Path, required=True)
    convert.add_argument("--profile", choices=["benchmark", "base", "force-ocr", "accurate"], required=True)
    source = convert.add_mutually_exclusive_group()
    source.add_argument("--selection", type=Path)
    source.add_argument("--from-retry", type=Path)
    convert.add_argument("--limit", type=int)
    convert.add_argument("--workers", type=int, default=1)
    convert.add_argument("--threads", type=int, default=max(1, min(8, os.cpu_count() or 4)))
    convert.add_argument("--batch-size", type=int, default=25)
    convert.add_argument("--resume", action="store_true")
    convert.add_argument("--artifacts-path", type=Path)
    convert.add_argument("--run-id")
    convert.add_argument("--no-tables", action="store_true", help="Skip table structure models; output records this limitation")
    convert.set_defaults(function=command_convert)

    chunk = sub.add_parser("chunk", help="Build a new deterministic chunk set from existing conversion outputs")
    chunk.add_argument("--config", type=Path, required=True)
    chunk.add_argument("--profile", choices=["benchmark", "base", "force-ocr", "accurate"], default="base")
    chunk.add_argument("--study-id")
    chunk.add_argument("--target-chars", type=int)
    chunk.add_argument("--max-chars", type=int)
    chunk.set_defaults(function=command_chunk)

    assess = sub.add_parser("assess", help="Assess text, identity and page quality; create an OCR retry queue")
    assess.add_argument("--config", type=Path, required=True)
    assess.add_argument("--profile", choices=["benchmark", "base", "force-ocr", "accurate"], default="base")
    assess.set_defaults(function=command_assess)

    verify = sub.add_parser("verify", help="Verify source/output hashes, chunk identity and locators")
    verify.add_argument("--config", type=Path, required=True)
    verify.add_argument("--profile", choices=["benchmark", "base", "force-ocr", "accurate"], default="base")
    verify.set_defaults(function=command_verify)

    status = sub.add_parser("status", help="Summarize registry and conversion progress without printing bibliography content")
    status.add_argument("--config", type=Path, required=True)
    status.set_defaults(function=command_status)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.function(args))
    except KeyboardInterrupt:
        print("Interrupted; completed outputs and event logs are preserved.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"{type(error).__name__}: {redact_error(str(error))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
