import os
import tempfile

from unittest.mock import MagicMock


REPO_MAP = {
    "src/auth.py": {
        "functions": [{"name": "login", "start_line": 1, "end_line": 10}],
        "classes": [],
        "imports": [],
    },
}

SAMPLE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index abc..def 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,3 +1,4 @@
+import random
 def login():
     pass
"""


def _write_diff(content: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".diff", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


def test_review_diff_no_deviations():
    from src.pr_reviewer import review_diff

    chain = MagicMock(
        return_value={"answer": "No deviations found.", "source_documents": []}
    )
    diff_file = _write_diff(SAMPLE_DIFF)
    try:
        result = review_diff(diff_file, chain, REPO_MAP)
    finally:
        os.unlink(diff_file)

    assert result["files_reviewed"] == ["src/auth.py"]
    assert result["deviations"] == []
    assert isinstance(result["summary"], str)


def test_review_diff_with_deviation():
    from src.pr_reviewer import review_diff

    def fake_chain(inputs):
        if "Review this git diff" in inputs["question"]:
            return {
                "answer": "This import violates the no-random pattern.\nSuggestion: remove it.",
                "source_documents": [],
            }
        return {"answer": "Overall: one deviation found.", "source_documents": []}

    diff_file = _write_diff(SAMPLE_DIFF)
    try:
        result = review_diff(diff_file, fake_chain, REPO_MAP)
    finally:
        os.unlink(diff_file)

    assert "src/auth.py" in result["files_reviewed"]
    assert len(result["deviations"]) == 1
    dev = result["deviations"][0]
    assert dev["file"] == "src/auth.py"
    assert "import" in dev["issue"].lower() or "violates" in dev["issue"].lower()
    assert isinstance(result["summary"], str)
