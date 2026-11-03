"""Summarize every declared option and flag scientific limitations explicitly."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from experiment import ARMS, CASES, OPTIONS

HERE = Path(__file__).resolve().parent
ORDER = ("1838", "1939", "2139", "2209")


def main():
    data = {case: json.loads((HERE / case / "results.json").read_text()) for case in ORDER}
    protocols = {d["protocol_sha256"] for d in data.values()}
    assert len(protocols) == 1
    assert next(iter(protocols)) == "sha256:" + hashlib.sha256((HERE / "experiment.py").read_bytes()).hexdigest()
    rows = []
    expected_options = {o[0] for o in OPTIONS}
    for case, doc in data.items():
        assert doc["status"] == "complete" and doc["session_id"] == CASES[case]
        assert len(doc["selections"]) == 12
        assert {(r["option"], r["arm"]) for r in doc["selections"]} == {(o, a) for o in expected_options for a in ARMS}
        expected_runs = {(b, o, a) for b in doc["basins"] for o in expected_options for a in ARMS}
        assert {(r["basin"], r["option"], r["arm"]) for r in doc["runs"]} == expected_runs
        assert len(doc["runs"]) == len(expected_runs)
        for run in doc["runs"]:
            assert run["seed_sha256"] == doc["basins"][run["basin"]]["seeds"][run["arm"]]["vector_sha256"]
            assert run["error"] is None, run
        assert max(r["discrepancy"] for b in doc["basins"].values() for r in b["repricing"]) < 1e-6
        for selected in doc["selections"]:
            same = [r for r in doc["candidates"] if r["option"] == selected["option"] and r["arm"] == selected["arm"]]
            assert abs(selected["selection_score"] - min(r["selection_score"] for r in same)) < 1e-8
            if selected["arm"] == "zero-c":
                assert selected["vector"][6] == 0
            original = next(r["selected"] for r in doc["original_results"] if r["method"] == "V16" and r["arm"] == selected["arm"])
            control = next(r for r in doc["selections"] if r["option"] == "sigma015" and r["arm"] == selected["arm"])
            rows.append({"case": case, "session_id": doc["session_id"],
                         **{k:v for k,v in selected.items() if k != "vector"},
                         "original_error_m": original["horizontal_error_m"],
                         "control_error_m": control["horizontal_error_m"],
                         "error_change_vs_original_m": selected["horizontal_error_m"] - original["horizontal_error_m"],
                         "error_change_vs_control_m": selected["horizontal_error_m"] - control["horizontal_error_m"],
                         "nested_score_gap": doc["nested_search_gaps"][selected["option"]]})
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (HERE / "selected.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    groups = []
    for arm in ARMS:
        for option, sigma, sweep in OPTIONS:
            group = [r for r in rows if r["arm"] == arm and r["option"] == option]
            errors = np.array([r["horizontal_error_m"] for r in group])
            groups.append(dict(arm=arm, option=option, relative_sigma_s=sigma, timing_sweep=sweep,
                               median_error_m=float(np.median(errors)), maximum_error_m=float(errors.max()),
                               mean_error_m=float(errors.mean()), over10km=int((errors > 10000).sum()),
                               converged=sum(r["converged"] for r in group), boundary=sum(r["boundary"] for r in group),
                               improved_vs_original=sum(r["error_change_vs_original_m"] < -1e-4 for r in group),
                               worsened_vs_original=sum(r["error_change_vs_original_m"] > 1e-4 for r in group),
                               improved_vs_control=sum(r["error_change_vs_control_m"] < -1e-4 for r in group),
                               worsened_vs_control=sum(r["error_change_vs_control_m"] > 1e-4 for r in group),
                               median_data_nll=float(np.median([r["data_nll"] for r in group])),
                               median_posterior_rms_hz=float(np.median([r["posterior_rms_hz"] for r in group])),
                               median_signal_fraction=float(np.median([r["signal_fraction"] for r in group]))))
    summary = dict(protocol_sha256=next(iter(protocols)), cases=ORDER,
                   continuations=sum(len(d["runs"]) for d in data.values()),
                   total_continuation_seconds=sum(r["elapsed_s"] for d in data.values() for r in d["runs"]),
                   max_continuation_seconds=max(r["elapsed_s"] for d in data.values() for r in d["runs"]),
                   budget_seconds_per_run=12,
                   groups=groups, selected=rows,
                   limitations=["Four preselected failures used in method development; not independent validation.",
                                "Conditional continuations of own-arm original fits; no fresh upstream calibration or spatial discovery.",
                                "Every original candidate basin retained; matched final c controls and continuation caps.",
                                "Raw total scores from different prior strengths must not be compared as model quality.",
                                "Convergence and residual RMS do not establish localization accuracy."])
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for arm in ARMS:
        print(arm)
        for case in ORDER:
            original = next(r["selected"] for r in data[case]["original_results"] if r["method"] == "V16" and r["arm"] == arm)
            values = [next(r for r in rows if r["case"] == case and r["option"] == option and r["arm"] == arm) for option, _, _ in OPTIONS]
            print(case, "original", round(original["horizontal_error_m"] / 1000, 3),
                  [(v["option"], round(v["horizontal_error_m"] / 1000, 3), v["converged"], v["boundary"]) for v in values])
    plot(data)


def plot(data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    labels = ["Published\n0.15 s", "Control\n0.15 s", "0.30 s", "0.50 s", "1.00 s",
              "Timing search\n0.15 s", "Timing search\n0.50 s"]
    fig, axes = plt.subplots(2, 1, figsize=(13, 8.5), sharex=True)
    for ax, arm in zip(axes, ARMS):
        matrix, flags = [], []
        for case in ORDER:
            original = next(r["selected"] for r in data[case]["original_results"] if r["method"] == "V16" and r["arm"] == arm)
            row = [original] + [next(r for r in data[case]["selections"] if r["option"] == option and r["arm"] == arm) for option, _, _ in OPTIONS]
            matrix.append([r["horizontal_error_m"] / 1000 for r in row])
            flags.append([("!" if not r["converged"] else "") + ("B" if r["boundary"] else "") for r in row])
        matrix = np.asarray(matrix)
        image = ax.imshow(matrix, norm=LogNorm(vmin=.1, vmax=400), cmap="YlOrRd", aspect="auto")
        for i in range(4):
            for j in range(7):
                ax.text(j, i, f"{matrix[i,j]:.2f}" + flags[i][j], ha="center", va="center",
                        color="white" if matrix[i,j] > 30 else "black", fontsize=12)
        ax.set_yticks(range(4), ["18:38 · distant winner", "19:39 · shared bias", "21:39 · boundary", "22:09 · timing prior"])
        ax.set_xticks(range(7), labels)
        ax.set_title("Fitted c" if arm == "fitted-c" else "c = 0 control", loc="left", weight="bold")
    fig.suptitle("Four recent failures: position error in km (lower is better)", fontsize=16, x=.02, ha="left")
    fig.subplots_adjust(left=.22, right=.91, top=.90, bottom=.15, hspace=.22)
    cax = fig.add_axes([.93, .20, .015, .65])
    colorbar = fig.colorbar(image, cax=cax)
    colorbar.set_label("Position error, km · logarithmic scale")
    fig.text(.02, .03, "! = failed independent convergence audit; B = spatial boundary.\n"
             "Same original regions, observations, and 12 s continuation caps. Selected by each option's score.\n"
             "Exploratory failure-case comparison; upstream calibration and discovery stay frozen.", fontsize=10)
    fig.savefig(HERE / "comparison.png", dpi=170)
    fig.savefig(HERE / "comparison.svg")


if __name__ == "__main__":
    main()
