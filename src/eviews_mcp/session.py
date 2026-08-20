"""COM session management for EViews 13.

All EViews interaction goes through a single dedicated thread that owns the
COM apartment. This matters: MCP dispatches synchronous tool functions on an
arbitrary worker thread, and a COM interface pointer obtained on one thread is
not valid on another unless it is marshalled. Funnelling every call onto one
apartment-initialised thread avoids that entirely, and has the useful side
effect of serialising access to EViews, which is single-user anyway.

The EViews process is owned by this client: when the server exits, the hidden
EViews instance it created shuts down with it.
"""

from __future__ import annotations

import atexit
import pathlib
import queue
import tempfile
import threading
from typing import Any, Callable

import pythoncom
import win32com.client

# CreateType enum from the EViews 13 type library.
CREATE_NEW = 0
CREATE_EXISTING_OR_NEW = 1
CREATE_EXISTING_ONLY = 2

# LookupReturnType
LOOKUP_STRING = 0
LOOKUP_ARRAY = 1

# NAType
NA_AS_EMPTY = 0
NA_AS_STRING = 1

# SeriesType / WriteType
SERIES_AUTO = 0
WRITE_UPDATE = 0
WRITE_OVERWRITE = 1

# Newest first. "EViews.Manager" resolves to the highest installed version.
PROGIDS = [
    "EViews.Manager",
    "EViews13.Manager",
    "EViews14.Manager",
    "EViews12.Manager",
    "EViews11.Manager",
]


class EViewsError(RuntimeError):
    """An error reported by EViews itself, with the message it produced."""


def com_message(exc: BaseException) -> str:
    """Pull the human-readable description out of a pywin32 com_error.

    A com_error carries (hresult, source, excepinfo, argerr) where
    excepinfo[2] holds the text EViews actually wrote, for example
    "SCALAR X is not defined ... in BAD.PRG on line 3." The outer part of the
    tuple is a localised OS string that carries no information, so it is
    discarded whenever a real description is present.
    """
    info = getattr(exc, "excepinfo", None)
    if isinstance(info, (tuple, list)) and len(info) > 2 and info[2]:
        return str(info[2]).strip()
    args = getattr(exc, "args", None)
    if isinstance(args, tuple) and len(args) > 2:
        inner = args[2]
        if isinstance(inner, (tuple, list)) and len(inner) > 2 and inner[2]:
            return str(inner[2]).strip()
    return str(exc)


def _short_workdir() -> pathlib.Path:
    """A scratch directory with a deliberately short path.

    Some EViews commands reject long paths outright ("Path exceeds maximum
    string length"), so generated program files are kept near the drive root
    when that is writable, falling back to the system temp directory.
    """
    candidates = [
        pathlib.Path("C:/ev_mcp"),
        pathlib.Path(tempfile.gettempdir()) / "evmcp",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_test"
            probe.write_text("", encoding="ascii")
            probe.unlink()
            return candidate
        except OSError:
            continue
    return pathlib.Path(tempfile.gettempdir())


class _ComThread:
    """Runs callables on one thread that has COM initialised."""

    def __init__(self) -> None:
        self._jobs: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="eviews-com"
        )
        self._thread.start()

    def _loop(self) -> None:
        pythoncom.CoInitialize()
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    return
                fn, args, kwargs, result_box, done = job
                try:
                    result_box.append(("ok", fn(*args, **kwargs)))
                except BaseException as exc:  # forwarded to the caller
                    result_box.append(("err", exc))
                finally:
                    done.set()
        finally:
            pythoncom.CoUninitialize()

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        box: list = []
        done = threading.Event()
        self._jobs.put((fn, args, kwargs, box, done))
        done.wait()
        kind, payload = box[0]
        if kind == "err":
            raise payload
        return payload

    def shutdown(self) -> None:
        self._jobs.put(None)


