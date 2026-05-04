import os
from pathlib import Path

_QUESTIONS = [
    "Give a 2 sentence summary of what this codebase does",
    "What is the tech stack used in this project?",
    "List every file in src/ and what it does in one sentence each",
    "What are the most important functions a developer should know about?",
    "How do you run this project and its tests?",
    "Are there any known issues, gotchas or things to avoid?",
]

_SECTION_HEADERS = [
    "## Overview",
    "## Tech Stack",
    "## Source Files",
    "## Key Functions",
    "## Running the Project",
    "## Known Issues & Gotchas",
]


def generate_claude_md(repo_path: str, repo_map: dict, chain) -> str:
    repo_name = Path(repo_path).resolve().name
    sections = [f"# CLAUDE.md — {repo_name}\n"]

    for header, question in zip(_SECTION_HEADERS, _QUESTIONS):
        result = chain({"question": question, "chat_history": []})
        answer = result["answer"].strip()
        sections.append(f"{header}\n\n{answer}\n")

    return "\n".join(sections)


def save_claude_md(content: str, repo_path: str) -> str:
    dest = os.path.join(repo_path, "CLAUDE.md")
    Path(dest).write_text(content, encoding="utf-8")
    return dest
