"""Inspect conditional group residuals at selected and oracle reference profiles."""

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
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter20"))
# isort: off
from newer import load_member  # noqa: E402
from dynamic_rf import DynamicRFObjective  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
# isort: on

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402


def describe(times, residual):
    centered = times - np.mean(times)
    slope = float(centered @ residual / (centered @ centered)) if np.ptp(times) > 0 else 0.0
    fitted = residual.mean() + slope * centered
    variance = np.sum((residual - residual.mean()) ** 2)
    return dict(
        count=len(times),
        mean_hz=float(residual.mean()),
        median_hz=float(np.median(residual)),
        rms_hz=float(np.sqrt(np.mean(residual**2))),
        std_hz=float(residual.std()),
        slope_hz_s=slope,
        linear_r2=float(1 - np.sum((residual - fitted) ** 2) / variance) if variance > 0 else 0.0,
        duration_s=float(np.ptp(times)),
    )


def run(label):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    binding = protocol["cases"][label]
    previous = json.loads((REPORTS / binding["result"]).read_text())["result"]
    document = json.loads((REPORTS / binding["baseline"]).read_text())
    profile = json.loads(
        (REPORTS / "2026_10_08_position_error_iter22/results" / f"{label}.json").read_text()
    )
    members = json.loads(
        (REPORTS / "2026_10_08_position_error_iter20/validation-protocol.json").read_text()
    )["members"]
    case = load_member(next(row for row in members if row["label"] == label))
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in previous["satellites"]])
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    correction = calibration["correction"]
    model = DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50)
    chosen = previous["stages"]["drift-50"]["fitted-c"]
    terms = model.evaluate_joint(
        np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    )[3]
    indices = terms.responsibilities.argmax(axis=1)
    groups = bank.numbers[indices].copy()
    groups[terms.responsibilities.max(axis=1) < 0.5] = 0
    profile_summary = json.loads(
        (REPORTS / "2026_10_08_position_error_iter22/summary.json").read_text()
    )[label]["fitted-c"]
    totals = {}
    for group in profile_summary["groups"]:
        number = group["satellite"]
        if number:
            totals[number] = totals.get(number, 0) + group["delta_nll"]
    dominant = sorted(totals, key=totals.get, reverse=True)[:2]
    results = {}
    obs = model.observations
    for arm in ("fitted-c", "zero-c"):
        figure, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
        results[arm] = {}
        for row_index, (phase, step) in enumerate(
            (("selected", 0), ("reference", profile["step_count"]))
        ):
            row = next(r for r in profile["rows"] if r["arm"] == arm and r.get("step") == step)[
                "attempts"
            ][-1]
            value, _, _, terms = model.evaluate_joint(
                np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
            )
            np.testing.assert_allclose(value, row["objective"], atol=1e-6, rtol=0)
            residual = terms.residual_hz[np.arange(len(indices)), indices]
            statistics = {}
            for number in np.unique(groups):
                mask = groups == number
                entry = dict(by_receiver={})
                for rx in (0, 1):
                    use = mask & (obs.receiver == rx)
                    if use.any():
                        entry["by_receiver"][str(rx)] = describe(obs.times_s[use], residual[use])
                # Exact rounded-ms/channel coincidences only, not nearest-neighbour time joins.
                pairs = {}
                for i in np.flatnonzero(mask):
                    key = (round(float(obs.times_s[i]), 3), int(obs.channel[i]))
                    pairs.setdefault(key, {}).setdefault(int(obs.receiver[i]), []).append(
                        residual[i]
                    )
                differences = [
                    np.mean(v[1]) - np.mean(v[0]) for v in pairs.values() if 0 in v and 1 in v
                ]
                entry["coincident_pairs"] = dict(
                    count=len(differences),
                    mean_rx1_minus_rx0_hz=float(np.mean(differences)) if differences else None,
                    rms_difference_hz=float(np.sqrt(np.mean(np.square(differences))))
                    if differences
                    else None,
                )
                statistics[str(int(number))] = entry
            results[arm][phase] = dict(groups=statistics, residual_hz=residual.tolist())
            for column, number in enumerate(dominant):
                ax = axes[row_index, column]
                for rx in (0, 1):
                    use = (groups == number) & (obs.receiver == rx)
                    ax.scatter(obs.times_s[use], residual[use], s=9, alpha=0.6, label=f"RX{rx}")
                ax.axhline(0, color="black", linewidth=1)
                ax.set(
                    title=f"{label}, {number}, {arm}, {phase}",
                    xlabel="Time (s)",
                    ylabel="Residual (Hz)",
                )
                ax.grid(alpha=0.2)
                ax.legend()
        figure.savefig(HERE / f"{label}-{arm}.png", dpi=140)
        plt.close(figure)
    write_json(
        HERE / "results" / f"{label}.json",
        json_value(
            dict(
                label=label,
                groups=groups,
                times_s=obs.times_s,
                receiver=obs.receiver,
                channel=obs.channel,
                dominant_satellites=dominant,
                arms=results,
                scope="Conditional assignments; reference residuals are oracle diagnostics only",
            )
        ),
    )
    print(label, dominant, "complete", flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
