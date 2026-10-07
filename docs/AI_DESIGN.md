# AI Layer Design — LiteLLM + own retrieval (RAG) on Firestore

## 1. Why this exists

Originally the chat was tied to OpenAI in three ways:

1. **Chat API** — `responses.create(...)` with OpenAI-only features.
2. **Document search** — OpenAI-hosted *vector stores* (`file_search` tool) held the league data and rules.
3. **Conversation memory** — OpenAI remembered the thread (`previous_response_id`).

That locked the app to one vendor and made the plan to move to Google services impossible without a rewrite.
The goal of this change: **the model is a config setting, and the document search belongs to us.**

Out of scope (later phases): Azure Blob → Cloud Storage, hosting on Cloud Run, moving auth/user tables from Supabase to Firestore.

## 2. Big picture

```
                    ┌─────────────────────── INDEXING (when data changes) ────────────────────────┐
 Yahoo league sync ─┤                                                                              │
 rules PDF / stats ─┤→ DocumentIndexer → RetrievalService → chunker → Embedder (LiteLLM) → VectorStore (Firestore)
                    └──────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────── CHAT (every question) ───────────────────────────┐
 POST /chat ─→ ChatRouter ─→ ChatService ─┬→ RetrievalService.retrieve ─→ Embedder + VectorStore.search
                                          ├→ ChatSessionManager (history)
                                          └→ LLMClient (LiteLLM) ─→ Gemini / OpenAI / Claude / ...
```

Everything in the middle is **ports and adapters**: services depend on small interfaces
(`LLMClient`, `Embedder`, `VectorStore` in `ai/ports.py`), and concrete implementations plug in at startup
in `config/dependencies.py`. That is what makes it swappable and testable.

## 3. Components (all in `src/appl/ai/` unless noted)

| File | What it does | Why it's designed this way |
|---|---|---|
| `ports.py` | `LLMClient.complete(messages)`, `Embedder.embed(texts)`, `VectorStore.{replace_collection, search, last_synced}`, plus `VectorRecord`, `SearchResult`. | Tiny interfaces = easy fakes in tests, easy new backends. |
| `chunker.py` | `chunk_text` (size 800, overlap 100) and `chunk_json` (one chunk per record of a list; nested JSON flattened to `a.b: value` lines; oversized records split). | Models retrieve better from small focused pieces. A player-stats list becomes one chunk per player, so "how is Curry doing" finds exactly Curry. |
| `pdf.py` | `extract_pdf_text` via `pypdf`. | The rules are a PDF; we now read it ourselves instead of uploading it to OpenAI. |
| `litellm_adapters.py` | `LiteLLMClient` (chat) and `LiteLLMEmbedder` (batches of 100). Model strings come from env. Transient errors (503, timeout, rate limit, connection) are retried with backoff (1s, 2s); a request timeout is always set; an optional fallback model is tried if the main one still fails. Every failure becomes an `LLMError` with secrets removed. |
| `redact.py` | `scrub_secrets(text)`: strips `key=...`, bearer tokens, `sk-`/`AIza` keys and the value of any `*_KEY/_SECRET/_TOKEN` env var from error text. | LiteLLM gives one call format for every provider; wrapping errors means the rest of the app never imports provider exceptions. |
| `memory_store.py` | `InMemoryVectorStore` (cosine similarity). | Fast offline tests / local experiments. |
| `firestore_store.py` | `FirestoreVectorStore` using Firestore native vector search (`find_nearest`, cosine). | Free tier, no keys on Google hosting, and vectors live in one Google database. |
| `retrieval.py` | `Document` (text *or* JSON), `RetrievalService.index(collection, docs)` and `.retrieve(query, collections, k)`. | The only place that knows "chunk → embed → store" and "embed query → search". |
| `chat_service.py` | `ChatService.chat(request) -> str`. | Replaces `OpenaiAgentManager`; builds the prompt and calls the LLM (see §5). |
| `document_indexer.py` | `DocumentIndexer` with `update_league_files`, `update_rules`, `update_player_stats`. | Same method names/arguments as the old `OpenaiFileManager`, so callers only needed a rename. |
| `chat_router.py` | Flask blueprint for `POST /chat`. | Maps errors to HTTP codes (§7). |
| `service/chat_session_manager.py` | Per-session message history with a turn cap. | Replaces OpenAI's server-side memory. |
| `config/dependencies.py` | Builds and wires everything (`set_services()`), loads the system prompt. | Single composition root. |

## 4. Collections and Firestore layout

Documents are grouped into **collections** (retrieval scopes). Ids reuse the existing helpers
(`model/vector_store.py`, `model/file.py`):

