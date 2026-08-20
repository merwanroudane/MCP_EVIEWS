"""MCP server exposing EViews to an LLM client.

Every tool here is a thin wrapper over :class:`eviews_mcp.client.EViews`, so
the server and the library never drift apart. Tools return plain text because
that is what a model reads best; the library returns real Python objects.

Two behaviours are worth knowing when reading this file:

* EViews reports failures by raising, with the offending command and, inside a
  program, the source line number. Those messages are passed through unchanged
  rather than being reworded.
* EViews sends program output to its own log window, which cannot be read over
  COM. Results are therefore obtained by freezing an object into a table and
  pulling that across, which is what ``show`` does.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from .client import EViews
from .session import EViewsError

mcp = FastMCP("eviews-mcp")

_CLIENT: EViews | None = None


def _client() -> EViews:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = EViews()
    return _CLIENT


def guard(fn: Callable[..., str]) -> Callable[..., str]:
    """Turn expected failures into readable text instead of a stack trace."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except EViewsError as exc:
            return "EViews error: %s" % exc
        except FileNotFoundError as exc:
            return "No such file: %s" % exc
        except ValueError as exc:
            return str(exc)

    return wrapper


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------


@mcp.tool()
@guard
def eviews_status() -> str:
    """Report whether EViews is reachable, and what the active workfile is.

    Start here when anything looks wrong. Connecting happens on demand, so a
    successful result also means the session is ready to use.
    """
    state = _client().status()
    if not state["connected"]:
        return "NOT CONNECTED to EViews."
    lines = [
        "Connected to EViews %s via %s" % (state["version"], state["progid"]),
        "Scratch directory: %s" % state["scratch_dir"],
    ]
    workfile = state.get("workfile")
    if not workfile:
        lines.append("Active workfile: none open "
                     "(use create_workfile or open_workfile)")
        return "\n".join(lines)
    lines.append("Active workfile: %s (page %s)" %
                 (workfile["name"], workfile["page"]))
    lines.append("Frequency: %s   Range: %s" %
                 (workfile["frequency"], workfile["range"]))
    lines.append("Current sample: %s" % workfile["sample"])
    lines.append("Objects: %s" % workfile["objects"])
    return "\n".join(lines)


@mcp.tool()
@guard
def reset_eviews() -> str:
    """Discard the current EViews instance and start a clean one.

    Anything unsaved is lost, so save first if the workfile matters. Use this
    when EViews has become unresponsive or is in a bad state.
    """
    global _CLIENT
    progid = _client().reset()
    _CLIENT = None
    return "Started a fresh EViews instance via %s. No workfile is open." % progid


@mcp.tool()
@guard
def set_eviews_visible(visible: bool = True) -> str:
    """Show or hide the EViews window.

    EViews runs hidden by default. Showing it lets the user inspect results and
    graphs interactively.
    """
    _client().set_visible(visible)
    return "EViews window is now %s." % ("visible" if visible else "hidden")


# --------------------------------------------------------------------------
# Workfiles
# --------------------------------------------------------------------------


@mcp.tool()
@guard
def create_workfile(frequency: str, start: str = "", end: str = "",
                    name: str = "untitled", observations: int = 0) -> str:
    """Create a new workfile page and make it active.

    frequency: an EViews frequency code -- "a" annual, "q" quarterly,
        "m" monthly, "d" daily, "u" undated.
    start, end: endpoints in EViews date notation, e.g. "1990q1" and "2020q4".
    observations: row count, for an undated workfile.

    Existing workfiles stay open; EViews simply switches which one is active.
    """
    span = _client().create_workfile(frequency, start, end, name, observations)
    return "Created workfile '%s' (%s, %s) and made it active." % (
        name, frequency, span)


@mcp.tool()
@guard
def open_workfile(path: str) -> str:
    """Open an existing EViews workfile (.wf1 or .wf2) and make it active."""
    _client().open_workfile(path)
    return "Opened %s." % path


@mcp.tool()
@guard
def save_workfile(path: str = "") -> str:
    """Save the active workfile, optionally to a new path.

    A workfile created in this session has no path yet, so one must be given
    the first time it is saved.
    """
    _client().save_workfile(path or None)
    return "Saved to %s." % path if path else "Workfile saved."


