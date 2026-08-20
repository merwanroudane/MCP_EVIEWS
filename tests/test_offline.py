"""Tests that need neither EViews nor Windows COM.

These cover the pure formatting and naming logic, so a contributor can verify
an install without an EViews licence. Runs under pytest, or directly:

    python tests/test_offline.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from eviews_mcp.render import (  # noqa: E402
    cell_text,
    format_number,
    render_series_columns,
    render_table,
    to_csv,
)


def test_format_number_keeps_integers_clean():
    assert format_number(2.0) == "2"
    assert format_number(-7.0) == "-7"


def test_format_number_uses_scientific_for_tiny_pvalues():
    text = format_number(3.93e-17)
    assert "e-17" in text


def test_format_number_handles_missing():
    assert format_number(float("nan")) == "NA"


def test_format_number_significant_digits():
    assert format_number(0.8907770016024783, digits=6) == "0.890777"


def test_cell_text_blank_for_none():
    assert cell_text(None) == ""


def test_cell_text_truncates_long_strings():
    assert len(cell_text("x" * 200)) <= 60
    assert cell_text("x" * 200).endswith("...")


def test_cell_text_truncation_is_ascii():
    # Terminals here are not reliably UTF-8, so no fancy ellipsis character.
    assert cell_text("x" * 200).isascii()


def test_title_rows_are_not_truncated():
    # A row holding one long cell is a title or note, and losing the end of
    # "Included observations: 122 after adjustments" would lose a result.
    note = "Included observations: 122 after adjustments end-of-line marker here"
    out = render_table([(note, None, None), ("A", 1.0, 2.0)])
    assert note in out


def test_long_labels_in_data_rows_are_capped():
    out = render_table([("x" * 200, 1.0, 2.0), ("B", 3.0, 4.0)])
    assert "..." in out
    assert max(len(line) for line in out.splitlines()) < 120


def test_render_table_aligns_and_keeps_separators():
    rows = [
        ("Dependent Variable: Y", None, None),
        (None, None, None),
        ("Variable", "Coefficient", "Prob."),
        ("C", 1.9595780136734053, 3.930121094079543e-17),
        ("X", 2.934707562694785, 1.0061264480376656e-24),
    ]
    out = render_table(rows)
    lines = out.splitlines()
    assert "Dependent Variable: Y" in lines[0]
    # Numeric columns line up, so the coefficient column starts at one offset.
    c_line = [line for line in lines if line.startswith("C ")][0]
    x_line = [line for line in lines if line.startswith("X ")][0]
    assert c_line.index("1.95") == x_line.index("2.93")


def test_render_table_empty():
    assert render_table(()) == "(empty)"
    assert render_table(None) == "(empty)"


def test_render_table_collapses_repeated_blank_rows():
    rows = [("a",), (None,), (None,), (None,), ("b",)]
    assert render_table(rows).splitlines() == ["a", "", "b"]


def test_render_series_columns_has_header_and_labels():
    out = render_series_columns(["gdp", "k"], [(1.0, 2.0), (3.0, 4.0)],
                                ["1990Q1", "1990Q2"])
    assert "gdp" in out and "k" in out
    assert "1990Q1" in out


def test_render_series_columns_truncates_politely():
    rows = [(float(i),) for i in range(500)]
    out = render_series_columns(["v"], rows, None, max_rows=50)
    assert "500 observations total" in out
    assert "..." in out


def test_small_max_rows_actually_shrinks_output():
    # A fixed tail slice used to invert the head slice, so a small max_rows
    # produced more rows than a large one.
    rows = [(float(i),) for i in range(100)]
    for cap in (2, 5, 8, 20):
        out = render_series_columns(["v"], rows, None, max_rows=cap)
        data_lines = [ln for ln in out.splitlines()
                      if ln.strip() and not ln.startswith("-")
                      and "observations total" not in ln]
        # header + at most cap data rows + the "..." separator
        assert len(data_lines) <= cap + 2, (cap, len(data_lines))


def test_to_csv_is_full_precision():
    csv = to_csv(["gdp"], [(0.8907770016024783,)], ["1990Q1"])
    assert "0.8907770016024783" in csv
    assert csv.splitlines()[0] == "obs,gdp"


def test_to_csv_blank_for_missing():
    csv = to_csv(["v"], [(None,)], None)
    assert csv.splitlines()[1] == "1,"


def _client_helpers():
    """Imported lazily: pulls in pywin32, which only exists on Windows."""
    from eviews_mcp.client import _clean_name, _is_missing, eviews_date

    return _clean_name, _is_missing, eviews_date


def test_clean_name_makes_legal_eviews_names():
    if sys.platform != "win32":
        return
    clean, _, _ = _client_helpers()
    assert clean("GDP growth (%)") == "GDP_growth____"
    assert clean("2020") == "s_2020"
    assert clean("") == "series"
    assert len(clean("x" * 100)) <= 24


def test_is_missing_detects_nan_and_none():
    if sys.platform != "win32":
        return
    _, missing, _ = _client_helpers()
    assert missing(None)
    assert missing(float("nan"))
    assert not missing(0.0)


def test_eviews_date_formats_by_frequency():
    if sys.platform != "win32":
        return
    import datetime

    _, _, as_date = _client_helpers()
    stamp = datetime.datetime(1990, 4, 1)
    assert as_date(stamp, "a") == "1990"
    assert as_date(stamp, "q") == "1990Q2"
    assert as_date(stamp, "m") == "1990M04"


def _main() -> int:
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print("[PASS] %s" % name)
        except AssertionError as exc:
            failures.append(name)
            print("[FAIL] %s  %s" % (name, exc))
        except Exception as exc:  # noqa: BLE001
            failures.append(name)
            print("[ERROR] %s  %s: %s" % (name, type(exc).__name__, exc))
    print("\n%d passed, %d failed" % (len(tests) - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