- `general` — rules PDF + consolidated player stats + NBA schedule (shared by all users).
- `league_<leagueId>` — that league's synced Yahoo files.

Firestore:

```
rag_collections/{collection_id}              { last_synced, chunk_count }
rag_collections/{collection_id}/chunks/{id}  { text, source, index, embedding: Vector }
```

Needs **one** vector index on `chunks.embedding` (collection-group `chunks`, flat, dimension = embedding size,
max 2048 in Firestore). Setup command is in `SETUP_CHECKLIST.md`.

## 5. Flows

### 5.1 Indexing
1. Caller invokes e.g. `update_league_files("42", {"roster": {...}, "standings": [...]})`.
2. Each file becomes a `Document` (`roster.json`, `standings.json`).
3. `RetrievalService.index("league_42", docs)`: chunk all docs → **one batched embedding call** (sub-batched by 100) → `replace_collection`.
4. `replace_collection` **deletes all existing chunks of that collection first**, writes new chunks in batches of ≤400, then stamps `last_synced`. Re-syncing never leaves stale or duplicate data (the old OpenAI flow created a new store each time and leaked the old one).

### 5.2 Chat (`POST /chat`)
Body: `{"session_id": "...", "user_message": "...", "league_id": "42" | null}`

1. Validate: `session_id` and a non-blank `user_message` are required, else `ValueError` → HTTP 400.
2. Choose collections: `["league_42", "general"]`, or just `["general"]` if no league.
3. Retrieve the top-k (default 5 per collection, best overall) chunks for the question.
4. Build messages in this order:
   1. `system`: the system prompt (`utils/system_prompt.md` or `SYSTEM_PROMPT_PATH`)
   2. `system`: "Relevant context…" with each chunk labelled by its source file (omitted if nothing found)
   3. the last `CHAT_HISTORY_TURNS` (default 10) user/assistant pairs
   4. `user`: the new question
