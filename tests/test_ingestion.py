import tempfile
from pathlib import Path

from src.ingestion import load_codebase, _is_ignored, _load_ignore_patterns


def test_load_codebase_returns_documents_with_metadata(tmp_path):
    (tmp_path / "main.py").write_text("def hello():\n    return 'world'\n")
    (tmp_path / "utils.py").write_text("x = 1\n")

    docs = load_codebase(str(tmp_path), suffixes=[".py"])

    assert len(docs) >= 1
    for doc in docs:
        assert "filename" in doc.metadata
        assert "filepath" in doc.metadata
        assert "line_count" in doc.metadata
        assert doc.metadata["filename"].endswith(".py")
        assert doc.metadata["line_count"] > 0


def test_load_codebase_skips_ignored_paths(tmp_path):
    claudeignore = Path(__file__).parent.parent / ".claudeignore"
    original = claudeignore.read_text() if claudeignore.exists() else None

    try:
        claudeignore.write_text("node_modules/\n__pycache__/\n*.pyc\n")

        (tmp_path / "app.py").write_text("print('hello')\n")
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "lib.py").write_text("x = 1\n")

        docs = load_codebase(str(tmp_path), suffixes=[".py"])

        filepaths = [doc.metadata["filepath"] for doc in docs]
        assert not any("node_modules" in fp for fp in filepaths)
        assert any("app.py" in fp for fp in filepaths)

    finally:
        if original is not None:
            claudeignore.write_text(original)
        elif claudeignore.exists():
            claudeignore.unlink()
