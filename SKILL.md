---
name: paper-fulltext-fetcher
description: Safely find, download, validate, and audit scholarly PDF or full-text XML, then optionally prepare verified local PDF/JATS XML as searchable Docling JSON, Markdown, and provenance-preserving chunks. Use for literature acquisition, resumable queues, identity checks, download reports, or local corpus structuring. Do not use to bypass access controls or to infer review variables from papers.
---

# Paper Fulltext Fetcher

Build a lawful, privacy-preserving and auditable path from a bibliography to verified full text and, when requested, a local structured corpus. Treat downloading as a permissioned workflow and corpus preparation as document parsing, not semantic review extraction.

## Operating modes

Choose the smallest mode that satisfies the request:

1. **Plan or diagnose:** inspect inputs, existing files, configuration and logs without changing external state.
2. **Offline acquisition work:** inventory, validate, prepare queues, import user-supplied files, audit or report.
3. **Local corpus preparation:** register verified sources, run Docling locally, create locatable chunks, assess quality, retry selected OCR cases and verify hashes.
4. **Open discovery:** query OA metadata services after the user authorizes network access.
5. **Official API/TDM:** use only credentials and entitlements the user has explicitly configured.
6. **Visible browser assistance:** attach only to a user-opened, user-authenticated session; never automate credentials or challenges.

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

For optional corpus preparation, require a current acquisition audit, keep source PDF/XML immutable, register sources with stable IDs and SHA-256, run a small benchmark before a batch, use selective OCR after quality assessment, and verify every derived output before downstream retrieval. This stage must not classify study scope, equipment, methods, locations or other review variables.

Read [references/workflow.md](references/workflow.md) when planning or operating the end-to-end pipeline. Read only the other reference relevant to the current mode:

- Network, campus IP, CARSI and TDM: [references/network-and-auth.md](references/network-and-auth.md)
- Publisher route selection: [references/providers.md](references/providers.md)
- Statuses, evidence and audit fields: [references/status-and-logs.md](references/status-and-logs.md)
- Manual and image-only PDF import: [references/manual-import.md](references/manual-import.md)
- Privacy and GitHub publication: [references/privacy-and-publication.md](references/privacy-and-publication.md)
- Local Docling conversion, OCR profiles and stage boundaries: [references/corpus-preparation.md](references/corpus-preparation.md)
- Registry, manifest and evidence-chunk fields: [references/corpus-schema.md](references/corpus-schema.md)

## Privacy invariants

- Never print, persist, copy or upload secret values, cookies, authorization headers, signed URLs, proxy subscriptions, browser profiles or institutional credentials.
- Report only whether a credential environment variable is configured.
- Use relative or user-supplied paths in reusable artifacts; do not embed usernames or machine-specific roots.
- Persist only relative paths or basenames in shareable audit and event logs.
- Do not place copyrighted PDF/XML files, acquisition logs, browser artifacts or real bibliography data in a public Skill repository.
- Treat derived Docling JSON, Markdown, chunks and source maps as copyrighted corpus content; keep them in the user's ignored project workspace.
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

For local corpus preparation, install the optional environment and start with:

```powershell
& scripts/bootstrap.ps1 -Corpus
& scripts/run.ps1 corpus self-test
& scripts/run.ps1 corpus self-test --pdf
& scripts/run.ps1 corpus register --config my-review/acquisition.local.toml
& scripts/run.ps1 corpus doctor --config my-review/acquisition.local.toml
& scripts/run.ps1 corpus convert --config my-review/acquisition.local.toml --profile benchmark
```

Use the optional `corpus self-test --pdf` before a real benchmark when the user asks to confirm PDF-model readiness. It converts one temporary synthetic page, may download local model weights on first use, never reads user papers, and keeps remote services disabled.

On macOS or Linux, create `.venv`, install `requirements.txt`, and invoke `.venv/bin/python scripts/paper_fulltext_fetcher.py ...`. For corpus work, additionally install `requirements-corpus.txt` and invoke `.venv/bin/python scripts/corpus_tool.py ...`.

Prefer `--dry-run` where available. Before any network command, state the hosts, record count, delay, output location and stopping conditions. Do not run a network command merely because credentials are present.
