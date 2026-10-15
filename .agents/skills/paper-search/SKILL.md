---
name: paper-search
description: Plan topic-based scholarly searches and register database exports with exact queries, provenance and conservative DOI deduplication. Use before full-text acquisition; not for finding a PDF for an already-known DOI.
---

# Paper Search

Turn a research question into a traceable bibliography, not a promise of exhaustive coverage.

1. Clarify scope, concepts, synonyms, date/language limits and appropriate sources. Translate queries to each database's actual syntax; do not represent an unexecuted query as a completed search.
2. Use available authorized search tools or guide the user through database export. This backend does not provide a universal database search API; unavailable databases remain an explicit coverage gap.
3. Preserve verbatim queries, platform/database, searched fields, filters, timezone-aware execution date, reported hits, pagination/export limits and truncation.
4. Use `workflow search-register` to snapshot completed exports and generate a bibliography with provenance. It merges exact normalized DOIs only; no-DOI records and uncertain title matches remain separate for adjudication.
5. Record citation chasing and updates as new search runs. Never overwrite original exports or silently rewrite conflicting source metadata.
6. Hand the bibliography to acquisition only when requested. Do not exclude records for missing abstracts or inaccessible full text, or claim this helper performed independent human screening.

Read [runtime setup](../../../references/skill-runtime.md) and [search evidence](../../../references/search-evidence.md). Source files and search strings belong in the private review workspace.
