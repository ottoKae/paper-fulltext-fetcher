from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from corpus_pipeline import CHUNK_SCHEMA_VERSION  # noqa: E402
from corpus_pipeline.audit import corpus_status, run_verify  # noqa: E402
from corpus_pipeline.chunks import build_chunks, jats_parts  # noqa: E402
from corpus_pipeline.common import (  # noqa: E402
    REGISTRY_FIELDS,
    atomic_write_csv,
    config_sha256,
    redact_error,
    runtime_paths,
    sha256_file,
)
from corpus_pipeline.engine import (  # noqa: E402
    MANIFEST_FIELDS,
    benchmark_records,
    profile_spec,
    successful_resume,
)
from corpus_pipeline.jats import prepare_jats  # noqa: E402
from corpus_pipeline.quality import assess_document, default_thresholds  # noqa: E402
from corpus_pipeline.rechunk import run_rechunk  # noqa: E402
from corpus_pipeline.registry import build_registry, write_registry  # noqa: E402


SPEC = importlib.util.spec_from_file_location("corpus_tool", SCRIPTS / "corpus_tool.py")
assert SPEC and SPEC.loader
corpus_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(corpus_tool)


def make_workspace(root: Path) -> tuple[Path, object]:
    workspace = root / "review"
    workspace.mkdir()
    for relative in ("papers_pdf", "papers_xml", "outputs/acquisition/audit"):
        (workspace / relative).mkdir(parents=True)
    config = workspace / "acquisition.local.toml"
    config.write_text(
        """[project]
pdf_dir = "papers_pdf"
xml_dir = "papers_xml"
output_root = "outputs/acquisition"

[corpus]
root = "corpus"
registry = "corpus/registry.csv"
runs_root = "outputs/corpus"
ocr_languages = ["english"]
target_chars = 240
max_chars = 360
""",
        encoding="utf-8",
    )
    return config, runtime_paths(config)


def write_audit(runtime: object, rows: list[dict[str, str]]) -> Path:
    path = runtime.audit_records
    fields = [
        "record_id", "excel_row", "title", "doi", "year", "source_title",
        "publisher", "authors", "status", "fulltext_file", "validation",
        "bytes", "sha256",
    ]
    atomic_write_csv(path, rows, fields)
    return path


def registry_row(runtime: object, source: Path, source_format: str = "pdf", study_id: str = "demo-1") -> dict[str, str]:
    return {
        "study_id": study_id,
        "record_id": study_id,
        "excel_row": "2",
        "title": "Synthetic Surface Study",
        "doi": "10.5555/example.corpus",
        "year": "2025",
        "source_title": "Synthetic Journal",
        "publisher": "Example Publisher",
        "authors": "Example Author",
        "source_format": source_format,
        "source_relpath": source.relative_to(runtime.workspace).as_posix(),
        "source_bytes": str(source.stat().st_size),
        "source_sha256": sha256_file(source),
        "acquisition_status": "valid_xml" if source_format == "xml" else "valid_pdf",
        "acquisition_validation": "synthetic_identity_match",
    }