5. `LLMClient.complete(messages)` → answer text.
6. Only **after success** are the question and answer saved to history (so a failed call doesn't pollute the session).
7. The router returns the answer as plain text (the same as before: `/chat` still returns a bare string).

## 6. Configuration

| Env var | Default | Meaning |
|---|---|---|
| `LLM_MODEL` | `gemini/gemini-3.8-flash` | any LiteLLM model string, e.g. `openai/gpt-4o-mini`, `anthropic/...` |
| `EMBEDDING_MODEL` | `gemini/gemini-embedding-001` | embedding model |
| `LLM_FALLBACK_MODEL` | none | optional second model tried when `LLM_MODEL` fails after its retries |
| `LLM_TIMEOUT_SECONDS` | 30 | per-request timeout |
| `EMBEDDING_DIMENSIONS` | `768` | vector size requested from the model (the model natively returns 3072, above Firestore's 2048 limit). **Must match the Firestore index.** The embedder rejects any vector of a different size. |
| `GEMINI_API_KEY` (or the provider's key) | — | read by LiteLLM |
| `GOOGLE_CLOUD_PROJECT` | — | Firestore project; auth via Application Default Credentials |
| `RETRIEVAL_TOP_K` | 5 | chunks retrieved |
| `CHAT_HISTORY_TURNS` | 10 | past turns sent to the model |
| `SYSTEM_PROMPT_PATH` | `utils/system_prompt.md` | override the prompt |

Changing `LLM_MODEL` needs no re-index. Changing `EMBEDDING_MODEL` (or its dimension) requires a new index and re-indexing everything, because vectors from different models aren't comparable.

## 7. Error handling

| Situation | Result |
|---|---|
| Body isn't JSON | 400 `{"error": "JSON body required"}` |
| Missing/blank `session_id` or `user_message` | 400 with message |
| Provider/network/quota/key problem, empty model answer (after retries and the fallback model) | `LLMError` → 502 `{"error": "The AI service is unavailable…"}` (details stay in the server log, with keys scrubbed; the original exception is deliberately not chained, because provider errors can contain the request URL with the API key) |
| No documents indexed | Chat still works, just without context |

## 8. How it was built (TDD) and how to test

Built test-first, in this order, each step red → green: chunker → PDF → vector-store contract → retrieval →
LiteLLM adapters → session history → ChatService → DocumentIndexer → router → Firestore store.

- `pytest` (config in `pytest.ini`): **70 offline tests** using fakes (`FakeEmbedder`, `FakeLLMClient`) in `tests/unit/conftest.py`. No network, no keys.
- **Contract suite** (`tests/unit/vector_store_contract.py`): one set of behaviours every `VectorStore` must satisfy (ranking, k limit, replace semantics, isolation between collections, multi-collection search, metadata round-trip, `last_synced`). It runs on the in-memory store always, and on real Firestore with `pytest -m integration` (needs `FIRESTORE_TEST_PROJECT`).
- Firestore logic (batching, delete-then-write, distance→score conversion) is additionally unit-tested against a small fake Firestore client.
- LiteLLM adapters are tested with `litellm.completion/embedding` patched.

## 9. Key decisions and trade-offs

| Decision | Alternative | Why this |
|---|---|---|
| Own retrieval instead of a vendor's file search | Gemini File Search / OpenAI vector stores | Provider-neutral; LiteLLM doesn't unify those features. Cost: we own chunking quality. |
| Firestore for vectors | Supabase pgvector, Cloud SQL | Your chosen Google direction, free tier, no secrets on Google hosting. Cost: 2048-dim cap, one-time index. |
| History stored by us, last-N turns | Send full history | Bounds cost and context length. |
| Replace-whole-collection on sync | Incremental upserts | Simple and always consistent; data volumes are small. |
| Keep `DocumentIndexer` method signatures | New API | Minimal change to Yahoo sync/main routes/scripts. |
| Cosine similarity, flat index | HNSW etc. | Firestore's supported flat index is fine at this size. |

## 10. Known limitations (and suggested follow-ups)

1. **Sessions are in process memory** — lost on restart; not shared across gunicorn workers. Follow-up: store history in Firestore (small change behind `ChatSessionManager`).
2. **Provider hiccups** — handled by retries, timeout and the optional fallback model; if all fail the user gets a 502 and retries. Retries happen inside the request, so a bad outage can make one request take up to ~(timeout × attempts) seconds.
2. **Indexing is synchronous** — a league sync now waits for embedding calls (OpenAI upload was also synchronous, but check latency). Follow-up: run indexing in a background task.
3. **Firestore dimension cap (2048)** — handled: `EMBEDDING_DIMENSIONS` (default 768) is passed to the provider, and the embedder raises `LLMError` if a vector comes back with another size. Models that can't shorten their output can't be used with Firestore.
4. **Integration tests** zero-pad their 2-D test vectors to `EMBEDDING_DIMENSIONS`, so they run against the real 768-D index (cosine similarity is unchanged by padding).
5. **No re-embedding guard** — nothing stops you from changing `EMBEDDING_MODEL` and querying old vectors. Idea: store the model name in the collection doc and refuse/warn on mismatch.
6. **Pre-existing bug, untouched:** the `/update_rules` route in `router/document_router.py` declares `update_rules(file: Dict)` as a Flask view and doesn't return a response.
7. **Login still requires an HTTPS tunnel locally** (`_scheme="https"` in `auth_routes.py`); unrelated to this change.

## 10b. Archive storage (Azure no longer required)

League sync used to stop with "Azure Storage not configured" *before* the new indexing ran, so Azure was a hard requirement for league-aware answers.
`appl/storage/blob_storage.py` now provides a `BlobStorage` interface with three backends, picked by `build_blob_storage()`:

| `BLOB_STORAGE` | Behavior |
|---|---|
| `none` (default when nothing is configured) | no archive; sync + indexing still run |
| `gcs` (auto when `GCS_BUCKET` is set) | `GcsBlobStorage`: JSON saved to the bucket under `<container>/<leagueId>/<file>.json`, retries with backoff, skips unchanged content via a SHA-256 stored in object metadata (same semantics as the Azure class) |
| `azure` (auto when `AZURE_STORAGE_CONNECTION_STRING` is set) | the existing `AzureBlobStorage`, loaded lazily so the Azure SDK is optional |

The archive is a backup/audit copy only; the chat reads from the Firestore index, not from blobs.

## 11. What was removed

`service/openai_agent_manager.py`, `service/openai_file_manager.py`, `service/vector_store_manager.py`,
`router/openai_agent_router.py`, `repository/supaBase/repositories/vector_metadata_repository.py`,
`FileMetadata`/`OpenaiStoredFiles`/`UpdateFile` in `model/file.py`, `VectorStoreMetadata` in `model/vector_store.py`.
`router/openai_file_router.py` was renamed `router/document_router.py`. The Supabase `vector_store_metadata` table is now unused and can be dropped.

## 12. Suggested next phases

1. Sessions → Firestore. 2. Azure Blob → Cloud Storage. 3. Cloud Run deployment (Dockerfile, env via Secret Manager, ADC identity so no key files). 4. Optional: users/auth tables from Supabase to Firestore, then remove Supabase.
