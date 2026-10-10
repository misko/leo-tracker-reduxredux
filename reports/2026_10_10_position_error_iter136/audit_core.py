"""Fixed-endpoint correlation score only; no optimizer or position reference."""

from collections import defaultdict

import numpy as np
from pair_score import pair_rows, zero_score


def summary(scores):
    values = np.asarray(scores, float)
    return dict(
        pairs=len(values),
        score_sum=float(values.sum()),
        score_mean=float(values.mean()) if len(values) else None,
        positive_pairs=int(np.sum(values > 0)),
        interpretation="conditional descriptive score, not a calibrated independence test",
    )


def audit(model, archive, support):
    """Pair acquisition support before evaluating either ordinary saved endpoint."""
    rows = support["rows"]
    if [r["window_id"] for r in rows] != list(model.observations.window_ids):
        raise ValueError("support rows differ from model observation order")
    pairing = pair_rows(rows)
    sigma = float(model.score.sigma_hz)
    if sigma != 125.0:
        raise ValueError("only frozen 125 Hz narrow-density audit is reviewed")
    endpoints = archive["stages"]["B7"]
    arms = {}
    for arm in ("fitted-c", "zero-c"):
        saved = endpoints[arm]
        value, _, _, terms = model.evaluate_joint(
            np.asarray(saved["vector"]).copy(),
            np.asarray(saved["clock_coefficients"]).copy(),
        )
        if not np.isfinite(value) or abs(value - saved["objective"]) > 1e-6:
            raise ValueError("ordinary archived objective mismatch: " + arm)
        score = zero_score(terms.responsibilities, terms.residual_hz / sigma, pairing["pairs"])
        groups = defaultdict(list)
        details = []
        for index, (first, second) in enumerate(pairing["pairs"]):
            row = rows[first]
            group = (row["receiver"], row["channel"], row["actual_rf_hz"], row["edge"])
            block = len(groups[group]) % 2
            groups[group].append(index)
            details.append(
                dict(
                    first_window_id=row["window_id"],
                    second_window_id=rows[second]["window_id"],
                    group=list(group),
                    alternating_block=block,
                    score=score["pair_scores"][index],
                    shared_label_mass=score["shared_label_mass"][index],
                )
            )
        arms[arm] = dict(
            archive_objective_delta=float(value - saved["objective"]),
            frequency_nll=float(terms.nll),
            **summary(score["pair_scores"]),
            pair_details=details,
            groups=[
                dict(
                    identity=list(group),
                    **summary([score["pair_scores"][i] for i in indices]),
                    shared_label_mass_sum=float(
                        sum(score["shared_label_mass"][i] for i in indices)
                    ),
                    alternating_blocks=[
                        summary([score["pair_scores"][i] for i in indices[block::2]])
                        for block in (0, 1)
                    ],
                )
                for group, indices in sorted(groups.items())
            ],
        )
    return dict(
        status="complete",
        observations=len(rows),
        pairing=pairing,
        support_unavailable_reasons=support["unavailable_reasons"],
        arms=arms,
        optimizer_calls=0,
        correlation_parameter_selected=False,
        position_evaluation=False,
        approximation="125 Hz production nearest-image residual; omitted-image score underflows",
    )
