from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import src.api as api_mod

client = TestClient(api_mod.app)


def test_index_endpoint(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo_path = str(repo_dir)
    mock_docs = [
        MagicMock(metadata={"filepath": "src/a.py"}),
        MagicMock(metadata={"filepath": "src/b.py"}),
        MagicMock(metadata={"filepath": "src/a.py"}),  # duplicate counts as one file
    ]
    with patch("src.api._load_codebase", return_value=mock_docs), \
         patch("src.api._build_index", return_value=MagicMock()), \
         patch("src.api._save_index"), \
         patch("src.api._load_index", return_value=MagicMock()), \
         patch("src.api._build_repo_map", return_value={}), \
         patch("src.api._build_chain", return_value=MagicMock()):
        resp = client.post("/index", json={"repo_path": repo_path, "rebuild": True})

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "files_indexed": 2}


def test_query_endpoint():
    mock_doc = MagicMock()
    mock_doc.metadata = {"filepath": "src/auth.py"}
    mock_chain = MagicMock(return_value={
        "answer": "Auth starts in auth.py",
        "source_documents": [mock_doc],
    })
    api_mod._state["chain"] = mock_chain

    resp = client.post("/query", json={"question": "How does auth work?"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Auth starts in auth.py"
    assert data["sources"] == ["src/auth.py"]


def test_review_endpoint():
    api_mod._state["chain"] = MagicMock()
    api_mod._state["repo_map"] = {}

    review_result = {
        "files_reviewed": ["src/foo.py"],
        "deviations": [],
        "summary": "Looks good.",
    }
    raw_diff = (
        "diff --git a/src/foo.py b/src/foo.py\n"
        "--- a/src/foo.py\n+++ b/src/foo.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
    )

    with patch("src.api._review_diff", return_value=review_result) as mock_review:
        resp = client.post("/review", json={"diff": raw_diff})
        called_path = mock_review.call_args[0][0]
        assert called_path.endswith(".diff")

    assert resp.status_code == 200
    data = resp.json()
    assert data["files_reviewed"] == ["src/foo.py"]
    assert data["summary"] == "Looks good."
