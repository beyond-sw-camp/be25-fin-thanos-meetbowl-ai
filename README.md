# meetbowl-ai

Meetbowl AI API server. The minutes pipeline uses the Gemini API for structured meeting
minutes generation.

Provider ports are split by capability: text, streaming, structured generation, and
embedding. Workflows request a logical model profile instead of depending on a concrete
provider or model name.

The generation workflow now prefers BE-provided transcript `segments` and rebuilds a
normalized `rawTranscript` internally. Generation is evidence-first: the model extracts
summary/agenda/decision/action evidence with `sourceSequences`, then the workflow drops
invalid or suspicious-only evidence and deterministically converts the validated result
into `MinutesDraft` and Tiptap `editorContent`.

After Gemini output validation, the workflow deterministically converts `MinutesDraft`
into Tiptap StarterKit-compatible `editorContent`. Gemini never generates editor nodes
directly. The REST response includes this document; the RabbitMQ event keeps the existing
root event contract and does not include it yet.

## Local setup

This project uses `uv` for Python dependency and virtual environment management.

```bash
uv sync
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env`. The default model is `gemini-2.5-flash`.
For embeddings, set `OPENAI_API_KEY`. The default embedding model is
`text-embedding-3-large`, shortened to 1536 dimensions.
Minutes generation can also fall back to OpenAI when Gemini returns a transient 503.
Configure this with `MINUTES_FALLBACK_PROVIDER` and `MINUTES_FALLBACK_MODEL`.

### API-only mode

RabbitMQ is disabled by default. Gemini remains the default LLM provider.

```bash
uv run fastapi dev
```

The development server starts at `http://127.0.0.1:8000`.

- OpenAPI docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`
- Readiness check: `http://127.0.0.1:8000/api/v1/health/ready`
- Minutes generation: `POST http://127.0.0.1:8000/api/v1/minutes/generate`
- Chatbot: `POST http://127.0.0.1:8000/api/v1/chat` (`X-Internal-Token` required)

The chatbot API uses a dedicated BE contract translator. API request/response schemas are
kept separate from the internal `ChatCommand` and `ChatResult` workflow contracts.
The existing minutes workflow remains independently configured and available; adding the
chatbot does not replace the minutes provider, endpoint, event flow, or Tiptap conversion.

Documents can be indexed through `POST /api/v1/indexes/documents`. The indexer stores
chat source metadata and the BE-provided owner/workspace access scope in Qdrant. For a
local Qdrant integration test without a Gemini key, run:

```bash
RUN_RAG_E2E=true uv run pytest -q tests/test_rag_e2e.py -s
```

### Manual realtime feedback check

For an end-to-end check on a deployed server, temporarily set
`FEEDBACK_DEMO_MODE=true` and redeploy the AI container. Demo mode evaluates every
finalized segment, uses a `0.45` cosine threshold, permits a semantic-match fallback,
and shortens duplicate feedback cooldown to 10 seconds. It does not bypass
`organizationId`, `allowedUserIds`, source type, or current-meeting exclusion filters.
At least one approved historical meeting-minutes document visible to every current
authenticated participant must already be indexed. Restore
`FEEDBACK_DEMO_MODE=false` after the check.

To inspect only the AI feedback result without BE, STT, LiveKit, or MariaDB, start the
API with Redis feedback enabled and deterministic embeddings in a dedicated collection:

```bash
REDIS_FEEDBACK_ENABLED=true \
DOCUMENT_EMBEDDING_PROVIDER=fake \
QUERY_EMBEDDING_PROVIDER=fake \
DOCUMENT_EMBEDDING_MODEL=fake-embedding \
QUERY_EMBEDDING_MODEL=fake-embedding \
QDRANT_COLLECTION=meetbowl-feedback-manual \
uv run fastapi dev
```

In another terminal, index fixture minutes, publish four finalized transcript events,
and wait for the generated Redis event:

```bash
uv run python scripts/manual_feedback_flow.py
```

The script generates isolated UUIDs, puts all fixture participants in `allowedUserIds`,
uses a different historical meeting ID, and prints the complete
`meeting.feedback.generated` envelope. Qdrant and Redis must already be running.

This test uses a dedicated temporary collection and verifies backup mail, personal memo,
personal drive file, shared workspace file version, meeting minutes, and workspace access
denial. Set `GEMINI_API_KEY` and `LLM_PROVIDER=gemini` to verify production embeddings and
LLM-generated answers.

With a valid Gemini key, run the production-path integration test:

```bash
RUN_GEMINI_RAG_E2E=true uv run pytest -q tests/test_gemini_rag_e2e.py -s
```

This uses `gemini-embedding-001`, a temporary 3072-dimensional Qdrant collection, and the
configured Gemini generation model. The collection is removed after the test.

### RabbitMQ consumer mode

Start the RabbitMQ configuration from `meetbowl-infra`, then enable the consumer.

```bash
RABBITMQ_ENABLED=true uv run fastapi dev
```

The server consumes `meeting.ended`, `minutes.generation.requested`, and
`document.index.requested`. It publishes `minutes.generated` after evidence extraction,
schema validation, transcript-quality filtering, and deterministic Tiptap conversion,
and it writes approved-document embeddings into Qdrant for `document.index.requested`.

Generation models are selected by logical profile. The default profiles are
`minutes-summary`, `chatbot`, and `meeting-feedback`; each has independent provider,
model, and temperature settings. They currently default to the same Gemini model.
Minutes structured generation can optionally fall back to OpenAI when the primary
Gemini request is temporarily unavailable.
Embedding settings are independently defined for `document-embedding` and
`query-embedding`. The default provider is OpenAI, and the default model is
`text-embedding-3-large` with 1536 dimensions. Document and query provider, model,
and dimensions must match. Changing this search space requires a new Qdrant collection
and full document reindexing.

Document indexing uses `QDRANT_URL`, `QDRANT_COLLECTION`, `DOCUMENT_CHUNK_SIZE`,
`DOCUMENT_CHUNK_OVERLAP`, and `DOCUMENT_CHUNK_STRATEGY_VERSION`. The default chunk
strategy is `paragraph-v1`.

Production deployment keeps the AI server private on the runtime network. Set
`BE_BASE_URL` to the internal BE address and use `/api/v1/health/ready` for smoke
tests. The readiness endpoint checks Qdrant and, when enabled, Redis and RabbitMQ.
It intentionally does not call paid external LLM APIs.

For local deterministic minutes testing without Gemini, set:

```bash
MINUTES_SUMMARY_PROVIDER=fake
MINUTES_SUMMARY_MODEL=fake-minutes-model
```

## Test

Tests inject fake Gemini clients and RabbitMQ messages, so external services are not required.

```bash
uv run pytest
```

## Layout

```text
app/
  api/          # Internal REST adapters
  events/       # RabbitMQ mapping, processing, and publishing
  pipelines/    # Raw transcript normalization
  ports/        # Context and LLM provider contracts
  providers/    # Gemini and development fake adapters
  schemas/      # API, event, and workflow Pydantic models
  workflows/    # AI workflow orchestration
tests/
```
