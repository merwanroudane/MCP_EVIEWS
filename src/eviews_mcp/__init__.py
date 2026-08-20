"""Drive EViews from Python, and expose it to LLM clients over MCP.

Library use::

    from eviews_mcp import EViews

    with EViews() as ev:
        ev.create_workfile("q", "1990q1", "2020q4")
        ev.run("series x = @nrnd")
        ev.run("series y = 2 + 3*x + @nrnd")
        ev.run("equation eq1.ls y c x")
        print(ev.show("eq1"))

As an MCP server, run the console script ``eviews-mcp``.

Requires Windows and a local EViews installation, since it drives EViews over
COM. The names below are resolved lazily so that importing this package on
another platform, or without pywin32 present, still works for reading version
metadata and documentation.
"""

from __future__ import annotations

import sys
from typing import Any

__version__ = "1.3.2"
__author__ = "Merwan Roudane"
__all__ = ["EViews", "EViewsError", "EViewsSession", "connect", "__version__"]

_PLATFORM_HINT = (
    "eviews_mcp drives EViews through Windows COM, so it needs Windows with "
    "EViews installed and the pywin32 package available."
)


def __getattr__(name: str) -> Any:
    """Import the COM-backed names on first use (PEP 562)."""
    if name not in ("EViews", "EViewsError", "EViewsSession", "connect"):
        raise AttributeError("module %r has no attribute %r" % (__name__, name))
    try:
        from .client import EViews
        from .session import EViewsError, EViewsSession
    except ImportError as exc:
        if sys.platform != "win32":
            raise ImportError("%s (current platform: %s)"
                              % (_PLATFORM_HINT, sys.platform)) from exc
        raise ImportError("%s Original error: %s" % (_PLATFORM_HINT, exc)) from exc

    def connect(visible: bool = False) -> "EViews":
        """Connect to EViews, starting it if necessary."""
        return EViews(visible=visible)

    globals().update(
        EViews=EViews,
        EViewsError=EViewsError,
        EViewsSession=EViewsSession,
        connect=connect,
    )
    return globals()[name]
