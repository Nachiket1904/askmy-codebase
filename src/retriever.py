from __future__ import annotations
import hashlib
import json
import os
import pickle
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain.retrievers import EnsembleRetriever
from src.embedder import get_embeddings

try:
    from bm25 import BM25Index
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False


# ---------------------------------------------------------------------------
# BM25 retriever wrapping the project's custom BM25Index
# ---------------------------------------------------------------------------

class _BM25Retriever(BaseRetriever):
    """Wraps BM25Index as a LangChain-compatible retriever for keyword search."""

    bm25_index: Any
    k: int = 4

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        results = self.bm25_index.search(query, k=self.k)
        return [
            Document(page_content=d["content"], metadata=d.get("metadata", {}))
            for d, _ in results
        ]


def _build_bm25_retriever(chunks: list, k: int = 4) -> _BM25Retriever:
    bm25 = BM25Index()
    bm25.add_documents([
        {"content": chunk.page_content, "metadata": chunk.metadata}
        for chunk in chunks
    ])
    return _BM25Retriever(bm25_index=bm25, k=k)


# ---------------------------------------------------------------------------
# Existing chain helpers
# ---------------------------------------------------------------------------

class _LLMChain:
    def __init__(self, prompt):
        self.prompt = prompt


class _CombineDocsChain:
    def __init__(self, prompt):
        self.llm_chain = _LLMChain(prompt)


class CodeRetrievalChain:
    return_source_documents = True

    def __init__(self, retriever, qa_prompt, llm):
        self.combine_docs_chain = _CombineDocsChain(qa_prompt)
        self._retriever = retriever
        self._llm = llm
        self._prompt = qa_prompt

    def __call__(self, inputs: dict) -> dict:
        question = inputs["question"]
        docs = self._retriever.invoke(question)
        context = "\n\n".join(d.page_content for d in docs)
        messages = self._prompt.format_messages(context=context, question=question)
        response = self._llm.invoke(messages)
        return {"answer": response.content, "source_documents": docs}


def _format_repo_map(repo_map: dict) -> str:
    lines = []
    for filepath, info in repo_map.items():
        fns = [f["name"] for f in info.get("functions", [])]
        cls = [c["name"] for c in info.get("classes", [])]
        parts = []
        if cls:
            parts.append(f"classes: {', '.join(cls)}")
        if fns:
            parts.append(f"functions: {', '.join(fns)}")
        summary = filepath + (f" [{'; '.join(parts)}]" if parts else "")
        lines.append(summary)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Index loading with integrity check + hybrid retrieval
# ---------------------------------------------------------------------------

def _verify_index_manifest(index_dir: Path) -> None:
    manifest_path = index_dir / "index.manifest"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Index integrity manifest missing at {index_dir}. "
            "Re-run indexing to rebuild the index."
        )
    manifest = json.loads(manifest_path.read_text())
    for fname, expected_hash in manifest.items():
        actual = hashlib.sha256((index_dir / fname).read_bytes()).hexdigest()
        if actual != expected_hash:
            raise ValueError(
                f"Index file '{fname}' failed integrity check — it may have been tampered with. "
                "Re-run indexing to rebuild."
            )


def load_index(index_path: str):
    """Load FAISS + BM25 and return an EnsembleRetriever (or FAISS-only if no chunks saved)."""
    safe_path = Path(index_path).resolve()
    if not safe_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    _verify_index_manifest(safe_path)

    faiss_index = FAISS.load_local(
        str(safe_path), get_embeddings(), allow_dangerous_deserialization=True
    )
    faiss_retriever = faiss_index.as_retriever(search_kwargs={"k": 6})

    chunks_file = safe_path / "chunks.pkl"
    if _BM25_AVAILABLE and chunks_file.exists():
        chunks = pickle.loads(chunks_file.read_bytes())
        bm25_retriever = _build_bm25_retriever(chunks, k=6)
        # FAISS handles semantic similarity; BM25 handles exact keyword/identifier matches
        return EnsembleRetriever(
            retrievers=[faiss_retriever, bm25_retriever],
            weights=[0.6, 0.4],
        )

    return faiss_retriever


def build_chain(retriever, repo_map: dict, codebase_context: str | None = None) -> CodeRetrievalChain:
    repo_map_text = _format_repo_map(repo_map)

    context_section = (
        f"\nCODEBASE CONTEXT (from CLAUDE.md):\n{codebase_context}\n"
        if codebase_context else ""
    )

    system_template = (
        "You are an expert code assistant with deep knowledge of this repository.\n\n"
        "REPOSITORY STRUCTURE:\n"
        f"{repo_map_text}\n"
        f"{context_section}\n"
        "Use the repository map to understand file relationships and the retrieved "
        "code chunks to answer accurately. Always cite the source file."
    )

    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", system_template),
        ("human", "RETRIEVED CODE:\n{context}\n\nQUESTION: {question}"),
    ])

    llm = ChatOpenAI(model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4.1-nano-2025-04-14"), temperature=0)

    return CodeRetrievalChain(retriever, qa_prompt, llm)

