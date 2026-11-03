"""Attribute the conditional wrong-versus-reference data score to observed blocks."""
import json
from dataclasses import replace

import numpy as np

from oracle import HERE, CONTROLS, load


def main():
    from leo.analysis.regional_position_score import PositionObjective, predict_orbits, ALIAS_HZ
    from leo.contracts.regional_position import PositionScore
    profile = json.loads((HERE / "bias_profile_results.json").read_text())
    assert profile["status"] == "complete"
    doc, receipt, obs, prior, bank, checkpoint, prefix = load("1939")
    rows = []
    for arm in CONTROLS.ARMS:
        endpoints = [r for r in profile["rows"] if r["arm"] == arm and r["fraction"] in (0., 1.)]
        assert len(endpoints) == 2 and all(r["converged"] for r in endpoints)
        basin = endpoints[0]["basin"]
        association = checkpoint.get(prefix + ":" + basin + ":association")["result"]
        calibration = checkpoint.get(prefix + ":" + basin + ":calibration")["result"]
        obj = PositionObjective(obs, bank.select(association["selected_indices"]), prior,
                                replace(PositionScore(**doc["configuration"]["scores"]["V16"]), relative_sigma_s=1.),
                                receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]))
        nll, support = {}, {}
        for r in endpoints:
            vector = np.asarray(r["vector"])
            value, _, terms = obj.evaluate(vector)
            assert abs(value - r["objective"]) < 1e-6
            _, visible, _, _ = predict_orbits(obj.bank, obs, prior, vector[:2], vector[7] + obj.basis @ vector[8:])
            # Recover per-window public singleton likelihood from its clutter posterior.
            log_p0 = -obj.score.clutter_rate + visible.sum(axis=1) * np.log1p(-obj.score.detection_budget / len(obj.bank.numbers))
            log_h = np.log(obj.score.clutter_rate / ALIAS_HZ) - np.log(terms.clutter_probability)
            per_window = -log_p0 + np.log(-np.expm1(log_p0)) - log_h
            np.testing.assert_allclose(per_window.sum(), terms.nll, atol=1e-7, rtol=0)
            nll[r["fraction"]] = per_window
            support[r["fraction"]] = terms.responsibilities.sum(axis=1)
        delta = nll[1.] - nll[0.]
        midpoint = (obs.times_s.min() + obs.times_s.max()) / 2
        masks = {"all": np.ones(len(delta), bool), "early": obs.times_s <= midpoint, "late": obs.times_s > midpoint,
                 **{f"rx{rx}": obs.receiver == rx for rx in np.unique(obs.receiver)},
                 **{f"channel{channel}": obs.channel == channel for channel in np.unique(obs.channel)}}
        blocks = {name: dict(windows=int(mask.sum()), reference_minus_wrong_data_nll=float(delta[mask].sum()),
                             wrong_signal_mass=float(support[0.][mask].sum()), reference_signal_mass=float(support[1.][mask].sum()))
                  for name, mask in masks.items()}
        worst = np.argsort(delta)[-20:][::-1]
        examples = [dict(window_id=obs.window_ids[i], time_s=float(obs.times_s[i]), receiver=int(obs.receiver[i]),
                         channel=int(obs.channel[i]), rf_hz=float(obs.rf_hz[i]), measured_hz=float(obs.measured_hz[i]),
                         reference_minus_wrong_data_nll=float(delta[i])) for i in worst]
        rows.append(dict(arm=arm, blocks=blocks, largest_wrong_preference_windows=examples))
        print(arm, json.dumps(blocks), flush=True)
    (HERE / "profile_breakdown.json").write_text(json.dumps(dict(rows=rows), indent=2) + "\n")


if __name__ == "__main__":
    main()
