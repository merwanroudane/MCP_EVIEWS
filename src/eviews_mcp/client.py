"""The public Python API for driving EViews.

This is the layer intended for direct use in scripts and notebooks::

    from eviews_mcp import EViews

    with EViews() as ev:
        ev.create_workfile("q", "1990q1", "2020q4")
        ev.run("series x = @nrnd")
        ev.run("equation eq1.ls y c x")
        print(ev.show("eq1"))
        print(ev.value("eq1.@r2"))

The MCP server in :mod:`eviews_mcp.server` is a thin adapter over this class,
so anything the server can do is available here too.
"""

from __future__ import annotations

import pathlib
import uuid
from typing import Any, Iterable, Sequence

from .render import render_series_columns, render_table, to_csv
from .results import (
    coefficient_block,
    stat_pairs,
    unit_root_block,
)
from .session import EViewsError, EViewsSession, session

__all__ = ["EViews", "EViewsError"]

_FREEZE_PREFIX = "mcp_frz_"
_HELPER_PREFIX = "mcp_tmp_"

#: Writes default to the whole page rather than the current sample. EViews
#: honours the active sample on writes, so a restricted sample would silently
#: drop values outside it and leave them NA -- a trap worth defaulting away
#: from. Pass ``sample=""`` to deliberately use the current sample instead.
WHOLE_PAGE = "@all"

#: Formats confirmed to work with an object's ``save`` procedure. EViews
#: accepts "svg" without complaint but writes nothing, so it is left out
#: deliberately rather than by oversight.
SAVE_FORMATS = frozenset({
    "png", "jpg", "pdf", "emf", "wmf", "bmp", "gif", "eps", "tex",  # graphs
    "csv", "rtf", "txt", "html",                                    # tables
})


def _quote(path: Any) -> str:
    return '"%s"' % str(path).replace('"', "")


def _quote_path(path: Any) -> str:
    """Quote a filesystem path, made absolute first.

    EViews resolves a relative path against its own working directory, not the
    calling process's, so a caller asking for ``"out.png"`` would otherwise
    find the file somewhere unexpected. Absolute paths remove the ambiguity.
    """
    return _quote(pathlib.Path(path).expanduser().resolve())


def _quote_dest(path: Any) -> str:
    """Quote a path to write to, creating its folder if it is missing.

    EViews will not create a directory on the way to a file: it stops with
    "Path ... does not exist". Since the caller asking to save into
    ``reports/figures/fit.png`` plainly means for the file to end up there,
    the folder is made first.
    """
    target = pathlib.Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    return _quote(target)