@mcp.tool()
@guard
def workfile_info() -> str:
    """Describe the active workfile: name, page, frequency, range and sample."""
    info = _client().workfile_info()
    order = ("name", "page", "frequency", "range", "sample",
             "obs_range", "obs_sample", "objects")
    labels = {
        "name": "Workfile", "page": "Page", "frequency": "Frequency",
        "range": "Page range", "sample": "Current sample",
        "obs_range": "Obs in range", "obs_sample": "Obs in sample",
        "objects": "Objects",
    }
    return "\n".join("%-15s %s" % (labels[k] + ":", info[k])
                     for k in order if info.get(k) is not None)


@mcp.tool()
@guard
def list_objects(pattern: str = "*", object_type: str = "") -> str:
    """List objects in the active workfile page.

    pattern: name pattern with wildcards, e.g. "*" or "gdp*".
    object_type: restrict to one EViews type such as "series", "equation",
        "group", "matrix", "table", "graph" or "var". Empty means every type.
    """
    names = _client().list_objects(pattern, object_type)
    suffix = " of type '%s'" % object_type if object_type else ""
    if not names:
        return "No objects match pattern '%s'%s." % (pattern, suffix)
    return ("%d object(s)%s:\n" % (len(names), suffix) +
            "\n".join("  " + n for n in names))


@mcp.tool()
@guard
def set_sample(sample: str) -> str:
    """Set the current sample, e.g. "1990q1 2010q4" or "@all".

    The sample governs every subsequent estimation and series calculation, and
    it also governs writes: values outside it are left untouched.
    """
    return "Sample set to %s." % _client().set_sample(sample)


# --------------------------------------------------------------------------
# Running code
# --------------------------------------------------------------------------


@mcp.tool()
@guard
def run_eviews_code(code: str, keep_program: bool = False) -> str:
    """Run a block of EViews program code. This is the main tool for analysis.

    The full EViews program language is available: control variables (!x),
    string variables (%s), for and while loops, if blocks and subroutines.

    Results are not echoed, because EViews sends program output to its own log
    window where it cannot be read. Estimate into a named object and then call
    show() on it, or pull single numbers out with evaluate(). For example:

        equation eq1.ls log(gdp) c log(k) log(l)

    then show("eq1").

    On failure EViews names the offending statement and the line number within
    the program.

    keep_program: leave the generated .prg on disk, useful when debugging.
    """
    created = _client().run(code, keep_program=keep_program)
    lines = ["Program ran successfully (%d line(s))." %
             len(code.strip().splitlines())]
    if created:
        lines.append("New objects: %s" % ", ".join(created))
        lines.append("Use show(<name>) to see results.")
    return "\n".join(lines)


@mcp.tool()
@guard
def run_program_file(path: str, arguments: str = "") -> str:
    """Run an existing EViews program file (.prg) from disk.

    arguments: whitespace-separated values passed to the program as %0, %1 and
        so on, exactly as EViews handles program arguments.
    """
    _client().run_file(path, arguments)
    return "Ran %s successfully." % path


@mcp.tool()
@guard
def command(command_line: str) -> str:
    """Execute a single EViews command line outside of a program.

    Prefer run_eviews_code for anything multi-line or using program features.
    This suits one-off commands such as "smpl @all" or "delete eq1".
    """
    _client().command(command_line)
    return "OK: %s" % command_line.strip()


# --------------------------------------------------------------------------
# Reading results
# --------------------------------------------------------------------------


@mcp.tool()
@guard
def show(object_name: str, view: str = "", digits: int = 6) -> str:
    """Render an EViews object as a text table. This is how results are read.

    object_name: the object to display, e.g. "eq1", "var1", "tab1".
    view: an optional view, written without the leading dot. Useful ones:
        "output"        estimation output (the default for an equation)
        "resids"        residual table
        "coefcov"       coefficient covariance matrix
        "wald c(2)=0"   coefficient restriction test
        "uroot"         unit root test on a series
        "stats"         descriptive statistics
        "correl"        correlogram
    digits: significant digits shown for numbers.

    Views that draw pictures cannot be returned as text; use export_object for
    those.
    """
    try:
        return _client().show(object_name, view, digits)
    except EViewsError as exc:
        return ("EViews error: %s\n"
                "(If this view produces a graph rather than a table, it cannot "
                "be shown as text; use export_object to write it to a file.)"
                % exc)


