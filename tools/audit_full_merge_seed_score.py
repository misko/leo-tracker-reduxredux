"""Decompose saved original/joined seed scores at a data-selected search point.

No refitting, reference coordinates or changes to the frozen numerical models.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import REPORT
from clock_conditioned_merge_study import verify
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write
from full_incumbent_merge_study import OUTPUT
from incumbent_clock_merge_study import restore

from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.profiled_position_bootstrap import bootstrap_coherence_cost
from leo.analysis.regional_position_score import ALIAS_HZ, circular, zero_sum_basis
from leo.application.hard60_b7 import SharedPoints
from leo.application.hard60_runner import HARD60_SCORE
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore


def decompose(observations, bank, tracks, seed):
    subset = bank.select(list(seed.satellite_indices))
    shifts = seed.vector[7] + zero_sum_basis(len(seed.satellite_indices)) @ seed.vector[8:]
    point = seed.vector[:2]
    predicted, visible, _, _ = predict_orbits(
        subset, observations, RegionalPrior(), point, shifts, derivatives=False
    )
    centered = observations.times_s - observations.time_center_s
    correction = seed.vector[2 + 2 * observations.receiver]
    correction += seed.vector[3 + 2 * observations.receiver] * centered
    rows = []
    for index, track in enumerate(tracks):
        ix = np.array(track)
        matches = [m for m in seed.matches if set(track) <= set(m.rows)]
        if len(matches) > 1:
            raise ValueError("ambiguous saved support assignment")
        supported = np.zeros(len(ix), dtype=bool)
        residual = np.full(len(ix), ALIAS_HZ / 2)
        catalogue = None
        if matches:
            column = seed.satellite_indices.index(matches[0].satellite_index)
            catalogue = int(subset.numbers[column])
            supported = visible[ix, column]
            residual[supported] = circular(
                observations.measured_hz[ix[supported]]
                - predicted[ix[supported], column]
                - correction[ix[supported]]
            )
        weight = np.sqrt(min(len(ix), 100)) / len(ix)
        contribution = weight * 2 * 200**2 * (np.sqrt(1 + (residual / 200) ** 2) - 1)
        rows.append(
            {
                "track_index": index,
                "receiver": int(observations.receiver[ix[0]]),
                "channel": int(observations.channel[ix[0]]),
                "rows": len(ix),
                "catalogue_number": catalogue,
                "assigned": bool(matches),
                "visible_rows": int(sum(supported)),
                "penalty_rows": int(sum(~supported)),
                "supported_rms_hz": float(np.sqrt(np.mean(residual[supported] ** 2)))
                if any(supported)
                else None,
                "supported_cost": float(sum(contribution[supported])),
                "unsupported_cost": float(sum(contribution[~supported])),
            }
        )
    reconstructed = sum(r["supported_cost"] + r["unsupported_cost"] for r in rows)
    cost = bootstrap_coherence_cost(observations, bank, RegionalPrior(), point, tracks, seed)
    if abs(reconstructed - cost) > max(1e-6, abs(cost) * 1e-12):
        raise ValueError("seed coherence decomposition failed closure")
    value, _, terms = Hard60Objective(observations, subset, RegionalPrior(), HARD60_SCORE).evaluate(
        seed.vector
    )
    return {
        "coherence": cost,
        "tracks": rows,
        "unsupported_cost": sum(r["unsupported_cost"] for r in rows),
        "supported_cost": sum(r["supported_cost"] for r in rows),
        "mixture_seed_objective": value,
        "mixture_seed_nll": terms.nll,
        "mixture_seed_signal_mass": float(sum(terms.responsibilities.sum(axis=1))),
        "catalogue_numbers": subset.numbers.tolist(),
    }


def main():
    protocol_path = OUTPUT / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol["bindings"])
    case = protocol["cases"][0]
    if case["dataset"] != "DS20":
        raise ValueError("expected first pinned DS20 development case")
    old = Path(case["original_case"])
    prepared = load_prepared(old / "baseline.json")
    with np.load(case["bank_path"]) as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    base = OUTPUT / case["dataset"] / case["session_id"]
    paths = sorted((base / "raw-joined-control/bootstrap-audits").glob("*.json"))
    if not paths:
        raise ValueError("saved joined bootstrap audits required")
    snapshots = [(p, json.loads(p.read_bytes())) for p in paths]
    path, audit = max(
        snapshots,
        key=lambda pair: (
            pair[1]["candidates"][0]["score"] - pair[1]["candidates"][pair[1]["selected"]]["score"],
            pair[1]["point"],
        ),
    )
    records, bindings = {}, {str(protocol_path): sha(protocol_path)}
    bindings.update({str(p): sha(p) for p in paths})
    for mode in ("original-control", "joined-control"):
        condition = base / ("raw-" + mode)
        binding = canonical_digest(
            {
                "protocol_sha256": sha(protocol_path),
                "case": case,
                "calibration": "raw",
                "mode": mode,
            }
        )
        e, n = audit["point"]
        key = canonical_digest({}) + f":point:{e:g}:{n:g}"
        receipt = SharedPoints(RegionalCheckpointStore(condition, case["session_id"], binding)).get(
            key
        )
        if receipt is None or receipt["result"] is None:
            raise ValueError("completed coarse point required in both controls")
        data = receipt["result"]
        seed = restore(data["bootstrap"])
        if seed.vector[6] != 0:
            raise ValueError("diagnostic seed RF coefficient must be zero")
        records[mode] = decompose(prepared.observations, bank, prepared.bootstrap_tracks, seed)
        expected = audit["candidates"][0 if mode == "original-control" else audit["selected"]][
            "score"
        ]
        if abs(records[mode]["coherence"] - expected) > max(1e-6, abs(expected) * 1e-12):
            raise ValueError("saved bootstrap audit score differs from reconstructed seed")
        fitted = data["fits"]["V16"]["fit"]
        records[mode]["saved_coarse_fit"] = {
            k: fitted[k]
            for k in (
                "objective",
                "converged",
                "stationarity",
                "posterior_rms_hz",
            )
        }
        records[mode]["point_receipt_sha256"] = canonical_digest(receipt)
    before, after = (records[m] for m in ("original-control", "joined-control"))
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True)
    for receiver, axis in enumerate(axes):
        rows = [r for r in before["tracks"] if r["receiver"] == receiver]
        x = np.arange(len(rows))
        for offset, mode, color in (
            (-0.18, "original-control", "tab:blue"),
            (0.18, "joined-control", "tab:orange"),
        ):
            values = {r["track_index"]: r for r in records[mode]["tracks"]}
            axis.bar(
                x + offset,
                [
                    values[r["track_index"]]["supported_rms_hz"] / 1000
                    if values[r["track_index"]]["supported_rms_hz"] is not None
                    else np.nan
                    for r in rows
                ],
                width=0.36,
                color=color,
                label=mode,
            )
        axis.set_xticks(x, [f"P{r['track_index']} CH{r['channel']}" for r in rows], fontsize=8)
        axis.set_ylabel("Common-clock seed residual RMS (kHz)")
        axis.set_title(f"RX{receiver} · original bootstrap proposal indices")
        axis.grid(axis="y", alpha=0.2)
        axis.legend(fontsize=8)
    fig.suptitle(
        f"Saved seeds at ({audit['point'][0]}, {audit['point'][1]}) km · largest coherence gain\n"
        "RF coefficient c=0; before coarse fitting; all original supports assigned and visible"
    )
    figure_path = REPORT / "full-incumbent/seed-score-residuals.png"
    fig.savefig(figure_path, dpi=160)
    plt.close(fig)
    write(
        REPORT / "full-incumbent/seed-score-audit.json",
        {
            "point": audit["point"],
            "dataset": case["dataset"],
            "session_id": case["session_id"],
            "selection": (
                "Largest saved coherence gain in first joined control; posthoc diagnostic only"
            ),
            "audited_snapshot_points": len(paths),
            "selection_audit": str(path),
            "records": records,
            "changes": {
                "coherence": after["coherence"] - before["coherence"],
                "unsupported_cost": after["unsupported_cost"] - before["unsupported_cost"],
                "supported_cost": after["supported_cost"] - before["supported_cost"],
                "mixture_seed_nll": after["mixture_seed_nll"] - before["mixture_seed_nll"],
            },
            "input_bindings": bindings,
            "script_sha256": sha(Path(__file__)),
            "figure_sha256": sha(figure_path),
            "reference_usage": "none",
            "scope": "Saved point diagnostic, not refitting or geographic evaluation",
        },
    )
    print(
        json.dumps(
            {m: {k: v for k, v in r.items() if k != "tracks"} for m, r in records.items()}, indent=2
        )
    )


if __name__ == "__main__":
    main()
