# EViews Researcher Guide

**How to run econometrics in EViews by talking to an AI assistant — from a clean machine to a finished ARDL study.**

Written for applied researchers. It assumes you know econometrics and EViews. It assumes nothing about Python, COM automation, or MCP.

Every command and every block of output in this guide was run against a real EViews 13 installation. Nothing is illustrative.

---

## Contents

1. [What this actually is](#1-what-this-actually-is)
2. [What MCP is, in plain terms](#2-what-mcp-is-in-plain-terms)
3. [Before you start](#3-before-you-start)
4. [Step 1 — Install Python](#step-1--install-python)
5. [Step 2 — Install the package](#step-2--install-the-package)
6. [Step 3 — Check EViews is reachable](#step-3--check-eviews-is-reachable)
7. [Step 4 — Connect your AI assistant](#step-4--connect-your-ai-assistant)
8. [Step 5 — Your first analysis](#step-5--your-first-analysis)
9. [Step 6 — A complete study, end to end](#step-6--a-complete-study-end-to-end)
10. [How results are read](#7-how-results-are-read)
11. [Writing it up as a reproducible script](#8-writing-it-up-as-a-reproducible-script)
12. [Tool reference](#9-tool-reference)
13. [Traps that silently corrupt results](#10-traps-that-silently-corrupt-results)
14. [Troubleshooting](#11-troubleshooting)
15. [Reproducibility and honest reporting](#12-reproducibility-and-honest-reporting)
16. [FAQ](#13-faq)

---

## 1. What this actually is

You keep EViews. You keep your workfiles, your estimators, your output. What changes is how you drive it.

Instead of clicking through dialogs or hand-writing a `.prg`, you describe what you want:

> *"Load `macro.csv`, test all three series for unit roots, and if they're I(1), estimate an ARDL with up to 4 lags and show me the long-run relationship."*

The assistant then issues real EViews commands into a real EViews session. The numbers come from EViews, not from the model. If EViews rejects something, you see EViews' own error message.

**This is not a reimplementation of EViews.** There is no separate statistical engine and no attempt to reproduce EViews results in Python. Every coefficient you see was computed by EViews itself.

Two ways to use it, from the same install:

| | |
|---|---|
| **As an MCP server** | An AI assistant drives EViews conversationally. Best for exploration, diagnostics, and getting unstuck. |
| **As a Python library** | You write a script that drives EViews. Best for the final, reproducible version of your analysis. |

Most researchers use both: converse to find the specification, then freeze it into a script for the paper.

---

## 2. What MCP is, in plain terms

**MCP** (Model Context Protocol) is a standard way to give an AI assistant access to a real program on your computer.

Without it, an assistant can *write* EViews code for you, but it cannot run it. It never sees whether the code worked, what the coefficients were, or whether the sample was what you thought. It is guessing, and when it guesses about numbers it invents them.

With it, the assistant runs the code, reads the actual output, and continues from there. If the ADF test says *p* = 0.886, the assistant sees 0.886.

Here is what sits between you and EViews:

```mermaid
flowchart LR
    A["You<br/><i>plain English</i>"] --> B["AI assistant<br/><i>Claude Desktop,<br/>Claude Code, …</i>"]
    B <-->|"MCP<br/>(tool calls)"| C["eviews-mcp<br/><i>this package</i>"]
    C <-->|"COM<br/>automation"| D["EViews 13<br/><i>the real thing</i>"]
    D --> E[("Your workfile<br/>.wf1")]

    style A fill:#e8eef7,stroke:#4a6fa5,color:#1a2733
    style B fill:#e8eef7,stroke:#4a6fa5,color:#1a2733
    style C fill:#d9e6d4,stroke:#5a7d4f,color:#1a2733
    style D fill:#f2e4d4,stroke:#a5764a,color:#1a2733
    style E fill:#efeae2,stroke:#8a8175,color:#1a2733
```

Reading it left to right:

- **You** type a request in ordinary language.
- **The assistant** decides which tools to call, and in what order.
- **`eviews-mcp`** translates each tool call into EViews commands and translates results back into readable text.
- **EViews** does the econometrics. It runs hidden by default; you can show the window whenever you want to look.

The important consequence: **the assistant cannot fabricate results, because the results come back from EViews.** It can still misread them or choose a poor specification — you remain the econometrician — but the numbers are real.

---

## 3. Before you start

| Requirement | Notes |
|---|---|
| **Windows** | Required. EViews automation uses COM, which is Windows-only. There is no macOS or Linux path. |
| **EViews 13** | Installed and licensed. EViews 10–14 also work. |
| **Python 3.10+** | Installed in Step 1 if you don't have it. |
| **An MCP-capable assistant** | Claude Desktop, Claude Code, or any other MCP client. |

You do **not** need to know Python to use the conversational half of this guide.

---

## Step 1 — Install Python

Skip this if `python --version` already prints 3.10 or higher.

1. Go to [python.org/downloads/windows](https://www.python.org/downloads/windows/) and download the latest **Windows installer (64-bit)**.
2. Run it. On the first screen, **tick "Add python.exe to PATH"**. This matters — without it, later commands will not be found.
3. Click **Install Now**.
4. Open a new terminal (press `Win`, type `cmd`, press Enter) and confirm:

```bash
python --version
```

You should see something like `Python 3.13.1`.

---

## Step 2 — Install the package

In the same terminal:

```bash
pip install "eviews-mcp[pandas]"
```

The `[pandas]` part adds DataFrame support, which you want if you plan to move data between EViews and Python.

Confirm it landed:

```bash
pip show eviews-mcp
```

---

## Step 3 — Check EViews is reachable

Before wiring up an assistant, confirm the connection works on its own. Run:

```bash
python -c "from eviews_mcp import EViews; print(EViews().status())"
```

A working install prints something like:

```text
{'connected': True, 'progid': 'EViews.Manager', 'version': '13.0',
 'workfile': None, 'scratch_dir': 'C:\\ev_mcp'}
```

`'connected': True` is the thing to look for. If EViews was not already running, it is started hidden — this takes a few seconds the first time.

If this fails, go to [Troubleshooting](#11-troubleshooting) before continuing. Nothing downstream will work until it succeeds.

---

## Step 4 — Connect your AI assistant

### Claude Code

One command:

```bash
claude mcp add eviews -- eviews-mcp
```

### Claude Desktop

Open **File → Settings → Developer → Edit Config**, which opens `claude_desktop_config.json`. Add the `eviews` entry:

```json
{
  "mcpServers": {
    "eviews": {
      "command": "eviews-mcp"
    }
  }
}
```

Save, then **fully quit and reopen Claude Desktop** — it only reads this file at startup.

If `eviews-mcp` is not found, give the full path instead. Find it with `where eviews-mcp`, then:

```json
{
  "mcpServers": {
    "eviews": {
      "command": "C:\\Users\\YourName\\AppData\\Local\\Programs\\Python\\Python313\\Scripts\\eviews-mcp.exe"
    }
  }
}
```

### Confirming it worked

Ask the assistant:

> *"Check the EViews connection."*

It should call `eviews_status` and report back:

```text
Connected to EViews 13.0 via EViews.Manager
Scratch directory: C:\ev_mcp
Active workfile: none open (use create_workfile or open_workfile)
```

You are ready.

---

## Step 5 — Your first analysis

Ask for something small, so you can see the shape of the interaction:

> *"Create a quarterly workfile from 1990Q1 to 2020Q4, generate a variable x as standard normal and y = 2 + 3x + noise, then regress y on x and show me the results."*

The assistant creates the workfile, runs the code, and shows you:

```text
Dependent Variable: Y
Method: Least Squares
Sample: 1990Q1 2020Q4
Included observations: 124

Variable      Coefficient   Std. Error   t-Statistic   Prob.

C             9.58073       0.829252     11.5535       2.90e-21
K             0.591693      0.0333819    17.7250       1.99e-35
L             0.322394      0.0673315     4.78816      4.81e-06

R-squared     0.994702      Mean dependent var         131.080
```

That is EViews' own output, laid out for reading. From here you can ask for anything EViews can do — `"now test the residuals for serial correlation"`, `"show me the correlogram"`, `"re-estimate with HAC standard errors"`.

---

## Step 6 — A complete study, end to end

This is a full ARDL exercise on quarterly data, exactly as it ran. Follow along with your own data or generate the sample file below.

### The data

A CSV with a date column and three log-level series — output, capital, labour:

```text
date,lngdp,lnk,lnl
1996Q1,6.062271,6.032577,4.495548
1996Q2,6.067971,6.077416,4.503464
1996Q3,6.122216,6.112350,4.482450
...
```

To generate this exact file for practice:

```python
import numpy as np, pandas as pd
rng = np.random.default_rng(2024)
n = 100
idx = pd.period_range("1996Q1", periods=n, freq="Q")
lnk = np.cumsum(rng.normal(0.012, 0.02, n)) + 6.0
lnl = np.cumsum(rng.normal(0.004, 0.01, n)) + 4.5
lngdp = 1.2 + 0.55*lnk + 0.35*lnl + rng.normal(0, 0.03, n)
df = pd.DataFrame({"lngdp": lngdp, "lnk": lnk, "lnl": lnl}, index=idx.astype(str))
df.index.name = "date"
df.to_csv(r"C:\ev_mcp\guide\macro.csv")
```

The true long-run relationship is **lngdp = 1.2 + 0.55·lnk + 0.35·lnl**. Keep those numbers in mind; the ARDL should recover them.

### 6.1 Load the data

> *"Import C:\ev_mcp\guide\macro.csv"*

```text
Imported C:\ev_mcp\guide\macro.csv.
Series now present: DATE, LNGDP, LNK, LNL
```

**Always check what you actually loaded.** Ask *"describe the workfile"*:

```text
Workfile:       MACRO
Page:           Macro
Frequency:      Q
Page range:     1996Q1 2020Q4
Current sample: 1996Q1 2020Q4
Obs in range:   100
Obs in sample:  100
Objects:        4
```

100 observations, quarterly, 1996Q1–2020Q4. EViews read the date column and structured the page itself. If this said 12 observations, you would stop here and find out why — see [the traps section](#10-traps-that-silently-corrupt-results).

And look at the actual numbers:

```text
   obs    lngdp      lnk      lnl
------  -------  -------  -------
1996Q1  6.06227  6.03258  4.49555
1996Q2  6.06797  6.07742  4.50346
1996Q3  6.12222  6.11235  4.48245
1996Q4   6.1264  6.10489  4.48595
1997Q1   6.1402  6.08903  4.48665
1997Q2  6.10148  6.10237  4.48546
   ...      ...      ...      ...
2020Q3  6.89099  7.34709  4.75048
2020Q4  6.85986  7.35791  4.75628

(100 observations total, middle rows omitted)
```

### 6.2 Test for unit roots

> *"Run an ADF test on lngdp in levels."*

```text
Null Hypothesis: LNGDP has a unit root
Exogenous: Constant
Lag Length: 2 (Automatic - based on SIC, maxlag=12)

                                            t-Statistic  Prob.*

Augmented Dickey-Fuller test statistic      -0.500089    0.885575
Test critical values:   1% level            -3.49917
                        5% level            -2.89155
                        10% level           -2.58285

*MacKinnon (1996) one-sided p-values.
```

Cannot reject a unit root (*p* = 0.886). Now the first difference:

> *"Now the same test on the first difference."*

```text
Null Hypothesis: D(LNGDP) has a unit root
Exogenous: Constant
Lag Length: 1 (Automatic - based on SIC, maxlag=11)

                                            t-Statistic  Prob.*

Augmented Dickey-Fuller test statistic      -12.1778     0.0001
Test critical values:   1% level            -3.49917
                        5% level            -2.89155
                        10% level           -2.58285
```

Strongly rejected. `lngdp` is I(1) — the ARDL bounds framework is appropriate.

### 6.3 Estimate the ARDL

> *"Estimate an ARDL of lngdp on lnk and lnl, up to 4 lags, with automatic selection."*

```text
Program ran successfully (1 line(s)).
New objects: ARDL1
Use show(<name>) to see results.
```

The underlying command was:

```text
equation ardl1.ardl(deplags=4, reglags=4) lngdp lnk lnl
```

### 6.4 The long-run relationship

This is the result the study exists to produce.

> *"Show me the cointegrating relationship."*

```text
------------------------------------------------------------
Deterministics: Rest. constant (Case 2)
------------------------------------------------------------
CE = LNGDP(-1) - (0.543006*LNK + 0.370972*LNL + 1.153436)
------------------------------------------------------------

    Variable *     Coefficient  Std. Error  t-Statistic  Prob.
------------------------------------------------------------
        LNK          0.543006   0.025016   21.70645   0.0000
        LNL          0.370972   0.080765   4.593229   0.0000
         C           1.153436   0.222325   5.188072   0.0000
------------------------------------------------------------
Note: * Coefficients derived from the CEC regression.
```

Estimated long-run elasticities of **0.543** and **0.371**, against true values of 0.55 and 0.35. Both strongly significant.

### 6.5 Diagnostics

> *"Test the residuals for serial correlation up to 2 lags."*

```text
Breusch-Godfrey Serial Correlation LM Test:
Null hypothesis: No serial correlation at up to 2 lags

F-statistic         1.47903      Prob. F(2,93)          0.233167
Obs*R-squared       3.05184      Prob. Chi-Square(2)    0.217421
```

No serial correlation (*p* = 0.233). The specification stands.

### 6.6 Save

> *"Save the workfile to C:\ev_mcp\guide\study.wf1"*

```text
Saved to C:\ev_mcp\guide\study.wf1.
```

You now have an ordinary `.wf1` you can open in the EViews GUI like any other. Nothing about this workflow locks your work inside the tool.

---

### 6.7 The same checks, in one call each

Sections 6.2 and 6.5 ran the unit root tests and the diagnostics one view at a
time, which is what is really happening underneath. Three tools do the whole
routine in a single step.

**Order of integration.** Ask *"test lngdp for a unit root"*:

```text
Unit root test on LNGDP (alpha = 0.05)

levels         statistic    -0.5001   p-value 0.8856     unit root not rejected
               lag length 2 (Automatic - based on SIC, maxlag=12)
1 difference   statistic   -12.1778   p-value 0.0001     stationary
               lag length 1 (Automatic - based on SIC, maxlag=11)

Conclusion: I(1)
```

It tests the levels, then successive differences, and stops at the first
rejection. The same on `lnk` also returns I(1), which is what justifies the
bounds framework for this data.

Other tests are a word away — *"use Phillips-Perron"* or *"use KPSS"*. Note that
**KPSS reverses the null**: it tests stationarity rather than a unit root, so the
"order of integration" line does not apply to it.

**Coefficients as numbers.** Ask *"show me the ARDL coefficients as a table"*:

```text
Variable                    Coefficient     Std. Error  t-Statistic        Prob.
--------------------------------------------------------------------------------
LNGDP(-1)                     0.0155166      0.0978296       0.1586       0.8743
LNK                             0.53458       0.059789       8.9411    3.027e-14
LNL                            0.365216       0.085789       4.2571    4.862e-05
C                               1.13554       0.249799       4.5458    1.611e-05
```

Same numbers as the full output, without the surrounding block — useful when you
want the assistant to compare a coefficient against a hypothesised value, or when
you are assembling your own table.

**The whole diagnostic battery.** Ask *"run the diagnostics on ardl1"*:

```text
Diagnostics for ARDL1 (alpha = 0.05)

  R-squared:             0.985599
  Adjusted R-squared:    0.985144
  S.E. of regression:    0.029251
  Durbin-Watson stat:    2.02168

  Breusch-Godfrey serial correlation
    null: no serial correlation up to 2 lags
    statistic 1.47903, p-value 0.2332 -> no evidence of serial correlation
  White heteroskedasticity
    null: homoskedasticity
    statistic 0.571757, p-value 0.635 -> no evidence of heteroskedasticity
  Jarque-Bera normality
    null: residuals are normal
    statistic 2.59087, p-value 0.2738 -> no evidence against normal residuals

All 3 diagnostics pass at the 0.05 level.
```

Two things to understand about that last line before you rely on it.

**It reads p-values, nothing more.** "Pass" means a null was not rejected at the
level you chose. It is not a judgement that the specification is sound. A model
can clear all three tests and still be misspecified — omitted variables, a
structural break, the wrong functional form — and none of these tests will say
so. The econometrics remains yours.

**A test that cannot run says so.** Some tests do not apply to some equations;
White has nothing to work with on a constant-only regression, for instance. When
that happens the report names the test and gives the reason EViews returned,
rather than quietly leaving it out:

```text
2 of 2 diagnostics reject: Breusch-Godfrey serial correlation, Jarque-Bera
normality. 1 could not be run: White heteroskedasticity.
```

Without that, a summary reading "all diagnostics pass" would be counting fewer
tests than you think it is.

In a script, the same three return structured values rather than text — a list
of coefficient dictionaries, and reports you can index into:

```python
ev.coefficients("ardl1")[1]["p_value"]     # 3.0273e-14
ev.unit_root("lngdp")["order_of_integration"]   # 1
ev.diagnose("ardl1")["tests"][0]["rejected"]    # False
```

## 7. How results are read

Worth understanding, because it explains one behaviour that surprises people.

**Running code does not print results.** EViews sends program output to its own log window, which cannot be read from outside the application. So when the assistant runs an estimation, it gets confirmation that the command succeeded — not a table.

Results are obtained separately, by *freezing* a named object into a table and reading that table. In practice this means:

> Estimate **into a named object**, then ask to see it.

```text
equation eq1.ls lngdp c lnk lnl     ← creates the object
show("eq1")                          ← reads the results
```

This is why the assistant names things. It is also why you can come back later in the session and ask *"show me eq1 again"* — the object is still in the workfile.

### Views: one object, many results

Every EViews view is available through the same mechanism, which means diagnostics need no special support:

| Ask for | View | What you get |
|---|---|---|
| Estimation output | *(default)* | The coefficient table |
| Unit root test | `uroot` | ADF on a series |
| Unit root on differences | `uroot(dif=1)` | ADF on Δ*x* |
| Descriptive statistics | `stats` | Mean, SD, skew, Jarque-Bera |
| Correlogram | `correl` | ACF and PACF |
| Residuals | `resids(t)` | Actual, fitted, residual table |
| Serial correlation | `auto(2)` | Breusch-Godfrey LM |
| Heteroskedasticity | `white` | White test |
| Coefficient restriction | `wald c(2)=c(3)` | Wald test |
| Coefficient covariance | `coefcov` | Variance-covariance matrix |
| Long-run relation (ARDL) | `cointrel` | Cointegrating equation |
| Error-correction results | `ecresults` | ECM form |
| Granger causality (VAR) | `testexog` | Block exogeneity Wald tests |
| Impulse responses (VAR) | `impulse(t)` | IRF table |
| Variance decomposition (VAR) | `decomp(10,t)` | Forecast error decomposition |

Ask in words — *"test for heteroskedasticity"* — and the assistant picks the view.

**Some views draw rather than tabulate.** `resids` and `impulse` are graphs by default; adding `t` — `resids(t)`, `impulse(t)` — asks EViews for the table form instead. That is why those two appear with `(t)` above.

**Genuine graphs are saved to a file**, since a picture cannot be returned as text:

> *"Save the residual plot to C:\work\residuals.png"*

---

## 8. Writing it up as a reproducible script

Conversation is good for finding a specification. It is bad for a paper, because a chat log is not a method section.

Once the analysis is settled, ask:

> *"Write that whole analysis as a Python script I can rerun."*

You get something like this, which is the same work as Section 6 with no assistant involved:

```python
from eviews_mcp import EViews

with EViews() as ev:
    ev.import_file(r"C:\ev_mcp\guide\macro.csv")

    # Order of integration
    for name in ("lngdp", "lnk", "lnl"):
        print(ev.show(name, "uroot"))
        print(ev.show(name, "uroot(dif=1)"))

    # Long-run model
    ev.run("equation ardl1.ardl(deplags=4, reglags=4) lngdp lnk lnl")
    print(ev.show("ardl1"))
    print(ev.show("ardl1", "cointrel"))
    print(ev.show("ardl1", "auto(2)"))

    print("R-squared:", ev.value("ardl1.@r2"))

    ev.export_object("ardl1", "residuals.png", view="resids")
    ev.save_workfile(r"C:\ev_mcp\guide\study.wf1")
```

Run it with `python study.py` and you get identical results, on any machine with EViews.

### Moving data to and from pandas

```python
frame = ev.to_dataframe(["lngdp", "lnk", "lnl"])   # indexed 1996Q1, 1996Q2, …
frame.describe()
```

Going the other way, a dated index sets the workfile frequency and span automatically:

```python
import pandas as pd

idx = pd.period_range("2005Q1", periods=40, freq="Q")
df = pd.DataFrame({"inflation": ..., "unemployment": ...}, index=idx)

ev.from_dataframe(df)          # builds a quarterly 2005Q1–2014Q4 page
ev.run("equation phillips.ls inflation c unemployment")
```

Text columns are skipped rather than causing an error.

---

## 9. Tool reference

What the assistant has available. You never call these by name — you ask in words — but knowing the vocabulary helps you ask precisely.

**Session**

| Tool | Purpose |
|---|---|
| `eviews_status` | Connection, version, active workfile |
| `reset_eviews` | Discard the instance and start clean |
| `set_eviews_visible` | Show or hide the EViews window |

**Workfiles**

| Tool | Purpose |
|---|---|
| `create_workfile` | New page by frequency and range |
| `open_workfile` / `save_workfile` | Open and save `.wf1` / `.wf2` |
| `close_workfile` | Close one or all open workfiles |
| `workfile_info` | Name, page, frequency, range, sample |
| `list_objects` | What is in the workfile |
| `set_sample` | Restrict the estimation sample |

**Running code**

| Tool | Purpose |
|---|---|
| `run_eviews_code` | Run a block of EViews program code |
| `run_program_file` | Run an existing `.prg` |
| `command` | A single command line |

**Results**

| Tool | Purpose |
|---|---|
| `show` | Render an object or view as text |
| `evaluate` | One number, e.g. `eq1.@r2` |
| `describe_object` | Type, and statistics for a series |
| `equation_coefficients` | Coefficients as a table of numbers. |
| `unit_root` | Order of integration, tested down through differences. |
| `diagnose_equation` | Serial correlation, heteroskedasticity, normality. |

**Data**

| Tool | Purpose |
|---|---|
| `read_data` | Series as a table or full-precision CSV |
| `write_series` | Write values into a series |
| `import_data` | Read `.xlsx`, `.csv`, `.dta`, `.sav`, … |
| `export_data` | Write series to a file |
| `export_object` | Save an object — how graphs come out |

---

## 10. Traps that silently corrupt results

These are properties of EViews automation that produce **wrong numbers without any error message**. The package defends against each one, but you should know they exist — especially if you also write your own EViews scripts.

### Importing into an open workfile truncates your data

If a workfile is already open, EViews imports a file *into that page* and cuts it to the page's length. A 100-row CSV read into an open 12-row page becomes 12 rows. No warning. Every result afterwards is computed on 12% of the data.

**How this package handles it:** importing creates a new workfile sized to the file by default. Merging into the current page is opt-in.

**What to do:** after any import, check `Obs in range`. It takes five seconds and it catches this instantly.

### The current sample governs writes, not just estimation

Under `smpl 2000q1 2005q4`, writing 100 values into a series writes only those inside the sample. The rest stay `NA` — silently.

**How this package handles it:** writes default to the whole page.

### A restricted sample persists

`smpl` stays in force until changed. If you restrict the sample for one test and forget, every later estimation uses the restricted sample.

**What to do:** the header of every EViews output names the sample used. Read it. If it says `Sample: 2000Q1 2005Q4` and you expected the full span, that is your answer.

### Graph exports ignore the file extension

In raw EViews automation, `graph.save "figure.png"` writes an **EMF** file with a `.png` name. Your figure will not open where you expect.

**How this package handles it:** the format is derived from the extension and passed explicitly, and a save that produces no file raises an error instead of reporting success.

### Relative paths are not relative to you

EViews resolves a relative path against *its own* working directory. Ask for `"output.csv"` and the file appears somewhere unrelated.

**How this package handles it:** all paths are made absolute before being handed to EViews.

### EViews limits how many workfiles can be open

A long session that keeps creating workfiles eventually fails with *"Maximum number of Workfiles are already open."* Ask the assistant to close workfiles you are finished with.

---

## 11. Troubleshooting

**`'python' is not recognized`**
Python is not on your PATH. Reinstall and tick *"Add python.exe to PATH"*, or use the full path to `python.exe`.

**`'eviews-mcp' is not recognized`**
The install did not add its script directory to PATH. Find it with `where eviews-mcp` and use the full path in your config file.

**`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`**
The installed version is older than 1.3.3 and pulled in an incompatible MCP SDK.
Upgrade, bypassing pip's cache in case it still lists the older release:
`pip install --upgrade --no-cache-dir "eviews-mcp[pandas]"`

**`NOT CONNECTED to EViews`**
Open EViews manually once and let it fully load — first launch may need to register its automation interface. Then retry. If EViews has never been opened since installation, do that first.

**Install fails with `Access is denied` or `file is used by another process`**
An MCP server using the package is still running. Fully quit your assistant, then reinstall.

**The assistant says it can't see EViews tools**
The config file was not read. Fully quit and reopen the application — reloading the window is not enough. Check the JSON is valid, particularly the double backslashes in Windows paths.

**A command hangs and never returns**
EViews is showing a dialog that you cannot see because the window is hidden. Ask to make EViews visible (`set_eviews_visible`), dismiss the dialog, and avoid the command that caused it.

**Results use the wrong sample**
See [the traps section](#10-traps-that-silently-corrupt-results). Read the `Sample:` line in the output header.

**`Maximum number of Workfiles are already open`**
Ask the assistant to close all workfiles, or restart the session.

---

## 12. Reproducibility and honest reporting

A few practices that keep AI-assisted work defensible.

**Ship the script, not the transcript.** Convert the final analysis into a Python script (Section 8) and include it in your replication package. A reviewer can run it; nobody can run a chat log.

**Set the seed.** If any part of your work simulates data, `rndseed` is what makes it reproducible. It is in the example in Section 6 for exactly this reason.

**Save the workfile.** The `.wf1` holds every estimated object, opens in the normal EViews GUI, and is the most complete record of what happened.

**Read the output headers.** Dependent variable, method, sample, included observations. These four lines catch most mistakes — including every trap in Section 10.

**Check the specification yourself.** The assistant will run whatever you ask and will happily estimate a badly-specified model. It handles the mechanics; the econometrics is still yours. Lag orders, deterministic terms, structural breaks, the choice of estimator — your call, your responsibility.

**Say that you used it.** In a methods or software note:

> Estimation was carried out in EViews 13, driven through the `eviews-mcp` interface (Roudane, 2026).

---

## 13. FAQ

**Does this replace EViews?**
No. It drives EViews. Without an EViews licence nothing here works.

**Can the assistant invent results?**
Not the numbers — those come back from EViews. It can misinterpret them or choose a poor specification, which is why you read the output yourself.

**Does it work on macOS or Linux?**
No. COM automation is Windows-only.

**Will it modify my existing workfiles?**
Only when asked to save. Opening a workfile and estimating into it changes the in-memory copy; nothing touches disk until a save.

**Can I still use the EViews GUI at the same time?**
Yes. Ask for the window to be made visible and you can watch and interact as normal.

**Which EViews versions work?**
Built and tested against 13. Versions 10–14 resolve through the same interface.

**Do I need to know Python?**
Not for the conversational workflow. You need it only for the scripted, reproducible version — and the assistant can write that script for you.

**Where do temporary files go?**
`C:\ev_mcp`. Generated program files are deleted after they run.

---

## Where everything lives

| | |
|---|---|
| Documentation site | [merwanroudane.github.io/MCP_EVIEWS](https://merwanroudane.github.io/MCP_EVIEWS/) |
| Package | [pypi.org/project/eviews-mcp](https://pypi.org/project/eviews-mcp/) |
| Source code | [github.com/merwanroudane/MCP_EVIEWS](https://github.com/merwanroudane/MCP_EVIEWS) |
| Issues and questions | [Report a bug or ask](https://github.com/merwanroudane/MCP_EVIEWS/issues) |
| Release history | [CHANGELOG](https://github.com/merwanroudane/MCP_EVIEWS/blob/main/CHANGELOG.md) |

Maintained by **Dr Merwan Roudane**. Licensed MIT.
