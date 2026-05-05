from __future__ import annotations
import logging
import os
import re
import secrets
import tempfile
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

logger = logging.getLogger(__name__)

load_dotenv()
if not os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_API_KEY_N"):
    os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY_N"]

_SUPPORTED_SUFFIXES = [".py", ".js", ".ts", ".java"]

_state: dict = {}
_state_lock = threading.Lock()

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_GITHUB_URL_RE = re.compile(r'^https://github\.com/[\w\-]+/[\w\-\.]+(/.*)?$')


def _require_api_key(api_key: str | None = Security(_API_KEY_HEADER)):
    secret = os.environ.get("API_SECRET_KEY")
    if not secret:
        return  # unauthenticated dev mode — warning already logged at startup
    if not api_key or not secrets.compare_digest(api_key, secret):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _validate_repo_path(repo_path: str) -> str:
    if _GITHUB_URL_RE.match(repo_path):
        return repo_path
    resolved = os.path.realpath(repo_path)
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=400, detail="repo_path must be an existing local directory or a GitHub URL")
    return resolved


def _load_codebase(repo_path, **kwargs):
    from src.ingestion import load_codebase as _f
    return _f(repo_path, **kwargs)


def _build_index(repo_path, index_path=None):
    from src.embedder import build_index as _f
    return _f(repo_path, index_path)


def _save_index(index, path, chunks=None, repo_path=None):
    from src.embedder import save_index as _f
    return _f(index, path, chunks, repo_path)


def _load_index(index_path):
    from src.retriever import load_index as _f
    return _f(index_path)


def _build_chain(retriever, repo_map):
    from src.retriever import build_chain as _f
    return _f(retriever, repo_map)


def _build_repo_map(repo_path):
    from src.ast_parser import build_repo_map as _f
    return _f(repo_path)


def _review_diff(diff_path, chain, repo_map):
    from src.pr_reviewer import review_diff as _f
    return _f(diff_path, chain, repo_map)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo_path = os.environ.get("REPO_PATH", "")
    index_path = os.environ.get("INDEX_PATH", "./index")

    if not os.environ.get("API_SECRET_KEY"):
        logger.warning("API_SECRET_KEY is not set — all endpoints are unauthenticated")

    with _state_lock:
        _state["repo_path"] = repo_path
        _state["index_path"] = index_path
        _state["chain"] = None
        _state["repo_map"] = None

    if repo_path and os.path.isdir(index_path):
        try:
            repo_map = _build_repo_map(repo_path)
            retriever = _load_index(index_path)
            chain = _build_chain(retriever, repo_map)
            with _state_lock:
                _state["repo_map"] = repo_map
                _state["chain"] = chain
        except Exception as exc:
            logger.warning("Startup index load failed: %s", exc)

    yield


app = FastAPI(lifespan=lifespan)


class IndexRequest(BaseModel):
    repo_path: str
    rebuild: bool = False


class QueryRequest(BaseModel):
    question: str


class ReviewRequest(BaseModel):
    diff: str


@app.post("/index")
def index_repo(req: IndexRequest, _: None = Depends(_require_api_key)):
    validated_path = _validate_repo_path(req.repo_path)

    with _state_lock:
        index_path = _state.get("index_path", "./index")

    docs = _load_codebase(validated_path, suffixes=_SUPPORTED_SUFFIXES)
    files_indexed = len({
        doc.metadata.get("filepath") or doc.metadata.get("source", "")
        for doc in docs
    })

    if os.path.isdir(index_path) and not req.rebuild:
        retriever = _load_index(index_path)
    else:
        index, chunks = _build_index(validated_path, index_path)
        _save_index(index, index_path, chunks, validated_path)
        retriever = _load_index(index_path)

    repo_map = _build_repo_map(validated_path)
    chain = _build_chain(retriever, repo_map)

    with _state_lock:
        _state["repo_path"] = validated_path
        _state["repo_map"] = repo_map
        _state["chain"] = chain

    return {"status": "ok", "files_indexed": files_indexed}


@app.post("/query")
def query(req: QueryRequest, _: None = Depends(_require_api_key)):
    with _state_lock:
        chain = _state.get("chain")

    if chain is None:
        raise HTTPException(status_code=503, detail="Index not loaded. Call /index first.")

    result = chain({"question": req.question, "chat_history": []})
    answer = result["answer"]
    seen: set[str] = set()
    sources: list[str] = []
    for doc in result.get("source_documents", []):
        fp = doc.metadata.get("filepath") or doc.metadata.get("source", "unknown")
        if fp not in seen:
            seen.add(fp)
            sources.append(fp)

    return {"answer": answer, "sources": sources}


@app.post("/review")
def review(req: ReviewRequest, _: None = Depends(_require_api_key)):
    with _state_lock:
        chain = _state.get("chain")
        repo_map = _state.get("repo_map") or {}

    if chain is None:
        raise HTTPException(status_code=503, detail="Index not loaded. Call /index first.")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".diff", delete=False, encoding="utf-8"
    ) as f:
        f.write(req.diff)
        tmp_path = f.name
    os.chmod(tmp_path, 0o600)

    try:
        result = _review_diff(tmp_path, chain, repo_map)
    finally:
        os.unlink(tmp_path)

    return result

