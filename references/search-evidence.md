# Reproducible search evidence

The search skill can formulate queries and use authorized search tools available in the host, or guide manual database exports. The local helper registers completed searches; it does not secretly perform those searches or provide a comprehensive database API.

For each executed query record: database, platform, exact query, searched fields, filters, timezone-aware execution time, reported hits, exported file and whether the export was truncated. Preserve original query syntax rather than translating it after execution. Include API version/cursor/range or manual export batches in additional fields when applicable. Report unavailable sources and incomplete exports as coverage gaps.

Create a private JSON manifest like this (the values are synthetic):

```json
{
  "searches": [{
    "database": "Example index",
    "platform": "Example authorized interface",
    "query": "TITLE(plantation AND satellite)",
    "fields": ["title"],
    "filters": {"language": "all"},
    "searched_at": "2026-01-01T10:00:00+00:00",
    "reported_hits": 12,
    "export_file": "export.csv",
    "truncated": false
  }]
}
```

Exports use the existing CSV/TSV/XLSX reader and supported header aliases; optional `columns`/`sheet` apply per export. Do not include credentials, authenticated URLs, signed links or private browser data in the manifest. The raw exports are private research material, not public fixtures.

```powershell
& .\scripts\run.ps1 workflow search-register --manifest ..\my-review\searches.json --output-dir ..\my-review\search-run-001
```

The output directory must not exist. The helper copies/hashes raw exports, records the manifest hash and creates `bibliography.csv`, `search_runs.json` and `provenance.json`. Equal normalized DOIs map to one stable record while all source rows and conflicting metadata remain in provenance. No-DOI records remain separate; title similarity alone does not remove them. Export counts must agree with reported hits or explicitly declare truncation. A truncated search is not complete merely because registration succeeds.

Create a new output directory for updates and citation chasing. Download the registered bibliography with the acquisition skill only when requested. Scientific screening, reviewer independence, adjudication and evidence interpretation are separate review procedures; neither deduplication nor missing full text constitutes an eligibility decision.
