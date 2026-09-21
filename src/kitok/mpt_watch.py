"""Bounded polling for an MPT task, shared by generation and regeneration."""
from __future__ import annotations

import time
from collections.abc import Callable

from .mpt_client import MPTError, TASK_STATE_COMPLETE, TASK_STATE_FAILED


class MPTTaskTimedOut(MPTError):
    pass


class MPTTaskStalled(MPTTaskTimedOut):
    pass


def wait_for_mpt_task(client, task_id: str, *, poll_seconds: float,
                      timeout_seconds: float, stall_seconds: float,
                      on_update: Callable) -> object:
    started = last_change = time.monotonic()
    previous = object()
    while True:
        task = client.get_task(task_id)
        now = time.monotonic()
        if task.state in (TASK_STATE_COMPLETE, TASK_STATE_FAILED):
            return task
        if task.progress != previous:
            previous = task.progress
            last_change = now
        on_update(task)
        unchanged = now - last_change
        detail = (f"task_id={task_id}, state={task.state}, progress={task.progress}, "
                  f"unchanged={unchanged:.0f}s, failed_stage={task.failed_stage}, error={task.error}")
        if now - started >= timeout_seconds:
            raise MPTTaskTimedOut(f"MPT task exceeded global timeout ({detail}); check MPT before retrying")
        if unchanged >= stall_seconds:
            raise MPTTaskStalled(f"MPT task progress stalled ({detail}); check MPT before retrying")
        time.sleep(poll_seconds)
