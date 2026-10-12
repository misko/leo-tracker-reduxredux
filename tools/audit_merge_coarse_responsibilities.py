"""Trace changed singleton responsibilities and correction training support."""

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

from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.analysis.regional_position_calibration import receiver_correction
from leo.application.hard60_b7 import SharedPoints
from leo.application.hard60_runner import HARD60_SCORE
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore


def main():
    sid = "fast-43ce59233fe914e1d273ee584efcd405"
    case = LOCAL / "DS20" / sid / "global-transfer"
    path = case / "protocol.json"
    protocol = json.loads(path.read_bytes())
    verify(protocol)
    prepared = load_prepared(Path(protocol["original_case"]) / "baseline.json")
    obs, _ = calibrated_band_observations(prepared.observations, protocol["fixed_band_offsets_hz"])
    terminal = json.loads((case / "cal-original/terminal.json").read_bytes())
    point = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")["basin"]
    with np.load(protocol["bank_path"]) as z:
        bank = PositionOrbitBank(**{key: z[key] for key in z.files})
    products, receipts = {}, []
    for mode in ("cal-original", "cal-joined"):
        binding = canonical_digest({"experiment": protocol, "mode": mode})
        receipt = SharedPoints(RegionalCheckpointStore(case / mode, sid, binding)).get(
            canonical_digest({}) + ":" + point
        )
        if not receipt or receipt["reason"] or receipt["result"] is None:
            raise ValueError("shared point unavailable")
        seed = receipt["result"]["bootstrap"]
        fit = receipt["result"]["fits"]["V16"]["fit"]
        if not fit["converged"]:
            raise ValueError("correction diagnostic requires stationary coarse fits")
        selected = bank.select(seed["satellite_indices"])
        model = Hard60Objective(obs, selected, RegionalPrior(), HARD60_SCORE)
        score, _, terms = model.evaluate(np.array(fit["vector"]))
        np.testing.assert_allclose(score, fit["objective"], atol=1e-6, rtol=0)
        correction = receiver_correction(obs, terms)
        winner = terms.responsibilities.argmax(axis=1)
        confidence = terms.responsibilities[np.arange(len(winner)), winner]
        products[mode] = (selected.numbers[winner], confidence, correction)
        receipts.append(
            {
                "mode": mode,
                "objective": score,
                "correction_support": list(correction.support_rows),
                "nodes_s": correction.nodes_s.tolist(),
                "knots_hz": correction.knots_hz.tolist(),
                "calibration_support_by_receiver": [
                    int(sum(obs.receiver[r] == rx for r in correction.support_rows))
                    for rx in (0, 1)
                ],
            }
        )
    old, new = (products[m] for m in ("cal-original", "cal-joined"))
    before, after = set(old[2].support_rows), set(new[2].support_rows)
    exchanged = []
    for rx in (0, 1):
        for ch in range(1, 9):
            mask = (obs.receiver == rx) & (obs.channel == ch)
            confident = mask & (old[1] >= 0.8) & (new[1] >= 0.8)
            exchanged.append(
                {
                    "receiver": rx,
                    "channel": ch,
                    "windows": int(mask.sum()),
                    "both_confident": int(confident.sum()),
                    "different_winner_both_confident": int(sum(confident & (old[0] != new[0]))),
                    "support_lost": sum(bool(mask[r]) for r in before - after),
                    "support_added": sum(bool(mask[r]) for r in after - before),
                }
            )
    delta = new[2].knots_hz - old[2].knots_hz
    result = {
        "session_id": sid,
        "point": point,
        "script_sha256": sha(Path(__file__)),
        "protocol_sha256": sha(path),
        "reference_usage": "none",
        "rows": receipts,
        "changes_by_lane": exchanged,
        "common_support": len(before & after),
        "lost_support": len(before - after),
        "added_support": len(after - before),
        "maximum_absolute_knot_change_hz": abs(delta).max(axis=1).tolist(),
        "scope": (
            "Read saved stationary coarse outputs at the same point and initial bank; "
            "reproduce their singleton objectives and apply the existing correction-training "
            "function. No optimization, reference use, identity confirmation or c ablation. "
            "This traces shared fitted-c discovery upstream of conditional final c arms."
        ),
    }
    write(REPORT / "refinement/coarse-responsibility-audit.json", result)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for rx, ax in enumerate(axes):
        for mode, (_, _, correction) in products.items():
            ax.plot(correction.nodes_s, correction.knots_hz[rx], marker="o", label=mode)
        ax.set(
            title=f"RX{rx}: correction trained from coarse responsibilities",
            xlabel="Seconds since capture start",
            ylabel="Clock correction (Hz)",
        )
        ax.grid(alpha=0.2)
        ax.legend()
    fig.suptitle("Same point, observations and initial bank · saved stationary coarse solutions")
    fig.savefig(REPORT / "refinement/coarse-responsibility-audit.png", dpi=180)
    plt.close(fig)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "scope")}), flush=True)


if __name__ == "__main__":
    main()
