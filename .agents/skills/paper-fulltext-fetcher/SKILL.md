---
name: paper-fulltext-fetcher
description: Acquire and verify PDF or full-text XML for an existing bibliography through OA, authorized APIs or a user-authenticated visible browser. Use for campus-access diagnosis, missing full text, imports and resumable acquisition; not topic searches or corpus parsing.
---

# Paper Fulltext Fetcher

Deliver verified files and an honest missing queue. An article page, a PDF viewer, HTTP 200 or a clicked button is not a saved full text.

1. Read [runtime setup](../../../references/skill-runtime.md). Establish input, private workspace, existing files and a current audit before networking.
2. Run offline `doctor`; configure institution domains and the real browser download directory. Read [campus onboarding](../../../references/campus-onboarding.md) before diagnosing network or browser access. Configuration matches do not prove routing or subscription.
3. Prefer existing verified files, lawful OA/repository versions, configured official API/TDM, then an authorized existing visible browser. Never copy credentials/Cookies or solve challenges. Consult [provider guidance](../../../references/providers.md) only for relevant publishers.
4. Before network work state hosts, count, delay, output and stops. Use one-item tests, one concurrent browser acquisition and 60–90 second gaps between papers unless a stricter site limit applies. Check terms and entitlements; webpage access does not grant bulk TDM rights.
5. Before browser work read [tool capability boundaries](../../../references/browser-capabilities.md). Use only currently exposed, permitted tools. A missing connector and a tool safety stop are different conditions. Never switch to CDP, shell-driven UI or another connector to bypass a safety stop. An authorized loopback bridge is optional; it does not launch a browser or log in.
6. Use `workflow browser-receive` to close the loop: stable local file, identity check, import dry-run, import and audit. It is preview-only unless `--execute` is present. A user-saved file can be imported without a browser connection.
7. Stop affected routes on 401/403/418/429, challenge, explicit denial or repeated failure. Persist the channel-specific reason. A timeout is not permanent non-subscription. Resume only after recorded fresh recovery evidence and explicit confirmation; allow one recovery test, not an unbounded retry loop.
8. Preserve original files and versioned receipts. Never overwrite an invalid existing destination with a new download without a separate reviewed decision. After interruption reconcile saved files through import/audit before retrying. Report counts from one frozen audit, not attempted links or mixed-time snapshots.
9. For an approved multi-paper queue use the preview-first `workflow batch` described in [reusable pipeline](../../../references/reusable-pipeline.md). Require explicit report role, version and lawful-source evidence. Metadata can contain links to cited works, datasets or supplements; do not approve them merely because they appear under a matching DOI record. No background retries or automatic recovery of stopped routes.

For a visible but unsaved PDF, use a permitted viewer save control only if the current tool supports it. Otherwise request user saving once, then run local `browser-receive` without a browser target. Do not repeat the same failed click or alter PDF settings by default. A wrapper timeout after a verified save is a process outcome, not proof of a failed transfer. Detailed stopping and reconciliation rules are in [tool capability boundaries](../../../references/browser-capabilities.md).

Use [workflow](../../../references/workflow.md), [manual import](../../../references/manual-import.md) and [status logs](../../../references/status-and-logs.md) when relevant. Do not modify Clash/browser settings without confirmation; record the original value and restore authorized temporary changes. Never publish real papers, signed URLs, browser artifacts or private acquisition logs.
