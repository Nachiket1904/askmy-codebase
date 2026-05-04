import os
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document


def _make_chain(answer="auth flow uses JWT", sources=None):
    if sources is None:
        sources = [Document(page_content="code", metadata={"filepath": "src/auth.py"})]
    mock_chain = MagicMock()
    mock_chain.return_value = {"answer": answer, "source_documents": sources}
    return mock_chain


# --- Pipeline step tests ------------------------------------------------------

def test_run_builds_index_when_no_existing_index():
    mock_index = MagicMock()
    mock_retriever = MagicMock()
    mock_chain = _make_chain()

    with patch("os.path.isdir", return_value=False), \
         patch("src.main.build_index", return_value=mock_index) as mock_build_idx, \
         patch("src.main.save_index") as mock_save_idx, \
         patch("src.main.build_repo_map", return_value={"src/auth.py": {}}) as mock_repo_map, \
         patch("src.main.load_index", return_value=mock_retriever) as mock_load_idx, \
         patch("src.main.build_chain", return_value=mock_chain) as mock_build_chain, \
         patch("builtins.input", side_effect=["exit"]):

        from src.main import run
        run("/fake/repo")

    mock_build_idx.assert_called_once_with("/fake/repo")
    mock_save_idx.assert_called_once_with(mock_index, "./index/411a6af354")
    mock_repo_map.assert_called_once_with("/fake/repo")
    mock_load_idx.assert_called_once_with("./index/411a6af354")
    mock_build_chain.assert_called_once_with(mock_retriever, {"src/auth.py": {}}, None)


def test_run_skips_index_build_when_index_exists():
    mock_chain = _make_chain()

    with patch("os.path.isdir", return_value=True), \
         patch("src.main.build_index") as mock_build_idx, \
         patch("src.main.save_index") as mock_save_idx, \
         patch("src.main.build_repo_map", return_value={}), \
         patch("src.main.load_index", return_value=MagicMock()), \
         patch("src.main.build_chain", return_value=mock_chain), \
         patch("builtins.input", side_effect=["exit"]):

        from src.main import run
        run("/fake/repo", rebuild_index=False)

    mock_build_idx.assert_not_called()
    mock_save_idx.assert_not_called()


def test_run_rebuild_index_forces_reindex_even_when_index_exists():
    mock_index = MagicMock()
    mock_chain = _make_chain()

    with patch("os.path.isdir", return_value=True), \
         patch("src.main.build_index", return_value=mock_index) as mock_build_idx, \
         patch("src.main.save_index") as mock_save_idx, \
         patch("src.main.build_repo_map", return_value={}), \
         patch("src.main.load_index", return_value=MagicMock()), \
         patch("src.main.build_chain", return_value=mock_chain), \
         patch("builtins.input", side_effect=["exit"]):

        from src.main import run
        run("/fake/repo", rebuild_index=True)

    mock_build_idx.assert_called_once()
    mock_save_idx.assert_called_once()


def test_run_custom_index_path_is_passed_through():
    mock_index = MagicMock()
    mock_chain = _make_chain()

    with patch("os.path.isdir", return_value=False), \
         patch("src.main.build_index", return_value=mock_index), \
         patch("src.main.save_index") as mock_save_idx, \
         patch("src.main.build_repo_map", return_value={}), \
         patch("src.main.load_index", return_value=MagicMock()) as mock_load_idx, \
         patch("src.main.build_chain", return_value=mock_chain), \
         patch("builtins.input", side_effect=["exit"]):

        from src.main import run
        run("/fake/repo", index_path="./custom-index")

    mock_save_idx.assert_called_once_with(mock_index, "./custom-index/411a6af354")
    mock_load_idx.assert_called_once_with("./custom-index/411a6af354")


def test_run_model_flag_sets_env_var():
    mock_chain = _make_chain()

    with patch("os.path.isdir", return_value=True), \
         patch("src.main.build_repo_map", return_value={}), \
         patch("src.main.load_index", return_value=MagicMock()), \
         patch("src.main.build_chain", return_value=mock_chain), \
         patch("builtins.input", side_effect=["exit"]):

        from src.main import run
        run("/fake/repo", model="gpt-4o-mini")

    assert os.environ.get("OPENAI_CHAT_MODEL") == "gpt-4o-mini"


# --- Interactive loop tests ---------------------------------------------------

def test_run_interactive_loop_prints_answer_and_sources(capsys):
    mock_chain = _make_chain(
        answer="Login is in auth.py",
        sources=[Document(page_content="def login():", metadata={"filepath": "src/auth.py"})],
    )

    with patch("os.path.isdir", return_value=True), \
         patch("src.main.build_repo_map", return_value={}), \
         patch("src.main.load_index", return_value=MagicMock()), \
         patch("src.main.build_chain", return_value=mock_chain), \
         patch("builtins.input", side_effect=["where is login?", "exit"]):

        from src.main import run
        run("/fake/repo")

    captured = capsys.readouterr()
    assert "Login is in auth.py" in captured.out
    assert "src/auth.py" in captured.out


def test_run_chain_error_is_caught_and_loop_continues(capsys):
    mock_chain = MagicMock(side_effect=[RuntimeError("API timeout"), {"answer": "ok", "source_documents": []}])

    with patch("os.path.isdir", return_value=True), \
         patch("src.main.build_repo_map", return_value={}), \
         patch("src.main.load_index", return_value=MagicMock()), \
         patch("src.main.build_chain", return_value=mock_chain), \
         patch("builtins.input", side_effect=["question 1", "question 2", "exit"]):

        from src.main import run
        run("/fake/repo")

    captured = capsys.readouterr()
    assert "[error]" in captured.out
    assert "ok" in captured.out


# --- main() / argparse tests --------------------------------------------------

def test_main_exits_on_nonexistent_repo_path():
    with patch("sys.argv", ["main", "--repo_path", "/nonexistent/xyz123"]), \
         pytest.raises(SystemExit) as exc_info:
        from src.main import main
        main()
    assert exc_info.value.code == 1


def test_main_exits_when_api_key_missing(tmp_path):
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with patch("sys.argv", ["main", "--repo_path", str(tmp_path)]), \
             pytest.raises(SystemExit) as exc_info:
            from src.main import main
            main()
        assert exc_info.value.code == 1
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved
