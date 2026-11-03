"""Presentation of sealed full-cohort counts; no fitting or per-window selection."""

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
IDENTITY = REPORTS / "2026_10_17_dsx01_iteration6/recovery_identity_audit"
JOINT = REPORTS / "2026_10_17_dsx01_iteration6/full_joint_band"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read_sealed(directory, name):
    seal = json.loads((directory / "FINAL_SEAL.json").read_text())
    files = seal["files"]
    if isinstance(files, dict):
        expected = files[name]
    else:
        expected = next(r["sha256"] for r in files if Path(r["path"]).name == name)
    path = directory / name
    if digest(path) != expected:
        raise ValueError("Sealed evidence changed: " + str(path))
    return json.loads(path.read_text())


def combine(policies):
    """Retain every complete policy and require identical windows/denominators."""
    reference = None
    indexed = {}
    for method, rows in policies.items():
        current = {r["window"]: r for r in rows}
        if len(current) != len(rows) or not rows:
            raise ValueError("Unique, nonempty windows required")
        sizes = {k: r["observations"] for k, r in current.items()}
        if reference is None:
            reference = sizes
        elif reference != sizes:
            raise ValueError("Identical window cohort and denominators required")
        if any(not 0 <= r["assigned"] <= r["observations"] for r in rows):
            raise ValueError("Assignment count outside original denominator")
        indexed[method] = current
    result = []
    for window in sorted(reference):
        result.append(dict(window=window, observations=reference[window],
                           **{k: v[window]["assigned"] for k, v in indexed.items()}))
    return result


def main():
    identity = read_sealed(IDENTITY, "summary.json")
    joint = read_sealed(JOINT, "evaluation.json")
    rows = combine(dict(
        original=[r for r in identity["rows"]
                  if r["arm"] == "fitted-c" and r["method"] == "original"],
        latest_joint=[r for r in joint["windows"]
                      if r["arm"] == "fitted-c" and r["method"] == "joint"],
        highest_coverage=[r for r in identity["rows"]
                          if r["arm"] == "fitted-c" and r["method"] == "b1000"],
    ))
    assert len(rows) == 15 and sum(r["observations"] for r in rows) == 693
    totals = {key: sum(r[key] for r in rows)
              for key in ("original", "latest_joint", "highest_coverage")}
    assert totals == dict(original=96, latest_joint=420, highest_coverage=462)
    with (HERE / "window_counts.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plt.rcParams.update({"font.size": 12, "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(14, 11))
    fig.subplots_adjust(left=.22, right=.97, top=.86, bottom=.16)
    y = np.arange(len(rows))
    for offset, key, color, label in [
        (-.25, "original", "#89939e", "Original: 96 / 693"),
        (0, "latest_joint", "#2878b5", "Latest full-cohort experiment: 420 / 693 (+324)"),
        (.25, "highest_coverage", "#dd8a27", "Highest-coverage experiment: 462 / 693 (+366)"),
    ]:
        values = [r[key] for r in rows]
        ax.barh(y + offset, values, height=.22, color=color, label=label)
        for yy, value in zip(y + offset, values):
            ax.text(value + .6, yy, str(value), va="center", color=color, fontsize=10)
    ax.set_yticks(y, [f"{r['window']}  (N={r['observations']})" for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 90)
    ax.set_xlabel("Associated original GLRT observations")
    ax.grid(axis="x", color="#dddddd", alpha=.7)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.015), frameon=False, fontsize=11)
    fig.suptitle("DSX01: progress across all 15 requested windows", y=.98, fontsize=21)
    fig.text(.5, .941, "Fitted c · same 693 observations · each series is one complete policy",
             ha="center", fontsize=12)
    fig.text(.22, .025,
             "Experimental model assignments; emitter identities and geographic accuracy remain unverified.\n"
             "The satellite-bias experiment (orange) failed 39/40 temporal-transfer checks.\n"
             "Recent one-source pilots have not produced another full-cohort improvement.",
             fontsize=10, color="#444444", linespacing=1.5)
    for extension in ("png", "pdf"):
        fig.savefig(HERE / ("all_15_windows." + extension), dpi=170)
    plt.close(fig)
    evidence = dict(
        observations=693, windows=15, arm="fitted-c", totals=totals,
        net_gain={k: v - totals["original"] for k, v in totals.items()},
        policies=dict(original="Original production assignments",
                      latest_joint="Iteration6 joint-band complete five-source policy",
                      highest_coverage="Iteration4 satellite-bias sigma1000 complete policy"),
        interpretation="Development coverage; highest coverage failed temporal transfer. No new fit.",
        inputs={str(p): digest(p) for p in [IDENTITY / "summary.json", IDENTITY / "FINAL_SEAL.json",
                                            JOINT / "evaluation.json", JOINT / "FINAL_SEAL.json"]},
        outputs={p.name: digest(p) for p in [HERE / "window_counts.csv", HERE / "all_15_windows.png",
                                            HERE / "all_15_windows.pdf"]},
        generator_sha256=digest(Path(__file__)),
    )
    with (HERE / "snapshot.json").open("w") as stream:
        json.dump(evidence, stream, indent=2)
        stream.write("\n")
    print(json.dumps(evidence["totals"]))


if __name__ == "__main__":
    main()
