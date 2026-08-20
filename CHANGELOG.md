# Changelog

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
