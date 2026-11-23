"""Score the sealed southern transfer and plot matched saved-solver comparisons."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_score import references
from aperture_trial import ARMS, read, write
from mixture_score import section
from paid_certified_trial import actual_exterior, check_binding, check_installed_binding, sealed


HERE = Path(__file__).resolve().parent
OFFERS = ("south-containing", "south-far")


def passed(row, scores, *, containing):
    if not containing:
        return actual_exterior(row)
    return row["status"] == "ok" and all(
        scores[arm]["delta_error_km"] is not None and scores[arm]["delta_error_km"] <= 0.25 for arm in ARMS
    )


def score(directory, summary, archive):
    raw = {case: (directory / f"{case}.json").read_bytes() for case in OFFERS}
    rows = {case: json.loads(data) for case, data in raw.items()}
    peer = rows[OFFERS[0]]["identity"]
    complete, paid, installed = (sealed(kind) for kind in ("complete", "quadratic", "installed"))
    for case, row in rows.items():
        identity = row["identity"]
        check_binding(identity, paid[case]["quadratic"]["identity"], "quadratic")
        check_installed_binding(identity, installed[case]["stock"]["identity"])
        if (any(identity[k] != peer[k] for k in ("native_sha256", "archive", "graph_parameters", "ledger", "source"))
                or identity["selection"]["mask_sha256"] != peer["selection"]["mask_sha256"]):
            raise ValueError("Southern offers must share the entire receiver packet and archive")
    truth = references()
    results = {}
    for case, row in rows.items():
        small, full = paid[case]["quadratic"], complete[case]["complete"]
        matches = {"complete_signed": full["result"], "paid_signed": small["result"], "installed": installed[case]["stock"]}
        comparisons = {name: section(row["arms"], truth[case], control["arms"]) for name, control in matches.items()}
        attempt, = row["attempts"]
        results[case] = dict(
            cpu_s=row["cpu_s"], elapsed_s=row["elapsed_s"], status=row["status"], reason=row["reason"],
            decision=attempt["decision"], attempt_reason=attempt.get("reason"), fallback=attempt.get("fallback_clocks"),
            owners=row.get("associated"), grid_points=row.get("grid_points"),
            paid_signed_cpu_s=small["charged"]["cpu_s"], same_owner_digest_as_paid_signed=row.get("owners") == small["result"].get("owners") if row["status"] == "ok" else None,
            comparisons=comparisons, passed=passed(row, comparisons["complete_signed"]["arms"], containing=case == OFFERS[0]),
        )
    write(summary, dict(cases=results, receipts={case: sha256(data).hexdigest() for case, data in raw.items()}))
    with archive.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(rows, separators=(",", ":"), allow_nan=False).encode(), mtime=0))


def plot(summary, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    north = read(HERE / "measurements/full-family-amortized-summary.json")["cases"]
    south = read(summary)["cases"]
    entry = []
    for case in ("DS30-0008", "DS30-0016"):
        row = north[case]["control"]
        match = row["versus"]["old_full_signed"]
        entry.append((match["cpu_s"], row["cpu_s"], match["arms"]))
    for case in OFFERS:
        row = south[case]
        entry.append((row["paid_signed_cpu_s"], row["cpu_s"], row["comparisons"]["paid_signed"]["arms"]))
    labels = ["DS30-0008\ncomplete", "DS30-0016\none third", "South · inside\none third", "South · omitted\none third"]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.8), layout="constrained")
    colors = ("#64748b", "#087f70")
    for i, (before, after, arms) in enumerate(entry):
        for j, (value, label, color) in enumerate(zip((before, after), ("Prior signed solver", "Full-catalogue prototype"), colors, strict=True)):
            axes[0].bar(i + (j - 0.5) * .34, value, width=.32, color=color, label=label if not i else None)
        for j, arm in enumerate(ARMS):
            v = arms[arm]
            if v["error_km"] is None:
                continue
            x = i + (j - .5) * .23
            old = v["error_km"] - v["delta_error_km"]
            axes[1].plot([x, x], [old, v["error_km"]], color="#999")
            for k, error in enumerate((old, v["error_km"])):
                axes[1].scatter(x, error, s=57 if not k else 23, marker=("o", "D")[j],
                                facecolors="none" if not k else colors[1], edgecolors=colors[k], zorder=3)
    axes[0].set_ylabel("Saved solve CPU (s)")
    axes[0].legend(frameon=False, fontsize=8)
    axes[1].set_ylabel("Horizontal position error (km)")
    axes[1].set_title("Circle = zero c     Diamond = fitted c", fontsize=10)
    axes[1].text(3, .49, "Both\nwithheld", ha="center", fontsize=9)
    for ax in axes:
        ax.set_xticks(range(4), labels, fontsize=8)
        ax.set_xlim(-.55, 3.55)
        ax.set_ylim(bottom=0)
        ax.spines[["right", "top"]].set_visible(False)
        ax.grid(axis="y", alpha=.17)
        ax.set_axisbelow(True)
    fig.suptitle("Same receiver observations within each solver comparison", fontweight="bold")
    fig.savefig(output, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "summary", "archive", "figure"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    score(args.directory, args.summary, args.archive)
    plot(args.summary, args.figure)
