---
name: paper-corpus
description: Convert verified local PDF or supported full-text XML into searchable Docling JSON, Markdown and provenance-preserving chunks. Use for document parsing, OCR quality checks and local corpus preparation; not downloading or semantic review extraction.
---

# Paper Corpus

Prepare local documents for later retrieval; do not interpret their scientific findings or decide review eligibility.

1. Read [runtime setup](../../../references/skill-runtime.md). Require a current acquisition audit and verified immutable source files.
2. Register stable IDs, source format and SHA-256. Keep parsing outputs outside the Skill installation and public repository.
3. Read [corpus preparation](../../../references/corpus-preparation.md). Install optional Docling/OCR dependencies only when this task needs them; disclose initial model downloads and do not upload papers to remote services.
4. Run an offline self-test and a small representative benchmark before batching. Use only supported XML formats; publisher-specific XML is not automatically JATS.
5. Convert, assess and verify. Retry OCR selectively for failed or low-quality files, preserving earlier runs and source hashes.
6. Preserve page/bounding-box or XML locators in chunks. Report parsing failures separately from acquisition failures; successful parsing does not establish evidence quality.
   For mixed languages, choose a representative benchmark and supported OCR languages explicitly. Inspect failed text extraction before attributing a failure to the wrong paper. Keep machine checks and any visual approval separate, with the actual actor recorded.
7. Semantic classification, review-variable extraction, synthesis and full RAG applications are separate tasks.
8. For colocated originals, Markdown, JSON and chunks use `workflow archive`, then `workflow archive-verify`; use `workflow library-search` for local full-text lookup. Read [reusable pipeline](../../../references/reusable-pipeline.md) when archiving or resuming batches. Preserve unknown versions and prior quality warnings; related thesis chapters do not automatically replace journal full text.

Consult [corpus schema](../../../references/corpus-schema.md) for output contracts. Existing `corpus` CLI commands remain the execution backend.
