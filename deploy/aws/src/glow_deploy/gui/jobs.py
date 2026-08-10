"""Background job execution for long-running provision()/update() calls.

FastAPI routes can't block on a 5-20 minute deploy, so work runs in a
ThreadPoolExecutor and progress is exposed for polling (via /jobs/{id}/status)
rather than a websocket/SSE connection.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from glow_deploy.errors import DeployError
from glow_deploy import core
from glow_deploy.gui.ansi import ansi_to_html


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending | running | succeeded | failed
    lines: list[str] = field(default_factory=list)
    error: str | None = None
    result: Any = None
    meta: dict = field(default_factory=dict)
    # Whether the last appended line ended with "\r" (inline) rather than "\n" —
    # mirrors the terminal sink: an inline message only overwrites the previous
    # line when that line was itself left "open" by a prior inline message.
    _last_inline: bool = field(default=False, repr=False)


class JobManager:
    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}

    def submit(self, fn: Callable[[], Any], meta: dict | None = None) -> str:
        job = Job(id=str(uuid.uuid4()), meta=meta or {})
        self._jobs[job.id] = job
        self._executor.submit(self._run, job, fn)
        return job.id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def has_running_jobs(self) -> bool:
        return any(job.status in ("pending", "running") for job in self._jobs.values())

    def _run(self, job: Job, fn: Callable[[], Any]) -> None:
        job.status = "running"
        token = core.set_progress_sink(
            lambda message, inline: self._append_line(job, message, inline)
        )
        try:
            job.result = fn()
            job.status = "succeeded"
        except DeployError as exc:
            job.error = ansi_to_html(str(exc))
            job.status = "failed"
        except Exception as exc:  # surface to the GUI instead of hanging the job forever
            job.error = ansi_to_html(str(exc))
            job.status = "failed"
        finally:
            core.reset_progress_sink(token)

    @staticmethod
    def _append_line(job: Job, message: str, inline: bool) -> None:
        html_message = ansi_to_html(message)
        if inline and job.lines and job._last_inline:
            job.lines[-1] = html_message
        else:
            job.lines.append(html_message)
        job._last_inline = inline
