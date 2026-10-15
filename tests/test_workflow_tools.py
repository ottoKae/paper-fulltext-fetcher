from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import paper_fulltext_fetcher as helper
import workflow_tools as workflow
from campus_support import RouteLedger, campus_diagnostics, local_endpoint
from corpus_tool import synthetic_text_pdf
from install_skills import NAMES, install


TITLE = "Synthetic Satellite Plantation Evidence Validation Paper"
DOI = "10.5555/example.workflow"


def make_workspace(root):
    args = helper.build_parser().parse_args(["init", "--workspace", str(root), "--input", "bibliography.csv"])
    with contextlib.redirect_stdout(io.StringIO()):
        helper.command_init(args)
    record = {"record_id": "demo", "title": TITLE, "doi": DOI, "expected_filename": "demo.pdf"}
    helper.write_csv(root / "bibliography.csv", [record])
    return root / "acquisition.local.toml"


def pdf_bytes(text=None):
    return synthetic_text_pdf((text or TITLE + " " + DOI) + " synthetic evidence" * 900)


def receive_args(config, *extra):
    return workflow.build_parser().parse_args(["browser-receive", "--config", str(config), "--record-id", "demo", "--wait-seconds", "0.3", "--poll-seconds", "0.1", *extra])


class CampusTests(unittest.TestCase):
    def test_no_institution_is_unknown_not_a_default_school(self):
        result = campus_diagnostics({}, Path("."))
        self.assertFalse(result["institution_configured"])
        self.assertFalse(result["network_tested"])
        self.assertFalse(result["pdf_transfer_verified"])

    def test_custom_school_and_quoted_rule_without_secrets(self):
        config = {"institution": {"domains": ["campus.example.edu"], "network_mode": "campus"}}
        secret = "private" + "-node-password"
        result = campus_diagnostics(config, Path("."), 'mode: "rule"\nrules:\n - "DOMAIN-SUFFIX,example.edu,DIRECT"\npassword: ' + secret)
        self.assertTrue(result["clash"]["institution_direct_rule_present"])
        self.assertFalse(result["clash"]["actual_route_verified"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result["clash"]["mode"], "rule")

    def test_other_school_rule_does_not_prove_this_school(self):
        result = campus_diagnostics({"institution": {"domains": ["second.example.edu"]}}, Path("."), "mode: global\nrules:\n - DOMAIN,first.example.edu,DIRECT")
        self.assertFalse(result["clash"]["institution_direct_rule_present"])

    def test_nonstandard_download_directory_and_privacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "saved files").mkdir()
            result = campus_diagnostics({"browser": {"downloads_dir": "saved files"}}, root)
            self.assertTrue(result["browser"]["downloads_directory_exists"])
            self.assertNotIn(str(root), json.dumps(result))

    def test_only_explicit_loopback_endpoint(self):
        self.assertEqual(local_endpoint("http://127.0.0.1:9333"), "http://127.0.0.1:9333")
        for value in ("http://192.168.1.2:9222", "http://localhost:9222", "https://127.0.0.1:9222", "http://127.0.0.1:9222/" + "?" + "key=value", "http://user@127.0.0.1:9222"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_endpoint(value)


class RouteTests(unittest.TestCase):
    def test_persistent_channel_specific_stop_and_single_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ledger = RouteLedger(root / "access")
            ledger.record("publisher.example", "http", "network_error")
            ledger = RouteLedger(root / "access")
            self.assertFalse(ledger.state("publisher.example", "http")["attempt_allowed"])
            self.assertTrue(ledger.state("publisher.example", "browser")["attempt_allowed"])
            evidence = root / "recovered.txt"
            evidence.write_text("Synthetic user-confirmed restoration", encoding="utf-8")
            with self.assertRaises(ValueError):
                ledger.recover("publisher.example", "http", evidence, False)
            ledger.recover("publisher.example", "http", evidence, True)
            self.assertTrue(ledger.begin("publisher.example", "http")["recovery_probe_only"])
            with self.assertRaises(ValueError):
                ledger.begin("publisher.example", "http")
            ledger.record("publisher.example", "http", "challenge_or_block")
            with self.assertRaises(ValueError):
                ledger.recover("publisher.example", "http", evidence, True)

    def test_interrupted_attempt_is_not_silently_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = RouteLedger(Path(temporary))
            ledger.begin("publisher.example", "browser")
            self.assertFalse(RouteLedger(Path(temporary)).state("publisher.example", "browser")["attempt_allowed"])
            ledger.record("publisher.example", "browser", "valid_pdf")
            self.assertTrue(ledger.state("publisher.example", "browser")["attempt_allowed"])


class ReceiveTests(unittest.TestCase):
    def test_read_only_probe_inspects_without_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = make_workspace(Path(temporary))
            args = workflow.build_parser().parse_args(["browser-probe", "--config", str(config), "--allow-browser", "--allow-host", "publisher.example", "--target", "observed-id"])
            with patch.object(workflow, "browser_call", return_value={"status": "observed_not_downloaded"}) as browser, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.probe(args), 0)
                self.assertEqual(browser.call_args.args[1], "inspect")

    def test_preview_does_not_touch_browser_or_create_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            with patch.object(workflow, "browser_call") as browser, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.receive(receive_args(config)), 0)
                browser.assert_not_called()
            self.assertFalse((root / "outputs/acquisition/browser-runs").exists())

    def test_nondefault_inbox_import_and_idempotent_second_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            inbox = root / "学校 下载"
            inbox.mkdir()
            source = inbox / "unrelated_filename.PDF"
            source.write_bytes(pdf_bytes())
            original_hash = helper.sha256_file(source)
            arguments = receive_args(config, "--inbox", str(inbox), "--execute")
            with patch.object(workflow, "browser_call") as browser, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.receive(arguments), 0)
                self.assertEqual(workflow.receive(arguments), 0)
                browser.assert_not_called()
            self.assertEqual(helper.sha256_file(source), original_hash)
            self.assertEqual(helper.sha256_file(root / "papers_pdf/demo.pdf"), original_hash)
            receipts = list((root / "outputs/acquisition/browser-runs").glob("*/finished.json"))
            self.assertEqual({json.loads(path.read_text())["status"] for path in receipts}, {"valid_pdf", "already_present"})
            self.assertFalse((root / "outputs/acquisition/browser-receive.lock").exists())
            summary = json.loads((root / "outputs/acquisition/audit/summary.json").read_text())
            self.assertEqual(summary["fulltext_coverage"], 1)

    def test_saved_pdf_is_checked_before_clicking_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            (root / "manual_pdf_inbox/saved.pdf").write_bytes(pdf_bytes())
            arguments = receive_args(config, "--execute", "--allow-browser", "--target", "observed-id", "--label", "Download PDF", "--allow-host", "publisher.example")
            with patch.object(workflow, "browser_call") as browser, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.receive(arguments), 0)
                browser.assert_not_called()

    def test_word_bag_match_does_not_receive_an_old_paper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            inbox = root / "manual_pdf_inbox"
            old = inbox / "a-old.pdf"
            old.write_bytes(pdf_bytes(" ".join(reversed(TITLE.split())) + " 10.5555/old.paper"))
            correct = inbox / "z-correct.pdf"
            correct.write_bytes(pdf_bytes())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.receive(receive_args(config, "--execute")), 0)
            self.assertEqual(helper.sha256_file(root / "papers_pdf/demo.pdf"), helper.sha256_file(correct))
            self.assertNotEqual(helper.sha256_file(root / "papers_pdf/demo.pdf"), helper.sha256_file(old))

    def test_conflicting_doi_is_not_accepted_by_complete_title_alone(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            source = root / "manual_pdf_inbox/wrong.pdf"
            source.write_bytes(pdf_bytes(TITLE + " 10.5555/another.paper"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.receive(receive_args(config, "--execute")), 2)
            self.assertFalse((root / "papers_pdf/demo.pdf").exists())

    def test_html_partial_and_wrong_identity_are_not_counted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            inbox = root / "manual_pdf_inbox"
            (inbox / "html.pdf").write_bytes(b"<html>blocked</html>" * 1000)
            (inbox / "partial.pdf.crdownload").write_bytes(pdf_bytes())
            (inbox / "wrong.pdf").write_bytes(pdf_bytes("A Completely Different Biology Investigation References " + DOI))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.receive(receive_args(config, "--execute")), 2)
            self.assertFalse((root / "papers_pdf/demo.pdf").exists())
            receipt = next((root / "outputs/acquisition/browser-runs").glob("*/finished.json"))
            self.assertEqual(json.loads(receipt.read_text())["status"], "watch_timeout")

    def test_challenge_is_persisted_without_click_or_wait(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            args = receive_args(config, "--execute", "--allow-browser", "--target", "observed-id", "--label", "Download PDF", "--allow-host", "publisher.example")
            result = {"status": "challenge_or_block", "target": {"host": "publisher.example"}}
            with patch.object(workflow, "browser_call", return_value=result) as browser, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.receive(args), 3)
                self.assertEqual(browser.call_count, 1)
            self.assertFalse(RouteLedger(root / "outputs/acquisition/access").state("publisher.example", "browser")["attempt_allowed"])

    def test_wrong_article_never_clicks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            args = receive_args(config, "--execute", "--allow-browser", "--target", "observed-id", "--label", "Download PDF", "--allow-host", "publisher.example")
            result = {"status": "observed_not_downloaded", "target": {"host": "publisher.example"}, "before": {"title": "Unrelated article", "text": ""}}
            with patch.object(workflow, "browser_call", return_value=result) as browser, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                workflow.receive(args)
            self.assertEqual(browser.call_count, 1)
            self.assertFalse((root / "outputs/acquisition/browser-receive.lock").exists())

    def test_popup_challenge_and_unsaved_viewer_never_count_as_downloads(self):
        for status, expected_code in (("challenge_or_block", 3), ("clicked_not_downloaded", 2)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                config = make_workspace(root)
                args = receive_args(config, "--execute", "--allow-browser", "--target", "observed-id", "--label", "Download PDF", "--allow-host", "publisher.example")
                observed = {"status": "observed_not_downloaded", "target": {"host": "publisher.example"}, "before": {"title": TITLE, "text": DOI}}
                clicked = {"status": status, "click": {"clicked": True}}
                with patch.object(workflow, "browser_call", side_effect=[observed, clicked]), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(workflow.receive(args), expected_code)
                self.assertFalse((root / "papers_pdf/demo.pdf").exists())
                state = RouteLedger(root / "outputs/acquisition/access").state("publisher.example", "browser")
                self.assertEqual(state["last_status"], "challenge_or_block" if expected_code == 3 else "watch_timeout")

    def test_empty_remaining_queue_never_imports_unrequested_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            (root / "manual_pdf_inbox/saved.pdf").write_bytes(pdf_bytes())
            helper.write_csv(root / "empty.csv", [])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.invoke("import", ["--config", config, "--remaining", root / "empty.csv"]), 0)
            self.assertFalse((root / "papers_pdf/demo.pdf").exists())

    def test_invalid_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            (root / "manual_pdf_inbox/saved.pdf").write_bytes(pdf_bytes())
            (root / "papers_pdf/demo.pdf").write_bytes(b"invalid existing file")
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                workflow.receive(receive_args(config, "--execute"))
            self.assertEqual((root / "papers_pdf/demo.pdf").read_bytes(), b"invalid existing file")

    def test_workspace_lock_prevents_parallel_receivers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            lock = root / "outputs/acquisition/browser-receive.lock"
            lock.write_text("another receiver", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                workflow.receive(receive_args(config, "--execute"))
            self.assertEqual(lock.read_text(), "another receiver")


class HttpTests(unittest.TestCase):
    def test_http_200_challenge_is_not_an_identity_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            manifest = root / "candidates.csv"
            helper.write_csv(manifest, [{"record_id": "demo", "title": TITLE, "doi": DOI, "candidate_url": "https://repo.example.edu/paper.pdf", "expected_filename": "demo.pdf", "approved": "true", "approval_scope": "open_access"}])
            def transfer(url, target, timeout, maximum, hosts, route_ledger=None):
                target.write_text("<html><title>Security verification</title></html>", encoding="utf-8")
                return 200, "text/html"
            args = helper.build_parser().parse_args(["fetch-verified", "--config", str(config), "--manifest", str(manifest), "--allow-host", "repo.example.edu", "--execute"])
            with patch.object(helper, "download_one", side_effect=transfer), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(helper.command_fetch_verified(args), 3)
            self.assertFalse((root / "papers_pdf/demo.pdf").exists())
            self.assertEqual(RouteLedger(root / "outputs/acquisition/access").state("repo.example.edu", "http")["last_status"], "challenge_or_block")

    def test_http_stop_survives_new_invocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = make_workspace(root)
            manifest = root / "candidates.csv"
            helper.write_csv(manifest, [{"record_id": "demo", "title": TITLE, "doi": DOI, "candidate_url": "https://repo.example.edu/paper.pdf", "expected_filename": "demo.pdf", "approved": "true", "approval_scope": "open_access"}])
            command = ["fetch-verified", "--config", str(config), "--manifest", str(manifest), "--allow-host", "repo.example.edu", "--execute"]
            with patch.object(helper, "download_one", return_value=(403, "blocked")) as fetch, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(helper.command_fetch_verified(helper.build_parser().parse_args(command)), 3)
                self.assertEqual(helper.command_fetch_verified(helper.build_parser().parse_args(command)), 3)
                self.assertEqual(fetch.call_count, 1)


class SearchTests(unittest.TestCase):
    def test_preserves_all_sources_and_no_doi_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper.write_csv(root / "export.csv", [{"title": TITLE, "doi": DOI}, {"title": TITLE, "doi": DOI.upper()}, {"title": "No identifier article", "doi": ""}, {"title": "No identifier article", "doi": ""}])
            entry = {"database": "Example", "platform": "Example", "query": "TITLE(plantation)", "fields": ["title"], "filters": {}, "searched_at": "2026-01-01T10:00:00+00:00", "export_file": "export.csv", "reported_hits": 4, "truncated": False}
            manifest = root / "search.json"
            manifest.write_text(json.dumps({"searches": [entry]}), encoding="utf-8")
            output = root / "registered"
            args = workflow.build_parser().parse_args(["search-register", "--manifest", str(manifest), "--output-dir", str(output)])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.search_register(args), 0)
            self.assertEqual(len(helper.load_records(output / "bibliography.csv")), 3)
            self.assertEqual(len(json.loads((output / "provenance.json").read_text())), 4)
            with self.assertRaises(FileExistsError):
                workflow.search_register(args)

    def test_zero_hits_and_truncation_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "export.tsv").write_text("title\tdoi\n", encoding="utf-8")
            entry = {"database": "Example", "platform": "Example", "query": "TITLE(impossible)", "fields": ["title"], "filters": {}, "searched_at": "2026-01-01T10:00:00+00:00", "export_file": "export.tsv", "reported_hits": 0, "truncated": False}
            manifest = root / "search.json"
            manifest.write_text(json.dumps({"searches": [entry]}), encoding="utf-8")
            args = workflow.build_parser().parse_args(["search-register", "--manifest", str(manifest), "--output-dir", str(root / "zero")])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(workflow.search_register(args), 0)
            entry["reported_hits"] = 100
            manifest.write_text(json.dumps({"searches": [entry]}), encoding="utf-8")
            args.output_dir = root / "incomplete"
            with self.assertRaises(ValueError):
                workflow.search_register(args)
            self.assertFalse(args.output_dir.exists())