class EViews:
    """A live EViews application.

    Parameters
    ----------
    visible:
        Show the EViews window. Hidden by default, which is what you want for
        unattended work.
    session_object:
        Supply an existing :class:`~eviews_mcp.session.EViewsSession`. Mostly
        useful for testing; by default the process-wide session is shared.
    """

    def __init__(self, visible: bool = False,
                 session_object: EViewsSession | None = None) -> None:
        self._session = session_object or session()
        self._session.app(visible=visible)

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "EViews":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def close(self) -> None:
        """Release EViews. The instance shuts down with the client."""
        self._session.close()

    def reset(self) -> str:
        """Abandon this instance and attach to a brand new one."""
        return self._session.reset()

    def set_visible(self, visible: bool = True) -> None:
        self._session.set_visible(visible)

    @property
    def version(self) -> str:
        """EViews version number, e.g. ``"13.0"``."""
        try:
            return str(self._session.get("=@vernum"))
        except EViewsError:
            return "unknown"

    @property
    def session(self) -> EViewsSession:
        """The underlying COM session, for calls this class does not wrap."""
        return self._session

    def status(self) -> dict:
        """Connection and workfile state as a dictionary."""
        info: dict[str, Any] = {
            "connected": False,
            "progid": self._session.progid,
            "version": None,
            "workfile": None,
            "scratch_dir": str(self._session.workdir),
        }
        try:
            self._session.get("=1")
            info["connected"] = True
            info["version"] = self.version
        except EViewsError:
            return info
        try:
            info["workfile"] = self.workfile_info()
        except EViewsError:
            info["workfile"] = None
        return info

    # -- workfiles ----------------------------------------------------------

    def create_workfile(self, frequency: str, start: str = "", end: str = "",
                        name: str = "untitled", observations: int = 0,
                        page: str = "") -> str:
        """Create a workfile page and make it active.

        ``frequency`` is an EViews frequency code: ``a`` annual, ``q``
        quarterly, ``m`` monthly, ``d`` daily, ``u`` undated. Give ``start``
        and ``end`` for a dated page, or ``observations`` for an undated one.
        """
        freq = frequency.strip()
        if not freq:
            raise ValueError("A frequency is required, e.g. 'q' or 'u'.")
        if freq.lower() in ("u", "undated", "unstructured") and observations > 0:
            span = "1 %d" % observations
        elif start and end:
            span = "%s %s" % (start, end)
        elif observations > 0:
            span = "1 %d" % observations
        else:
            raise ValueError("Provide either start and end, or observations.")
        command = "wfcreate(wf=%s%s) %s %s" % (
            name, ", page=%s" % page if page else "", freq, span)
        self._session.run(command)
        return span

    def open_workfile(self, path: str | pathlib.Path) -> None:
        target = pathlib.Path(path)
        if not target.exists():
            raise FileNotFoundError(str(target))
        self._session.run("wfopen %s" % _quote_path(target))

    def save_workfile(self, path: str | pathlib.Path | None = None) -> None:
        if path:
            self._session.run("wfsave %s" % _quote_dest(path))
        else:
            self._session.run("wfsave")

    def close_workfile(self) -> None:
        """Close the active workfile, discarding unsaved changes."""
        self._session.run("wfclose")

    def close_all_workfiles(self, limit: int = 200) -> int:
        """Close every open workfile and return how many were closed.

        EViews caps the number of workfiles open at once, and a long-running
        session that keeps creating them will eventually refuse to make another
        with "Maximum number of Workfiles are already open". Calling this
        between pieces of work keeps that from happening.
        """
        closed = 0
        while closed < limit:
            try:
                self._session.run("wfclose")
            except EViewsError:
                break
            closed += 1
        return closed

    def workfile_info(self) -> dict:
        """Name, page, frequency, range, sample and object count."""
        get = self._session.get
        info = {
            "name": get("=@wfname"),
            "page": get("=@pagename"),
            "frequency": get("=@pagefreq"),
            "range": get("=@pagerange"),
            "sample": get("=@pagesmpl"),
        }
        for key, expr in (("obs_range", "=@obsrange"), ("obs_sample", "=@obssmpl")):
            try:
                info[key] = int(get(expr))
            except EViewsError:
                info[key] = None
        try:
            info["objects"] = len(self.list_objects())
        except EViewsError:
            info["objects"] = None
        return info

    def list_objects(self, pattern: str = "*", object_type: str = "") -> list[str]:
        return [str(n) for n in self._session.lookup(pattern or "*", object_type)]

    def exists(self, name: str) -> bool:
        """Whether an object of that name exists in the active page."""
        try:
            return bool(self._session.get('=@isobject("%s")' % name.strip()))
        except EViewsError:
            return False

    def set_sample(self, sample: str) -> str:
        self._session.run("smpl %s" % sample)
        return str(self._session.get("=@pagesmpl"))

    def delete(self, name: str) -> None:
        self._session.run("delete %s" % name)

    # -- running code -------------------------------------------------------

    def run(self, code: str, keep_program: bool = False) -> list[str]:
        """Run a block of EViews program code.

        The code is executed as a program file, so the full program language is
        available: control variables, loops, conditionals and subroutines.
        Raises :class:`EViewsError` with the failing line number on error.

        Returns the names of objects that appeared in the workfile as a result.
        """
        if not code.strip():
            raise ValueError("No code supplied.")
        program = self._session.workdir / ("mcp_%s.prg" % uuid.uuid4().hex[:12])
        program.write_text(code if code.endswith("\n") else code + "\n",
                           encoding="utf-8")
        try:
            before = set(self.list_objects())
        except EViewsError:
            before = set()  # no workfile yet; the program may create one
        try:
            self._session.run("run %s" % _quote(program))
        finally:
            if not keep_program:
                program.unlink(missing_ok=True)
        try:
            return sorted(set(self.list_objects()) - before)
        except EViewsError:
            return []

    def command(self, command_line: str) -> None:
        """Execute a single command line outside of a program."""
        if not command_line.strip():
            raise ValueError("No command supplied.")
        self._session.run(command_line.strip())

    def run_file(self, path: str | pathlib.Path, arguments: str = "") -> None:
        """Run an existing ``.prg`` file, optionally with program arguments."""
        target = pathlib.Path(path)
        if not target.exists():
            raise FileNotFoundError(str(target))
        command = "run %s" % _quote_path(target)
        if arguments.strip():
            command += " " + arguments.strip()
        self._session.run(command)

    # -- results ------------------------------------------------------------

    def table(self, object_name: str, view: str = "") -> tuple:
        """Freeze an object and return its table as raw rows.

        Values keep full double precision. Use :meth:`show` for a formatted
        string instead.
        """
        name = object_name.strip()
        if not name:
            raise ValueError("Provide an object name.")
        spec = "%s.%s" % (name, view.strip()) if view.strip() else name
        frozen = _FREEZE_PREFIX + uuid.uuid4().hex[:8]
        self._session.run("freeze(%s) %s" % (frozen, spec))
        try:
            return self._session.get(frozen)
        finally:
            self._quiet_delete(frozen)

    def show(self, object_name: str, view: str = "", digits: int = 6) -> str:
        """Render an object as aligned text. This is how results are read.

        ``view`` selects an alternative view, written without the leading dot,
        for example ``"resids"``, ``"stats"``, ``"uroot"`` or
        ``"wald c(2)=0"``.

        Most views freeze into a table, which is read directly. Some -- the
        ARDL cointegrating relationship and error-correction results among
        them -- freeze into a spool, which cannot be read over COM at all; for
        those the frozen object is written out as text and returned instead.
        Graph views produce neither, so use :meth:`export_object` for those.
        """
        name = object_name.strip()
        if not name:
            raise ValueError("Provide an object name.")
        spec = "%s.%s" % (name, view.strip()) if view.strip() else name
        frozen = _FREEZE_PREFIX + uuid.uuid4().hex[:8]
        self._session.run("freeze(%s) %s" % (frozen, spec))
        try:
            try:
                body = render_table(self._session.get(frozen), digits)
            except EViewsError:
                body = self._frozen_as_text(frozen)
        finally:
            self._quiet_delete(frozen)
        return "%s\n%s\n%s" % (spec, "-" * min(len(spec) + 8, 60), body)

    def _frozen_as_text(self, frozen: str) -> str:
        """Read a frozen object that Get cannot handle, such as a spool."""
        dump = self._session.workdir / ("mcp_%s.txt" % uuid.uuid4().hex[:8])
        try:
            self._session.run('%s.save(t=txt) %s' % (frozen, _quote(dump)))
        except EViewsError as exc:
            raise EViewsError(
                "This view produced an object that cannot be read as text "
                "(%s). If it is a graph, use export_object to save it to a "
                "file." % exc) from None
        if not dump.exists():
            raise EViewsError(
                "This view produced no readable table. If it is a graph, use "
                "export_object to save it to a file.")
        try:
            raw = dump.read_text(encoding="utf-8", errors="replace")
        finally:
            dump.unlink(missing_ok=True)
        return _tidy_text_dump(raw)

    def value(self, expression: str) -> Any:
        """Evaluate an expression and return a number or string.

        Examples: ``"eq1.@r2"``, ``"eq1.@coefs(2)"``, ``"@mean(gdp)"``.
        """
        expr = expression.strip()
        if not expr:
            raise ValueError("Provide an expression.")
        if not expr.startswith("="):
            expr = "=" + expr
        return self._session.get(expr)

    def describe(self, name: str) -> dict:
        """Type of an object, plus summary statistics when it is a series."""
        target = name.strip()
        if not self.exists(target):
            raise EViewsError("No object named '%s' in the active page." % target)
        info: dict[str, Any] = {"name": target, "type": None}
        kinds = ("series", "alpha", "equation", "group", "matrix", "vector",
                 "scalar", "string", "table", "graph", "var", "model", "coef",
                 "sym", "system", "pool", "spool", "text", "sspace", "logl",
                 "valmap", "link", "sample", "factor", "rowvector")
        upper = target.upper()
        for kind in kinds:
            try:
                if any(str(n).upper() == upper
                       for n in self._session.lookup(target, kind)):
                    info["type"] = kind
                    break
            except EViewsError:
                continue
        if info["type"] in ("series", "alpha"):
            for key, expr in (("obs", "@obs(%s)"), ("mean", "@mean(%s)"),
                              ("sd", "@stdev(%s)"), ("min", "@min(%s)"),
                              ("max", "@max(%s)")):
                try:
                    info[key] = self._session.get("=" + expr % target)
                except EViewsError:
                    break
        return info

    # -- structured results --------------------------------------------------

    def coefficients(self, equation: str) -> list[dict]:
        """Estimated coefficients as a list of dictionaries.

        Each entry carries ``variable``, ``coefficient``, ``std_error``,
        ``t_stat`` and ``p_value`` at full precision -- the numbers rather than
        the layout, for building your own tables.
        """
        found = coefficient_block(self.table(equation))
        if not found:
            raise EViewsError(
                "No coefficient block found in '%s'. Is it an estimated "
                "object?" % equation)
        return found

    def fit(self, equation: str) -> dict:
        """Summary statistics beneath an estimation: R-squared, AIC, DW, ..."""
        stats = stat_pairs(self.table(equation))
        if not stats:
            raise EViewsError("No summary statistics found in '%s'." % equation)
        return stats

    def unit_root(self, series: str, options: str = "", max_diff: int = 2,
                  alpha: float = 0.05) -> dict:
        """Test a series for a unit root, differencing until it is stationary.

        Runs the test on the levels and then on successive differences, and
        reports the order of integration as the first difference at which the
        unit root null is rejected.

        ``options`` is passed through to the EViews view, so the default
        augmented Dickey-Fuller test can be swapped for another -- ``"pp"`` for
        Phillips-Perron, ``"kpss"`` for KPSS -- or given deterministics, as in
        ``"adf, trend"``. Note that KPSS reverses the null, so the order
        reported here does not apply to it.

        The verdict is a mechanical reading of the p-values at ``alpha``. It is
        not a substitute for looking at the series: structural breaks, seasonal
        behaviour and short samples all mislead these tests.
        """
        name = series.strip()
        steps: list[dict] = []
        order: int | None = None

        for d in range(0, max(0, max_diff) + 1):
            parts = [options.strip()] if options.strip() else []
            if d:
                parts.append("dif=%d" % d)
            view = "uroot(%s)" % ", ".join(parts) if parts else "uroot"

            block = unit_root_block(self.table(name, view))
            probability = block.get("p_value")
            rejected = probability is not None and probability < alpha
            block.update({
                "difference": d,
                "view": view,
                "stationary": rejected,
            })
            steps.append(block)
            if rejected:
                order = d
                break

        return {
            "series": name.upper(),
            "alpha": alpha,
            "steps": steps,
            "order_of_integration": order,
            "conclusion": (
                "I(%d)" % order if order is not None
                else "no rejection through %d difference(s)" % max_diff),
        }

    def diagnose(self, equation: str, lags: int = 2, alpha: float = 0.05) -> dict:
        """Run the standard post-estimation battery and report each outcome.

        Covers residual serial correlation (Breusch-Godfrey), heteroskedasticity
        (White) and normality (Jarque-Bera), alongside the fit statistics. Each
        test reports its statistic, p-value, and whether its null is rejected at
        ``alpha``.

        Every number comes from EViews. The wording attached to each result is
        only a reading of the p-value, and passing a battery does not make a
        specification correct.
        """
        name = equation.strip()
        report: dict[str, Any] = {"equation": name.upper(), "alpha": alpha,
                                  "tests": [], "skipped": [], "fit": {}}

        try:
            report["fit"] = self.fit(name)
        except EViewsError:
            report["fit"] = {}

        def record(label: str, null: str, stats: dict, stat_key: str,
                   prob_key: str, when_rejected: str, when_not: str) -> None:
            statistic = stats.get(stat_key)
            probability = None
            for key, value in stats.items():
                if key.lower().startswith(prob_key.lower()):
                    probability = value
                    break
            if statistic is None or probability is None:
                return
            rejected = probability < alpha
            report["tests"].append({
                "test": label,
                "null": null,
                "statistic": statistic,
                "p_value": probability,
                "rejected": rejected,
                "reading": when_rejected if rejected else when_not,
            })

        def skip(label: str, exc: BaseException) -> None:
            report["skipped"].append({"test": label, "reason": str(exc)})

        try:
            record("Breusch-Godfrey serial correlation",
                   "no serial correlation up to %d lags" % lags,
                   stat_pairs(self.table(name, "auto(%d)" % lags)),
                   "F-statistic", "Prob. F",
                   "serial correlation present; standard errors are unreliable",
                   "no evidence of serial correlation")
        except EViewsError as exc:
            skip("Breusch-Godfrey serial correlation", exc)

        try:
            record("White heteroskedasticity",
                   "homoskedasticity",
                   stat_pairs(self.table(name, "white")),
                   "F-statistic", "Prob. F",
                   "heteroskedasticity present; consider robust standard errors",
                   "no evidence of heteroskedasticity")
        except EViewsError as exc:
            skip("White heteroskedasticity", exc)

        helper = _HELPER_PREFIX + uuid.uuid4().hex[:6]
        try:
            self._session.run("%s.makeresid %s" % (name, helper))
            stats = stat_pairs(self.table(helper, "stats"))
            record("Jarque-Bera normality", "residuals are normal", stats,
                   "Jarque-Bera", "Probability",
                   "residuals depart from normality",
                   "no evidence against normal residuals")
        except EViewsError as exc:
            skip("Jarque-Bera normality", exc)
        finally:
            self._quiet_delete(helper)

        failures = [t["test"] for t in report["tests"] if t["rejected"]]
        ran = len(report["tests"])
        if failures:
            summary = ("%d of %d diagnostics reject: %s."
                       % (len(failures), ran, ", ".join(failures)))
        elif ran:
            summary = "All %d diagnostics pass at the %g level." % (ran, alpha)
        else:
            summary = "No diagnostics could be run."
        if report["skipped"]:
            summary += (" %d could not be run: %s."
                        % (len(report["skipped"]),
                           ", ".join(s["test"] for s in report["skipped"])))
        report["summary"] = summary
        return report

    # -- data ---------------------------------------------------------------

    def obs_labels(self, count: int | None = None) -> list[str] | None:
        """Observation labels for the active page, or None if unavailable."""
        helper = _HELPER_PREFIX + uuid.uuid4().hex[:6]
        try:
            self._session.run("alpha %s = @otod(@obsnum)" % helper)
            raw = self._session.get(helper, na_as_string=True)
        except EViewsError:
            self._quiet_delete(helper)
            return None
        self._quiet_delete(helper)
        labels = []
        for row in raw or ():
            value = row[0] if isinstance(row, (tuple, list)) else row
            labels.append("" if value is None else str(value))
        if not labels:
            return None
        return labels[:count] if count else labels

    def get_series(self, name: str, sample: str = "") -> list:
        """One series as a flat list of floats, with None for NA."""
        return list(self._session.get_series(name, sample))

    def get_data(self, names: Sequence[str] | str, sample: str = "") -> tuple:
        """Several series as rows of tuples, one row per observation."""
        wanted = names.split() if isinstance(names, str) else list(names)
        if not wanted:
            raise ValueError("Provide at least one series name.")
        if len(wanted) == 1:
            return tuple((v,) for v in self._session.get_series(wanted[0], sample))
        return self._session.get_group(" ".join(wanted), sample)

    def read_text(self, names: Sequence[str] | str, sample: str = "",
                  max_rows: int = 200, digits: int = 6) -> str:
        """Series values rendered as an aligned table."""
        wanted = names.split() if isinstance(names, str) else list(names)
        rows = self.get_data(wanted, sample)
        labels = self.obs_labels(len(rows))
        return render_series_columns(wanted, rows, labels, digits=digits,
                                     max_rows=max_rows)

    def read_csv(self, names: Sequence[str] | str, sample: str = "") -> str:
        """Series values as full-precision CSV text."""
        wanted = names.split() if isinstance(names, str) else list(names)
        rows = self.get_data(wanted, sample)
        return to_csv(wanted, rows, self.obs_labels(len(rows)))

    def put_series(self, name: str, values: Iterable, sample: str = WHOLE_PAGE,
                   overwrite: bool = True) -> int:
        """Write values into a series.

        Writes cover the whole page by default. EViews honours the active
        sample on writes, so under a restricted sample the values outside it
        would be left NA without any error.
        """
        payload = [None if v is None else float(v) for v in values]
        if not payload:
            raise ValueError("No values supplied.")
        self._session.put_series(name.strip(), payload, sample, overwrite)
        return len(payload)

    def put_data(self, names: Sequence[str] | str, rows: Iterable[Sequence],
                 sample: str = WHOLE_PAGE, overwrite: bool = True) -> int:
        """Write several series at once from rows of values."""
        wanted = names.split() if isinstance(names, str) else list(names)
        payload = [[None if v is None else float(v) for v in row] for row in rows]
        if not payload:
            raise ValueError("No rows supplied.")
        self._session.put_group(" ".join(wanted), payload, sample, overwrite)
        return len(payload)

    # -- pandas -------------------------------------------------------------

    def to_dataframe(self, names: Sequence[str] | str | None = None,
                     sample: str = ""):
        """Read series into a pandas DataFrame indexed by observation label.

        Requires pandas, which is an optional dependency.
        """
        pandas = _require_pandas()
        wanted = (self.list_objects("*", "series")
                  if names is None
                  else (names.split() if isinstance(names, str) else list(names)))
        if not wanted:
            raise EViewsError("No series to read.")
        rows = self.get_data(wanted, sample)
        frame = pandas.DataFrame(list(rows), columns=[n.upper() for n in wanted])
        labels = self.obs_labels(len(frame))
        if labels and len(labels) >= len(frame):
            frame.index = labels[: len(frame)]
            frame.index.name = "obs"
        return frame

    def from_dataframe(self, frame, frequency: str = "", start: str = "",
                       end: str = "", create: bool = True,
                       sample: str = WHOLE_PAGE) -> list[str]:
        """Write a pandas DataFrame into the workfile, one series per column.

        When no workfile is open, or the open page is too short, a page sized
        to the frame is created first.

        The page is dated when it can be: give ``frequency`` with ``start`` and
        ``end`` explicitly, or simply hand over a frame with a DatetimeIndex or
        PeriodIndex and the endpoints are taken from it. Failing both, an
        undated page of the right length is used.

        Non-numeric columns are skipped rather than failing the whole frame.
        """
        _require_pandas()
        rows = len(frame)
        if rows == 0:
            raise ValueError("The frame is empty.")

        span = _dates_from_index(frame, frequency, start, end)
        if span:
            # A dated frame governs the page outright. Reusing a page whose
            # span differs would silently land the values on the wrong dates,
            # which is far worse than creating the right page.
            freq, first, last = span
            try:
                matches = (str(self._session.get("=@pagefreq")).upper()
                           == freq.upper()
                           and str(self._session.get("=@pagerange")).upper()
                           == ("%s %s" % (first, last)).upper())
            except EViewsError:
                matches = False
            if not matches:
                if not create:
                    raise EViewsError(
                        "The open page does not cover %s to %s; pass "
                        "create=True to build one that does." % (first, last))
                self.create_workfile(freq, start=first, end=last,
                                     name="frompandas")
        else:
            try:
                needs_page = int(self._session.get("=@obsrange")) < rows
            except EViewsError:
                needs_page = True
            if needs_page:
                if not create:
                    raise EViewsError(
                        "No workfile large enough is open; pass create=True.")
                self.create_workfile("u", observations=rows, name="frompandas")

        written: list[str] = []
        for column in frame.columns:
            series = frame[column]
            try:
                values = [None if _is_missing(v) else float(v) for v in series]
            except (TypeError, ValueError):
                continue  # not numeric; skip rather than fail the whole frame
            name = _clean_name(str(column))
            self._session.put_series(name, values, sample, True)
            written.append(name)
        if not written:
            raise EViewsError("No numeric columns to write.")
        return written

    # -- files --------------------------------------------------------------

    def import_file(self, path: str | pathlib.Path, options: str = "",
                    into_current_page: bool = False) -> list[str]:
        """Read an external data file (xlsx, csv, dta, sav, ...) into EViews.

        By default the file is opened as a new workfile sized to the data.
        That is deliberate: importing into whatever page happens to be open
        makes EViews truncate the file to the page length, so a 100-row file
        read into an open 12-row page would quietly lose 88 rows and the
        analysis that followed would be wrong with no warning anywhere.

        Pass ``into_current_page=True`` to merge into the active page instead,
        which is the right choice when adding variables to data already loaded.
        """
        target = pathlib.Path(path)
        if not target.exists():
            raise FileNotFoundError(str(target))

        verb = "wfopen"
        if into_current_page:
            try:
                self._session.get("=@wfname")
                verb = "import"
            except EViewsError:
                verb = "wfopen"  # nothing open to merge into

        command = "%s%s %s" % (
            verb, "(%s)" % options.strip() if options.strip() else "",
            _quote_path(target))
        self._session.run(command)
        try:
            return self.list_objects("*", "series")
        except EViewsError:
            return []

    def export_data(self, names: Sequence[str] | str, path: str | pathlib.Path,
                    options: str = "") -> None:
        """Write series to a file; the extension selects the format."""
        wanted = names.split() if isinstance(names, str) else list(names)
        if not wanted:
            raise ValueError("Provide at least one series name.")
        self._session.run("wfsave%s %s @keep %s" % (
            "(%s)" % options.strip() if options.strip() else "",
            _quote_dest(path), " ".join(wanted)))

    def export_object(self, object_name: str, path: str | pathlib.Path,
                      view: str = "", file_format: str = "") -> pathlib.Path:
        """Save an object to disk. This is how graphs are retrieved.

        The format is taken from the file extension and passed to EViews
        explicitly, because ``save`` on its own ignores the extension and falls
        back to EMF for graphs regardless of what the filename says.

        Graph formats: png, jpg, pdf, emf, wmf, bmp, gif, eps, tex.
        Table formats: csv, rtf, txt, html, tex.
        """
        target = pathlib.Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        fmt = (file_format or target.suffix.lstrip(".")).lower()
        if fmt in ("jpeg",):
            fmt = "jpg"
        option = "(t=%s)" % fmt if fmt in SAVE_FORMATS else ""

        name = object_name.strip()
        temporary = None
        if view.strip():
            temporary = _FREEZE_PREFIX + uuid.uuid4().hex[:8]
            self._session.run("freeze(%s) %s.%s" % (temporary, name, view.strip()))
            name = temporary
        try:
            self._session.run("%s.save%s %s" % (name, option, _quote(target)))
        finally:
            if temporary:
                self._quiet_delete(temporary)

        if not target.exists():
            raise EViewsError(
                "EViews reported no error but wrote no file to %s. The format "
                "'%s' is probably not supported for this object type; try one "
                "of: %s." % (target, fmt, ", ".join(sorted(SAVE_FORMATS))))
        return target

    # -- internals ----------------------------------------------------------

    def _quiet_delete(self, name: str) -> None:
        try:
            self._session.run("delete %s" % name)
        except EViewsError:
            pass


