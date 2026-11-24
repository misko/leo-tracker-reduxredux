"""Partition the two measured whole-recording runs using their sealed stage clocks."""

import argparse
from pathlib import Path

from reports.ALGO08.v3.blind_saved_figure import read_receipt


def rows():
    trial = read_receipt("integrated-original.json.gz",
                         "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff")
    result = []
    for order in ("positive_first", "withholding_first"):
        pair = trial["runs"][order]
        fix, withheld = (pair[name]["result"]["document"] for name in ("DS30-0016", "DS30-0107"))
        if not all(run["qualified"] and run["process"]["exit_code"] == 0 for run in (fix, withheld)):
            raise ValueError("Both complete original workers must qualify")
        acquisition = fix["science"]["phases"]["authenticated_raw_acquisition"]["elapsed_s"]
        solve, = fix["science"]["timing"]["solve"]
        rendering, = fix["science"]["timing"]["render"]
        fix_s, withheld_s = (run["process"]["elapsed_s"] for run in (fix, withheld))
        other = fix_s - acquisition - solve["elapsed_s"] - rendering["elapsed_s"]
        if other < 0:
            raise ValueError("The measured fixing-worker stages exceed its through-exit clock")
        baseline = sum(run["installed"]["elapsed_s"] for run in (fix, withheld))
        result.append(dict(order=order, acquisition=acquisition, solve=solve["elapsed_s"],
                           render=rendering["elapsed_s"], other=other, withheld=withheld_s,
                           total=fix_s + withheld_s, baseline=baseline))
    return result


def render(path):
    import matplotlib.pyplot as plt

    data = rows()
    fig, ax = plt.subplots(figsize=(10, 3.5))
    fig.subplots_adjust(left=.19, right=.94, bottom=.26, top=.68)
    fig.suptitle("Where the two original recordings spend time", x=.025, ha="left",
                 fontsize=16, fontweight="bold")
    labels = (("acquisition", "0016 acquisition", "#336287"), ("solve", "Solve and grid", "#38827e"),
              ("render", "Render", "#c29343"), ("other", "Other on 0016", "#a8b6c1"),
              ("withheld", "Entire 0107", "#625775"))
    left = [0., 0.]
    for key, label, color in labels:
        times = [row[key] for row in data]
        ax.barh([1, 0], times, left=left, height=.46, color=color, label=label)
        left = [t + width for t, width in zip(left, times, strict=True)]
    for y, row in zip([1, 0], data, strict=True):
        ax.text(row["total"] + .10, y, f'{row["total"]:.3f} s', va="center", fontsize=10)
    target = data[0]["baseline"] / 2
    ax.axvline(target, color="#293545", ls="--", lw=1.4)
    ax.text(target, 1.48, f"2× target  {target:.3f} s", ha="center", color="#293545", fontsize=9)
    ax.set(yticks=[1, 0], yticklabels=["Fix processed first", "Withhold processed first"],
           xlabel="Single-core wall time for both recordings (seconds)", xlim=(0, 8.6), ylim=(-.43, 1.77))
    ax.spines[:].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(loc="upper left", bbox_to_anchor=(-.20, 1.47), ncol=5, frameon=False, fontsize=9)
    fig.text(.025, .04, "DS30-0016 fixed and DS30-0107 withheld in both orders. Target uses archived ALGO08v3. Admission timed separately.",
             color="#425063", fontsize=9)
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    render(parser.parse_args().output)
