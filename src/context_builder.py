import sys
from pathlib import Path

CONTEXT_FILENAME = "CLAUDE.md"

_QUESTIONS = [
    ("purpose",    "What does this codebase do? (1-2 sentences)", False),
    ("components", "What are the main modules or components?",    False),
    ("stack",      "What language(s) and frameworks does it use?",False),
    ("notes",      "Any known issues, gotchas, or important context? (Enter to skip)", True),
]


def _ask(prompt: str, optional: bool) -> str:
    while True:
        try:
            ans = input(f"  {prompt}\n  > ").strip()
        except (EOFError, KeyboardInterrupt):
            return ""
        if ans or optional:
            return ans
        print("  (required — please provide an answer)")


def gather_context(repo_path: str) -> str:
    """Interactively ask the user about the codebase, save CLAUDE.md, return its content."""
    print("\n--- Codebase Context Setup ---")
    print("Answer a few questions so the assistant has context for this repo.")
    print("Answers are saved as CLAUDE.md in the repo root.\n")

    answers: dict[str, str] = {}
    for key, question, optional in _QUESTIONS:
        answers[key] = _ask(question, optional)

    lines = [
        "# Codebase Context",
        "",
        "## Purpose",
        answers["purpose"],
        "",
        "## Main Components",
        answers["components"],
        "",
        "## Stack",
        answers["stack"],
    ]
    if answers.get("notes"):
        lines += ["", "## Notes", answers["notes"]]

    content = "\n".join(lines) + "\n"
    context_path = Path(repo_path) / CONTEXT_FILENAME
    context_path.write_text(content, encoding="utf-8")
    print(f"\n  Context saved to {context_path}\n")
    return content


def load_context(repo_path: str) -> str | None:
    """Return contents of CLAUDE.md if it exists in repo_path, else None."""
    context_path = Path(repo_path) / CONTEXT_FILENAME
    if context_path.is_file():
        return context_path.read_text(encoding="utf-8")
    return None