def _tidy_text_dump(raw: str) -> str:
    """Clean up EViews text output written for a fixed-width page.

    The file is padded to a fixed column width and separated by long rules of
    equals signs, several in a row where the spool joins sections. Trailing
    padding goes, over-long rules are shortened, and repeated blank lines and
    rules are collapsed.
    """
    lines: list[str] = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        stripped = line.rstrip()
        if set(stripped.strip()) == {"="} and len(stripped.strip()) > 4:
            stripped = "-" * 60
        if not stripped and lines and not lines[-1]:
            continue
        if stripped.startswith("-" * 60) and lines and lines[-1].startswith("-" * 60):
            continue
        lines.append(stripped)
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) if lines else "(empty)"


def _require_pandas():
    try:
        import pandas
    except ImportError:  # pragma: no cover - depends on the environment
        raise EViewsError(
            "pandas is required for DataFrame support. "
            "Install it with: pip install eviews-mcp[pandas]"
        ) from None
    return pandas


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    return value != value  # NaN


def _clean_name(column: str) -> str:
    """Turn a DataFrame column label into a legal EViews object name."""
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in column.strip())
    if not cleaned:
        cleaned = "series"
    if cleaned[0].isdigit():
        cleaned = "s_" + cleaned
    return cleaned[:24]


