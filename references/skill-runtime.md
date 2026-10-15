# Shared runtime and skill installation

The four repository skills live under `.agents/skills/`. Each links to this shared runtime rather than embedding another copy of the execution code. Resolve relative Markdown links from the skill file, not from the user's working directory. The runtime root is the parent of this `references/` directory; it contains `scripts/run.ps1`, `scripts/bootstrap.ps1`, `assets/` and requirements files.

## Repository or user installation

- When working inside this repository, use its `.agents/skills` entries directly.
- For another review directory, run `python scripts/install_skills.py` from this repository to preview a user-level installation. Use `--execute` only when the user requests installation; `--destination` selects an alternative skills directory.
- The installer writes four skill folders and one content-versioned `.paper-fulltext-runtime/<version>/` backend. References are rewritten to that bundled runtime, so the original checkout is not required afterward.
- It refuses existing skill folders instead of overwriting them. Review/disable an older same-name installation first, including legacy skills in other client search roots. Do not edit the user's client configuration automatically.
- It does not copy `.venv`, source research data, browser profiles or private configuration, and does not install Python dependencies or alter network settings.
- Runtime contents are explicitly allowlisted in `assets/bundle-files.json`, not recursively collected from the checkout. New private helper scripts are not implicitly installed. Use `release_tools.py` to check an actual public candidate bundle before publication.
- Root `SKILL.md` remains a legacy whole-repository entry. Choose legacy or modular installation, not both. Other clients may use different discovery directories; select their documented directory rather than assuming Codex paths apply everywhere.

## Execution

Windows: bootstrap the selected runtime using `scripts/bootstrap.ps1`. Then use its absolute `scripts/run.ps1` path with a separately supplied `--config` path. From the runtime root, examples are:

```powershell
& .\scripts\bootstrap.ps1
& .\scripts\run.ps1 self-test
& .\scripts\run.ps1 init --workspace ..\my-review --input bibliography.csv
& .\scripts\run.ps1 doctor --config ..\my-review\acquisition.local.toml
```

Linux/macOS: create the runtime's `.venv`, install `requirements.txt`, and use `.venv/bin/python scripts/paper_fulltext_fetcher.py`. For `workflow` commands use `.venv/bin/python scripts/workflow_tools.py` without the `workflow` prefix. For parsing use `scripts/corpus_tool.py` and optional `requirements-corpus.txt`.

Optional browser assistance requires Node.js exposing built-in `fetch` and `WebSocket`. It is not required for manual PDF import or local parsing. Prefer an already available supported browser connector; do not start a second browser profile solely because a connector is unavailable.

The skills do not install or enable Ponytail, Windows computer use, a browser connector or a CDP session. Read [browser capability boundaries](browser-capabilities.md) and the current host's own tool instructions before selecting one. Never invent a mandatory MCP dependency for an optional browser path. Local import and authorized OA/API acquisition remain usable without UI tools.

## Task boundaries

Input bibliography and source PDFs remain in a private project outside the install directory. `doctor` is offline unless a separate explicit browser/network operation is requested. Installation, network retrieval, settings mutation and Docling model download are separate actions with separate prerequisites. A request to diagnose does not authorize them all.
