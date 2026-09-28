"""Descriptive conditional-LOSO ratio residual-sum audit; no fitting."""
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

import mixture_calibration_inputs as inputs
import mixture_reception_core as core

HERE = Path(__file__).resolve().parent


def ratio_moments(track, theta, layout):
    matched = track.matched
    if not np.any(matched):
        return None
    pd = layout.detection_size
    logits = np.einsum("knp,p->kn", track.detection_design, theta[:pd])
    detection_ll = (matched[None, :] * logits - np.logaddexp(0., logits)).sum(axis=1)
    log_weights = track.log_weights + detection_ll
    weights = np.exp(log_weights - logsumexp(log_weights))
    means = np.einsum("knp,p->kn", track.ratio_design[:, matched, :], theta[pd:-1])
    residual = track.log_ratio[matched] - weights @ means
    candidate_sum = means.sum(axis=1)
    variance = (np.exp(2 * theta[-1]) * matched.sum() +
                weights @ ((candidate_sum - weights @ candidate_sum) ** 2))
    return float(residual.sum() ** 2), float(variance), int(matched.sum())


def run():
    tracks, receipt = inputs.load_joined()
    result = {"arms": {}, "sources": receipt["source_hashes"],
              "fold_sha256": {},
              "interpretation": "Descriptive conditional ratio residual-sum dispersion. Candidate weights condition on detection outcomes only, never ratio outcomes. Shared-candidate variance is included. Frozen frequency priors use all six sessions; reception coefficients are LOSO. Mean bias, dependence, variance error, or incorrect identities can all cause excess dispersion."}
    for arm in ("M0", "mean", "mixture"):
        numerator = denominator = 0.
        count = rows = 0
        for sid in receipt["sessions"]:
            train = tuple(t for t in tracks if t.session_id != sid)
            held = tuple(t for t in tracks if t.session_id == sid)
            tensors, layout, _ = inputs.build_arm(held, inputs.fit_schema(train), arm, core)
            path = HERE / f"mixture-calibration-polished-fold-{sid}.json"
            payload = path.read_bytes(); artifact = json.loads(payload)
            if artifact["held_session"] != sid or not artifact["all_models_converged"]:
                raise ValueError("invalid held fold")
            result["fold_sha256"][sid] = inputs.digest(payload)
            theta = np.asarray(artifact["models"][arm]["polish"]["theta"])
            for track in tensors:
                moment = ratio_moments(track, theta, layout)
                if moment is not None:
                    n, d, m = moment
                    numerator += n; denominator += d; rows += m; count += 1
        result["arms"][arm] = {"matched_tracks": count, "matched_rows": rows,
                              "residual_sum_squared": numerator,
                              "expected_variance_sum": denominator,
                              "dispersion_ratio": numerator / denominator}
    result["code_sha256"] = inputs.digest(Path(__file__).read_bytes())
    with (HERE / "calibration_ratio_dispersion.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    run()
