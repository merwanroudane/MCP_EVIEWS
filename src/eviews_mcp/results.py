"""Turning frozen EViews tables into structured Python values.

:mod:`eviews_mcp.render` formats a table for a person to read. This module does
the opposite: it pulls the numbers back out, so results can be tested,
tabulated, or handed to something else to interpret.

The layouts here were read off real EViews 13 output rather than assumed. Three
shapes recur:

* a coefficient block -- a ``Variable | Coefficient | Std. Error | t-Statistic |
  Prob.`` header, a blank row, then one row per regressor;
* paired summary statistics -- ``('R-squared', 0.98, 'Mean dependent var',
  None, 6.49)``, two label/value pairs sharing one row;
* a test row -- ``('F-statistic', 0.767, 'Prob. F(2,95)', None, 0.467)``.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

__all__ = [
    "grid", "coefficient_block", "stat_pairs", "find_row", "numbers_in",
    "unit_root_block",
]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def grid(rows: Any) -> list[list[Any]]:
    """Normalise whatever ``table()`` returned into a list of row lists."""
    if rows is None:
        return []
    out: list[list[Any]] = []
    for row in rows:
        out.append(list(row) if isinstance(row, (list, tuple)) else [row])
    return out


def numbers_in(row: Sequence[Any]) -> list[float]:
    return [float(c) for c in row if _is_number(c)]


def find_row(rows: Any, *needles: str, start: int = 0) -> int:
    """Index of the first row whose text contains every needle, else -1."""
    wanted = [n.lower() for n in needles]
    for i, row in enumerate(grid(rows)[start:], start=start):
        text = " ".join(str(c).lower() for c in row if isinstance(c, str))
        if all(w in text for w in wanted):
            return i
    return -1


def coefficient_block(rows: Any) -> list[dict]:
    """Extract the estimated coefficients from an estimation table.

    Returns one dictionary per regressor with ``variable``, ``coefficient``,
    ``std_error``, ``t_stat`` and ``p_value``. Rows are read until the block
    ends, which EViews marks with a blank row.
    """
    table = grid(rows)
    header = find_row(table, "variable", "coefficient")
    if header < 0:
        return []

    found: list[dict] = []
    for row in table[header + 1:]:
        label = row[0] if row and isinstance(row[0], str) else None
        values = numbers_in(row)
        if label is None or not label.strip():
            # A blank row ends the block, but only once something was read;
            # EViews puts one directly beneath the header too.
            if found:
                break
            continue
        if len(values) < 4:
            break  # summary statistics start here
        found.append({
            "variable": label.strip(),
            "coefficient": values[0],
            "std_error": values[1],
            "t_stat": values[2],
            "p_value": values[3],
        })
    return found


def stat_pairs(rows: Any) -> dict[str, float]:
    """Collect every ``label -> number`` pair in a table.

    Handles rows carrying two pairs, which is how EViews lays out the summary
    block beneath a regression, as well as the single-pair rows of a
    descriptive-statistics table.
    """
    pairs: dict[str, float] = {}
    for row in grid(rows):
        label: str | None = None
        for cell in row:
            if isinstance(cell, str) and cell.strip():
                label = cell.strip().rstrip(":")
            elif _is_number(cell) and label is not None:
                pairs.setdefault(label, float(cell))
                label = None
    return pairs


def unit_root_block(rows: Any) -> dict:
    """Test statistic, p-value and critical values from a unit root table."""
    table = grid(rows)
    result: dict[str, Any] = {
        "statistic": None, "p_value": None, "critical_values": {},
        "lag_length": None, "null": None,
    }

    idx = find_row(table, "test statistic")
    if idx >= 0:
        values = numbers_in(table[idx])
        if len(values) >= 2:
            result["statistic"], result["p_value"] = values[0], values[1]
        elif values:
            result["statistic"] = values[0]

    for row in table:
        text = " ".join(str(c) for c in row if isinstance(c, str))
        if "null hypothesis" in text.lower() and result["null"] is None:
            result["null"] = text.split(":", 1)[-1].strip()
        if "lag length" in text.lower() and result["lag_length"] is None:
            result["lag_length"] = text.split(":", 1)[-1].strip()
        for cell in row:
            if isinstance(cell, str) and "% level" in cell:
                values = numbers_in(row)
                if values:
                    result["critical_values"][cell.strip()] = values[0]
    return result
