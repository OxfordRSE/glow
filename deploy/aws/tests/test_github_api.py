import pytest

import glow_deploy.github_api as github_api


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 404:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get(self, path):
        return self._responses[path]


def _install_fake_responses(monkeypatch, responses):
    monkeypatch.setattr(
        github_api.httpx, "Client", lambda **kwargs: _FakeClient(responses)
    )


REPO = "https://github.com/OxfordRSE/glow.git"


def test_resolve_git_commit_via_github_short_circuits_a_full_sha():
    sha = "a" * 40
    assert github_api.resolve_git_commit_via_github(REPO, sha) == sha


def test_resolve_git_commit_via_github_prefers_peeled_annotated_tag_commit(
    monkeypatch,
):
    tag_object_sha = "1111111111111111111111111111111111111111"
    peeled_commit_sha = "2222222222222222222222222222222222222222"
    _install_fake_responses(
        monkeypatch,
        {
            "/repos/OxfordRSE/glow/git/ref/tags/v1.2.3": _FakeResponse(
                200, {"object": {"sha": tag_object_sha, "type": "tag"}}
            ),
            f"/repos/OxfordRSE/glow/git/tags/{tag_object_sha}": _FakeResponse(
                200, {"object": {"sha": peeled_commit_sha, "type": "commit"}}
            ),
        },
    )

    assert (
        github_api.resolve_git_commit_via_github(REPO, "v1.2.3") == peeled_commit_sha
    )


def test_resolve_git_commit_via_github_uses_lightweight_tag_commit_directly(
    monkeypatch,
):
    commit_sha = "3333333333333333333333333333333333333333"
    _install_fake_responses(
        monkeypatch,
        {
            "/repos/OxfordRSE/glow/git/ref/tags/v1.2.3": _FakeResponse(
                200, {"object": {"sha": commit_sha, "type": "commit"}}
            ),
        },
    )

    assert github_api.resolve_git_commit_via_github(REPO, "v1.2.3") == commit_sha


def test_resolve_git_commit_via_github_prefers_tag_over_branch_of_the_same_name(
    monkeypatch,
):
    tag_commit_sha = "4444444444444444444444444444444444444444"
    branch_commit_sha = "5555555555555555555555555555555555555555"
    _install_fake_responses(
        monkeypatch,
        {
            "/repos/OxfordRSE/glow/git/ref/tags/release": _FakeResponse(
                200, {"object": {"sha": tag_commit_sha, "type": "commit"}}
            ),
            "/repos/OxfordRSE/glow/git/ref/heads/release": _FakeResponse(
                200, {"object": {"sha": branch_commit_sha, "type": "commit"}}
            ),
        },
    )

    assert github_api.resolve_git_commit_via_github(REPO, "release") == tag_commit_sha


def test_resolve_git_commit_via_github_falls_back_to_branch_when_no_tag_matches(
    monkeypatch,
):
    branch_commit_sha = "6666666666666666666666666666666666666666"
    _install_fake_responses(
        monkeypatch,
        {
            "/repos/OxfordRSE/glow/git/ref/tags/main": _FakeResponse(404),
            "/repos/OxfordRSE/glow/git/ref/heads/main": _FakeResponse(
                200, {"object": {"sha": branch_commit_sha, "type": "commit"}}
            ),
        },
    )

    assert github_api.resolve_git_commit_via_github(REPO, "main") == branch_commit_sha


def test_resolve_git_commit_via_github_raises_when_ref_not_found(monkeypatch):
    _install_fake_responses(
        monkeypatch,
        {
            "/repos/OxfordRSE/glow/git/ref/tags/missing": _FakeResponse(404),
            "/repos/OxfordRSE/glow/git/ref/heads/missing": _FakeResponse(404),
        },
    )

    with pytest.raises(github_api.DeployError, match="could not resolve git ref"):
        github_api.resolve_git_commit_via_github(REPO, "missing")


@pytest.mark.parametrize(
    "repo_url,expected",
    [
        ("https://github.com/OxfordRSE/glow.git", ("OxfordRSE", "glow")),
        ("https://github.com/OxfordRSE/glow", ("OxfordRSE", "glow")),
        ("git@github.com:OxfordRSE/glow.git", ("OxfordRSE", "glow")),
    ],
)
def test_parse_owner_repo_handles_https_and_scp_style_urls(repo_url, expected):
    assert github_api._parse_owner_repo(repo_url) == expected


def test_parse_owner_repo_rejects_urls_without_a_repo_path():
    with pytest.raises(github_api.DeployError, match="could not parse owner/repo"):
        github_api._parse_owner_repo("https://github.com/OxfordRSE")