class EViewsSession:
    """A live connection to one EViews 13 application instance."""

    def __init__(self) -> None:
        self._com = _ComThread()
        self._app: Any = None
        self._progid: str | None = None
        self._visible = False
        self.workdir = _short_workdir()
        self._lock = threading.RLock()
        atexit.register(self.close)

    # -- connection ---------------------------------------------------------

    def _connect_impl(self, prefer_existing: bool, visible: bool) -> Any:
        create = CREATE_EXISTING_OR_NEW if prefer_existing else CREATE_NEW
        errors = []
        for progid in PROGIDS:
            try:
                manager = win32com.client.Dispatch(progid)
            except Exception as exc:
                errors.append("%s: %s" % (progid, com_message(exc)))
                continue
            try:
                app = manager.GetApplication(create, False)
            except Exception as exc:
                errors.append("%s.GetApplication: %s" % (progid, com_message(exc)))
                continue
            self._progid = progid
            if visible:
                try:
                    app.Show()
                except Exception:
                    pass
            return app
        raise EViewsError(
            "Could not start or attach to EViews. Checked: " + "; ".join(errors)
        )

    def app(self, visible: bool | None = None) -> Any:
        """Return the live application object, connecting on first use."""
        with self._lock:
            if self._app is not None and self._alive():
                return self._app
            want_visible = self._visible if visible is None else visible
            self._app = self._com.call(self._connect_impl, True, want_visible)
            self._visible = want_visible
            return self._app

    def _alive(self) -> bool:
        if self._app is None:
            return False
        try:
            # Cheap round trip that does not need a workfile to be open.
            self._com.call(self._app.Get, "=1", NA_AS_EMPTY, "NA")
            return True
        except Exception:
            self._app = None
            return False

    def close(self) -> None:
        with self._lock:
            self._app = None
        try:
            self._com.shutdown()
        except Exception:
            pass

    def reset(self) -> str:
        """Drop the current instance and attach to a brand new one."""
        with self._lock:
            self._app = None
            self._app = self._com.call(self._connect_impl, False, self._visible)
            return self._progid or "unknown"

    def set_visible(self, visible: bool) -> None:
        app = self.app()
        self._visible = visible
        self._com.call(app.Show if visible else app.Hide)

    @property
    def progid(self) -> str | None:
        return self._progid

    # -- primitives ---------------------------------------------------------

    def run(self, command: str) -> None:
        """Execute one EViews command line, raising EViewsError on failure."""
        app = self.app()
        try:
            self._com.call(app.Run, command)
        except Exception as exc:
            raise EViewsError(com_message(exc)) from None

    def get(self, expression: str, na_as_string: bool = False) -> Any:
        app = self.app()
        na = NA_AS_STRING if na_as_string else NA_AS_EMPTY
        try:
            return self._com.call(app.Get, expression, na, "NA")
        except Exception as exc:
            raise EViewsError(com_message(exc)) from None

    def lookup(self, pattern: str = "*", type_filter: str = "") -> tuple:
        app = self.app()
        try:
            result = self._com.call(app.Lookup, pattern, type_filter, LOOKUP_ARRAY)
        except Exception as exc:
            raise EViewsError(com_message(exc)) from None
        if result is None:
            return ()
        if isinstance(result, str):
            return tuple(result.split()) if result else ()
        return tuple(result)

    def get_series(self, name: str, sample: str = "") -> tuple:
        app = self.app()
        try:
            return self._com.call(app.GetSeries, name, sample, NA_AS_EMPTY, "NA")
        except Exception as exc:
            raise EViewsError(com_message(exc)) from None

    def get_group(self, names: str, sample: str = "") -> tuple:
        app = self.app()
        try:
            return self._com.call(app.GetGroup, names, sample, NA_AS_EMPTY, "NA")
        except Exception as exc:
            raise EViewsError(com_message(exc)) from None

    def put_series(
        self, name: str, values: list, sample: str = "", overwrite: bool = True
    ) -> None:
        app = self.app()
        write = WRITE_OVERWRITE if overwrite else WRITE_UPDATE
        try:
            self._com.call(app.PutSeries, name, values, sample, SERIES_AUTO, write)
        except Exception as exc:
            raise EViewsError(com_message(exc)) from None

    def put_group(
        self, names: str, rows: list, sample: str = "", overwrite: bool = True
    ) -> None:
        app = self.app()
        write = WRITE_OVERWRITE if overwrite else WRITE_UPDATE
        try:
            self._com.call(app.PutGroup, names, rows, sample, SERIES_AUTO, write)
        except Exception as exc:
            raise EViewsError(com_message(exc)) from None


_SESSION: EViewsSession | None = None
_SESSION_LOCK = threading.Lock()


def session() -> EViewsSession:
    """Process-wide EViews session, created on first use."""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            _SESSION = EViewsSession()
        return _SESSION