class CorpusToolTests(unittest.TestCase):
    def test_version_and_parser_expose_corpus_commands(self) -> None:
        self.assertEqual(corpus_tool.VERSION, "0.3.0")
        parser = corpus_tool.build_parser()
        args = parser.parse_args(["status", "--config", "example.toml"])
        self.assertEqual(args.command, "status")
        args = parser.parse_args(["self-test"])
        self.assertEqual(args.command, "self-test")

    def test_runtime_rejects_outputs_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config, _ = make_workspace(Path(temp))
            config.write_text(
                '[project]\npdf_dir="papers_pdf"\nxml_dir="papers_xml"\noutput_root="outputs/acquisition"\n'
                '[corpus]\nroot="../outside"\n',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                runtime_paths(config)

    def test_registry_supports_arbitrary_pdf_and_xml_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config, runtime = make_workspace(Path(temp))
            pdf = runtime.pdf_dir / "one.pdf"
            xml = runtime.xml_dir / "two.xml"
            pdf.write_bytes(b"%PDF-1.4\nsynthetic")
            xml.write_text("<article><body><p>Synthetic XML text.</p></body></article>", encoding="utf-8")
            rows = [
                {
                    "record_id": "paper-a", "excel_row": "2", "title": "Synthetic A",
                    "doi": "10.5555/example.a", "year": "2024", "source_title": "J",
                    "publisher": "Example Publisher", "authors": "A", "status": "valid_pdf",
                    "fulltext_file": pdf.name, "validation": "ok", "bytes": str(pdf.stat().st_size),
                    "sha256": sha256_file(pdf),
                },
                {
                    "record_id": "paper-b", "excel_row": "3", "title": "Synthetic B",
                    "doi": "10.5555/example.b", "year": "2025", "source_title": "J",
                    "publisher": "Example Publisher", "authors": "B", "status": "valid_xml",
                    "fulltext_file": xml.name, "validation": "ok", "bytes": str(xml.stat().st_size),
                    "sha256": sha256_file(xml),
                },
                {
                    "record_id": "paper-c", "excel_row": "4", "title": "Missing",
                    "doi": "10.5555/example.c", "year": "2025", "source_title": "J",
                    "publisher": "Example Publisher", "authors": "C", "status": "missing",
                    "fulltext_file": "", "validation": "", "bytes": "", "sha256": "",
                },
            ]
            audit = write_audit(runtime, rows)
            registry, summary = build_registry(runtime, audit)
            self.assertEqual(len(registry), 2)
            self.assertEqual(summary["pdf_records"], 1)
            self.assertEqual(summary["xml_records"], 1)
            self.assertTrue(summary["registry_ready"])
            write_registry(runtime, registry, summary)
            self.assertTrue(runtime.registry.exists())

    def test_registry_blocks_source_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, runtime = make_workspace(Path(temp))
            pdf = runtime.pdf_dir / "one.pdf"
            pdf.write_bytes(b"%PDF-1.4\nsynthetic")
            audit = write_audit(runtime, [{
                "record_id": "paper-a", "excel_row": "2", "title": "Synthetic A",
                "doi": "10.5555/example.a", "year": "2024", "source_title": "J",
                "publisher": "Example Publisher", "authors": "A", "status": "valid_pdf",
                "fulltext_file": pdf.name, "validation": "ok", "bytes": str(pdf.stat().st_size),
                "sha256": "0" * 64,
            }])
            registry, summary = build_registry(runtime, audit)
            self.assertEqual(registry, [])
            self.assertEqual(summary["error_counts"]["source_hash_mismatch"], 1)

    def test_nested_oai_jats_preserves_xpath_and_reference_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "wrapped.xml"
            source.write_text(
                """<record xmlns:j="urn:jats"><metadata><j:article><j:front><j:article-meta>
                <j:title-group><j:article-title>Synthetic Article</j:article-title></j:title-group>
                </j:article-meta></j:front><j:body><j:sec><j:title>Methods</j:title>
                <j:p>Mapped evidence text.</j:p></j:sec></j:body><j:back><j:ref-list>
                <j:title>References</j:title><j:ref><j:mixed-citation>Example citation.</j:mixed-citation></j:ref>
                </j:ref-list></j:back></j:article></metadata></record>""",
                encoding="utf-8",
            )
            target = root / "derived.xml"
            source_map = root / "map.jsonl"
            _, mode, rows = prepare_jats(source, target, source_map)
            self.assertEqual(mode, "unwrapped_oai_jats")
            evidence = next(row for row in rows if "Mapped evidence" in row["text"])
            self.assertTrue(evidence["xpath"].startswith("/article[1]/body[1]"))
            self.assertEqual(evidence["section_path"], "Methods")
            citation = next(row for row in rows if "Example citation" in row["text"])
            self.assertTrue(citation["is_reference"])
            prepared = target.read_text(encoding="utf-8")
            self.assertIn('<!DOCTYPE article SYSTEM "JATS-archive">', prepared)
            self.assertNotIn("<!ENTITY", prepared)
            self.assertTrue(source_map.exists())

    def test_jats_rejects_entity_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "unsafe.xml"
            source.write_text('<!DOCTYPE article [<!ENTITY x "unsafe">]><article><p>&x;</p></article>', encoding="utf-8")
            with self.assertRaises(ValueError):
                prepare_jats(source, root / "derived.xml")

    def test_pdf_chunks_keep_pages_bbox_and_reference_exclusion(self) -> None:
        parts = [
            {"source_item_id": "#/texts/1", "label": "section_header", "text": "Methods", "section_path": "Methods", "provenance": [{"page_no": 2, "bbox": {"l": 1}}], "is_reference": False},
            {"source_item_id": "#/texts/2", "label": "text", "text": "Synthetic method evidence.", "section_path": "Methods", "provenance": [{"page_no": 2, "bbox": {"l": 2}}], "is_reference": False},
            {"source_item_id": "#/texts/3", "label": "section_header", "text": "References", "section_path": "References", "provenance": [{"page_no": 3, "bbox": {"l": 3}}], "is_reference": True},
        ]
        chunks = build_chunks(parts, study_id="demo", source_format="pdf", source_sha256="a" * 64, docling_json_sha256="b" * 64, target_chars=200, max_chars=300)
        self.assertEqual(chunks[0]["locator_type"], "page_bbox")
        self.assertEqual(chunks[0]["page_start"], 2)
        self.assertTrue(any(not chunk["extraction_eligible"] for chunk in chunks))

    def test_xml_chunks_use_xpath(self) -> None:
        parts = jats_parts([{"xpath": "/article[1]/body[1]/p[1]", "label": "p", "section_path": "Methods", "text": "Evidence", "is_reference": False}])
        chunks = build_chunks(parts, study_id="demo", source_format="xml", source_sha256="a" * 64, docling_json_sha256="b" * 64, target_chars=200, max_chars=300)
        self.assertEqual(chunks[0]["locator_type"], "xpath")
        self.assertEqual(chunks[0]["locator_value"], "/article[1]/body[1]/p[1]")

    def test_resume_requires_source_config_and_output_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values = {}
            for name in ("a.json", "a.md", "a.jsonl"):
                path = root / name
                path.write_text(name, encoding="utf-8")
                values[name] = sha256_file(path)
            row = {
                "status": "success", "source_sha256": "a" * 64, "config_sha256": "b" * 64,
                "json_relpath": "a.json", "json_sha256": values["a.json"],
                "md_relpath": "a.md", "md_sha256": values["a.md"],
                "chunks_relpath": "a.jsonl", "chunks_sha256": values["a.jsonl"],
            }
            self.assertTrue(successful_resume(row, {"source_sha256": "a" * 64, "config_sha256": "b" * 64}, root))
            (root / "a.md").write_text("changed", encoding="utf-8")
            self.assertFalse(successful_resume(row, {"source_sha256": "a" * 64, "config_sha256": "b" * 64}, root))

    def test_profile_spec_disables_remote_services(self) -> None:
        public, private = profile_spec("base", threads=2, artifacts_path=None, settings={"ocr_languages": ["en"], "target_chars": 2800, "max_chars": 3600}, no_tables=True)
        self.assertFalse(public["enable_remote_services"])
        self.assertFalse(public["allow_external_plugins"])
        self.assertEqual(public["table_extraction"], "disabled")
        self.assertIsNone(private["artifacts_path"])

    def test_benchmark_selection_handles_small_single_format_corpus(self) -> None:
        records = [{"study_id": f"p{index}", "source_format": "pdf", "source_bytes": str(index)} for index in range(1, 4)]
        selected = benchmark_records(records)
        self.assertEqual({row["study_id"] for row in selected}, {"p1", "p2", "p3"})

    def test_quality_metrics_route_weak_pdf_to_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config, runtime = make_workspace(Path(temp))
            source = runtime.pdf_dir / "weak.pdf"
            source.write_bytes(b"%PDF-1.4\nsynthetic")
            record = registry_row(runtime, source)
            manifest = {"profile": "base", "config_sha256": "c" * 64, "page_count": "2", "json_relpath": "corpus/a.json"}
            data = {"texts": [{"label": "text", "text": "tiny", "prov": [{"page_no": 1}]}], "tables": [], "pictures": []}
            result = assess_document(data, record, manifest, default_thresholds(runtime), lambda _: 2, runtime.workspace)
            self.assertEqual(result["quality_class"], "C_retry_required")
            self.assertEqual(result["ocr_recommended"], "true")

    def test_rechunk_xml_uses_manifest_paths_not_hardcoded_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, runtime = make_workspace(Path(temp))
            source = runtime.xml_dir / "paper.xml"
            source.write_text("<article><body><p>Evidence text.</p></body></article>", encoding="utf-8")
            record = registry_row(runtime, source, "xml")
            atomic_write_csv(runtime.registry, [record], REGISTRY_FIELDS)
            json_path = runtime.corpus_root / "odd-layout" / "paper.json"
            markdown_path = runtime.corpus_root / "odd-layout" / "paper.md"
            old_chunks = runtime.corpus_root / "odd-layout" / "old.jsonl"
            source_map = runtime.corpus_root / "odd-layout" / "map.jsonl"
            json_path.parent.mkdir(parents=True)
            json_path.write_text("{}", encoding="utf-8")
            markdown_path.write_text("Evidence text.", encoding="utf-8")
            old_chunks.write_text("{}\n", encoding="utf-8")
            source_map.write_text(json.dumps({"xpath": "/article[1]/body[1]/p[1]", "label": "p", "section_path": "", "text": "Evidence text.", "is_reference": False}) + "\n", encoding="utf-8")
            manifest = {
                "run_id": "synthetic", "study_id": record["study_id"], "source_sha256": record["source_sha256"],
                "source_format": "xml", "source_relpath": record["source_relpath"], "profile": "base",
                "config_sha256": "c" * 64, "status": "success",
                "json_relpath": json_path.relative_to(runtime.workspace).as_posix(), "json_sha256": sha256_file(json_path),
                "md_relpath": markdown_path.relative_to(runtime.workspace).as_posix(), "md_sha256": sha256_file(markdown_path),
                "chunks_relpath": old_chunks.relative_to(runtime.workspace).as_posix(), "chunks_sha256": sha256_file(old_chunks),
                "source_map_relpath": source_map.relative_to(runtime.workspace).as_posix(), "source_map_sha256": sha256_file(source_map),
            }
            atomic_write_csv(runtime.corpus_root / "manifests" / "conversion_manifest.csv", [manifest], MANIFEST_FIELDS)
            code, summary = run_rechunk(runtime, profile="base", study_id=None, target_chars=200, max_chars=300)
            self.assertEqual(code, 0)
            self.assertEqual(summary["success"], 1)

    def test_verify_and_status_accept_a_valid_synthetic_xml_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _, runtime = make_workspace(Path(temp))
            source = runtime.xml_dir / "paper.xml"
            source.write_text("<article><body><p>Evidence text.</p></body></article>", encoding="utf-8")
            record = registry_row(runtime, source, "xml")
            atomic_write_csv(runtime.registry, [record], REGISTRY_FIELDS)
            derived = runtime.corpus_root / "derived"
            derived.mkdir(parents=True)
            json_path, md_path, chunks_path = derived / "paper.json", derived / "paper.md", derived / "paper.jsonl"
            json_path.write_text("{}", encoding="utf-8")
            md_path.write_text("Evidence", encoding="utf-8")
            chunk = {
                "schema_version": CHUNK_SCHEMA_VERSION, "study_id": record["study_id"],
                "source_sha256": record["source_sha256"], "locator_type": "xpath",
            }
            chunks_path.write_text(json.dumps(chunk) + "\n", encoding="utf-8")
            manifest = {
                "run_id": "synthetic", "study_id": record["study_id"], "source_sha256": record["source_sha256"],
                "source_format": "xml", "source_relpath": record["source_relpath"], "profile": "base",
                "config_sha256": "c" * 64, "status": "success",
                "json_relpath": json_path.relative_to(runtime.workspace).as_posix(), "json_sha256": sha256_file(json_path),
                "md_relpath": md_path.relative_to(runtime.workspace).as_posix(), "md_sha256": sha256_file(md_path),
                "chunks_relpath": chunks_path.relative_to(runtime.workspace).as_posix(), "chunks_sha256": sha256_file(chunks_path),
            }
            atomic_write_csv(runtime.corpus_root / "manifests" / "conversion_manifest.csv", [manifest], MANIFEST_FIELDS)
            code, summary = run_verify(runtime, "base")
            self.assertEqual(code, 0)
            self.assertTrue(summary["ready"])
            status = corpus_status(runtime)
            self.assertEqual(status["profiles"]["base"]["successful_studies"], 1)

    def test_error_redaction_hides_paths_email_and_tokens(self) -> None:
        message = "C:\\Users\\private-person\\paper.pdf person@example.edu token=secret-value"
        redacted = redact_error(message)
        self.assertNotIn("private-person", redacted)
        self.assertNotIn("person@example.edu", redacted)
        self.assertNotIn("secret-value", redacted)


if __name__ == "__main__":
    unittest.main()
