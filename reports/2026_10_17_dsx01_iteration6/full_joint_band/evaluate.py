"""Evaluate only after all twenty outcomes and training selectors are sealed."""
# ruff: noqa: E402

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import run_v2 as run
from leo.analysis.regional_position_score import coordinates

HERE = Path(__file__).resolve().parent


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else None


def paired(original, current, use):
    use = np.asarray(use, bool)
    a, b = use & original["associated"], use & current["associated"]
    both = a & b
    return dict(
        observations=int(use.sum()),
        assigned=int(b.sum()),
        associated_rms_hz=rms(current["residual_hz"][b]),
        new=int(np.sum(b & ~a)),
        lost=int(np.sum(a & ~b)),
        retained=int(both.sum()),
        intersection_original_rms_hz=rms(original["residual_hz"][both]),
        intersection_current_rms_hz=rms(current["residual_hz"][both]),
        retained_identity_changes=int(
            np.sum(both & (original["satellite_number"] != current["satellite_number"]))
        ),
    )


def classify(model, vector, nuisance):
    ev, details, best, assigned, residual = run.common.point_state(model, vector, nuisance)
    return (
        dict(
            associated=assigned,
            residual_hz=residual,
            satellite_number=model.bank.numbers[best],
            row_nll=details["row_nll"],
        ),
        ev,
        details,
    )


