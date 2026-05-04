import os
import tempfile
from unittest.mock import MagicMock, call

from src.claude_md_generator import generate_claude_md, save_claude_md


def _make_chain(answers):
    chain = MagicMock()
    chain.side_effect = [{"answer": a, "source_documents": []} for a in answers]
    return chain


def test_generate_claude_md_calls_all_six_questions():
    answers = [f"answer_{i}" for i in range(6)]
    chain = _make_chain(answers)

    content = generate_claude_md("/fake/repo", {}, chain)

    assert chain.call_count == 6
    called_questions = [c.args[0]["question"] for c in chain.call_args_list]
    assert "Give a 2 sentence summary of what this codebase does" in called_questions
    assert "What is the tech stack used in this project?" in called_questions
    assert "List every file in src/ and what it does in one sentence each" in called_questions
    assert "What are the most important functions a developer should know about?" in called_questions
    assert "How do you run this project and its tests?" in called_questions
    assert "Are there any known issues, gotchas or things to avoid?" in called_questions
    for answer in answers:
        assert answer in content


def test_save_claude_md_writes_to_repo_root():
    content = "# CLAUDE.md\n\nHello world"
    with tempfile.TemporaryDirectory() as tmpdir:
        saved = save_claude_md(content, tmpdir)
        expected = os.path.join(tmpdir, "CLAUDE.md")
        assert saved == expected
        with open(expected, encoding="utf-8") as f:
            assert f.read() == content
