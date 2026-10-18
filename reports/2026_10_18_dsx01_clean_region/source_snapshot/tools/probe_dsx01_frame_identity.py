"""Test conflicting blind labels on timing-linked curved fragments."""

import copy
import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_frame_joint import FrameJoint
from probe_dsx01_cut_linear import prepare
from prototype_dsx01_continuous_position import latlon
from prototype_dsx01_frame_bias import linked_tracks
from report_dsx01_joint_marginal import EvaluationAdapter
from report_dsx01_model_iterations import nominated_metrics
from run_dsx01_frame_joint import OUTPUT

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD


def replace_labels(seed, components, candidate, norad):
    result = copy.deepcopy(seed)
    for row in result["rows"]:
        if row["component"] in components:
            row.update(candidate_index=int(candidate), candidate_norad=int(norad))
    return result


def run(case):
    scan, fits, _, _, source = prepare(case)
    fit = fits["c0"]
    seed = dict(rows=fit["rows"], state=fit["state"])
    _, metadata = linked_tracks(scan, seed)
    by_key = {t["key"]: i for i, t in enumerate(scan.tracks)}
    rows_by_key = {r["component"]: r for r in fit["rows"]}
    anchor = np.asarray(fit["parameters"])
    results = []
    for edge in metadata["skipped_conflicting_candidate_edges"]:
        keys = [edge["left"], edge["right"]]
        labels = [rows_by_key[key]["candidate_index"] for key in keys]
        proposals = [("incumbent", seed, [])]
        for j in labels:
            changed = [key for key in keys if rows_by_key[key]["candidate_index"] != j]
            proposals.append(
                (
                    str(int(scan.norads[j])),
                    replace_labels(seed, set(keys), j, scan.norads[j]),
                    changed,
                )
            )
        variants = []
        for name, proposed, changed in proposals:
            aliases = list(fit["aliases"])
            row_position = {r["component"]: k for k, r in enumerate(proposed["rows"])}
            state = proposed["state"]
            for key in changed:
                i = by_key[key]
                t = scan.tracks[i]
                j = proposed["rows"][row_position[key]]["candidate_index"]
                frequency, _ = paired_phase_frequency(
                    scan.sky,
                    t["times"],
                    np.full(len(t["times"]), j, dtype=int),
                    np.asarray(state["phases"]),
                    *latlon(anchor),
                )
                radio = (
                    scan.hardware(t, state["beta"])
                    + t["rf_hz"]
                    / 11.5e9
                    * scan.rx_basis[i]
                    @ np.asarray(state["smooth"])[t["receiver"] - 1]
                )
                raw = t["values"] - radio - t["rf_hz"] / 11.5e9 * frequency
                aliases[row_position[key]] = int(np.rint(-np.mean(raw) / PERIOD))
            p = FrameJoint(
                scan,
                proposed,
                False,
                variant="linked_300",
                sigma=fit["diagnostics"]["noise_sigma_hz"],
                aliases=aliases,
                point_noise=fit["diagnostics"]["point_noise_sigma_hz"],
            )
            result = p.calculate(anchor)
            z = p.residual(anchor)
            score = float(z @ z + result["full_objective_offset"])
            adapter = EvaluationAdapter(p)
            fake = dict(
                fit,
                rows=proposed["rows"],
                state=proposed["state"],
                aliases=aliases,
                fits=[dict(parameters=anchor, score=0.0)],
            )
            metrics = nominated_metrics(
                scan,
                dict(fit=fake, method="receiver_smooth", arm="c0"),
                problem_factory=lambda *args, adapter=adapter: adapter,
            )
            target = [r for r in metrics["tracks"] if r["component"] in keys]
            variants.append(
                dict(
                    name=name,
                    changed_components=changed,
                    seed=proposed,
                    aliases=aliases,
                    full_anchor_score=score,
                    changed_pair_gate_results=target,
                    linked_groups=len(p.frame_groups),
                    phase_reference=p.reference,
                )
            )
        base = variants[0]["full_anchor_score"]
        selected = min(variants, key=lambda r: r["full_anchor_score"])
        results.append(
            dict(
                edge=edge,
                old_labels=[int(scan.norads[j]) for j in labels],
                variants=variants,
                selected=selected["name"],
                anchor_gain=base - selected["full_anchor_score"],
            )
        )
    directory = OUTPUT / "identity_probe" / case
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "proposals.json",
        dict(
            case=case,
            blind_anchor=anchor,
            no_GPS_or_future_TLE_in_proposal=True,
            only_original_curved_fragments_used=True,
            all_observation_ids_preserved=True,
            source_endpoint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            proposals=results,
        ),
    )
    print(
        json.dumps(
            dict(
                case=case,
                proposals=[
                    dict(
                        edge=r["edge"],
                        old_labels=r["old_labels"],
                        selected=r["selected"],
                        gain=r["anchor_gain"],
                        scores={v["name"]: v["full_anchor_score"] for v in r["variants"]},
                    )
                    for r in results
                ],
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    for case in ["DSX01-S01", "DSX01-S04"]:
        run(case)