def evaluate():
    run.verify()
    seal_path = HERE / "outcomes_seal.json"
    seal = run.read(seal_path)
    if not seal["all20_complete"] or len(seal["records"]) != 20 or len(seal["selectors"]) != 20:
        raise ValueError("All twenty outcomes and selectors required before evaluation")
    run.verify_bindings({r["path"]: r["sha256"] for r in seal["records"]})
    run.qualifications()
    with (run.DATA / "membership.csv").open() as stream:
        members = list(csv.DictReader(stream))
    originals, states, rows, windows = {}, {}, [], []
    # Configured station metadata is first accessed here, after the global seal.
    for source in run.SOURCES:
        base = run.common.load_context(source)
        original, original_ev, original_details = classify(base.model, base.vector, base.nuisance)
        originals[source] = original
        original_position = coordinates(base.prior, base.vector[:2])
        reference = base.source.get("configured_station_reference")
        if reference is None:
            raise ValueError(
                "Explicit qualified reference metadata required for post-seal diagnostic"
            )
        reference_position = [reference["latitude_deg"], reference["longitude_deg"]]
        q_original = original_details["detection_probability"]
        observed = base.observations
        full = np.ones(len(observed.times_s), bool)
        subsets = {}
        for window in sorted({r["region_id"] for r in members if r["source_id"] == source}):
            ids = {r["observation_id"] for r in members if r["region_id"] == window}
            subsets[window] = np.isin(observed.window_ids, list(ids))
            if int(subsets[window].sum()) != len(ids):
                raise ValueError("Original requested denominator changed")
        challenge = np.logical_or.reduce(list(subsets.values()))
        original_record = dict(
            source_id=source,
            observations=int(full.sum()),
            full=paired(original, original, full),
            challenge=paired(original, original, challenge),
            objective=float(original_ev[0]),
            likelihood_nll=float(original_ev[3].nll),
            configured_reference_distance_km=run.common.distance_km(
                original_position, reference_position
            ),
            common_timing_s=float(base.vector[7]),
            relative_timing_s=base.model.basis @ base.vector[8:],
            total_timing_s=base.vector[7] + base.model.basis @ base.vector[8:],
            detection_probability=q_original,
            numbers=base.bank.numbers,
            configured_reference_authority=reference,
        )
        run.save(HERE / f"original_{source}.json", original_record)
        for arm in run.ARMS:
            for method in run.METHODS:
                selected = next(
                    r
                    for r in seal["selectors"]
                    if (r["source_id"], r["arm"], r["method"]) == (source, arm, method)
                )
                fit = run.read(HERE / f"fit_{source}_{arm}_{method}.json")
                point = selected["point"]
                v, n = np.array(point["vector"]), np.array(point["nuisance"])
                target = base if method == "fixed" else run.free_context(base)
                raw, _, _ = classify(
                    target.model, np.array(fit["vector"]), np.array(fit["nuisance"])
                )
                current, ev, details = classify(target.model, v, n)
                np.testing.assert_allclose(
                    ev[0], point["audit"]["training_objective"], atol=1e-7, rtol=0
                )
                np.testing.assert_allclose(
                    ev[3].nll, point["audit"]["training_nll"], atol=1e-7, rtol=0
                )
                data = dict(
                    current,
                    times_s=observed.times_s,
                    observation_id=np.asarray(observed.window_ids),
                    receiver=observed.receiver,
                    channel=observed.channel,
                    challenge_mask=challenge,
                )
                np.savez_compressed(HERE / f"eval_{source}_{arm}_{method}.npz", **data)
                states[source, arm, method] = current
                position = coordinates(base.prior, v[:2])
                band_model = run.free_context(base).model
                bands = (
                    band_model.original_offsets_hz
                    if method == "fixed"
                    else target.model.unpack(n)[1]
                )
                row = dict(
                    source_id=source,
                    arm=arm,
                    method=method,
                    selected=selected["selected"],
                    audit=point["audit"],
                    raw_audit=fit["audit"],
                    diagnostics=fit["diagnostics"],
                    full=paired(original, current, full),
                    challenge=paired(original, current, challenge),
                    outside=paired(original, current, ~challenge),
                    raw_full=paired(original, raw, full),
                    raw_challenge=paired(original, raw, challenge),
                    objective=float(ev[0]),
                    likelihood_nll=float(ev[3].nll),
                    prior_penalty=float(details["prior_penalty"]),
                    configured_reference_distance_km=run.common.distance_km(
                        position, reference_position
                    ),
                    latitude_deg=float(position[0]),
                    longitude_deg=float(position[1]),
                    c=float(v[6]),
                    common_timing_s=float(v[7]),
                    relative_timing_s=base.model.basis @ v[8:],
                    total_timing_s=v[7] + base.model.basis @ v[8:],
                    numbers=base.bank.numbers,
                    q=details["detection_probability"],
                    q_original=q_original,
                    q_change_rms=float(
                        np.sqrt(np.mean((details["detection_probability"] - q_original) ** 2))
                    ),
                    band_receivers=band_model.band_receivers,
                    absolute_band_offsets_hz=bands,
                    original_band_offsets_hz=band_model.original_offsets_hz,
                    band_update_hz=bands - band_model.original_offsets_hz,
                )
                rows.append(row)
                for window, use in subsets.items():
                    stats = paired(original, current, use)
                    original_count = int(np.sum(original["associated"] & use))
                    missing = int(use.sum()) - original_count
                    net = stats["assigned"] - original_count
                    windows.append(
                        dict(
                            source_id=source,
                            arm=arm,
                            method=method,
                            window=window,
                            **stats,
                            original_assigned=original_count,
                            original_missing=missing,
                            net_original_missing_restored_fraction=net / missing
                            if missing
                            else None,
                            strong_restoration_descriptive=bool(missing and net / missing >= 0.8),
                            frequency_nll=float(current["row_nll"][use].sum()),
                        )
                    )

    def merged(items):
        return {
            key: np.concatenate([s[key] for s in items])
            for key in ("associated", "residual_hz", "satellite_number", "row_nll")
        }

    old = merged([originals[s] for s in run.SOURCES])
    aggregates = []
    for arm in run.ARMS:
        control = merged([states[s, arm, "fixed"] for s in run.SOURCES])
        for method in run.METHODS:
            current = merged([states[s, arm, method] for s in run.SOURCES])
            requested = np.concatenate(
                [
                    np.load(HERE / f"eval_{s}_{arm}_{method}.npz")["challenge_mask"]
                    for s in run.SOURCES
                ]
            )
            if len(current["associated"]) != 20084 or int(requested.sum()) != 693:
                raise ValueError("All-five fixed denominator required")
            use = np.ones(20084, bool)
            matching = [r for r in rows if r["arm"] == arm and r["method"] == method]
            aggregates.append(
                dict(
                    arm=arm,
                    method=method,
                    source_count=5,
                    full_vs_original=paired(old, current, use),
                    requested_vs_original=paired(old, current, requested),
                    full_vs_matched_fixed=paired(control, current, use),
                    requested_vs_matched_fixed=paired(control, current, requested),
                    strict_selected=sum(r["audit"]["accepted"] for r in matching),
                    strict_returned=sum(r["raw_audit"]["accepted"] for r in matching),
                    charged_inference_calls=sum(r["diagnostics"]["evaluations"] for r in matching),
                    strict_warning="All raw feasible selectors retained even when nonstationary",
                    strongly_restored_windows=[
                        w["window"]
                        for w in windows
                        if w["arm"] == arm
                        and w["method"] == method
                        and w["strong_restoration_descriptive"]
                    ],
                )
            )
    run.save(
        HERE / "evaluation.json",
        dict(
            rows=rows,
            windows=windows,
            aggregates=aggregates,
            outcomes_seal_sha256=run.digest(seal_path),
            all20_sealed_before_evaluation=True,
            full_observations=20084,
            requested_observations=693,
            windows_count=15,
            scope="Full development in broad regional domain; no held validation/promotion",
            postseal_classification_objectives=45,
            public_source_replay_additional=True,
            configured_reference_read_after_global_seal=True,
        ),
    )
    print(json.dumps(run.plain(aggregates), indent=2))


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    evaluate()
