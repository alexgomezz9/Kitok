from __future__ import annotations

from collections.abc import Callable

from .base import LongformRenderer, RenderResult


class MptRenderer(LongformRenderer):
    """Thin adapter around the preserved MPT long-form implementation."""

    name = "mpt"

    def __init__(self, callback: Callable[..., object]):
        self.callback = callback

    def render(self, definition, *, start_over: bool = False) -> RenderResult:
        output = self.callback(definition, start_over=start_over)
        return RenderResult(output=output, renderer=self.name)
