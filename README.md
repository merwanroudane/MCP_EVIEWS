# eviews-mcp

[![Tests](https://github.com/merwanroudane/MCP_EVIEWS/actions/workflows/tests.yml/badge.svg)](https://github.com/merwanroudane/MCP_EVIEWS/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/eviews-mcp?color=2c5f9e&label=PyPI)](https://pypi.org/project/eviews-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/eviews-mcp?color=2c5f9e)](https://pypi.org/project/eviews-mcp/)
[![Licence](https://img.shields.io/badge/licence-MIT-2c5f9e)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-2c5f9e)](https://pypi.org/project/eviews-mcp/)
[![EViews](https://img.shields.io/badge/EViews-10--14-c05621)](https://www.eviews.com)

Drive **EViews** from Python, and expose it to LLM clients over the Model
Context Protocol.

**[Documentation site](https://merwanroudane.github.io/MCP_EVIEWS/)** &nbsp;·&nbsp;
**[Researcher guide](https://github.com/merwanroudane/MCP_EVIEWS/blob/main/docs/EViews-Researcher-Guide.md)** &nbsp;·&nbsp;
**[PyPI](https://pypi.org/project/eviews-mcp/)**

Two things in one package:

- **A library.** An `EViews` class for scripts and notebooks — build workfiles,
  estimate models, read results back as text or pandas DataFrames.
- **An MCP server.** The same capabilities as tools, so an assistant can do
  econometrics in a real EViews session.

Built and tested against **EViews 13** on Windows; EViews 10–14 resolve
correctly through the same COM interface.

> **New to this?** The [**EViews Researcher Guide**](https://github.com/merwanroudane/MCP_EVIEWS/blob/main/docs/EViews-Researcher-Guide.md)
> takes you from a clean machine to a finished ARDL study, with every command and
> every output verified against a real EViews session. No Python knowledge assumed.

## Install

```bash
pip install eviews-mcp
```

With pandas support:

```bash
pip install "eviews-mcp[pandas]"
```

Or from a clone, for development:

```bash
git clone https://github.com/merwanroudane/MCP_EVIEWS.git
cd MCP_EVIEWS
pip install -e .[dev]
```

Requires Windows and a local EViews installation, since it drives EViews
through COM automation.

## Library use

```python
from eviews_mcp import EViews

with EViews() as ev:
    ev.create_workfile("q", "1990q1", "2020q4")
    ev.run("""
        series k   = 100 + @trend + 3*@nrnd
        series l   = 50 + 0.5*@trend + 2*@nrnd
        series gdp = 10 + 0.6*k + 0.3*l + 2*@nrnd
        equation eq1.ls gdp c k l
    """)

    print(ev.show("eq1"))
    print(ev.value("eq1.@r2"))
```

```text
Dependent Variable: GDP
Method: Least Squares
Included observations: 124

Variable      Coefficient   Std. Error   t-Statistic   Prob.

C             9.58073       0.829252     11.5535       2.90e-21
K             0.591693      0.0333819    17.7250       1.99e-35
L             0.322394      0.0673315     4.78816      4.81e-06

R-squared     0.994702      Mean dependent var         131.080
```

### Any EViews view, as text

`show` takes a view, so diagnostics need no extra API:

```python
ev.show("eq1", "wald c(2)=c(3)")   # coefficient restriction test
ev.show("eq1", "resids(t)")        # residual table
ev.show("eq1", "coefcov")          # coefficient covariance
ev.show("eq1", "auto(2)")          # Breusch-Godfrey serial correlation
ev.show("eq1", "white")            # White heteroskedasticity test
ev.show("gdp", "uroot")            # unit root test
ev.show("gdp", "correl")           # correlogram
ev.show("ardl1", "cointrel")       # ARDL long-run relationship
ev.show("var1", "impulse(t)")      # impulse response table
ev.show("var1", "testexog")        # Granger causality
```

`resids` and `impulse` draw graphs by default; the `(t)` variants ask EViews
for the table form. Views that freeze into a spool rather than a table -- the
ARDL cointegrating relationship among them -- cannot be read over COM at all,
so `show` falls back to a text dump for those.

For the numbers rather than the layout, `table()` returns raw rows at full
double precision, and `value()` returns one number:

```python
rows = ev.table("eq1")             # tuple of row tuples
r2   = ev.value("eq1.@r2")         # 0.9947015...
beta = ev.value("eq1.@coefs(2)")
```

### Results as data, not just text

`show` formats a table for reading. These return the numbers instead, for
testing, tabulating, or passing to something else:

```python
ev.coefficients("eq1")
# [{'variable': 'LNK', 'coefficient': 0.549198724914677,
#   'std_error': 0.023936158605687322, 't_stat': 22.94431341143375,
#   'p_value': 5.677925593821611e-41}, ...]

ev.fit("eq1")["R-squared"]        # 0.9858630667863459
```

Order of integration, tested down through differences until stationary:

```python
ev.unit_root("lngdp")
# {'series': 'LNGDP', 'order_of_integration': 1, 'conclusion': 'I(1)',
#  'steps': [{'difference': 0, 'statistic': -0.5001, 'p_value': 0.8856, ...},
#            {'difference': 1, 'statistic': -12.1778, 'p_value': 0.0001, ...}]}
```

Pass `options` to choose the test: `"pp"` for Phillips-Perron, `"kpss"` for
KPSS, `"adf, trend"` to add a trend. KPSS reverses the null, so the reported
order does not apply to it.

The standard post-estimation battery in one call:

```python
report = ev.diagnose("eq1")
report["summary"]
# 'All 3 diagnostics pass at the 0.05 level.'
```

Breusch-Godfrey, White and Jarque-Bera, each with its statistic, p-value and
whether the null is rejected. A test that cannot run is listed under
`report["skipped"]` with the reason EViews gave, so the summary never overstates
how much was actually checked.

These verdicts read p-values against a level you choose. They do not establish
that a specification is sound -- structural breaks, seasonality and short
samples all mislead these tests.

### pandas both ways

```python
frame = ev.to_dataframe(["gdp", "k", "l"])   # indexed 1990Q1, 1990Q2, ...
frame.corr()
```

Writing back, a `DatetimeIndex` or `PeriodIndex` decides the page frequency and
span, so dates stay aligned:

```python
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
index = pd.period_range("2005Q1", periods=40, freq="Q")
unemployment = 7.0 - 0.05 * np.arange(40) + rng.normal(0, 0.4, 40)

df = pd.DataFrame(
    {"unemployment": unemployment,
     "inflation": 9.0 - 0.9 * unemployment + rng.normal(0, 0.5, 40)},
    index=index,
)

ev.from_dataframe(df)              # creates a quarterly 2005Q1-2014Q4 page
ev.run("equation phillips.ls inflation c unemployment")
```

Non-numeric columns are skipped rather than failing the whole frame.

### Graphs

Graphs cannot be rendered as text, so write them to a file:

```python
ev.export_object("phillips", "residuals.png", view="resids")
```

Graph formats: `png`, `jpg`, `pdf`, `emf`, `wmf`, `bmp`, `gif`, `eps`, `tex`.
Table formats: `csv`, `rtf`, `txt`, `html`.

### Errors

EViews reports failures precisely, including the line number inside a program,
and those messages are passed through unchanged:

```python
ev.run("""series ok = 1
broken_command
""")
```

```text
EViewsError: BROKEN_COMMAND is not defined or is an illegal command in "BROKEN_COMMAND"
in MCP_77B699157F3B.PRG on line 2.
```

The generated program is given a random name each run, so only that part varies.

## MCP server use

Register the `eviews-mcp` command with your MCP client:

```json
{
  "mcpServers": {
    "eviews": {
      "command": "eviews-mcp"
    }
  }
}
```

For Claude Code:

```bash
claude mcp add eviews -- eviews-mcp
```

### Tools

| Tool | Purpose |
|---|---|
| `eviews_status` | Connection, version, active workfile. Start here when debugging. |
| `reset_eviews` | Discard the instance and start clean. |
| `set_eviews_visible` | Show or hide the EViews window. |
| `create_workfile` | New page by frequency and range. |
| `open_workfile` / `save_workfile` | Open and save `.wf1` / `.wf2`. |
| `close_workfile` | Close one or all open workfiles. |
| `workfile_info` | Name, page, frequency, range, sample. |
| `list_objects` | Inventory, filterable by EViews type. |
| `set_sample` | Set the estimation sample. |
| `run_eviews_code` | **Main tool.** Run a block of EViews program code. |
| `run_program_file` | Run an existing `.prg`, with arguments. |
| `command` | A single command line. |
| `show` | **Render any object as a text table.** |
| `evaluate` | One value from an expression. |
| `describe_object` | Type, plus statistics for a series. |
| `equation_coefficients` | Coefficients as a clean table of numbers. |
| `unit_root` | Order of integration, tested down through differences. |
| `diagnose_equation` | Serial correlation, heteroskedasticity and normality. |
| `read_data` | Series as an aligned table or full-precision CSV. |
| `write_series` | Write values into a series. |
| `import_data` | Read `.xlsx`, `.csv`, `.dta`, `.sav`, and more. |
| `export_data` | Write series to a file. |
| `export_object` | Save an object — the way to retrieve graphs. |

Results are not echoed by `run_eviews_code`, because EViews sends program
output to its own log window where COM cannot reach it. Estimate into a named
object and call `show` on it.

## Troubleshooting

### If the server will not start

A version before 1.3.3 could install the MCP SDK 2.x, which removed the module
this server is built on. The symptom is the same every time:

```text
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```

1.3.3 pins the SDK below 2.0. Upgrading fixes it -- but pip may serve a cached
index that predates the release, so bypass the cache:

```bash
pip install --upgrade --no-cache-dir "eviews-mcp[pandas]"
```

Confirm the server itself imports, not just the package. The package imports
lazily and succeeds even when the SDK is unusable, so checking it proves
nothing:

```bash
python -c "import eviews_mcp.server as s; print(len(s.mcp._tool_manager.list_tools()), 'tools')"
```

Twenty-four tools means the install is healthy.

## Behaviour worth knowing

These are EViews characteristics that the library handles for you, documented
because they surprise people writing COM code directly.

- **Writes respect the active sample.** Under `smpl 2000m3 2000m6`, writing 12
  values lands 4 and silently leaves the rest NA. Writes therefore default to
  the whole page; pass `sample=""` to opt into the current sample instead.
- **`save` ignores the file extension.** `graph.save "out.png"` writes EMF
  data. The format is passed explicitly, and a save that produces no file
  raises rather than reporting success.
- **Relative paths resolve against EViews**, not the calling process, so paths
  are made absolute before they are handed over.
- **A dated frame governs the page.** Writing a 12-row quarterly frame into an
  open 80-row page would land the values on the wrong dates, so a page matching
  the frame is created instead.
- **No log redirection.** The `output` command requires a frozen object name
  and otherwise writes nothing at all, so it cannot capture a log. Results come
  from freezing an object into a table and reading that.
- **No `GetScalar` / `PutScalar` / `GetString`.** These are not on the EViews
  COM interface at all. `Get` covers them and infers the type.
- **One COM thread.** MCP dispatches synchronous tools across a thread pool,
  and a COM pointer is not valid across apartments, so every EViews call is
  funnelled onto a single apartment-initialised thread.
- **Importing into an open workfile truncates the file** to that page's length,
  silently. Imports therefore create a new workfile by default; merging into the
  current page is opt-in.
- **EViews limits how many workfiles may be open** and then refuses to create
  another, so `close_workfile` exists to keep long sessions healthy.

## Tests

```bash
python tests/test_offline.py        # 27 tests, no EViews needed
python tests/test_live.py           # 25 tests, drives the MCP tool layer
python tests/test_live_client.py    # 62 tests, drives the library API
```

`pytest` runs the offline suite by default; the live suites are opt-in because
they need an EViews licence.

## Licence

MIT. Copyright (c) 2026 Merwan Roudane.
