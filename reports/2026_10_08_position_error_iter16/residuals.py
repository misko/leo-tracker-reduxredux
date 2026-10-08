"""Conditional residual structure on fixed development fits; no new fitting."""

import hashlib
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path[:0] = [
    str(REPORTS / "2026_10_08_position_error_iter13"),
    str(REPORTS / "2026_10_08_hard60_bounded_recovery"),
]
from inputs import json_value, write_json  # noqa: E402
from post_prune import JointClockObjective, load_basis  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402


def describe(times, residual, receiver, channel):
    pairs = []
    gaps = []
    for rx, ch in sorted(set(zip(receiver.tolist(), channel.tolist(), strict=True))):
        order = np.flatnonzero((receiver == rx) & (channel == ch))
        order = order[np.argsort(times[order], kind="stable")]
        dt = np.diff(times[order])
        gaps.extend(dt.tolist())
        for a, b, gap in zip(order[:-1], order[1:], dt, strict=True):
            if 0 < gap <= 2:
                pairs.append((residual[a], residual[b]))
    pair_array = np.asarray(pairs)
    correlation = None
    if len(pairs) >= 10 and np.all(np.std(pair_array, axis=0) > 1e-6):
        correlation = float(np.corrcoef(pair_array.T)[0, 1])
    bins = []
    for slot in np.unique(np.floor(times / 30)):
        mask = np.floor(times / 30) == slot
        bins.append(
            dict(
                start_s=float(30 * slot),
                count=int(mask.sum()),
                mean_hz=float(residual[mask].mean()),
            )
        )
    return dict(
        count=len(times),
        mean_hz=float(residual.mean()),
        median_hz=float(np.median(residual)),
        rms_hz=float(np.sqrt(np.mean(residual**2))),
        std_hz=float(residual.std()),
        duration_s=float(np.ptp(times)),
        distinct_times=len(np.unique(times)),
        adjacent_pair_count=len(pairs),
        adjacent_correlation=correlation,
        median_within_receiver_channel_gap_s=float(np.median(gaps)) if gaps else None,
        bins_30s=bins,
    )


def run(label):
    source = REPORTS / "2026_10_08_position_error_iter13/results" / f"{label}.json"
    previous = json.loads(source.read_text())
    protocol = json.loads((REPORTS / "2026_10_08_position_error_iter13/protocol.json").read_text())
    case, document, base = load_basis(label, protocol["consumed_ds17_labels"])
    lookup = {int(n): i for i, n in enumerate(base.bank.numbers)}
    bank = base.bank.select([lookup[n] for n in previous["satellites"]])
    subset = Hard60Objective(
        base.observations, bank, base.prior, base.score, receiver_baseline_hz=base.baseline
    )
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    model = JointClockObjective(subset, correction["nodes_s"], correction["knots_hz"], 4)
    fitted = next(
        r for r in previous["candidates"] if r["variant"] == "post-200" and r["arm"] == "fitted-c"
    )
    terms = model.evaluate_joint(
        np.asarray(fitted["vector"]), np.asarray(fitted["clock_coefficients"])
    )[3]
    indices = terms.responsibilities.argmax(axis=1)
    groups = bank.numbers[indices].copy()
    groups[terms.responsibilities.max(axis=1) < 0.5] = 0
    dominant = [67908, 65908] if label == "S41" else [63860, 63870]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    results = {}
    obs = model.observations
    for row, arm in enumerate(("fitted-c", "zero-c")):
        chosen = next(
            r for r in previous["candidates"] if r["variant"] == "post-200" and r["arm"] == arm
        )
        assert chosen["converged"]
        value, _, _, terms = model.evaluate_joint(
            np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
        )
        np.testing.assert_allclose(value, chosen["objective"], atol=1e-6, rtol=0)
        residual = terms.residual_hz[np.arange(len(indices)), indices]
        stats = {}
        for number in np.unique(groups):
            mask = groups == number
            stats[str(number)] = describe(
                obs.times_s[mask], residual[mask], obs.receiver[mask], obs.channel[mask]
            )
            stats[str(number)]["by_receiver"] = {
                str(rx): describe(obs.times_s[m], residual[m], obs.receiver[m], obs.channel[m])
                for rx in (0, 1)
                if (m := mask & (obs.receiver == rx)).any()
            }
        results[arm] = dict(
            groups=stats, residual_hz=residual.tolist(), error_km=chosen["error_km"]
        )
        for col, number in enumerate(dominant):
            ax = axes[row, col]
            for rx in (0, 1):
                mask = (groups == number) & (obs.receiver == rx)
                ax.scatter(obs.times_s[mask], residual[mask], s=9, alpha=0.65, label=f"RX{rx}")
            ax.axhline(0, color="black", linewidth=1)
            ax.set(
                title=f"{label}, group {number}, {arm}",
                xlabel="Time from scan start (s)",
                ylabel="Conditional residual (Hz)",
            )
            ax.grid(alpha=0.2)
            ax.legend()
    fig.savefig(HERE / f"{label}.png", dpi=160)
    write_json(
        HERE / "results" / f"{label}.json",
        json_value(
            dict(
                label=label,
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                groups=groups,
                times_s=obs.times_s,
                receiver=obs.receiver,
                channel=obs.channel,
                rf_hz=obs.rf_hz,
                arms=results,
                interpretation=(
                    "Conditional on fitted-c assignments; "
                    "repeated evidence is not necessarily independent"
                ),
            )
        ),
    )
    print(label, "complete", flush=True)


if __name__ == "__main__":
    for label in ("S41", "DS17-040"):
        run(label)
