"""Separate added support and inherited-row reweighting in a frozen clock seed."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import LOCAL, REPORT
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write
from global_band_merge_study import verify
from scipy.optimize import least_squares

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.analysis.regional_position_score import ALIAS_HZ, circular, zero_sum_basis
from leo.application.hard60_b7 import SharedPoints
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore


def solve_line(times, residuals, squared_weights):
    """Reproduce the production nine-start bounded robust receiver-line fit."""
    counts, edges = np.histogram(residuals, bins=128, range=(-ALIAS_HZ / 2, ALIAS_HZ / 2))
    centers = (edges[:-1] + edges[1:]) / 2
    fits = []
    for index in np.argsort(-counts, kind="stable")[:3]:
        for slope in (-20.0, 0.0, 20.0):
            result = least_squares(
                lambda v: (
                    np.sqrt(squared_weights) * circular(residuals - v[0] - v[1] * times) / 200
                ),
                [centers[index], slope],
                bounds=([-np.inf, -50], [np.inf, 50]),
                loss="soft_l1",
                max_nfev=80,
                x_scale=[200, 2],
            )
            fits.append(result)
    chosen = min(fits, key=lambda f: f.cost)
    return chosen, [{"cost": f.cost, "success": f.success, "nfev": f.nfev} for f in fits]


def main():
    sid = "fast-43ce59233fe914e1d273ee584efcd405"
    case = LOCAL / "DS20" / sid / "global-transfer"
    protocol_path = case / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol)
    prepared = load_prepared(Path(protocol["original_case"]) / "baseline.json")
    obs, _ = calibrated_band_observations(prepared.observations, protocol["fixed_band_offsets_hz"])
    terminal = json.loads((case / "cal-original/terminal.json").read_bytes())
    point_key = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")["basin"]
    point = tuple(float(v) for v in point_key.split(":")[1:])
    seeds = {}
    for mode in ("cal-original", "cal-joined"):
        binding = canonical_digest({"experiment": protocol, "mode": mode})
        receipt = SharedPoints(RegionalCheckpointStore(case / mode, sid, binding)).get(
            canonical_digest({}) + ":" + point_key
        )
        if not receipt or receipt["reason"] or receipt["result"] is None:
            raise ValueError("bootstrap checkpoint unavailable")
        seeds[mode] = receipt["result"]["bootstrap"]
    original, joined = (seeds[m] for m in ("cal-original", "cal-joined"))
    if original["satellite_indices"] != joined["satellite_indices"]:
        raise ValueError("factorial requires a common candidate bank")
    if not np.array_equal(original["vector"][6:], joined["vector"][6:]):
        raise ValueError("factorial requires identical timing parameters")
    with np.load(protocol["bank_path"]) as z:
        bank = PositionOrbitBank(**{key: z[key] for key in z.files})
    indices = original["satellite_indices"]
    vector = np.array(original["vector"])
    shifts = zero_sum_basis(len(indices)) @ vector[8:] + vector[7]
    predicted = predict_orbits(
        bank.select(indices), obs, RegionalPrior(), point, shifts, derivatives=False
    )[0]
    weights = {}
    assignments = {}
    for name, seed in seeds.items():
        weights[name], assignments[name] = {}, {}
        for match in seed["matches"]:
            rows = match["rows"]
            weight = float(np.sqrt(min(len(rows), 100)) / len(rows))
            for row in rows:
                if row in weights[name]:
                    raise ValueError("factorial does not support duplicated bootstrap rows")
                weights[name][row] = weight
                assignments[name][row] = match["satellite_index"]
    old_rows, all_rows = set(weights["cal-original"]), set(weights["cal-joined"])
    if not old_rows <= all_rows or any(
        assignments["cal-original"][r] != assignments["cal-joined"][r] for r in old_rows
    ):
        raise ValueError("factorial requires retained rows and candidate assignments")
    center_time = obs.times_s - obs.time_center_s
    results, lines = [], {}
    for add_rows in (False, True):
        for reweight in (False, True):
            support = all_rows if add_rows else old_rows
            name = ("add" if add_rows else "keep") + (
                "-reweight" if reweight else "-original-weight"
            )
            fitted = []
            rx_results = []
            for rx in (0, 1):
                rows = np.array(sorted(r for r in support if obs.receiver[r] == rx))
                squares = np.array(
                    [
                        weights["cal-joined"][r]
                        if reweight or r not in old_rows
                        else weights["cal-original"][r]
                        for r in rows
                    ]
                )
                residuals = circular(
                    obs.measured_hz[rows]
                    - np.array(
                        [predicted[r, indices.index(assignments["cal-joined"][r])] for r in rows]
                    )
                )
                fit, attempts = solve_line(center_time[rows], residuals, squares)
                fitted.extend(fit.x.tolist())
                rx_results.append(
                    {
                        "receiver": rx,
                        "support_rows": len(rows),
                        "sum_squared_weight": float(squares.sum()),
                        "line_hz_hz_per_s": fit.x.tolist(),
                        "success": fit.success,
                        "attempts": attempts,
                    }
                )
            if not add_rows and not reweight:
                np.testing.assert_allclose(fitted, original["vector"][2:6], atol=0.001, rtol=0)
            if add_rows and reweight:
                np.testing.assert_allclose(fitted, joined["vector"][2:6], atol=0.001, rtol=0)
            lines[name] = np.array(fitted).reshape(2, 2)
            results.append(
                {
                    "name": name,
                    "add_rows": add_rows,
                    "reweight_inherited_rows": reweight,
                    "receivers": rx_results,
                }
            )
    for result in results:
        for rx in result["receivers"]:
            rx["change_from_original"] = (
                np.array(rx["line_hz_hz_per_s"]) - lines["keep-original-weight"][rx["receiver"]]
            ).tolist()
    write(
        REPORT / "refinement/clock-factorial-audit.json",
        {
            "session_id": sid,
            "point": point_key,
            "protocol_sha256": sha(protocol_path),
            "script_sha256": sha(Path(__file__)),
            "added_rows": sorted(all_rows - old_rows),
            "reference_usage": "none",
            "c_term": "not present in this receiver-line bootstrap",
            "scope": (
                "Fixed position, candidate assignment, orbit prediction and timing gauge. Cross "
                "adding 40 observations with changing weights of inherited rows. Added rows use "
                "joined-row weights in both addition arms. Production endpoints reproduced "
                "within 0.001 Hz or Hz/s. No downstream position re-fit or accuracy claim."
            ),
            "rows": results,
        },
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    times = np.linspace(obs.times_s.min(), obs.times_s.max(), 400)
    labels = {
        "keep-reweight": "Change weights only",
        "add-original-weight": "Add rows, keep existing weights",
        "add-reweight": "Add rows and change weights",
    }
    for name, line in lines.items():
        if name == "keep-original-weight":
            continue
        delta = line[1] - lines["keep-original-weight"][1]
        axes[0].plot(times, delta[0] + delta[1] * (times - obs.time_center_s), label=labels[name])
    axes[0].axhline(0, color="black", lw=0.8)
    axes[0].set(
        xlabel="Seconds since capture start",
        ylabel="RX1 seed change (Hz)",
        title="Clock-line change from original support and weights",
    )
    axes[0].legend(fontsize=8)
    deltas = [r["receivers"][1]["change_from_original"][1] for r in results]
    axes[1].bar(range(4), deltas)
    axes[1].set_xticks(range(4), ["Original", "Weights only", "Rows only", "Rows + weights"])
    axes[1].set(ylabel="RX1 slope change (Hz/s)", title="Matched support × weight diagnostic")
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle("DS20 sparse case · fixed candidate bank and timings · no position re-fit")
    fig.savefig(REPORT / "refinement/clock-factorial-audit.png", dpi=180)
    plt.close(fig)
    print(
        json.dumps(
            [
                {"name": r["name"], "rx1_delta": r["receivers"][1]["change_from_original"]}
                for r in results
            ]
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