#: pandas offset letters mapped to EViews frequency codes.
_PANDAS_TO_EVIEWS = {"A": "a", "Y": "a", "Q": "q", "M": "m", "W": "w", "D": "d"}


def eviews_date(stamp, frequency: str) -> str:
    """Format one timestamp the way EViews writes dates for that frequency."""
    freq = frequency.lower()[:1]
    if freq == "a":
        return "%d" % stamp.year
    if freq == "q":
        return "%dQ%d" % (stamp.year, (stamp.month - 1) // 3 + 1)
    if freq == "m":
        return "%dM%02d" % (stamp.year, stamp.month)
    return "%d/%d/%d" % (stamp.month, stamp.day, stamp.year)


def _dates_from_index(frame, frequency: str, start: str, end: str):
    """Work out (frequency, start, end) for a dated page, or None.

    Explicit arguments win. Otherwise a DatetimeIndex or PeriodIndex on the
    frame supplies both the frequency and the endpoints, which is the common
    case for time-series data already in pandas.
    """
    if frequency and start and end:
        return frequency, start, end

    pandas = _require_pandas()
    index = getattr(frame, "index", None)
    if index is None or len(index) == 0:
        return None

    if isinstance(index, pandas.PeriodIndex):
        code = _PANDAS_TO_EVIEWS.get(str(index.freqstr)[:1].upper())
        if not code:
            return None
        first, last = index[0].to_timestamp(), index[-1].to_timestamp()
    elif isinstance(index, pandas.DatetimeIndex):
        letter = str(getattr(index, "freqstr", "") or "")[:1].upper()
        code = _PANDAS_TO_EVIEWS.get(letter) or (frequency[:1].lower()
                                                if frequency else None)
        if not code:
            return None
        first, last = index[0], index[-1]
    else:
        return None

    return (frequency[:1].lower() if frequency else code,
            start or eviews_date(first, code),
            end or eviews_date(last, code))
