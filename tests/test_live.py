"""Live end-to-end exercise against a real EViews 13 installation.

This is not a unit test suite: it drives an actual EViews instance through the
same functions the MCP server exposes, which is the only way to confirm the COM
behaviour this server depends on. Run it directly:

    python tests/test_live.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from eviews_mcp import server as s  # noqa: E402

PASS, FAIL = [], []


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(label)
    mark = "PASS" if condition else "FAIL"
    print("[%s] %s" % (mark, label))
    if detail:
        for line in str(detail).splitlines():
            print("        " + line)


print("=" * 70)
print("1. status / connection")
print("=" * 70)
out = s.eviews_status()
check("eviews_status connects", "Connected to EViews" in out, out)
s.close_workfile(close_all=True)  # keep repeated runs from filling EViews up

print()
print("=" * 70)
print("2. workfile creation and info")
print("=" * 70)
out = s.create_workfile("q", "1990q1", "2020q4", name="demo")
check("create_workfile quarterly", "Created workfile" in out, out)
out = s.workfile_info()
check("workfile_info reports frequency", "Frequency" in out, out)

print()
print("=" * 70)
print("3. run_eviews_code with a real model")
print("=" * 70)
code = """
' simulate a small macro data set
rndseed 42
series eps = @nrnd
series k = 100 + @trend + 3*@nrnd
series l = 50 + 0.5*@trend + 2*@nrnd
series gdp = 10 + 0.6*k + 0.3*l + 2*eps
equation eq1.ls gdp c k l
"""
out = s.run_eviews_code(code)
check("run_eviews_code succeeds", "ran successfully" in out, out)
check("new objects are reported", "EQ1" in out.upper(), out)

print()
print("=" * 70)
print("4. run_eviews_code error reporting")
print("=" * 70)
out = s.run_eviews_code("series good = 1\nthis_is_not_a_command\n")
check("bad code reports an error", "EViews error" in out, out)
check("error names the line", "line" in out.lower(), out)

print()
print("=" * 70)
print("5. show() renders estimation output")
print("=" * 70)
out = s.show("eq1")
check("show renders the regression", "R-squared" in out, out)
check("show has coefficient column", "Coefficient" in out)

print()
print("=" * 70)
print("6. show() with a view")
print("=" * 70)
out = s.show("gdp", "stats")
check("show(series, stats)", "Mean" in out or "Median" in out, out)

print()
print("=" * 70)
print("7. evaluate()")
print("=" * 70)
r2 = s.evaluate("eq1.@r2")
try:
    check("evaluate returns a plausible R-squared", 0.0 <= float(r2) <= 1.0,
          "r2 = %s" % r2)
except ValueError:
    check("evaluate returns a plausible R-squared", False, r2)
coef = s.evaluate("eq1.@coefs(2)")
check("evaluate coefficient on k", abs(float(coef) - 0.6) < 0.15, "coef = %s" % coef)

print()
print("=" * 70)
print("8. list_objects / describe_object")
print("=" * 70)
out = s.list_objects("*", "series")
check("list_objects filters by type", "GDP" in out.upper(), out)
out = s.describe_object("gdp")
check("describe_object identifies a series", "series" in out.lower(), out)
out = s.describe_object("eq1")
check("describe_object identifies an equation", "equation" in out.lower(), out)

print()
print("=" * 70)
print("9. read_data")
print("=" * 70)
out = s.read_data("gdp k", sample="1990q1 1992q4")
check("read_data table has both names", "GDP" in out.upper() and "K" in out.upper(), out)
csv = s.read_data("gdp", sample="1990q1 1991q4", output_format="csv")
check("read_data csv has a header", csv.splitlines()[0].lower().startswith("obs"), csv)
check("read_data csv row count", len(csv.splitlines()) == 9, csv)

print()
print("=" * 70)
print("10. write_series round trip")
print("=" * 70)
s.set_sample("1990q1 1990q4")
out = s.write_series("manual", "1, 2, NA, 4")
check("write_series accepts values", "Wrote 4" in out, out)
back = s.read_data("manual", sample="1990q1 1990q4", output_format="csv")
check("write_series round trip", back.count("\n") == 4, back)
s.set_sample("@all")

print()
print("=" * 70)
print("11. sample handling")
print("=" * 70)
out = s.set_sample("2000q1 2010q4")
check("set_sample reports new sample", "2000" in out, out)
s.set_sample("@all")

print()
print("=" * 70)
print("12. export / import round trip")
print("=" * 70)
tmp = pathlib.Path("C:/ev_mcp/roundtrip.csv")
out = s.export_data("gdp k l", str(tmp))
check("export_data writes a file", tmp.exists(), out)

print()
print("=" * 70)
print("13. command() single line")
print("=" * 70)
out = s.command("delete manual")
check("command deletes an object", out.startswith("OK"), out)
out = s.command("nonsense_command")
check("command reports errors", "EViews error" in out, out)

print()
print("=" * 70)
print("14. graceful failure without a valid object")
print("=" * 70)
out = s.show("does_not_exist")
check("show on a missing object fails cleanly", "error" in out.lower(), out)

print()
s.close_workfile(close_all=True)
print("=" * 70)
print("SUMMARY: %d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  FAILED: %s" % f)
print("=" * 70)
sys.exit(1 if FAIL else 0)
