import argparse
import itertools
import os
import shutil
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from src.github_loader import resolve_repo_path
from src.embedder import get_index_path
from src.context_builder import gather_context, load_context

load_dotenv()
if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_API_KEY_N"):
    os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY_N"]


# --- Spinner ------------------------------------------------------------------

class _Spinner:
    """Print-based spinner. Silent when stdout is not a TTY (tests, pipes)."""
    _FRAMES = r"|/-\\"

    def __init__(self, message: str):
        self._message = message
        self._tty = sys.stdout.isatty()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            sys.stdout.write(f"\r{frame} {self._message}  ")
            sys.stdout.flush()
            time.sleep(0.1)

    def __enter__(self):
        if self._tty:
            self._thread.start()
        return self

    def __exit__(self, *_):
        if self._tty:
            self._stop.set()
            self._thread.join()
            sys.stdout.write(f"\r[ok] {self._message}\n")
            sys.stdout.flush()


# --- Lazy-import wrappers -----------------------------------------------------
# Defined at module level so tests can patch src.main.<name>.
# Lazy so importing src.main never triggers langchain.prompts at import time.

def load_codebase(repo_path, **kwargs):
    from src.ingestion import load_codebase as _f
    return _f(repo_path, **kwargs)


def build_index(repo_path, index_path=None):
    from src.embedder import build_index as _f
    return _f(repo_path, index_path)


def save_index(index, path, chunks=None, repo_path=None):
    from src.embedder import save_index as _f
    return _f(index, path, chunks, repo_path)


def has_index_changes(repo_path, index_path):
    from src.embedder import has_index_changes as _f
    return _f(repo_path, index_path)


def build_repo_map(repo_path):
    from src.ast_parser import build_repo_map as _f
    return _f(repo_path)


def load_index(index_path):
    from src.retriever import load_index as _f
    return _f(index_path)


def build_chain(retriever, repo_map, codebase_context=None):
    from src.retriever import build_chain as _f
    return _f(retriever, repo_map, codebase_context)


def review_diff(diff_path, chain, repo_map):
    from src.pr_reviewer import review_diff as _f
    return _f(diff_path, chain, repo_map)


def generate_claude_md(repo_path, repo_map, chain):
    from src.claude_md_generator import generate_claude_md as _f
    return _f(repo_path, repo_map, chain)


def save_claude_md(content, repo_path):
    from src.claude_md_generator import save_claude_md as _f
    return _f(content, repo_path)


# --- Core pipeline ------------------------------------------------------------