@mcp.tool()
@guard
def evaluate(expression: str) -> str:
    """Evaluate an EViews expression and return its value.

    Works for scalars, strings and object data members. Examples:
        "eq1.@r2"        R-squared
        "eq1.@coefs(2)"  second coefficient
        "eq1.@tstats(2)" its t-statistic
        "@mean(gdp)"     sample mean

    For a whole table of results use show() instead.
    """
    value = _client().value(expression)
    if isinstance(value, (tuple, list)):
        from .render import render_table
        return render_table(value)
    return str(value)


@mcp.tool()
@guard
def describe_object(name: str) -> str:
    """Report an object's EViews type, with summary statistics for a series."""
    info = _client().describe(name)
    lines = ["%s is a %s." % (info["name"], info["type"] or "(unknown type)")]
    for key, label in (("obs", "Observations"), ("mean", "Mean"),
                       ("sd", "Std. dev."), ("min", "Minimum"),
                       ("max", "Maximum")):
        if key in info:
            lines.append("  %-14s %s" % (label + ":", info[key]))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------


@mcp.tool()
@guard
def read_data(names: str, sample: str = "", output_format: str = "table",
              max_rows: int = 200) -> str:
    """Read series values out of the workfile.

    names: one or more series names separated by spaces, e.g. "gdp cpi".
    sample: sample to read, e.g. "2000q1 2010q4". Empty means the current one.
    output_format: "table" for an aligned readable view, or "csv" for
        full-precision values suitable for further processing.
    max_rows: row cap for table format; csv is never truncated.
    """
    client = _client()
    if output_format.lower() == "csv":
        return client.read_csv(names, sample)
    return client.read_text(names, sample, max_rows=max_rows)


@mcp.tool()
@guard
def write_series(name: str, values: str, sample: str = "@all",
                 overwrite: bool = True) -> str:
    """Write numeric values from the conversation into a workfile series.

    values: numbers separated by commas or whitespace. Use "NA" for a missing
        observation.
    sample: defaults to the whole page. EViews honours the sample on writes, so
        a restricted sample would leave values outside it as NA.

    For bulk data prefer import_data, which reads a file directly.
    """
    tokens = [t for t in values.replace(",", " ").split() if t]
    if not tokens:
        return "No values supplied."
    parsed: list = []
    for token in tokens:
        if token.upper() in ("NA", "N/A", "."):
            parsed.append(None)
        else:
            try:
                parsed.append(float(token))
            except ValueError:
                return "Could not read '%s' as a number." % token
    count = _client().put_series(name, parsed, sample, overwrite)
    return "Wrote %d value(s) into series %s." % (count, name)


@mcp.tool()
@guard
def import_data(path: str, options: str = "") -> str:
    """Read an external data file into the active workfile.

    Handles the formats EViews reads natively, including .xlsx, .xls, .csv,
    .txt, .dta, .sav and .rdata. When no workfile is open, one is created to
    fit the file.

    options: raw EViews options, e.g. "range=Sheet2" or "namepos=first".
    """
    found = _client().import_file(path, options)
    listing = ("\nSeries now present: %s" % ", ".join(found[:40])) if found else ""
    return "Imported %s.%s" % (path, listing)


@mcp.tool()
@guard
def export_data(names: str, path: str, options: str = "") -> str:
    """Write series from the workfile to a file on disk.

    names: series to export, separated by spaces. The file extension selects
    the format, e.g. .csv, .xlsx, .txt.
    options: raw EViews options, only needed when the extension is ambiguous.
    """
    _client().export_data(names, path, options)
    return "Exported %s to %s." % (names, path)


@mcp.tool()
@guard
def export_object(object_name: str, path: str, view: str = "",
                  file_format: str = "") -> str:
    """Save an object to a file. This is how graphs are retrieved.

    path: destination. The extension selects the format: png, jpg, pdf, emf,
        wmf, bmp, gif, eps or tex for graphs; csv, rtf, txt or html for tables.
    view: an optional view to freeze first, e.g. "line", "resids" or "correl".
    file_format: override the format when the extension does not imply it.

    A relative path is resolved against this process's directory, not the one
    EViews happens to be using.
    """
    written = _client().export_object(object_name, path, view, file_format)
    return "Saved %s to %s." % (object_name, written)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
