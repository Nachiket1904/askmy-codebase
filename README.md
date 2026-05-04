# Codebase Knowledge AI

Chat with any codebase in plain English and get answers with exact source file references. Point it at a local repo or a GitHub URL — it indexes the code locally, builds a structural map, and lets you ask questions like "Where is the auth flow?" or "How does the payment module connect to the database?"

Embeddings run **fully locally** (no API cost). Only the chat LLM calls OpenAI.

## Table of Contents

- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [Environment setup](#environment-setup)
- [Usage — CLI chat](#usage--cli-chat)
- [Usage — PR review](#usage--pr-review)
- [Usage — REST API server](#usage--rest-api-server)
- [Codebase context (CLAUDE.md)](#codebase-context-claudemd)
- [Index isolation](#index-isolation)
- [All CLI flags](#all-cli-flags)
- [Example session](#example-session)
- [Project structure](#project-structure)
- [Architecture](#architecture)
- [Run tests](#run-tests)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
Repo / GitHub URL
      │
      ▼
 ingestion.py       ← loads source files, respects .claudeignore
      │
      ▼
 embedder.py        ← language-aware chunking → HuggingFace embeddings → FAISS index
      │                 (stored at ./index/<sha256-hash-of-repo-path>/)
      ▼
 ast_parser.py      ← tree-sitter AST → repo map (files, classes, functions)
      │
      ▼
 context_builder.py ← loads or gathers CLAUDE.md context on first run
      │
      ▼
 retriever.py       ← similarity search + GPT chain with repo map + CLAUDE.md context
      │
      ▼
 Answer with source file references
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Embeddings | `sentence-transformers` — `BAAI/bge-small-en-v1.5` (local, free) |
| Vector store | FAISS (local, no server needed) |
| AST parsing | `tree-sitter` (Python, JavaScript) |
| LLM | OpenAI GPT (default: `gpt-4.1-nano-2025-04-14`) |
| LLM framework | LangChain |
| REST API | FastAPI + Uvicorn |
| Config | `python-dotenv` |

---

## Prerequisites

- Python 3.11 or higher
- An OpenAI API key
- Git (required if indexing GitHub URLs)

---

## Install

```bash
pip install -r requirements.txt
```

---

## Environment setup

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

> If your key lives under a different name (`OPENAI_API_KEY_N`), the app remaps it automatically — no change needed.

**Optional variables:**

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key for the chat LLM | *(required)* |
| `OPENAI_CHAT_MODEL` | Model name to use for chat | `gpt-4.1-nano-2025-04-14` |
| `API_SECRET_KEY` | Bearer token for the REST API server | *(open if unset)* |
| `REPO_PATH` | Default repo path loaded at API server startup | *(none)* |
| `INDEX_PATH` | Default index path used at API server startup | `./index` |

---

## Usage — CLI chat

**First run** — indexes the repo and starts chat:

```bash
python -m src.main --repo_path /path/to/your/repo
```

On first run for a new repo, you will be prompted for codebase context (see [Codebase context](#codebase-context-claudemd) below). Subsequent runs load the saved context automatically.

**Subsequent runs** — index is reused, no re-embedding:

```bash
python -m src.main --repo_path /path/to/your/repo
```

**Force a fresh index** (after large code changes):

```bash
python -m src.main --repo_path /path/to/your/repo --rebuild-index
```

**Index a GitHub repo** (cloned to a temp dir, cleaned up after):

```bash
python -m src.main --repo_path https://github.com/owner/repo
```

**Use a different model:**

```bash
python -m src.main --repo_path . --model gpt-4o-mini
```

**Custom index location:**

```bash
python -m src.main --repo_path . --index_path ./my-project-index
```

---

## Usage — PR review

Analyze a git diff against the indexed codebase and flag deviations from existing patterns:

```bash
# Generate a diff file
git diff main..feature-branch > changes.diff

# Review it
python -m src.main --repo_path . --mode pr-review --diff changes.diff
```

Output is JSON with per-file deviations and an overall summary:

```json
{
  "files_reviewed": ["src/api.py", "src/retriever.py"],
  "deviations": [
    {
      "file": "src/api.py",
      "issue": "Missing authentication dependency on new endpoint",
      "suggestion": "Add `_: None = Depends(_require_api_key)` ..."
    }
  ],
  "summary": "One deviation found in src/api.py. The new /status endpoint ..."
}
```

---

## Usage — REST API server

Start the FastAPI server:

```bash
uvicorn src.api:app --reload
```

The server exposes three endpoints, all requiring `X-API-Key: <API_SECRET_KEY>` if `API_SECRET_KEY` is set in your `.env`.

### `POST /index`

Index a repository (local path or GitHub URL):

```bash
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{"repo_path": "/path/to/repo", "rebuild": false}'
```

Response:
```json
{"status": "ok", "files_indexed": 42}
```

### `POST /query`

Ask a question about the indexed codebase:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d '{"question": "How does authentication work?"}'
```

Response:
```json
{
  "answer": "Authentication is handled in src/api.py via ...",
  "sources": ["src/api.py", "src/github_loader.py"]
}
```

### `POST /review`

Review a raw diff string:

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret" \
  -d "{\"diff\": \"$(cat changes.diff)\"}"
```

Response: same structure as the CLI PR review output.

---

## Codebase context (CLAUDE.md)

On the **first chat session** for any repo, the assistant prompts you with four quick questions about the codebase:

```
--- Codebase Context Setup ---
Answer a few questions so the assistant has context for this repo.
Answers are saved as CLAUDE.md in the repo root.

  What does this codebase do? (1-2 sentences)
  > A FastAPI service that handles payment processing for the storefront.

  What are the main modules or components?
  > payments, orders, webhooks, auth

  What language(s) and frameworks does it use?
  > Python, FastAPI, PostgreSQL, Stripe SDK

  Any known issues, gotchas, or important context? (Enter to skip)
  > Stripe webhook verification must stay in place — do not remove it.

  Context saved to /path/to/repo/CLAUDE.md
```

The answers are written to `CLAUDE.md` in the repo root. On every subsequent run the file is loaded automatically and injected into the LLM's system prompt — so answers are grounded in your own description of the project, not just code pattern matching.

**Editing context manually:** `CLAUDE.md` is plain Markdown — open it in any editor and update it whenever the codebase changes significantly.

**Skipping context setup:** Run in non-interactive mode (e.g., piped input, CI) and the Q&A is skipped automatically. The file is only created when `stdin` is a TTY.

---

## Index isolation

Each repository gets its own FAISS index subfolder named by a SHA-256 hash of the repo path:

```
./index/
  a3f9c12b01/   ← repo A
  7e4d8f2c99/   ← repo B
```

Switching repos never loads the wrong index or triggers an unnecessary rebuild. The resolved path is printed at startup:

```
[1/4] Using index at: ./index/a3f9c12b01/ (my-repo)  (--rebuild-index to force rebuild)
```

---

## All CLI flags

| Flag | Default | Description |
|---|---|---|
| `--repo_path` | *(required)* | Local path or GitHub URL to index |
| `--index_path` | `./index` | Base directory for FAISS indexes |
| `--model` | `gpt-4.1-nano-2025-04-14` | OpenAI chat model |
| `--rebuild-index` | off | Force re-indexing even if an index exists |
| `--mode` | `chat` | `chat` or `pr-review` |
| `--diff` | *(none)* | Path to `.diff` file (required for `--mode pr-review`) |

---

## Example session

```
[1/4] Using index at: ./index/a3f9c12b01/ (code_assistant)  (--rebuild-index to force rebuild)
      Context loaded from /path/to/code_assistant/CLAUDE.md

[2/4] Building repository map...
      Mapped 8 file(s)
[3/4] Loading retrieval chain...
      Ready.

[4/4] Starting chat session.
Ask questions about the codebase. Type 'exit' to quit.

> How does the .claudeignore file work?

The .claudeignore file is read by load_codebase() in src/ingestion.py.
It supports glob patterns — any file whose relative path matches a pattern
is excluded from indexing. Directory names are matched against each path
segment, so adding `node_modules` excludes all nested paths.

Sources: src/ingestion.py

> What endpoints does the API expose?

The FastAPI server in src/api.py exposes three endpoints:
- POST /index  — indexes a repo (auth required)
- POST /query  — answers a question about the indexed repo (auth required)
- POST /review — reviews a raw diff against the index (auth required)

Sources: src/api.py

> exit
Bye.
```

---

## Project structure

```
src/
  main.py            — CLI entry point (chat + PR review modes)
  ingestion.py       — loads source files, applies .claudeignore rules
  embedder.py        — language-aware chunking, HuggingFace embeddings, FAISS index
  ast_parser.py      — tree-sitter AST: extracts functions, classes, imports
  retriever.py       — FAISS retriever + GPT chain builder
  context_builder.py — CLAUDE.md creation and loading (codebase context)
  github_loader.py   — GitHub URL detection and temp-dir cloning
  pr_reviewer.py     — diff splitting and per-file deviation analysis
  api.py             — FastAPI server (index / query / review endpoints)

tests/
  test_embedder.py
  test_ast_parser.py
  test_retriever.py
  test_main.py
  test_ingestion.py
  test_github_loader.py
  test_pr_reviewer.py
  test_api.py
```

---

## Architecture

```
                        ┌─────────────────────────────────┐
                        │         User / CI / IDE          │
                        └────────────┬────────────────────┘
                                     │
                     ┌───────────────┼────────────────┐
                     │               │                │
               CLI (main.py)   REST API (api.py)  PR Review
                     │               │                │
                     └───────────────┴────────────────┘
                                     │
              ┌──────────────────────▼──────────────────────┐
              │              Core Pipeline                   │
              │                                              │
              │  github_loader → ingestion → embedder        │
              │       ↓              ↓           ↓           │
              │  (clone URL)    (load files)  (FAISS index)  │
              │                                              │
              │  ast_parser → repo map                       │
              │                                              │
              │  context_builder → CLAUDE.md context         │
              │                                              │
              │  retriever → similarity search + GPT chain   │
              └──────────────────────────────────────────────┘
```

### Key design decisions

- **Local embeddings** — `BAAI/bge-small-en-v1.5` runs on CPU, costs nothing, and keeps your code off third-party servers.
- **Index isolation** — SHA-256 hash of the repo path as the index subfolder name. Different repos never collide; same repo always reuses its index.
- **CLAUDE.md context** — Human-supplied description injected into every LLM call. Compensates for what embeddings can't capture (intent, constraints, team conventions).
- **Repo map in system prompt** — Full file/class/function index from tree-sitter always in context, so the LLM knows the shape of the codebase even for questions where retrieved chunks are sparse.

---

## Run tests

```bash
pytest tests/ -v
```

No real API calls are made. All LLM and embedding calls are mocked.

---

## Troubleshooting

### `OPENAI_API_KEY is not set`

Add the key to `.env`:
```
OPENAI_API_KEY=sk-...
```
Or use `OPENAI_API_KEY_N` — the app remaps it automatically.

### Index loads slowly on first run

The first run downloads the `BAAI/bge-small-en-v1.5` model (~130 MB) and builds the FAISS index. Both are cached — subsequent runs are fast.

### Wrong answers after large refactors

The index is stale. Force a rebuild:
```bash
python -m src.main --repo_path . --rebuild-index
```
Then update `CLAUDE.md` if the architecture changed significantly.

### GitHub clone fails

Private repos are not supported — a clear error is raised. Ensure the URL is a public GitHub repository:
```
https://github.com/owner/repo
```

### `401 Unauthorized` on API endpoints

Set `API_SECRET_KEY` in `.env` and pass it in requests:
```
X-API-Key: your-secret-value
```
If `API_SECRET_KEY` is not set, all endpoints are open (development only — not for production).

### Context Q&A skipped unexpectedly

The Q&A only runs when `stdin` is a TTY. In CI, scripts, or piped input it is skipped automatically. Run interactively in a real terminal, or create `CLAUDE.md` manually before running.