def run(
    repo_path: str,
    index_path: str = "./index",
    model: str | None = None,
    rebuild_index: bool = False,
) -> None:
    repo_path, is_temp = resolve_repo_path(repo_path)
    resolved_index_path = get_index_path(index_path, repo_path)
    repo_name = repo_path.rstrip("/").rstrip("\\").split("/")[-1].split("\\")[-1]

    if model:
        os.environ["OPENAI_CHAT_MODEL"] = model

    index_exists = os.path.isdir(resolved_index_path) and not rebuild_index
    use_existing = index_exists and not has_index_changes(repo_path, resolved_index_path)

    if use_existing:
        print(f"[1/4] No changes detected — using index at: {resolved_index_path}/  (--rebuild-index to force rebuild)")
    elif index_exists:
        print(f"[1/4] Changes detected — updating index from: {repo_path}")
        try:
            with _Spinner("Embedding changed chunks (cache used for unchanged)..."):
                index, chunks = build_index(repo_path, resolved_index_path)
                save_index(index, resolved_index_path, chunks, repo_path)
            print(f"      Index updated at {resolved_index_path}/")
        except Exception as exc:
            _die(f"Indexing failed: {exc}")
    else:
        print(f"[1/4] Indexing codebase from: {repo_path}")
        try:
            with _Spinner("Embedding code chunks..."):
                index, chunks = build_index(repo_path, resolved_index_path)
                save_index(index, resolved_index_path, chunks, repo_path)
            print(f"      Index saved to {resolved_index_path}/")
        except Exception as exc:
            _die(f"Indexing failed: {exc}")

    codebase_context = load_context(repo_path)
    if codebase_context is None and sys.stdin.isatty():
        codebase_context = gather_context(repo_path)
    elif codebase_context:
        print(f"      Context loaded from {repo_path}/CLAUDE.md\n")

    print("[2/4] Building repository map...")
    try:
        with _Spinner("Parsing files..."):
            repo_map = build_repo_map(repo_path)
        print(f"      Mapped {len(repo_map)} file(s)")
    except Exception as exc:
        _die(f"Repo map failed: {exc}")

    print("[3/4] Loading retrieval chain...")
    try:
        with _Spinner("Initializing model..."):
            retriever = load_index(resolved_index_path)
            chain = build_chain(retriever, repo_map, codebase_context)
        print("      Ready.\n")
    except Exception as exc:
        _die(
            f"Chain initialization failed: {exc}\n"
            "  Tip: make sure OPENAI_API_KEY (or OPENAI_API_KEY_N) is set in your .env file."
        )

    chat_history = []
    print("[4/4] Starting chat session.")
    print("Ask questions about the codebase. Type 'exit' to quit.")
    print("Tip: Run with --mode generate-claude-md to generate a CLAUDE.md for this repo\n")
    try:
        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not question:
                continue
            if question.lower() == "exit":
                print("Bye.")
                break

            try:
                result = chain({"question": question, "chat_history": chat_history})
            except Exception as exc:
                print(f"[error] {exc}\n")
                continue

            answer = result["answer"]
            sources = result.get("source_documents", [])

            print(f"\n{answer}\n")

            if sources:
                seen: set[str] = set()
                refs = []
                for doc in sources:
                    fp = doc.metadata.get("filepath") or doc.metadata.get("source", "unknown")
                    if fp not in seen:
                        seen.add(fp)
                        refs.append(fp)
                print("Sources: " + ", ".join(refs) + "\n")

            chat_history.append((question, answer))
    finally:
        if is_temp:
            shutil.rmtree(repo_path, ignore_errors=True)


# --- CLAUDE.md generation pipeline -------------------------------------------

