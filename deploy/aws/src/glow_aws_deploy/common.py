from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[4]
AWS_DEPLOY_DIR = REPO_ROOT / "deploy" / "aws"
RUNNER_VERSION_PATH = "deploy/aws/runner/VERSION"

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class DeploymentError(RuntimeError):
    """Raised when deployment cannot continue safely."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


@dataclass(frozen=True)
class TerraformResult:
    outputs: dict[str, Any]


@dataclass(frozen=True)
class ResolvedGitRef:
    requested_ref: str
    resolved_ref: str
    commit_sha: str


@dataclass(frozen=True)
class DeploymentConfig:
    app_name: str
    aws_region: str
    domain_name: str
    certificate_arn: str
    git_repo_url: str
    git_ref: ResolvedGitRef
    runner_ami_version: str
    runner_instance_type: str
    runner_root_volume_size_gb: int
    data_volume_size_gb: int
    dry_run: bool
    force_rebuild: bool
    verbose: bool

    @property
    def backend_bucket_prefix(self) -> str:
        base = sanitize_bucket_component(self.domain_name)
        return f"{base}-glow-deploy-state"


class Console:
    def __init__(self, *, verbose: bool) -> None:
        self.verbose = verbose

    def step(self, message: str) -> None:
        print(f"[deploy] {message}", file=sys.stderr)

    def info(self, message: str) -> None:
        print(f"[deploy] {message}", file=sys.stderr)

    def warn(self, message: str) -> None:
        print(f"[deploy] WARNING: {message}", file=sys.stderr)

    def error(self, message: str) -> None:
        print(f"[deploy] ERROR: {message}", file=sys.stderr)

    def detail(self, message: str) -> None:
        if self.verbose:
            print(f"[deploy]   {message}", file=sys.stderr)


def require_command(command: str) -> None:
    if shutil_which(command):
        return
    raise DeploymentError(f"required command not found: {command}")


def shutil_which(command: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def sanitize_bucket_component(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9-]", "-", value.lower())
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    return sanitized or "glow"


def ensure_lines_tail(text: str, limit: int = 25) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-limit:])


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> CommandResult:
    completed = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    result = CommandResult(returncode=completed.returncode, stdout=(completed.stdout or "") + (completed.stderr or ""))
    if check and result.returncode != 0:
        tail = ensure_lines_tail(result.stdout)
        raise DeploymentError(f"command failed: {' '.join(args)}\n{tail}")
    return result


def run_live_command(
    console: Console,
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    label: str,
) -> CommandResult:
    process = subprocess.Popen(
        list(args),
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert process.stdout is not None

    q: queue.Queue[str | None] = queue.Queue()
    output: list[str] = []

    def pump() -> None:
        for line in process.stdout:
            q.put(line)
        q.put(None)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()

    last_elapsed = -1
    started = time.monotonic()
    stream_done = False

    while not stream_done or process.poll() is None:
        try:
            item = q.get(timeout=1)
        except queue.Empty:
            elapsed = int(time.monotonic() - started)
            if elapsed != last_elapsed and elapsed > 0 and elapsed % 10 == 0:
                console.info(f"{label} still running ({elapsed}s elapsed)")
                last_elapsed = elapsed
            continue

        if item is None:
            stream_done = True
            continue

        output.append(item)
        if console.verbose:
            console.info(item.rstrip())

    returncode = process.wait()
    combined = "".join(output)
    result = CommandResult(returncode=returncode, stdout=combined)
    if check and returncode != 0:
        raise DeploymentError(f"{label} failed\n{ensure_lines_tail(combined)}")
    return result


def validate_domain_name(domain_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain_name) or "." not in domain_name:
        raise DeploymentError(f"invalid domain name: {domain_name!r}")


def resolve_requested_git_ref(console: Console, repo_url: str, requested_ref: str) -> ResolvedGitRef:
    if requested_ref.strip():
        resolved = requested_ref.strip()
        sha = resolve_git_sha(repo_url, resolved)
        return ResolvedGitRef(requested_ref=resolved, resolved_ref=resolved, commit_sha=sha)

    tag = latest_release_tag(console, repo_url)
    sha = resolve_git_sha(repo_url, tag)
    return ResolvedGitRef(requested_ref="", resolved_ref=tag, commit_sha=sha)


def latest_release_tag(console: Console, repo_url: str) -> str:
    console.info("Resolving latest release tag")
    result = run_command(["git", "ls-remote", "--tags", "--sort=-version:refname", repo_url])
    for line in result.stdout.splitlines():
        if "refs/tags/" not in line or line.endswith("^{}"):
            continue
        _, ref_name = line.split("\t", 1)
        tag = ref_name.removeprefix("refs/tags/")
        return tag
    return "main"


def resolve_git_sha(repo_url: str, git_ref: str) -> str:
    if FULL_SHA_RE.fullmatch(git_ref):
        return git_ref
    result = run_command([
        "git",
        "ls-remote",
        repo_url,
        git_ref,
        f"refs/tags/{git_ref}",
        f"refs/heads/{git_ref}",
    ])
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, _ = line.split("\t", 1)
        return sha
    raise DeploymentError(f"git ref not found in remote repository: {git_ref}")


def github_raw_file_url(repo_url: str, commit_sha: str, repo_path: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.netloc != "github.com":
        raise DeploymentError("only public github.com repositories are supported by this deployment flow")
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    owner, repository = path.split("/", 1)
    return f"https://raw.githubusercontent.com/{owner}/{repository}/{commit_sha}/{repo_path}"


def fetch_text(url: str) -> str:
    try:
        with urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise DeploymentError(f"failed to fetch {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise DeploymentError(f"failed to fetch {url}: {exc.reason}") from exc


def resolve_runner_ami_version(repo_url: str, commit_sha: str) -> str:
    url = github_raw_file_url(repo_url, commit_sha, RUNNER_VERSION_PATH)
    return fetch_text(url).strip()


def enveloping_domain(domain_name: str) -> str:
    parts = domain_name.split(".")
    if len(parts) <= 2:
        return domain_name
    return ".".join(parts[1:])


def render_dns_instructions(
    *,
    domain_name: str,
    alb_dns_name: str,
    certificate_status: str,
    validation_records: Sequence[dict[str, str]] = (),
) -> str:
    owner = enveloping_domain(domain_name)
    validation_lines = [
        f"- `{record['name']}` {record['type']} `{record['value']}`"
        for record in validation_records
    ]

    app_lines = [
        f"- `{domain_name}` CNAME/ALIAS `{alb_dns_name}`",
        f"- `api.{domain_name}` CNAME `{alb_dns_name}`",
        f"- `odk.{domain_name}` CNAME `{alb_dns_name}`",
    ]

    warning = "The ACM certificate is issued, so the ALB can serve HTTPS as soon as these routing records point at it."
    if certificate_status != "ISSUED":
        warning = "The ACM certificate is not issued yet, so HTTPS will not work until the validation records are added and ACM finishes issuing the certificate."

    lines = [
        f"Ask the owner of `{owner}` to create these DNS records:",
        "",
    ]

    if validation_lines:
        lines.extend([
            "Certificate validation records:",
            *validation_lines,
            "",
        ])

    lines.extend([
            "Application routing records:",
            *app_lines,
            "",
            "Notes:",
            "- The dashboard/root record can use CNAME when this is a delegated subdomain.",
            f"- If `{domain_name}` is a zone apex at the external DNS provider, they may need provider-specific ALIAS/ANAME support instead of a plain CNAME.",
            f"- Current ACM status: {certificate_status}",
            f"- {warning}",
        ]
    )

    return "\n".join(lines)


def render_certificate_setup_instructions(
    *,
    domain_name: str,
    certificate_arn: str,
    validation_records: Sequence[dict[str, str]],
    certificate_status: str,
    dry_run: bool,
) -> str:
    owner = enveloping_domain(domain_name)
    lines = [
        f"No issued ACM certificate is available yet for `{domain_name}`.",
        f"Certificate ARN: `{certificate_arn}`",
        f"Current ACM status: {certificate_status}",
        "",
        f"Ask the owner of `{owner}` to create these certificate validation records:",
    ]
    lines.extend(
        f"- `{record['name']}` {record['type']} `{record['value']}`"
        for record in validation_records
    )
    lines.extend(
        [
            "",
            "The deployment requires an `ISSUED` ACM certificate before it can create the HTTPS ALB listeners.",
            "Run the deploy command again after ACM shows the certificate as `ISSUED`."
            if not dry_run
            else "Dry-run mode does not request or change infrastructure after certificate validation is missing.",
        ]
    )
    return "\n".join(lines)


def json_dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)
