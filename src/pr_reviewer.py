import re


def _split_diff(raw: str) -> dict[str, str]:
    chunks = {}
    current_file = None
    current_lines: list[str] = []
    for line in raw.splitlines(keepends=True):
        m = re.match(r"^diff --git a/(.+?) b/.+$", line)
        if m:
            if current_file:
                chunks[current_file] = "".join(current_lines)
            current_file = m.group(1)
            current_lines = [line]
        elif current_file:
            current_lines.append(line)
    if current_file:
        chunks[current_file] = "".join(current_lines)
    return chunks


def review_diff(diff_path: str, chain, repo_map: dict) -> dict:
    with open(diff_path, encoding="utf-8") as f:
        raw = f.read()

    file_chunks = _split_diff(raw)
    files_reviewed = list(file_chunks.keys())
    deviations = []

    _MAX_DIFF_CHARS = 8000
    for filename, chunk in file_chunks.items():
        safe_filename = re.sub(r"[^\w./\-]", "_", filename)[:200]
        safe_chunk = chunk[:_MAX_DIFF_CHARS] + ("...[truncated]" if len(chunk) > _MAX_DIFF_CHARS else "")
        question = (
            f"Review this git diff for `{safe_filename}`. "
            "Does it deviate from the existing patterns in the codebase? "
            "If yes, describe the issue and suggest a fix. "
            "If no deviations, reply with 'No deviations found.'\n\n"
            "<diff>\n"
            f"{safe_chunk}\n"
            "</diff>"
        )
        result = chain({"question": question, "chat_history": []})
        answer = result["answer"]
        if "no deviation" not in answer.lower():
            deviations.append({
                "file": filename,
                "issue": answer.split("\n")[0],
                "suggestion": answer,
            })

    if file_chunks:
        summary_q = (
            f"Summarize the overall code review of this PR which touched "
            f"{len(files_reviewed)} file(s): {', '.join(files_reviewed)}. "
            f"There were {len(deviations)} deviation(s) found. "
            "Give a one-paragraph assessment."
        )
        summary = chain({"question": summary_q, "chat_history": []})["answer"]
    else:
        summary = "No files found in diff."

    return {
        "files_reviewed": files_reviewed,
        "deviations": deviations,
        "summary": summary,
    }
