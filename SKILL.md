---
name: paper-fulltext-fetcher
description: Compatibility entry for lawful scholarly full-text acquisition, validation and optional local corpus preparation. For new installations use the four modular skills bundled in .agents/skills.
---

# Paper Fulltext Fetcher — compatibility entry

This root entry remains for older whole-repository installations. Do not install it alongside the modular skill with the same name.

Read the canonical [full-text acquisition skill](.agents/skills/paper-fulltext-fetcher/SKILL.md) and follow its workflow. All relative links in that document resolve from its own directory.

For Ponytail or another host, follow the current [browser capability boundaries](references/browser-capabilities.md). This compatibility entry does not supply a browser connection or expand tool permissions.

- For topic-based search or registering database exports, read [paper-search](.agents/skills/paper-search/SKILL.md).
- For verified local PDF/XML parsing, read [paper-corpus](.agents/skills/paper-corpus/SKILL.md).
- For a cross-stage request, read [paper-workflow](.agents/skills/paper-workflow/SKILL.md).

Existing `scripts/run.ps1` acquisition and `corpus` commands remain supported. New installations should use `scripts/install_skills.py` to install four entries with a single shared runtime. Never copy only this file, personal configurations, browser profiles or research data into a release.
