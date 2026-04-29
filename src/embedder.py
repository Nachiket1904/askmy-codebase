import hashlib
from pathlib import Path
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from src.ingestion import load_codebase

_EXT_TO_LANGUAGE = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".ts": Language.TS,
    ".java": Language.JAVA,
}

_SUPPORTED_SUFFIXES = list(_EXT_TO_LANGUAGE.keys())


def get_index_path(base_index_dir: str, repo_path: str) -> str:
    hash_prefix = hashlib.sha256(repo_path.encode()).hexdigest()[:10]
    return f"{base_index_dir}/{hash_prefix}"


def _split_documents(docs: list) -> list:
    chunks = []
    by_language: dict[Language, list] = {}

    for doc in docs:
        ext = Path(doc.metadata.get("filepath", "")).suffix.lower()
        lang = _EXT_TO_LANGUAGE.get(ext)
        if lang is None:
            lang = Language.PYTHON  # fallback
        by_language.setdefault(lang, []).append(doc)

    for lang, lang_docs in by_language.items():
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=lang,
            chunk_size=1500,
            chunk_overlap=150,
        )
        chunks.extend(splitter.split_documents(lang_docs))

    return chunks


def build_index(repo_path: str) -> FAISS:
    docs = load_codebase(repo_path, suffixes=_SUPPORTED_SUFFIXES)
    chunks = _split_documents(docs)
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    return FAISS.from_documents(chunks, embeddings)


def save_index(index: FAISS, path: str) -> None:
    index.save_local(path)