class InstallTests(unittest.TestCase):
    def test_bundle_is_portable_and_preserves_existing_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skills"
            preview = install(ROOT, destination)
            self.assertEqual(preview["mode"], "dry_run")
            self.assertFalse(destination.exists())
            result = install(ROOT, destination, True)
            runtime = destination / result["runtime"]
            self.assertFalse((runtime / ".venv").exists())
            self.assertFalse((runtime / "SKILL.md").exists())
            self.assertTrue((runtime / "scripts/workflow_tools.py").is_file())
            execution = subprocess.run([sys.executable, "-B", str(runtime / "scripts/paper_fulltext_fetcher.py"), "self-test"], cwd=destination, capture_output=True, text=True, timeout=30)
            self.assertEqual(execution.returncode, 0, execution.stderr)
            for name in NAMES:
                skill = destination / name / "SKILL.md"
                content = skill.read_text(encoding="utf-8")
                self.assertIn("name: " + name, content)
                self.assertNotIn(str(ROOT), content)
                for target in re.findall(r"\]\(([^)]+)\)", content):
                    self.assertTrue((skill.parent / target).is_file(), target)
            before = helper.sha256_file(destination / NAMES[0] / "SKILL.md")
            with self.assertRaises(ValueError):
                install(ROOT, destination, True)
            self.assertEqual(helper.sha256_file(destination / NAMES[0] / "SKILL.md"), before)


if __name__ == "__main__":
    unittest.main()
