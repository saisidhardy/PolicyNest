# Policy retrieval architecture

## Ingestion and sources

`tools/ingest_posp_manual.mjs <pdf> <json>` uses PDF.js to extract all seven pages from the supplied operational manual. It preserves source content order and additionally reconstructs table rows into labelled cells, avoiding interleaving wrapped columns. Numbered sections/workflows and Q&A pairs are semantic boundaries. The current revised extraction contains 48 page-aware sections/rows; the earlier 26-section extraction is superseded for table fidelity.

Each chunk has document ID/name, page, section, subsection, content type, source type, document SHA-256 as version, and source classification. Original extracted source text remains in `posp_manual.json`; applicant-facing text is filtered separately. Table-row metadata and source headings are preserved. `rag.py prepare` combines this with the existing generated challenge corpus. Rebuild the vector index after changing source content.

## Retrieval

`embeddings.mjs` runs `Xenova/all-MiniLM-L6-v2` locally with quantised CPU inference, mean pooling and normalisation (384 dimensions). `rag_index.json` holds vectors and metadata for a small corpus; no separate vector database is needed. Downloaded weights live in ignored `.model-cache/`. The Python service uses a locked, persistent Node worker for query embeddings; it sends only policy questions, not raw applicant records. Startup/query timeouts fall back to keyword retrieval.

Retrieval combines BM25-style scores with vector cosine similarity, normalises the keyword contribution, applies minimum relevance thresholds and an exact-phrase bonus, and returns several sources. Diagnostics expose retrieval mode, latency and candidate count. Metadata/citations retain page/section references. Approved challenge sources take precedence when directly relevant; the operational manual is not allowed to override the protected decision policy.

## Grounding

`/api/assistant` ignores client-supplied passages and application context. If authenticated, it derives the owner from cookies, loads that owner's minimised stored progress and case/appeal statuses, and labels device-reported evidence explicitly. Unauthenticated answers are general policy only. The UI separately identifies its on-device guidance.

Without a configured LLM, the service returns a deterministic source excerpt or abstains. With a configured provider, it builds a prompt containing selected passages and authorised state; output is filtered for identity numbers, prohibited wording, compliance decisions and citations outside the retrieved source set. This is a guardrail, not a mathematical guarantee of factual entailment. The assistant cannot execute database actions or make decisions. Appeal creation requires a separate confirmed API call.

## Source classification

Supported classes: verified regulatory requirement, internal operational rule, illustrative example, organization-specific placeholder, unverified/potentially outdated claim. No manual statement is currently classified as externally verified regulation. Manual claims remain unverified, examples or placeholders and are introduced with a warning. The approved challenge corpus supplies company/challenge policy; it is not evidence that every referenced legal statement is currently applicable. Conflicts (including manual exam thresholds and photograph requirements) do not change the engine or configured demo behaviour.

## Evaluation

`eval/rag_cases.json` covers eligibility/exclusivity, six workflow stages, document refusals, training/exam, error codes, motor/NCB, health/life, commission/compliance, ambiguity and unanswerable requests. `eval/run_rag.py` measures retrieval hit checks, citation metadata integrity, mode and latency. HTTP tests cover injection, manipulated client context and ownership. See `eval/out/rag_results.json` for actual results. These are development checks, not independent human answer-quality measurements. Live LLM factual correctness/completeness and real Hindi questions remain unmeasured.
