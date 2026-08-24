from __future__ import annotations

import csv
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "paper_fulltext_fetcher.py"
SPEC = importlib.util.spec_from_file_location("paper_fulltext_fetcher", SCRIPT)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class HelperTests(unittest.TestCase):
    def test_clean_doi(self) -> None:
        self.assertEqual(helper.clean_doi("https://doi.org/10.5555/Example.001?x=1"), "10.5555/example.001")

    def test_custom_column_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "custom.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Research Name", "Persistent Identifier", "Release"])
                writer.writeheader()
                writer.writerow({
                    "Research Name": "Synthetic Custom Mapping",
                    "Persistent Identifier": "10.5555/example.mapping",
                    "Release": "2025",
                })
            records = helper.load_records(path, column_overrides={
                "title": "Research Name", "doi": "Persistent Identifier", "year": "Release",
            })
            self.assertEqual(records[0]["title"], "Synthetic Custom Mapping")
            self.assertEqual(records[0]["doi"], "10.5555/example.mapping")

    def test_doi_only_input_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "doi-only.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["DOI"])
                writer.writeheader()
                writer.writerow({"DOI": "10.5555/example.doi-only"})
            records = helper.load_records(path)
            self.assertEqual(records[0]["doi"], "10.5555/example.doi-only")
            self.assertEqual(records[0]["title"], "")

    def test_init_inspect_and_config_driven_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "review"
            init_args = Namespace(
                workspace=workspace, input=Path("bibliography.csv"),
                dry_run=False, force=False,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(helper.command_init(init_args), 0)
            config = workspace / "acquisition.local.toml"
            self.assertTrue((workspace / ".gitignore").exists())
            bibliography = workspace / "bibliography.csv"
            with bibliography.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["title", "doi", "year", "publisher"])
                writer.writeheader()
                writer.writerow({
                    "title": "Synthetic Config Workflow", "doi": "10.5555/example.config",
                    "year": "2025", "publisher": "Example Publisher",
                })
            inspect_output = workspace / "inspect.json"
            inspect_args = Namespace(config=config, input=None, sheet=None, column=[], output=inspect_output)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(helper.command_inspect_input(inspect_args), 0)
            self.assertTrue(json.loads(inspect_output.read_text(encoding="utf-8"))["ready_for_audit"])

            audit_args = Namespace(
                config=config, input=None, sheet=None, column=[], pdf_dir=None, xml_dir=None,
                output_dir=None, minimum_pdf_bytes=10_000, visual_approvals=[],
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(helper.command_audit(audit_args), 0)
            summary = json.loads((workspace / "outputs" / "acquisition" / "audit" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["bibliography_records"], 1)
            self.assertEqual(summary["missing_fulltext"], 1)

    @unittest.skipIf(helper.openpyxl is None, "openpyxl is optional")
    def test_excel_bibliography_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "synthetic.xlsx"
            workbook = helper.openpyxl.Workbook()
            workbook.active.title = "Cover"
            sheet = workbook.create_sheet("Records")
            sheet.append(["Article Title", "DOI", "Publication Year", "Publisher"])
            sheet.append(["Synthetic Fulltext Fetch Test", "10.5555/example.003", 2025, "Example Publisher"])
            workbook.save(path)
            workbook.close()
            records = helper.load_records(path, sheet_name="Records")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["doi"], "10.5555/example.003")
            self.assertEqual(records[0]["year"], "2025")

    @unittest.skipIf(helper.PdfReader is None, "pypdf is optional")
    def test_blank_but_parseable_pdf_is_not_accepted_by_filename_alone(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "expected.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=300)
            with path.open("wb") as handle:
                writer.write(handle)
            record = {
                "record_id": "demo", "excel_row": "2", "title": "Synthetic Target Paper",
                "doi": "10.5555/example.004", "year": "2025", "source_title": "",
                "publisher": "Example Publisher", "authors": "", "expected_filename": path.name,
            }
            valid, detail, _ = helper.validate_pdf(path, record, 100)
            self.assertFalse(valid)
            self.assertIn("identity_mismatch", detail)

    def test_visual_approval_can_validate_image_only_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bibliography = root / "bibliography.csv"
            with bibliography.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["title", "doi", "year", "publisher"])
                writer.writeheader()
                writer.writerow({
                    "title": "Synthetic UAV Surface Reconstruction Study",
                    "doi": "10.5555/example.001",
                    "year": "2024",
                    "publisher": "Example Publisher",
                })
            records = helper.load_records(bibliography)
            pdf_dir = root / "papers_pdf"
            xml_dir = root / "papers_xml"
            pdf_dir.mkdir()
            pdf = pdf_dir / records[0]["expected_filename"]
            pdf.write_bytes(b"%PDF-1.4\n" + b"synthetic-image-data\n" * 20)
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            approval = root / "approvals.jsonl"
            approval.write_text(json.dumps({
                "status": "visual_approved_imported",
                "expected_filename": pdf.name,
                "sha256": digest,
            }) + "\n", encoding="utf-8")
            rows, anomalies, summary = helper.audit_records(
                records, pdf_dir, xml_dir, 20, helper.load_visual_approvals([approval])
            )
            self.assertEqual(rows[0]["status"], "visual_approved_pdf")
            self.assertEqual(rows[0]["fulltext_file"], pdf.name)
            self.assertNotIn(str(root), json.dumps(rows))
            self.assertEqual(summary["fulltext_coverage"], 1)
            self.assertEqual(anomalies, [])

    def test_manual_queue_outputs_csv_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remaining = root / "remaining.csv"
            with remaining.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["record_id", "excel_row", "title", "doi", "year", "publisher", "status", "expected_filename"])
                writer.writeheader()
                writer.writerow({
                    "record_id": "demo", "excel_row": "2", "title": "Synthetic Paper",
                    "doi": "10.5555/example.002", "year": "2024",
                    "publisher": "Example Publisher", "status": "missing",
                    "expected_filename": "demo.pdf",
                })
            output = root / "manual"
            code = helper.command_manual_queue(Namespace(remaining=remaining, output_dir=output))
            self.assertEqual(code, 0)
            self.assertTrue((output / "manual_queue.csv").exists())
            self.assertTrue((output / "manual_queue.html").exists())

    def test_privacy_scan_reports_kind_without_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private_path = "C:" + "\\Users\\" + "private-person\\data"
            (root / "sample.txt").write_text(private_path, encoding="utf-8")
            findings = helper.privacy_findings(root)
            self.assertEqual(findings[0]["kind"], "windows_user_path")
            self.assertNotIn("private-person", json.dumps(findings))

    def test_private_network_hosts_are_never_allowed(self) -> None:
        self.assertFalse(helper.is_allowed_host("127.0.0.1", {"127.0.0.1"}))
        self.assertFalse(helper.is_allowed_host("192.168.1.2", {"192.168.1.2"}))
        self.assertTrue(helper.is_allowed_host("repo.example.edu", {"example.edu"}))

    def test_error_redaction_removes_developer_identity(self) -> None:
        private_path = "C:" + "\\Users\\" + "private-person\\project\\input.xlsx"
        private_email = "person" + "@" + "private.example"
        message = helper.redact_error_message(f"missing {private_path} for {private_email}")
        self.assertNotIn("private-person", message)
        self.assertNotIn(private_email, message)
        self.assertIn("<local-path>", message)
        self.assertIn("<email>", message)

    def test_fetch_is_dry_run_without_explicit_execute(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "approved.csv"
            with manifest.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["record_id", "candidate_url", "expected_filename", "approved", "approval_scope"])
                writer.writeheader()
                writer.writerow({
                    "record_id": "demo", "candidate_url": "https://repo.example.edu/paper.pdf",
                    "expected_filename": "demo.pdf", "approved": "true", "approval_scope": "open_access",
                })
            args = Namespace(
                manifest=manifest, pdf_dir=root / "pdf", xml_dir=root / "xml",
                log_dir=root / "logs", allow_host=[], delay=10.0, timeout=10,
                max_bytes=1000, minimum_pdf_bytes=20,
                max_consecutive_failures=2, limit=1, execute=False,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(helper.command_fetch_verified(args), 0)
            self.assertFalse((root / "pdf").exists())
            self.assertFalse((root / "logs").exists())

    def test_doctor_never_prints_credential_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config.toml"
            variable_name = "DEMO_PRIVATE_TOKEN"
            secret_value = "not" + "-for" + "-output-123456"
            config.write_text(f'[credentials]\ndemo = "{variable_name}"\n', encoding="utf-8")
            previous = os.environ.get(variable_name)
            os.environ[variable_name] = secret_value
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    helper.command_doctor(Namespace(config=config, clash_config=None))
                self.assertNotIn(secret_value, output.getvalue())
                self.assertIn(f'"{variable_name}": true', output.getvalue())
            finally:
                if previous is None:
                    os.environ.pop(variable_name, None)
                else:
                    os.environ[variable_name] = previous


if __name__ == "__main__":
    unittest.main()
