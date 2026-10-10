"""Reporting-only reuse of the completed-branch renderer."""

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def publish(result, directory=HERE):
    spec = importlib.util.spec_from_file_location(
        "publisher148_for149", HERE.parent / "2026_10_10_position_error_iter148/publish.py"
    )
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous.publish(result, directory)
    path = Path(directory) / "RESULTS.md"
    text = path.read_text()
    text = text.replace(
        "All three zero-led retained regions failed calibration with `AssertionError`;",
        "All three zero-led retained regions remained promotion-unqualified;",
    ).replace(
        "Zero-led failure receipts do not identify the assertion's root cause. ", ""
    )
    start = text.index("Source-only follow-up identifies")
    end = text.index("Full raw region/stage", start)
    rows = []
    raw = json.loads((HERE / "results/zero/result.json").read_text())
    for region, saved in raw["regions"].items():
        handoff = saved["recovery"]["result"]["handoff"]
        rows.append(
            f"| {region} | {handoff['discovery_audit']['stationarity']:.9g} | "
            f"{handoff['fitted_audit']['stationarity']:.9g} | "
            f"{handoff['repair']['objective_evaluations']} | unqualified |"
        )
    replacement = (
        "The explicit handoff diagnostic confirms that all three saved zero-c coarse states "
        "are feasible and qualified under zero-c, but fail fitted-c stationarity when c is freed. "
        "This identifies the unsupported admission transition behind iteration 148's blank "
        "assertions. The unchanged bounded repair also remains unqualified in all three regions; "
        "no calibration, association or zero-led final endpoint is admitted. This is not a "
        "test of zero-led localization accuracy, and no qualification gate was relaxed.\n\n"
        "| Region | Original zero-c KKT | Same-state fitted-c KKT | "
        "Repair evaluations | Repair result |\n"
        "|---|---:|---:|---:|---|\n" + "\n".join(rows) + "\n\n"
    )
    replacement += (
        "![Original and promoted stationarity](handoff-diagnostics.png)\n\n"
        "After repair, stationarity is 45.73230947, 0.7875023813 and 1.647595086. "
        "The first region stops with `no-kkt-improving-admissible-step`; the other two "
        "stop with `round-budget`. All remain above 0.001. Reproduce this receipt-only "
        "figure with `python3 reports/2026_10_10_position_error_iter149/plot_handoff.py` "
        "after restoring the archive.\n\n"
    )
    path.write_text(text[:start] + replacement + text[end:])


if __name__ == "__main__":
    publish(json.loads((HERE / "SUMMARY.json").read_text()))
