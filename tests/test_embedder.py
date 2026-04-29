from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from src.embedder import build_index, save_index, get_index_path


def _make_doc(content: str, filepath: str) -> Document:
    return Document(
        page_content=content,
        metadata={"source": filepath, "filename": filepath.split("/")[-1], "filepath": filepath, "line_count": 3},
    )


@patch("src.embedder.FAISS.from_documents")
@patch("src.embedder.HuggingFaceEmbeddings")
@patch("src.embedder.load_codebase")
def test_build_index_returns_faiss(mock_load, mock_embeddings_cls, mock_faiss):
    mock_load.return_value = [
        _make_doc("def foo():\n    pass\n", "/repo/foo.py"),
        _make_doc("function bar() {}\n", "/repo/bar.js"),
    ]
    mock_embeddings_cls.return_value = MagicMock()
    fake_index = MagicMock()
    mock_faiss.return_value = fake_index

    result = build_index("/repo")

    mock_load.assert_called_once_with("/repo", suffixes=[".py", ".js", ".ts", ".java"])
    mock_faiss.assert_called_once()
    assert result is fake_index


@patch("src.embedder.FAISS.from_documents")
@patch("src.embedder.HuggingFaceEmbeddings")
@patch("src.embedder.load_codebase")
def test_save_index_calls_save_local(mock_load, mock_embeddings_cls, mock_faiss):
    mock_load.return_value = [_make_doc("x = 1\n", "/repo/x.py")]
    mock_embeddings_cls.return_value = MagicMock()
    fake_index = MagicMock()
    mock_faiss.return_value = fake_index

    index = build_index("/repo")
    save_index(index, "/tmp/my_index")

    fake_index.save_local.assert_called_once_with("/tmp/my_index")


def test_get_index_path_same_repo_returns_same_hash():
    path1 = get_index_path("./index", "/home/user/myrepo")
    path2 = get_index_path("./index", "/home/user/myrepo")
    assert path1 == path2


def test_get_index_path_different_repos_return_different_hashes():
    path1 = get_index_path("./index", "/home/user/repo_a")
    path2 = get_index_path("./index", "/home/user/repo_b")
    assert path1 != path2
