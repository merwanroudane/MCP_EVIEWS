# Changelog

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
