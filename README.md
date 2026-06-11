# meetbowl-ai

Meetbowl AI API server. The minutes pipeline uses the Gemini API for structured meeting
minutes generation. RabbitMQ events still use a deterministic fake context loader until
the meetbowl-be internal context API is available.

The generation workflow accepts one normalized `rawTranscript` string. If the upstream
contract later becomes an utterance list, the context adapter should sort and join the
utterances into this string before invoking the workflow.

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

### API-only mode

RabbitMQ is disabled by default. Gemini remains the default LLM provider.

```bash
uv run fastapi dev
```

The development server starts at `http://127.0.0.1:8000`.

- OpenAPI docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`
- Minutes generation: `POST http://127.0.0.1:8000/api/v1/minutes/generate`
- Chatbot: `POST http://127.0.0.1:8000/api/v1/chat` (`X-Internal-Token` required)

### RabbitMQ consumer mode

Start the RabbitMQ configuration from `meetbowl-infra`, then enable the consumer.

```bash
RABBITMQ_ENABLED=true uv run fastapi dev
```

The server consumes `meeting.ended` and `minutes.generation.requested`, then publishes
`minutes.generated` after Gemini structured-output generation and schema validation.

For local deterministic testing without Gemini, set `LLM_PROVIDER=fake`.

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
