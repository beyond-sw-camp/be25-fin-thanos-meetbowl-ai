# meetbowl-ai

Meetbowl AI API server.

## Local setup

This project uses `uv` for Python dependency and virtual environment management.

```bash
uv sync
uv run fastapi dev
```

The development server starts at `http://127.0.0.1:8000`.

- OpenAPI docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`

## Test

```bash
uv run pytest
```

## Layout

```text
app/
  main.py          # FastAPI application entrypoint
  api/v1/          # Versioned API routers
tests/             # API tests
```
