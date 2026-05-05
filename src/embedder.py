from __future__ import annotations
import hashlib
import json
import pickle
from pathlib import Path

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
from src.ingestion import load_codebase

_EXT_TO_LANGUAGE = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".ts": Language.TS,
    ".java": Language.JAVA,
}

_SUPPORTED_SUFFIXES = list(_EXT_TO_LANGUAGE.keys())

_embeddings: HuggingFaceEmbeddings | None = None


def _detect_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        device = _detect_device()
        # Larger batches on GPU (fewer kernel launches); conservative on MPS
        batch_size = {"cuda": 512, "mps": 128, "cpu": 256}.get(device, 256)
        print(f"      [embedder] device={device}  batch_size={batch_size}")
        _embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": device},
            encode_kwargs={"batch_size": batch_size, "normalize_embeddings": True},
        )
    return _embeddings


def get_index_path(base_index_dir: str, repo_path: str) -> str:
    hash_prefix = hashlib.sha256(repo_path.encode()).hexdigest()[:10]
    return f"{base_index_dir}/{hash_prefix}"


def _get_cached_embeddings(index_dir: str) -> CacheBackedEmbeddings:
    """Returns an embedding wrapper that caches results by chunk text on disk.

    On first run every chunk is embedded and written to embed_cache/.
    On subsequent runs identical chunks are read from cache — only
    changed/new chunks hit the model.
    """
    cache_path = Path(index_dir) / "embed_cache"
    cache_path.mkdir(parents=True, exist_ok=True)
    store = LocalFileStore(str(cache_path))
    base = get_embeddings()
    return CacheBackedEmbeddings.from_bytes_store(base, store, namespace=base.model_name)


def _split_documents(docs: list) -> list:
    chunks = []
    by_language: dict[Language, list] = {}

    for doc in docs:
        ext = Path(doc.metadata.get("filepath", "")).suffix.lower()
        lang = _EXT_TO_LANGUAGE.get(ext, Language.PYTHON)
        by_language.setdefault(lang, []).append(doc)

    for lang, lang_docs in by_language.items():
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=lang,
            chunk_size=1500,
            chunk_overlap=150,
        )
        chunks.extend(splitter.split_documents(lang_docs))

    return chunks


def _compute_file_hashes(repo_path: str) -> dict[str, str]:
    root = Path(repo_path).resolve()
    hashes: dict[str, str] = {}
    for suffix in _SUPPORTED_SUFFIXES:
        for f in root.rglob(f"*{suffix}"):
            try:
                hashes[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
            except OSError:
                pass
    return hashes


def has_index_changes(repo_path: str, index_path: str) -> bool:
    """True if any source file changed, was added, or was deleted since last index."""
    hashes_file = Path(index_path) / "file_hashes.json"
    if not hashes_file.exists():
        return True
    stored = json.loads(hashes_file.read_text())
    current = _compute_file_hashes(repo_path)
    return current != stored


def build_index(repo_path: str, index_path: str | None = None) -> tuple[FAISS, list]:
    """Build a FAISS index for repo_path.

    When index_path is given, chunk-level embeddings are read from an on-disk
    cache so only changed/new chunks are sent to the embedding model.
    Returns (faiss_index, raw_chunks) so callers can save chunks for BM25.
    """
    docs = load_codebase(repo_path, suffixes=_SUPPORTED_SUFFIXES)
    chunks = _split_documents(docs)
    embeddings = _get_cached_embeddings(index_path) if index_path else get_embeddings()
    faiss_index = FAISS.from_documents(chunks, embeddings)
    return faiss_index, chunks


def _write_manifest(path: str) -> None:
    index_dir = Path(path)
    manifest = {}
    for fname in ("index.faiss", "index.pkl", "chunks.pkl"):
        fpath = index_dir / fname
        if fpath.exists():
            manifest[fname] = hashlib.sha256(fpath.read_bytes()).hexdigest()
    (index_dir / "index.manifest").write_text(json.dumps(manifest))


def save_index(
    index: FAISS,
    path: str,
    chunks: list | None = None,
    repo_path: str | None = None,
) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    index.save_local(path)
    if chunks is not None:
        (Path(path) / "chunks.pkl").write_bytes(pickle.dumps(chunks))
    if repo_path:
        hashes = _compute_file_hashes(repo_path)
        (Path(path) / "file_hashes.json").write_text(json.dumps(hashes))
    _write_manifest(path)

