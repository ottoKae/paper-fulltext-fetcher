from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


STOP_STATUSES = {"challenge_or_block", "rate_limited", "not_subscribed", "api_not_entitled", "network_error", "repeated_failures"}
CHANNELS = {"http", "browser", "tdm"}


def domain(value):
    value = str(value).strip().lower().rstrip(".")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value) or ".." in value:
        raise ValueError("Expected a domain without credentials, port or URL")
    return value


def local_endpoint(value):
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"} or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Browser endpoint must be an explicitly configured loopback HTTP origin")
    return value.rstrip("/")


def campus_diagnostics(config, base, clash_text=None):
    institution = config.get("institution", {})
    browser = config.get("browser", {})
    domains = [domain(value) for value in institution.get("domains", [])]
    authentication = [domain(value) for value in institution.get("authentication_domains", [])]
    publishers = [domain(value) for value in config.get("network", {}).get("publisher_domains", [])]
    configured_downloads = browser.get("downloads_dir", "")
    downloads = Path(configured_downloads).expanduser() if configured_downloads else None
    if downloads and not downloads.is_absolute():
        downloads = base / downloads
    endpoint = browser.get("cdp_endpoint", "")
    result = {
        "institution_configured": bool(domains),
        "institution_domains": domains,
        "authentication_domains": authentication,
        "network_mode": institution.get("network_mode", "unspecified"),
        "browser": {"downloads_configured": bool(downloads), "downloads_directory_exists": bool(downloads and downloads.is_dir()), "loopback_endpoint_configured": bool(endpoint), "endpoint_valid": bool(local_endpoint(endpoint)) if endpoint else False, "session_tested": False},
        "institution_recognition_verified": False,
        "pdf_transfer_verified": False,
        "network_tested": False,
        "next_steps": ["Confirm the user's institution and campus/VPN/CARSI access mode", "Inspect institution recognition in the user's existing visible browser", "Verify one saved PDF before a small batch"],
    }
    if clash_text is not None:
        mode = re.search(r"(?m)^mode:\s*['\"]?([a-zA-Z]+)", clash_text)
        rules = []
        for line in clash_text.splitlines():
            match = re.match(r"\s*-\s*['\"]?(DOMAIN-SUFFIX|DOMAIN),([^,\s]+),([^,\s'\"#]+)", line, re.I)
            if match:
                rules.append(tuple(part.lower() for part in match.groups()))
        def direct_rule_present(host):
            return any(policy == "direct" and (host == suffix or kind == "domain-suffix" and host.endswith("." + suffix)) for kind, suffix, policy in rules)
        result["clash"] = {"mode": mode.group(1).lower() if mode else "unknown", "institution_direct_rule_present": any(direct_rule_present(host) for host in domains + authentication), "configured_domain_checks": {host: direct_rule_present(host) for host in domains + authentication + publishers}, "actual_route_verified": False, "inspection_only": True}
        result["next_steps"].append("Check actual matched policy and campus egress; text matches do not establish routing or subscription")
    return result


def write_exclusive(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class RouteLedger:
    def __init__(self, root):
        self.root = Path(root)

    def directory(self, host, channel):
        if channel not in CHANNELS:
            raise ValueError("Unknown acquisition channel")
        identifier = hashlib.sha256((domain(host) + "|" + channel).encode()).hexdigest()
        return self.root / identifier

    def events(self, host, channel):
        return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.directory(host, channel).glob("*.json"))]

    def state(self, host, channel):
        events = self.events(host, channel)
        status = events[-1]["status"] if events else "ready"
        allowed = status in {"ready", "recovery_authorized", "valid_pdf", "valid_xml", "already_present", "identity_mismatch", "invalid_container", "existing_invalid", "manual_required", "watch_timeout"}
        return {"host": domain(host), "channel": channel, "last_status": status, "attempt_allowed": allowed and not (self.directory(host, channel) / "active.lock").exists(), "recovery_probe_only": status == "recovery_authorized", "last_event_id": events[-1]["event_id"] if events else None}

    def record(self, host, channel, status, **fields):
        event = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "event_id": uuid.uuid4().hex, "host": domain(host), "channel": channel, "status": status, **fields}
        filename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + event["event_id"] + ".json"
        write_exclusive(self.directory(host, channel) / filename, event)
        if status not in {"attempt_started", "recovery_authorized"}:
            (self.directory(host, channel) / "active.lock").unlink(missing_ok=True)
        return event

    def begin(self, host, channel):
        state = self.state(host, channel)
        if not state["attempt_allowed"]:
            raise ValueError("Route paused; inspect evidence and authorize one recovery probe before retrying")
        directory = self.directory(host, channel)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "active.lock").open("x", encoding="utf-8") as stream:
            stream.write("In-flight route; recovery requires confirming this attempt has stopped.\n")
        self.record(host, channel, "attempt_started", recovery_probe=state["recovery_probe_only"])
        return state

    def recover(self, host, channel, evidence, confirmed):
        state = self.state(host, channel)
        if state["attempt_allowed"] or not confirmed or evidence is None or not evidence.is_file():
            raise ValueError("A paused route, explicit user confirmation and an evidence file are required")
        evidence_hash = hashlib.sha256(evidence.read_bytes()).hexdigest()
        if any(event.get("evidence_sha256") == evidence_hash for event in self.events(host, channel)):
            raise ValueError("Recovery evidence already used; no automatic repeated recovery")
        event = self.record(host, channel, "recovery_authorized", stopped_event_id=state["last_event_id"], evidence_sha256=evidence_hash, evidence_basename=evidence.name, user_confirmed=True)
        (self.directory(host, channel) / "active.lock").unlink(missing_ok=True)
        return event
