# Changelog

## 1.3.1

A packaging and documentation release. Nothing under `src/` changed since
1.3.0, so the installed library is byte-for-byte the same; what is new is the
project page and the release machinery around it.

### Added
- `.github/workflows/publish.yml`, publishing through PyPI Trusted Publishing
  rather than a stored API token, and refusing to run when the release tag does
  not match the version in `pyproject.toml`.
- `.github/workflows/tests.yml`, running the offline suite on Windows and Ubuntu
  across Python 3.10 and 3.12, plus a build-and-metadata check.
- Section 6.7 of the researcher guide covers `unit_root`, `equation_coefficients`
  and `diagnose_equation`, which the guide predated.

### Fixed
- The offline suite required pywin32 on Windows, because three tests keyed their
  skip on `sys.platform` rather than on whether the import actually worked --
  being on Windows says nothing about whether pywin32 is installed. It now needs
  no dependencies anywhere, as it always claimed to.
- The version badge on the documentation site was maintained by hand and had
  drifted a release behind. It reads PyPI directly now.
- The guide still installed from git rather than PyPI.

## 1.3.0

Results can now be read as data, not only as formatted text.

### Added
- `eviews_mcp.results`, which parses frozen EViews tables back into Python
  values. The layouts it handles were read off real EViews 13 output.
- `coefficients()` returns one dictionary per regressor, carrying the estimate,
  standard error, t-statistic and p-value at full precision. `fit()` returns the
  summary block beneath an estimation.
- `unit_root()` tests the levels and then successive differences, stopping at
  the first rejection, and reports the order of integration. Any EViews unit
  root view can be selected, so Phillips-Perron and KPSS work too.
- `diagnose()` runs Breusch-Godfrey, White and Jarque-Bera against an equation
  and reports each statistic, p-value and whether its null is rejected. A test
  that cannot run -- White has nothing to work with on a constant-only
  equation -- is reported with the reason EViews gave, rather than dropped
  silently and leaving the summary overstating how much was checked.
- Three matching MCP tools: `equation_coefficients`, `unit_root` and
  `diagnose_equation`.

The verdicts these produce are mechanical readings of p-values against a stated
level. They do not establish that a specification is sound.

## 1.2.0

### Added
- Researcher guide (`docs/EViews-Researcher-Guide.md`): a zero-to-analysis
  walkthrough with every command and output verified against a live session.
- `close_workfile` / `close_all_workfiles`. EViews caps how many workfiles may
  be open and then refuses to create another.
- `show` now reads views that freeze into a spool rather than a table, such as
  the ARDL cointegrating relationship and error-correction results, by writing
  the frozen object out as text.

### Fixed
- Importing a data file while a workfile was open made EViews truncate the file
  to that page's length, silently. A 100-row file read into an open 12-row page
  lost 88 rows with no warning. Imports now create a workfile sized to the file;
  merging into the open page is opt-in via `into_current_page`.
- Long title and note rows padded column 0 across the whole table, pushing the
  numbers far to the right in unit root and diagnostic output. Such rows are now
  written full width and excluded from column measurement.
- `read_data` with `max_rows` below 20 sliced the head negatively and returned
  more rows than asked for, not fewer.
- Table cells were truncated at 40 characters with a non-ASCII ellipsis, cutting
  text such as "Included observations: 122 after adjustments" and mangling in
  consoles that are not UTF-8.

## 1.1.0

Restructured into a library with the MCP server as a thin adapter on top.

### Added
- `EViews` client class as the public Python API, usable from scripts and
  notebooks independently of MCP. Context-manager support.
- pandas integration: `to_dataframe` and `from_dataframe`, with the EViews page
  frequency and span derived from a `DatetimeIndex` or `PeriodIndex`.
- `exists`, `describe`, `table` (raw rows at full precision), `value`,
  `obs_labels`.
- Offline test suite that needs neither EViews nor Windows.
- Packaging metadata, MIT licence, examples.

### Fixed
- `from_dataframe` wrote a dated frame into whatever page was already open when
  that page was long enough, silently landing the values on the wrong dates. A
  dated frame now governs the page.
- Writes default to the whole page. EViews honours the active sample on writes,
  so under a restricted sample values outside it were silently left NA.

### Changed
- Import on a non-Windows platform now raises a clear message instead of an
  opaque `pythoncom` `ImportError`.

## 1.0.0

First working version, built against the EViews 13 COM type library.

### Fixed relative to the original prototype
- `GetScalar`, `PutScalar` and `GetString` do not exist on the EViews COM
  interface and failed on every call. Replaced with `Get`, which covers all
  three and infers the type.
- Log capture through `output(r) "file"` never wrote a file, so every run
  reported "Done (no output)" whether it succeeded or failed. Results are now
  read by freezing an object into a table and pulling it across COM.
- COM calls were made from arbitrary MCP worker threads. All EViews access is
  now funnelled onto one apartment-initialised thread.
