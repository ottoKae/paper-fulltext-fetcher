---
name: paper-fulltext-fetcher
description: Safely find, download, validate, and audit scholarly PDF or full-text XML from bibliography lists using open sources, licensed publisher API/TDM access, authenticated visible browser sessions, and manual imports. Use for literature-download workflows, resumable queues, PDF/XML identity checks, or download reports. Do not use to bypass paywalls, bot controls, access suspensions, or publisher restrictions.
---

# Paper Fulltext Fetcher

Build a lawful, privacy-preserving and auditable path from a bibliography to downloaded, verified PDF or full-text XML. Treat downloading as a permissioned workflow, not as unrestricted scraping.

## Operating modes

Choose the smallest mode that satisfies the request:

1. **Plan or diagnose:** inspect inputs, existing files, configuration and logs without changing external state.
2. **Offline corpus work:** inventory, validate, prepare queues, import user-supplied files, audit or report.
3. **Open discovery:** query OA metadata services after the user authorizes network access.
4. **Official API/TDM:** use only credentials and entitlements the user has explicitly configured.
5. **Visible browser assistance:** attach only to a user-opened, user-authenticated session; never automate credentials or challenges.

Do not infer authorization for network retrieval from a request to review, plan, audit or configure.

## Required workflow

1. Establish the bibliography, corpus directories and current audit baseline.
2. Skip files already verified by the latest audit.
3. Repair metadata without changing the source bibliography.
4. Prefer OA and repository routes, then official API/TDM routes.
5. Use a browser-assisted route only after a one-item read-only probe and user-completed authentication.
6. Run one-item smoke tests before small batches.
7. Default to one concurrent request per publisher and durable event logs.
8. Import into the corpus only after container and identity validation.
9. Re-audit after every acquisition or manual-import batch.

Read [references/workflow.md](references/workflow.md) when planning or operating the end-to-end pipeline. Read only the other reference relevant to the current mode:

- Network, campus IP, CARSI and TDM: [references/network-and-auth.md](references/network-and-auth.md)
- Publisher route selection: [references/providers.md](references/providers.md)
- Statuses, evidence and audit fields: [references/status-and-logs.md](references/status-and-logs.md)
- Manual and image-only PDF import: [references/manual-import.md](references/manual-import.md)
- Privacy and GitHub publication: [references/privacy-and-publication.md](references/privacy-and-publication.md)

## Privacy invariants

- Never print, persist, copy or upload secret values, cookies, authorization headers, signed URLs, proxy subscriptions, browser profiles or institutional credentials.
- Report only whether a credential environment variable is configured.
- Use relative or user-supplied paths in reusable artifacts; do not embed usernames or machine-specific roots.
- Persist only relative paths or basenames in shareable audit and event logs.
- Do not place copyrighted PDF/XML files, acquisition logs, browser artifacts or real bibliography data in a public Skill repository.
- Use synthetic fixtures for tests and examples.
- Run the privacy scanner before recommending Git publication.

## Safety stops

Stop the affected provider on `403`, `418`, `429`, CAPTCHA, challenge pages, access suspension, explicit non-subscription, or repeated failures. Do not respond by increasing concurrency, rotating identities or bypassing controls. Preserve the failure reason and route the record to OA, library delivery, author sharing or a manual queue.

## Helper script

Use `scripts/run.ps1` on Windows so every command runs in the Skill's private `.venv`. If the environment is missing or incomplete, run `scripts/bootstrap.ps1` first. Start with:

```powershell
& scripts/bootstrap.ps1
& scripts/run.ps1 self-test
& scripts/run.ps1 init --workspace my-review
& scripts/run.ps1 doctor --config my-review/acquisition.local.toml
& scripts/run.ps1 inspect-input --config my-review/acquisition.local.toml
```

On macOS or Linux, create `.venv`, install `requirements.txt`, and invoke `.venv/bin/python scripts/paper_fulltext_fetcher.py ...`.

Prefer `--dry-run` where available. Before any network command, state the hosts, record count, delay, output location and stopping conditions. Do not run a network command merely because credentials are present.
