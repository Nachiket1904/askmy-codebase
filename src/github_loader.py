import re
import shutil
import tempfile

import git

_GITHUB_URL_RE = re.compile(r'^https://github\.com/[\w\-]+/[\w\-\.]+(/.*)?$')


def is_github_url(path: str) -> bool:
    return bool(_GITHUB_URL_RE.match(path))


def resolve_repo_path(path: str) -> tuple[str, bool]:
    if not is_github_url(path):
        return (path, False)

    tmp_dir = tempfile.mkdtemp(prefix="code_assistant_")
    try:
        git.Repo.clone_from(path, tmp_dir)
        return (tmp_dir, True)
    except git.exc.GitCommandError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        err = str(exc).lower()
        if any(word in err for word in ("authentication", "auth", "credential", "403", "not found", "repository not found")):
            raise ValueError(
                f"This repository is private. Please clone it manually:\n"
                f"  git clone {path}\n"
                f"Then run: python -m src.main --repo_path <local_folder>"
            ) from exc
        raise
