"""Turning EViews COM payloads into text a reader can actually use.

A frozen EViews table comes back over COM as a tuple of equal-length row
tuples, with None for blank cells and full double precision for every number.
Printed verbatim that is unreadable, so these helpers lay it out as an aligned
grid and trim the numeric noise while keeping enough digits for p-values.
"""

from __future__ import annotations

from typing import Any, Sequence

MAX_CELL = 40


def format_number(value: float, digits: int = 6) -> str:
    """Format a float roughly the way EViews prints it.

    Very small numbers (p-values such as 3.93e-17) keep scientific notation;
    everything else is shown with a fixed number of significant digits and no
    trailing zero clutter.
    """
    if value != value:  # NaN
        return "NA"
    if value in (float("inf"), float("-inf")):
        return "inf" if value > 0 else "-inf"
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    if value != 0 and (abs(value) < 1e-4 or abs(value) >= 1e10):
        return "%.*e" % (digits - 1, value)
    text = "%.*g" % (digits, value)
    return text


def cell_text(value: Any, digits: int = 6) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return format_number(value, digits)
    text = str(value).strip()
    if len(text) > MAX_CELL:
        text = text[: MAX_CELL - 1] + "…"
    return text


def _normalise(rows: Any) -> list[list[Any]]:
    """Coerce whatever Get returned into a list of row lists."""
    if rows is None:
        return []
    if isinstance(rows, (str, float, int)):
        return [[rows]]
    out: list[list[Any]] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            out.append(list(row))
        else:
            out.append([row])
    return out


def render_table(rows: Any, digits: int = 6) -> str:
    """Render a frozen EViews table as an aligned plain-text grid.

    Numeric columns are right-aligned and text columns left-aligned, which is
    what makes a regression table scan correctly. Fully blank rows are kept as
    separators because EViews uses them to delimit result blocks.
    """
    grid = _normalise(rows)
    if not grid:
        return "(empty)"

    width = max(len(r) for r in grid)
    for row in grid:
        row.extend([None] * (width - len(row)))

    text_grid = [[cell_text(c, digits) for c in row] for row in grid]

    # A column is numeric if every populated original cell in it is a number.
    numeric_col = []
    for col in range(width):
        populated = [row[col] for row in grid if row[col] is not None]
        numeric_col.append(
            bool(populated)
            and all(isinstance(c, (int, float)) and not isinstance(c, bool)
                    for c in populated)
        )

    widths = [
        max((len(text_grid[r][col]) for r in range(len(text_grid))), default=0)
        for col in range(width)
    ]

    lines = []
    for row in text_grid:
        if not any(cell for cell in row):
            lines.append("")
            continue
        parts = []
        for col, cell in enumerate(row):
            if widths[col] == 0:
                continue
            parts.append(
                cell.rjust(widths[col]) if numeric_col[col] else cell.ljust(widths[col])
            )
        lines.append("  ".join(parts).rstrip())

    # Collapse the runs of blank separator rows EViews emits.
    cleaned: list[str] = []
    for line in lines:
        if line == "" and (not cleaned or cleaned[-1] == ""):
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned) if cleaned else "(empty)"


def render_series_columns(names: Sequence[str], rows: Any, labels: Sequence[str] | None,
                          digits: int = 6, max_rows: int = 200) -> str:
    """Render series values as a labelled column layout, truncating politely."""
    grid = _normalise(rows)
    total = len(grid)
    truncated = total > max_rows
    if truncated:
        head = grid[: max_rows - 20]
        tail = grid[-20:]
    else:
        head, tail = grid, []

    header = ["obs"] + list(names)

    def to_line(index: int, row: Sequence[Any]) -> list[str]:
        label = labels[index] if labels and index < len(labels) else str(index + 1)
        return [str(label)] + [cell_text(c, digits) for c in row]

    body = [to_line(i, r) for i, r in enumerate(head)]
    if tail:
        offset = total - len(tail)
        body.append(["..."] + ["..."] * len(names))
        body.extend(to_line(offset + i, r) for i, r in enumerate(tail))

    widths = [len(h) for h in header]
    for row in body:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    lines = ["  ".join(h.rjust(widths[i]) for i, h in enumerate(header))]
    lines.append("  ".join("-" * w for w in widths))
    for row in body:
        lines.append(
            "  ".join(
                cell.rjust(widths[i]) for i, cell in enumerate(row) if i < len(widths)
            )
        )
    if truncated:
        lines.append("")
        lines.append("(%d observations total, middle rows omitted)" % total)
    return "\n".join(lines)


def to_csv(names: Sequence[str], rows: Any, labels: Sequence[str] | None) -> str:
    """Full-precision CSV, for when the caller wants the numbers not the view."""
    import csv
    import io

    grid = _normalise(rows)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["obs"] + list(names))
    for i, row in enumerate(grid):
        label = labels[i] if labels and i < len(labels) else i + 1
        writer.writerow([label] + ["" if c is None else c for c in row])
    return buf.getvalue().rstrip("\n")
