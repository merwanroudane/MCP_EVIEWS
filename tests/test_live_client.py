"""Live exercise of the library API against a real EViews installation.

Complements test_live.py, which drives the MCP tool layer. Run directly:

    python tests/test_live_client.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from eviews_mcp import EViews, EViewsError  # noqa: E402

PASS, FAIL = [], []


def check(label, condition, detail=""):
    ok = bool(condition)
    (PASS if ok else FAIL).append(label)
    print("[%s] %s" % ("PASS" if ok else "FAIL", label))
    if not ok and detail is not None:
        for line in str(detail).splitlines()[:12]:
            print("        " + line)


ev = EViews()
# Repeated runs would otherwise accumulate workfiles until EViews
# refuses to create another one.
ev.close_all_workfiles()

print("== connection ==")
check("version reported", ev.version.startswith("1"), ev.version)
check("status is connected", ev.status()["connected"] is True)

print("\n== workfile ==")
ev.create_workfile("q", "1990q1", "2009q4", name="lib")
info = ev.workfile_info()
check("quarterly page created", info["frequency"] == "Q", info)
check("80 observations", info["obs_range"] == 80, info)

print("\n== run and results ==")
created = ev.run("""
rndseed 7
series x = @nrnd
series y = 1 + 2*x + 0.5*@nrnd
equation eq1.ls y c x
""")
check("run reports new objects", "EQ1" in [c.upper() for c in created], created)
check("exists() finds the equation", ev.exists("eq1"))
check("exists() rejects a missing name", not ev.exists("no_such_thing"))

r2 = ev.value("eq1.@r2")
check("value returns a float", isinstance(r2, float), type(r2))
check("R-squared in range", 0.0 <= r2 <= 1.0, r2)
slope = ev.value("eq1.@coefs(2)")
check("slope near 2", abs(slope - 2.0) < 0.2, slope)

text = ev.show("eq1")
check("show renders output", "R-squared" in text, text)
raw = ev.table("eq1")
check("table returns raw rows", isinstance(raw, tuple) and len(raw) > 5)
check("raw keeps full precision",
      any(isinstance(c, float) and len(repr(c)) > 10
          for row in raw for c in row if c is not None))

print("\n== describe ==")
d = ev.describe("y")
check("describe types a series", d["type"] == "series", d)
check("describe includes mean", "mean" in d, d)
d = ev.describe("eq1")
check("describe types an equation", d["type"] == "equation", d)
try:
    ev.describe("nope_not_here")
    check("describe raises on missing object", False)
except EViewsError:
    check("describe raises on missing object", True)

print("\n== data round trip ==")
values = [float(i) for i in range(80)]
ev.put_series("manual", values)
back = ev.get_series("manual")
check("put/get round trip", back[:5] == values[:5] and len(back) == 80, back[:5])

print("\n== writes default to the whole page, not the current sample ==")
ev.set_sample("1995q1 1996q4")
ev.put_series("fullwrite", [float(i) for i in range(80)])
full = ev.get_series("fullwrite", "@all")
check("default write ignores restricted sample",
      full[0] == 0.0 and full[-1] == 79.0, (full[0], full[-1]))
ev.put_series("narrow", [float(i) for i in range(80)], sample="")
narrow = ev.get_series("narrow", "@all")
check("explicit sample='' honours the restriction",
      narrow[0] is None and any(v is not None for v in narrow),
      (narrow[0], narrow[20], narrow[25]))
ev.set_sample("@all")

print("\n== pandas ==")
try:
    import pandas as pd
except ImportError:
    print("  pandas not installed; skipping")
else:
    frame = ev.to_dataframe(["y", "x"])
    check("to_dataframe shape", frame.shape == (80, 2), frame.shape)
    check("to_dataframe columns", list(frame.columns) == ["Y", "X"], frame.columns)
    check("to_dataframe index is dated", str(frame.index[0]) == "1990Q1",
          frame.index[:3])

    idx = pd.period_range("2001Q1", periods=12, freq="Q")
    src = pd.DataFrame({"alpha": range(12),
                        "beta": [i * 2.5 for i in range(12)],
                        "label": list("abcdefghijkl")}, index=idx)
    written = ev.from_dataframe(src)
    check("from_dataframe writes numeric columns",
          set(written) == {"alpha", "beta"}, written)
    check("from_dataframe skips text columns", "label" not in written, written)
    check("from_dataframe made a dated page",
          ev.workfile_info()["frequency"] == "Q", ev.workfile_info())
    check("from_dataframe start date correct",
          ev.workfile_info()["range"].startswith("2001Q1"),
          ev.workfile_info()["range"])
    round_trip = ev.to_dataframe(["alpha", "beta"])
    check("from_dataframe values survive",
          list(round_trip["BETA"])[:3] == [0.0, 2.5, 5.0],
          list(round_trip["BETA"])[:3])

print("\n== export ==")
out = pathlib.Path("C:/ev_mcp/lib_export.csv")
if out.exists():
    out.unlink()
ev.export_data("alpha beta", str(out))
check("export_data writes a file", out.exists())
if out.exists():
    out.unlink()

print("\n== graph export honours the extension and the caller's directory ==")
ev.run("graph gr_test.line alpha beta")
png = pathlib.Path("lib_graph.png")
if png.exists():
    png.unlink()
written = ev.export_object("gr_test", "lib_graph.png")
check("export_object returns an absolute path", written.is_absolute(), written)
check("graph lands in the caller's directory", png.resolve() == written, written)
check("file is a real PNG, not EMF",
      png.exists() and png.read_bytes()[:4] == b"\x89PNG",
      png.read_bytes()[:8] if png.exists() else "missing")
if png.exists():
    png.unlink()

pdf = pathlib.Path("lib_graph.pdf")
ev.export_object("gr_test", str(pdf))
check("pdf export works", pdf.exists() and pdf.read_bytes()[:4] == b"%PDF")
if pdf.exists():
    pdf.unlink()

try:
    ev.export_object("gr_test", "lib_graph.svg")
    check("unsupported format is reported, not silently skipped", False)
except EViewsError:
    check("unsupported format is reported, not silently skipped", True)

print("\n== spool views are readable, not just tables ==")
# ARDL cointegrating relationship freezes into a spool, which Get cannot read;
# show() falls back to a text dump for these.
ev.create_workfile("q", "1996q1", "2020q4", name="spool")
ev.run("""
rndseed 99
series a = @cumsum(@nrnd)/10 + 5
series b = 1.2 + 0.5*a + 0.2*@nrnd
equation ardl_t.ardl(deplags=4, reglags=4) b a
""")
try:
    out = ev.show("ardl_t", "cointrel")
    check("spool view returns text", "CE =" in out or "Variable" in out, out[:400])
    check("spool text is not empty", len(out.strip()) > 60, out[:200])
except EViewsError as exc:
    check("spool view returns text", False, exc)

try:
    ev.show("ardl_t", "not_a_real_view")
    check("invalid view still raises", False)
except EViewsError:
    check("invalid view still raises", True)

print("\n== structured results ==")
ev.create_workfile("q", "1996q1", "2020q4", name="struct")
ev.run("""
rndseed 5
series kk = @cumsum(@nrnd)/20 + 6
series ll = @cumsum(@nrnd)/40 + 4.5
series yy = 1.2 + 0.55*kk + 0.35*ll + 0.03*@nrnd
equation e_s.ls yy c kk ll
""")

coefs = ev.coefficients("e_s")
check("coefficients returns one row per regressor", len(coefs) == 3, coefs)
names = [c["variable"] for c in coefs]
check("coefficients names the regressors", names == ["C", "KK", "LL"], names)
kk = [c for c in coefs if c["variable"] == "KK"][0]
check("coefficient recovers the true slope", abs(kk["coefficient"] - 0.55) < 0.06,
      kk["coefficient"])
check("coefficient carries std error, t and p",
      all(k in kk for k in ("std_error", "t_stat", "p_value")), kk)
check("coefficients keep full precision", len(repr(kk["coefficient"])) > 10,
      kk["coefficient"])
check("summary statistics are not read as regressors",
      "R-squared" not in names, names)

fit = ev.fit("e_s")
check("fit reports R-squared", 0.0 <= fit.get("R-squared", -1) <= 1.0,
      fit.get("R-squared"))
check("fit reports Durbin-Watson", "Durbin-Watson stat" in fit, sorted(fit)[:6])

print("\n== unit root verdicts ==")
ur = ev.unit_root("kk")
check("random walk is not stationary in levels",
      ur["steps"][0]["stationary"] is False, ur["steps"][0])
check("random walk is I(1)", ur["order_of_integration"] == 1, ur["conclusion"])
check("unit root records critical values",
      bool(ur["steps"][0]["critical_values"]), ur["steps"][0]["critical_values"])

ev.run("series wn = @nrnd")
ur0 = ev.unit_root("wn")
check("white noise is I(0)", ur0["order_of_integration"] == 0, ur0["conclusion"])

print("\n== diagnostics ==")
good = ev.diagnose("e_s")
check("diagnose runs three tests", len(good["tests"]) == 3,
      [d["test"] for d in good["tests"]])
check("well-specified model passes",
      all(not d["rejected"] for d in good["tests"]), good["summary"])
check("diagnose reports fit alongside", "R-squared" in good["fit"])

ev.run("equation e_bad.ls yy c")
bad = ev.diagnose("e_bad")
check("misspecified model is flagged",
      any(d["rejected"] for d in bad["tests"]), bad["summary"])
serial = [d for d in bad["tests"] if "serial" in d["test"].lower()]
check("serial correlation detected in the bad model",
      bool(serial) and serial[0]["rejected"], bad["summary"])
check("tests that cannot run are reported, not dropped",
      isinstance(bad["skipped"], list), bad.get("skipped"))
check("summary mentions anything skipped",
      ("could not be run" in bad["summary"]) == bool(bad["skipped"]),
      bad["summary"])

print("\n== errors are informative ==")
try:
    ev.run("series ok = 1\nbroken_command_here\n")
    check("bad program raises", False)
except EViewsError as exc:
    check("bad program raises", True)
    check("error names the line", "line" in str(exc).lower(), exc)

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  FAILED: %s" % f)
sys.exit(1 if FAIL else 0)
