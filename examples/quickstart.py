"""A short tour of the library API.

Run it with EViews installed:

    python examples/quickstart.py
"""

import numpy as np
import pandas as pd

from eviews_mcp import EViews

with EViews() as ev:
    print("EViews version:", ev.version)

    # --- build a workfile and estimate something -------------------------
    ev.create_workfile("q", "1990q1", "2020q4", name="demo")
    ev.run(
        """
        rndseed 42
        series k   = 100 + @trend + 3*@nrnd
        series l   = 50 + 0.5*@trend + 2*@nrnd
        series gdp = 10 + 0.6*k + 0.3*l + 2*@nrnd
        equation eq1.ls gdp c k l
        """
    )

    # --- read the results ------------------------------------------------
    print(ev.show("eq1"))
    print("R-squared:", ev.value("eq1.@r2"))
    print("Coefficient on k:", ev.value("eq1.@coefs(2)"))

    # Any EViews view works, so diagnostics need no extra API.
    print(ev.show("eq1", "wald c(2)=c(3)"))
    print(ev.show("gdp", "uroot"))

    # --- move data to pandas and back ------------------------------------
    frame = ev.to_dataframe(["gdp", "k", "l"])
    print(frame.head())
    print("Correlation:\n", frame.corr())

    # A dated index decides the page frequency and span.
    rng = np.random.default_rng(7)
    index = pd.period_range("2005Q1", periods=40, freq="Q")
    unemployment = 7.0 - 0.05 * np.arange(40) + rng.normal(0, 0.4, 40)
    outside = pd.DataFrame(
        {"inflation": 9.0 - 0.9 * unemployment + rng.normal(0, 0.5, 40),
         "unemployment": unemployment},
        index=index,
    )
    ev.from_dataframe(outside)
    print("Page is now:", ev.workfile_info()["range"])

    ev.run("equation phillips.ls inflation c unemployment")
    print(ev.show("phillips"))

    # --- graphs come out as files ----------------------------------------
    ev.export_object("phillips", "phillips_residuals.png", view="resids")
    print("Wrote phillips_residuals.png")
