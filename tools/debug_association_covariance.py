"""Reproduce selected production polynomial controls and inspect covariance sensitivity."""

import argparse
import gzip
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.nearest_neighbour_association import (
    deterministic_randomized_observation_partition,
)
from leo.analysis.persistent_hop_trajectory import (
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.research.radio_polynomial_null import (
    RadioPolynomialNullConfig,
    score_radio_polynomial_null,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.catalogue_association import CataloguePredictionSupportV1, PhysicalEpisodeGraphV1
from leo.contracts.digests import canonical_digest
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def inspect(sessions, cases, root):
    by_id = {s["session_id"]: s for s in sessions}
    store = ScannerTrackingInputStore(root)
    results = []
    try:
        for case in cases:
            source = store.load(case["session_id"])
            trajectory = reconstruct_persistent_hop_trajectories(project_scanner_candidates(source))
            a = case["association"]
            hypothesis = next(
                h for h in trajectory.hypotheses if h.hypothesis_id == a["hypothesis_id"]
            )
            graph = persistent_hop_tracklet_graph(hypothesis, a["representative_tracklet_id"])
            assert len(graph.observations) == a["scored_observation_count"]
            p = by_id[case["session_id"]]["tracking"]["product"]
            seed = canonical_digest(
                dict(
                    policy="persistent-hop-fixed-orbit-randomized-residual-v1",
                    response_free_support_digest=CataloguePredictionSupportV1.from_graph(
                        graph
                    ).content_digest,
                    selection_protocol_digest=p["configuration_digest"],
                )
            )
            rows = sorted(graph.observations, key=lambda r: r.support_center_utc_ns)
            train, evaluation = deterministic_randomized_observation_partition(
                tuple(r.observation_id for r in rows), training_fraction=0.6, split_seed=seed
            )
            config = RadioPolynomialNullConfig(
                training_observation_ids=train,
                evaluation_observation_ids=evaluation,
                observation_partition_policy="deterministic-randomized-observation-v1",
                calendar_block_duration_s=5.0,
            )
            original = score_radio_polynomial_null(graph, config)
            reproduced = min(
                s.evaluation_predictive_negative_log_likelihood for s in original.scores
            )
            assert abs(reproduced - a["radio_null_heldout_negative_log_score"]) < 1e-7
            sensitivity = []
            for extra in (0.0, 400.0, 800.0, 1600.0):
                payload = graph.model_dump(mode="json", exclude={"content_digest"})
                for row in payload["observations"]:
                    row["standard_uncertainty_hz"] = float(
                        np.hypot(row["standard_uncertainty_hz"], extra)
                    )
                altered = PhysicalEpisodeGraphV1.model_validate(
                    dict(**payload, content_digest=canonical_digest(payload))
                )
                result = score_radio_polynomial_null(altered, config)
                sensitivity.append(
                    dict(extra_sigma_hz=extra, scores=[asdict(s) for s in result.scores])
                )
            results.append(
                dict(
                    session_id=case["session_id"],
                    measurement_sigma_hz=[r.standard_uncertainty_hz for r in rows],
                    utc_bracket_ns=source.timing.first_sample_bracket_width_ns,
                    production_tle_nll=a["nominal_heldout_negative_log_score"],
                    production_null_nll=reproduced,
                    evaluation_count=len(evaluation),
                    sensitivity=sensitivity,
                )
            )
    finally:
        store.close()
    return results


def render(results, output):
    fig, axes = plt.subplots(3, 2, figsize=(13, 11))
    for axis, result in zip(axes.flat, results, strict=True):
        x = [s["extra_sigma_hz"] for s in result["sensitivity"]]
        for degree in (1, 2, 3):
            y = [
                next(
                    s["evaluation_predictive_negative_log_likelihood"]
                    for s in item["scores"]
                    if s["degree"] == degree
                )
                for item in result["sensitivity"]
            ]
            axis.plot(x, y, "o-", label=f"Polynomial degree {degree}")
        axis.axhline(
            result["production_tle_nll"],
            color="black",
            linestyle="--",
            label="Production TLE NLL (unchanged)",
        )
        axis.set_title(result["session_id"])
        axis.set_xlabel("Extra independent control uncertainty (Hz)")
        axis.set_ylabel("Evaluation NLL · lower is better")
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)
    fig.suptitle("Sensitivity diagnostic: not a corrected or calibrated association policy")
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    with gzip.open(args.audit) as stream:
        sessions = json.load(stream)["sessions"]
    results = inspect(sessions, json.loads(args.cases.read_text()), args.bulk_root)
    args.output.write_text(json.dumps(results, indent=2))
    render(results, args.output.with_suffix(".png"))
