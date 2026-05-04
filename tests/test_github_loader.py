import pytest
from unittest.mock import MagicMock, patch
from git.exc import GitCommandError


def test_local_path_passes_through_unchanged():
    from src.github_loader import resolve_repo_path
    result_path, is_temp = resolve_repo_path("/some/local/folder")
    assert result_path == "/some/local/folder"
    assert is_temp is False


def test_public_github_url_clones_to_temp_folder():
    url = "https://github.com/some-org/public-repo"
    fake_tmp = "/tmp/code_assistant_abc123"

    with patch("src.github_loader.tempfile.mkdtemp", return_value=fake_tmp), \
         patch("src.github_loader.git.Repo") as mock_repo_cls:

        mock_repo_cls.clone_from.return_value = MagicMock()

        from src.github_loader import resolve_repo_path
        result_path, is_temp = resolve_repo_path(url)

    mock_repo_cls.clone_from.assert_called_once_with(url, fake_tmp)
    assert result_path == fake_tmp
    assert is_temp is True


def test_private_github_url_exits_with_clear_message():
    url = "https://github.com/some-org/private-repo"
    fake_tmp = "/tmp/code_assistant_xyz789"

    auth_error = GitCommandError(
        "clone",
        128,
        stderr="remote: Repository not found.\nfatal: repository 'https://github.com/some-org/private-repo/' not found",
    )

    with patch("src.github_loader.tempfile.mkdtemp", return_value=fake_tmp), \
         patch("src.github_loader.git.Repo") as mock_repo_cls, \
         pytest.raises(ValueError) as exc_info:

        mock_repo_cls.clone_from.side_effect = auth_error

        from src.github_loader import resolve_repo_path
        resolve_repo_path(url)

    err_msg = str(exc_info.value).lower()
    assert "private" in err_msg
    assert "git clone" in err_msg
    assert url in err_msg
