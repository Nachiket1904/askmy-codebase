from unittest.mock import MagicMock, patch


REPO_MAP = {
    "src/auth.py": {
        "functions": [{"name": "login", "start_line": 1, "end_line": 10}],
        "classes": [{"name": "AuthManager", "start_line": 12, "end_line": 40}],
        "imports": [{"statement": "import os", "line": 1}],
    },
    "src/utils.py": {
        "functions": [{"name": "hash_password", "start_line": 1, "end_line": 5}],
        "classes": [],
        "imports": [],
    },
}


def test_load_index_returns_retriever():
    mock_retriever = MagicMock()
    mock_faiss = MagicMock()
    mock_faiss.as_retriever.return_value = mock_retriever

    with patch("src.retriever.FAISS.load_local", return_value=mock_faiss) as mock_load:
        from src.retriever import load_index
        result = load_index("/fake/index/path")

    mock_load.assert_called_once()
    call_args = mock_load.call_args
    assert call_args[0][0] == "/fake/index/path"
    assert call_args[1].get("allow_dangerous_deserialization") is True
    mock_faiss.as_retriever.assert_called_once()
    assert result is mock_retriever


def test_build_chain_has_source_documents_and_repo_map_injected():
    mock_retriever = MagicMock()
    mock_llm_instance = MagicMock()

    with patch("src.retriever.ChatOpenAI", return_value=mock_llm_instance):
        from src.retriever import build_chain
        chain = build_chain(mock_retriever, REPO_MAP)

    assert chain.return_source_documents is True

    # Verify repo map text is present in the system prompt
    combine_chain = chain.combine_docs_chain
    prompt = combine_chain.llm_chain.prompt
    system_msg = prompt.messages[0]
    prompt_text = system_msg.prompt.template
    assert "src/auth.py" in prompt_text
    assert "login" in prompt_text
    assert "AuthManager" in prompt_text
    assert "src/utils.py" in prompt_text
    assert "hash_password" in prompt_text
