from __future__ import annotations
import fnmatch
from pathlib import Path
from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers.language.language_parser import LanguageParser


def _load_ignore_patterns(claudeignore_path: Path) -> list[str]:
    if not claudeignore_path.exists():
        return []
    patterns = []
    for line in claudeignore_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_ignored(path: Path, repo_root: Path, patterns: list[str]) -> bool:
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        relative = path
    rel_str = relative.as_posix()
    for pattern in patterns:
        normalized = pattern.rstrip("/")
        if fnmatch.fnmatch(rel_str, normalized):
            return True
        for part in relative.parts:
            if fnmatch.fnmatch(part, normalized):
                return True
    return False


def load_codebase(repo_path: str, glob: str = "**/*", suffixes: list[str] | None = None) -> list:
    """
    Load all source files from repo_path, skipping .claudeignore patterns.
    Returns a list of LangChain Documents with metadata: source, filename, line_count.
    """
    repo_root = Path(repo_path).resolve()
    # Read .claudeignore from the target repo, not from this project's root
    ignore_patterns = _load_ignore_patterns(repo_root / ".claudeignore")

    if suffixes is None:
        suffixes = [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".cpp", ".c", ".h"]

    loader = GenericLoader.from_filesystem(
        path=str(repo_root),
        glob=glob,
        suffixes=suffixes,
        parser=LanguageParser(),
    )

    raw_docs = loader.load()

    docs = []
    for doc in raw_docs:
        file_path = Path(doc.metadata.get("source", ""))
        if _is_ignored(file_path, repo_root, ignore_patterns):
            continue

        doc.metadata["filename"] = file_path.name
        doc.metadata["filepath"] = str(file_path)
        doc.metadata["line_count"] = len(doc.page_content.splitlines())
        docs.append(doc)

    return docs