def run_generate_claude_md(
    repo_path: str,
    index_path: str = "./index",
    model: str | None = None,
    rebuild_index: bool = False,
) -> None:
    repo_path, is_temp = resolve_repo_path(repo_path)
    resolved_index_path = get_index_path(index_path, repo_path)
    repo_name = repo_path.rstrip("/").rstrip("\\").split("/")[-1].split("\\")[-1]

    if model:
        os.environ["OPENAI_CHAT_MODEL"] = model

    index_exists = os.path.isdir(resolved_index_path) and not rebuild_index
    use_existing = index_exists and not has_index_changes(repo_path, resolved_index_path)

    if use_existing:
        print(f"[1/4] No changes detected — using index at: {resolved_index_path}/ ({repo_name})")
    elif index_exists:
        print(f"[1/4] Changes detected — updating index from: {repo_path}")
        try:
            with _Spinner("Embedding changed chunks (cache used for unchanged)..."):
                index, chunks = build_index(repo_path, resolved_index_path)
                save_index(index, resolved_index_path, chunks, repo_path)
        except Exception as exc:
            _die(f"Indexing failed: {exc}")
    else:
        print(f"[1/4] Indexing codebase from: {repo_path}")
        try:
            with _Spinner("Embedding code chunks..."):
                index, chunks = build_index(repo_path, resolved_index_path)
                save_index(index, resolved_index_path, chunks, repo_path)
        except Exception as exc:
            _die(f"Indexing failed: {exc}")

    print("[2/4] Building repository map...")
    try:
        with _Spinner("Parsing files..."):
            repo_map = build_repo_map(repo_path)
    except Exception as exc:
        _die(f"Repo map failed: {exc}")

    print("[3/4] Loading retrieval chain...")
    try:
        with _Spinner("Initializing model..."):
            retriever = load_index(resolved_index_path)
            chain = build_chain(retriever, repo_map)
        print("      Ready.\n")
    except Exception as exc:
        _die(f"Chain initialization failed: {exc}")

    print("[4/4] Generating CLAUDE.md (6 queries)...")
    try:
        with _Spinner("Querying codebase..."):
            content = generate_claude_md(repo_path, repo_map, chain)
    except Exception as exc:
        if is_temp:
            shutil.rmtree(repo_path, ignore_errors=True)
        _die(f"Generation failed: {exc}")

    # For cloned GitHub repos, save destination is cwd (temp dir is gone after cleanup)
    save_dest = os.getcwd() if is_temp else repo_path
    if is_temp:
        shutil.rmtree(repo_path, ignore_errors=True)

    try:
        answer = input(f"\nSave CLAUDE.md to {save_dest}? (y/n) ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer == "y":
        saved_path = save_claude_md(content, save_dest)
        print(f"Saved to {saved_path}")
    else:
        print("\n" + content)


# --- PR Review pipeline -------------------------------------------------------

def run_pr_review(
    repo_path: str,
    diff_path: str,
    index_path: str = "./index",
    model: str | None = None,
) -> None:
    import json

    if model:
        os.environ["OPENAI_CHAT_MODEL"] = model

    print("[1/2] Loading retrieval chain...")
    try:
        repo_map = build_repo_map(repo_path)
        retriever = load_index(index_path)
        chain = build_chain(retriever, repo_map)
        print("      Ready.\n")
    except Exception as exc:
        _die(f"Chain initialization failed: {exc}")

    print(f"[2/2] Reviewing diff: {diff_path}")
    try:
        result = review_diff(diff_path, chain, repo_map)
    except Exception as exc:
        _die(f"PR review failed: {exc}")

    print(json.dumps(result, indent=2))


# --- Helpers ------------------------------------------------------------------

def _die(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


# --- Entry point --------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Codebase Knowledge AI — chat with your source code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m src.main --repo_path .\n"
            "  python -m src.main --repo_path . --model gpt-4o-mini\n"
            "  python -m src.main --repo_path . --rebuild-index\n"
            "  python -m src.main --repo_path . --index_path ./my-index"
        ),
    )
    parser.add_argument(
        "--repo_path",
        required=True,
        help="Path to the repository to index and query",
    )
    parser.add_argument(
        "--index_path",
        default="./index",
        help="Directory to store/load the FAISS index (default: ./index)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI chat model to use (default: gpt-4.1-nano-2025-04-14)",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Force re-indexing even if an existing index is found at --index_path",
    )
    parser.add_argument(
        "--mode",
        choices=["chat", "pr-review", "generate-claude-md"],
        default="chat",
        help="Operation mode: 'chat' (default), 'pr-review', or 'generate-claude-md'",
    )
    parser.add_argument(
        "--diff",
        default=None,
        help="Path to a .diff file (required when --mode pr-review)",
    )
    args = parser.parse_args()

    from src.github_loader import is_github_url
    if not is_github_url(args.repo_path):
        repo = Path(args.repo_path)
        if not repo.exists():
            _die(f"Repository path does not exist: '{args.repo_path}'")
        if not repo.is_dir():
            _die(f"Repository path is not a directory: '{args.repo_path}'")
    if not os.environ.get("OPENAI_API_KEY"):
        _die("OPENAI_API_KEY is not set. Add it to your .env file as OPENAI_API_KEY or OPENAI_API_KEY_N.")

    if args.mode == "pr-review":
        if not args.diff:
            _die("--diff is required when --mode pr-review")
        diff_path = Path(args.diff)
        if not diff_path.exists():
            _die(f"Diff file does not exist: '{args.diff}'")
        run_pr_review(
            args.repo_path,
            diff_path=str(diff_path),
            index_path=args.index_path,
            model=args.model,
        )
    elif args.mode == "generate-claude-md":
        run_generate_claude_md(
            args.repo_path,
            index_path=args.index_path,
            model=args.model,
            rebuild_index=args.rebuild_index,
        )
    else:
        run(
            args.repo_path,
            index_path=args.index_path,
            model=args.model,
            rebuild_index=args.rebuild_index,
        )


if __name__ == "__main__":
    main()
