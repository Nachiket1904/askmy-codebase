# askmy-codebase

Chat with any codebase using AI — from your terminal or via REST API. Point it at a local folder or a GitHub URL, ask questions in plain English, and get answers grounded in the actual source code.

## Key Features

- **Terminal CLI** — `askmy-codebase --repo_path .` works from any directory after a one-time install
- **GitHub URL support** — clones and indexes any public repo on the fly
- **Hybrid search** — combines FAISS vector search with BM25 keyword search for better retrieval
- **PR review mode** — feed it a `.diff` file and get a structured code review
- **CLAUDE.md generator** — auto-generate a codebase summary file for any repo
- **REST API** — run it as a FastAPI server for programmatic access
- **Incremental indexing** — only re-embeds files that changed since the last run
- **No cloud embedding** — uses `BAAI/bge-small-en-v1.5` locally (free, private)

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Environment Variables](#environment-variables)
- [REST API](#rest-api)
- [Deployment on Render](#deployment-on-render)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Troubleshooting](#troubleshooting)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.9+ |
| LLM | OpenAI GPT (default: `gpt-4.1-nano-2025-04-14`) |
| Embeddings | HuggingFace `BAAI/bge-small-en-v1.5` (local) |
| Vector Store | FAISS (CPU) |
| Keyword Search | BM25 (rank-bm25) |
| Code Parsing | tree-sitter (Python, JS) |
| Orchestration | LangChain |
| REST API | FastAPI + Uvicorn |
| Deployment | Docker / Render |

---

## Prerequisites

- Python 3.9 or higher
- An [OpenAI API key](https://platform.openai.com/api-keys)
- Git (for cloning GitHub repos)

---

## Installation

### Option 1 — Install from PyPI (recommended)

```bash
pip install askmy-codebase
```

### Option 2 — Install from source

```bash
git clone https://github.com/Nachiket1904/askmy-codebase.git
cd askmy-codebase
pip install -e .
```

### Save your API key (one time only)

```bash
askmy-codebase configure --api-key sk-xxxxx
```

This saves the key to `~/.config/askmy-codebase/config.json` so you never need a `.env` file. The key is loaded automatically on every run.

> **Alternative:** Set `OPENAI_API_KEY` as an environment variable or add it to a `.env` file in your working directory.

---

## Quick Start

```bash
# Chat with the current directory
askmy-codebase --repo_path .

# Chat with a GitHub repo (clones automatically)
askmy-codebase --repo_path https://github.com/username/reponame
```

First run downloads the embedding model (~130 MB) and builds the index. Subsequent runs reuse the index and only re-embed changed files.

---

## Usage

### Chat mode (default)

```bash
askmy-codebase --repo_path .
```

```
[1/4] Indexing codebase from: /your/project
      Index saved to ./index/abc123/
[2/4] Building repository map...
      Mapped 12 file(s)
[3/4] Loading retrieval chain...
      Ready.

[4/4] Starting chat session.
Ask questions about the codebase. Type 'exit' to quit.

> How does authentication work?

The authentication flow uses JWT tokens issued at login...

Sources: src/auth.py, src/middleware.py

> exit
Bye.
```

### PR review mode

```bash
# Generate a diff first
git diff main...my-branch > changes.diff

# Review it
askmy-codebase --repo_path . --mode pr-review --diff changes.diff
```

Outputs a JSON object with a summary, file-by-file feedback, and a risk score.

### Generate CLAUDE.md

Creates a structured `CLAUDE.md` context file for the repo — useful for AI assistants like Claude Code.

```bash
askmy-codebase --repo_path . --mode generate-claude-md
```

### All flags

| Flag | Default | Description |
|---|---|---|
| `--repo_path` | required | Local path or GitHub URL |
| `--index_path` | `./index` | Where to store/load the FAISS index |
| `--model` | `gpt-4.1-nano-2025-04-14` | OpenAI chat model to use |
| `--mode` | `chat` | `chat`, `pr-review`, or `generate-claude-md` |
| `--diff` | — | Path to `.diff` file (required for `pr-review`) |
| `--rebuild-index` | false | Force re-index even if index exists |

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key | Yes (or use `configure`) |
| `OPENAI_CHAT_MODEL` | Override the default chat model | No |
| `API_SECRET_KEY` | Secret key for REST API auth | No (dev mode if unset) |
| `REPO_PATH` | Pre-load a repo at API server startup | No |
| `INDEX_PATH` | Base directory for FAISS indexes | No (default: `./index`) |

---

## REST API

Run as an API server for programmatic access:

```bash
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

Interactive docs available at `http://localhost:8000/docs`.

### Endpoints

#### `POST /index`

Index a repository (required before querying).

```bash
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{"repo_path": "https://github.com/username/repo", "rebuild": false}'
```

```json
{ "status": "ok", "files_indexed": 24 }
```

#### `POST /query`

Ask a question about the indexed codebase.

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{"question": "How does the ingestion pipeline work?"}'
```

```json
{
  "answer": "The ingestion pipeline loads source files using GenericLoader...",
  "sources": ["src/ingestion.py", "src/embedder.py"]
}
```

#### `POST /review`

Review a diff string.

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{"diff": "--- a/src/api.py\n+++ b/src/api.py\n..."}'
```

---

## Deployment on Render

The repo includes a `render.yaml` and `Dockerfile` for one-click deployment.

1. Fork/push this repo to GitHub
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo
3. Render detects `render.yaml` and configures automatically
4. Set these environment variables in the Render dashboard:
   - `OPENAI_API_KEY` — your OpenAI key
   - `API_SECRET_KEY` — a random secret for API auth
5. Deploy

> **Note:** The free tier uses ephemeral storage (`/tmp/index`). The index is rebuilt after each redeploy. For persistence, attach a Render Disk and set `INDEX_PATH` to a persistent path.

### Calling the deployed API

```bash
# Index a repo
curl -X POST https://your-app.onrender.com/index \
  -H "X-API-Key: your-secret" \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "https://github.com/username/repo"}'

# Query it
curl -X POST https://your-app.onrender.com/query \
  -H "X-API-Key: your-secret" \
  -H "Content-Type: application/json" \
  -d '{"question": "What does this project do?"}'
```

---

## Architecture

```
repo_path (local or GitHub URL)
        │
        ▼
  [github_loader]  ← clones GitHub URLs to temp dir
        │
        ▼
  [ingestion]      ← loads .py/.js/.ts/.java files, respects .claudeignore
        │
        ▼
  [embedder]       ← splits by language, embeds with BAAI/bge-small-en-v1.5
        │           ← caches embeddings on disk (incremental re-indexing)
        ▼
  [FAISS index]  +  [BM25 index]
        │                │
        └──────┬──────────┘
               ▼
         [retriever]      ← hybrid search: vector + keyword, re-ranked
               │
               ▼
         [LangChain chain] ← ConversationalRetrievalChain with GPT
               │
               ▼
           answer + sources
```

### How hybrid retrieval works

For each query, two retrievers run in parallel:
- **FAISS** finds semantically similar chunks (meaning-based)
- **BM25** finds chunks with matching keywords (exact-match)

Results are merged and de-duplicated. This handles both conceptual questions ("how does auth work?") and exact lookups ("find where `load_codebase` is called").

### Index isolation

Each repo gets its own index directory keyed by a SHA-256 hash of the repo path. Running against two different repos never overwrites each other's index.

```
./index/
  a3f7c12b4e/   ← hash of /projects/repo-a
  9d2e1f8c03/   ← hash of /projects/repo-b
```

---

## Project Structure

```
askmy-codebase/
├── src/
│   ├── main.py                 # CLI entry point, all modes
│   ├── api.py                  # FastAPI REST server
│   ├── ingestion.py            # File loading, .claudeignore support
│   ├── embedder.py             # FAISS index build/save/load, incremental
│   ├── retriever.py            # Hybrid BM25+FAISS retrieval, LangChain chain
│   ├── github_loader.py        # Clone GitHub URLs to temp dir
│   ├── ast_parser.py           # tree-sitter repo map (functions, classes)
│   ├── pr_reviewer.py          # Diff review pipeline
│   ├── claude_md_generator.py  # CLAUDE.md generation
│   └── context_builder.py      # Load/save CLAUDE.md context
├── tests/                      # pytest test suite (21 tests)
├── .github/
│   └── workflows/
│       └── publish.yml         # Auto-publish to PyPI on GitHub release
├── Dockerfile                  # Docker build (pre-downloads embedding model)
├── render.yaml                 # Render deployment config
├── setup.py                    # Package entry point
├── pyproject.toml              # Build metadata
└── requirements.txt            # All dependencies
```

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

Expected: 21 tests passing.

```bash
# Run a specific file
pytest tests/test_ingestion.py -v
pytest tests/test_retriever.py -v
```

---

## Troubleshooting

### `IndexError: list index out of range` on `/index`

The repo has no supported source files (`.py`, `.js`, `.ts`, `.java`). Check that `repo_path` points to a repo with code in those languages, or that the GitHub URL is correct and the repo is public.

### `OPENAI_API_KEY is not set`

Run `askmy-codebase configure --api-key sk-xxxxx` or export the variable:

```bash
export OPENAI_API_KEY=sk-xxxxx
```

### First run is slow

The embedding model (`BAAI/bge-small-en-v1.5`, ~130 MB) downloads on first use and is cached in `~/.cache/huggingface/`. Subsequent runs are fast.

### Render free tier — index lost after redeploy

Free tier uses ephemeral storage. The index rebuilds on every deploy. To persist it, add a Render Disk and set `INDEX_PATH=/data/index` in your environment variables.

### API returns 503 "Index not loaded"

Call `POST /index` first to build the index before calling `/query` or `/review`.

---

## License

MIT
