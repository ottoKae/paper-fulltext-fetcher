---
name: paper-workflow
description: Coordinate a literature workflow across search, lawful full-text acquisition and local document structuring. Use for cross-stage requests or deciding where to start, not for a single download or conversion.
---

# Paper Workflow

Use this as a thin coordinator, not a second implementation of the three stages.

1. Determine whether the user has a research question, bibliography, or existing full text. Ask only for missing inputs that change execution.
2. Select `paper-search`, `paper-fulltext-fetcher`, or `paper-corpus` as needed. Each works independently; do not run every stage by default.
3. Preserve the user's institution, browser, directories and network choices. A request for planning does not authorize downloading, changing proxies or installing models.
4. Use one private workspace and stable record IDs. Keep search evidence, acquisition events and parsing outputs distinct.
5. Report retrieved full text, missing text and conversion failures separately. Retrieval is not review inclusion; do not make screening decisions or infer review variables.
6. Keep the user's stage order. If the request is to acquire every candidate without screening, retain the entire queue and leave eligibility decisions unfilled. New files do not change the frozen candidate denominator. Publish each progress view from one verified audit snapshot.
7. For repeated acquisition-to-library tasks use `workflow batch` rather than creating project-specific controllers. Read [reusable pipeline](../../../references/reusable-pipeline.md) for preview/execute, frozen inputs, resume, route stops, local Docling and archive contracts. It consumes reviewed sources, not arbitrary metadata links. Report partial completion honestly.

For browser-assisted stages read [tool capability boundaries](../../../references/browser-capabilities.md). Check current tool availability rather than assuming a previous browser connection still works. A skill cannot extend the host's permissions or bypass a safety stop.

Read [runtime setup](../../../references/skill-runtime.md) to locate the shared backend. Read the selected peer skill only when it is actually needed. If it is not installed, explain the missing capability rather than pretending to invoke it.
