# Codebase Knowledge AI

Chat with any codebase. Ask questions in plain English and get answers with exact source file references.

## How it works

```
Your code → chunk → embed (HuggingFace, local) → FAISS index
                                                        ↓
User question → embed → similarity search → GPT answers with your real code
```

Embeddings run **fully locally** (no API cost). Only the chat LLM calls OpenAI.

## Install

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

> If your key is stored as `OPENAI_API_KEY_N`, the app remaps it automatically.

## Usage

**First run** — index the repo and start chatting:

```bash
python -m src.main --repo_path /path/to/your/repo
```

**Skip re-indexing** on subsequent runs (index is reused automatically):

```bash
python -m src.main --repo_path /path/to/your/repo
```

**Force a fresh index** (after big code changes):

```bash
python -m src.main --repo_path /path/to/your/repo --rebuild-index
```

**Use a different model:**

```bash
python -m src.main --repo_path . --model gpt-4o-mini
```

**Custom index location:**

```bash
python -m src.main --repo_path . --index_path ./my-project-index
```

## All flags

| Flag | Default | Description |
|---|---|---|
| `--repo_path` | *(required)* | Path to the repository to index |
| `--index_path` | `./index` | Where to store/load the FAISS index |
| `--model` | `gpt-4.1-nano-2025-04-14` | OpenAI chat model to use |
| `--rebuild-index` | off | Force re-indexing even if an index exists |

## Example session

```
[1/3] Using existing index at ./index/
[2/3] Building repository map...
      Mapped 6 file(s)
[3/3] Loading retrieval chain...
      Ready.

Ask questions about the codebase. Type 'exit' to quit.

> How does the .claudeignore file work?

The .claudeignore file is loaded by `load_codebase()` in src/ingestion.py.
It supports glob patterns — any file whose relative path matches a pattern
is excluded from indexing. Directory names are also matched against each
path segment, so adding `node_modules` excludes all nested paths.

Sources: src/ingestion.py

> exit
Bye.
```

## Run tests

```bash
pytest tests/ -v
```

## Project structure

```
src/
  ingestion.py   — loads source files, applies .claudeignore
  embedder.py    — chunks code, builds FAISS index (HuggingFace embeddings)
  ast_parser.py  — extracts functions/classes/imports via tree-sitter
  retriever.py   — FAISS retriever + GPT chain
  main.py        — CLI entry point
tests/
  test_*.py      — unit tests (no real API calls)
```
