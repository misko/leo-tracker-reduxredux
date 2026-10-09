"""Five-member generic recovery pilot, one bounded baseline/candidate slice."""

import argparse
import copy
import hashlib
import importlib.util
import os
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from inventory import regional_triggers
from overlay import Overlay, claim_slice, read, write

from leo.application.hard60_b7 import B7_POLICY, SharedPoints, regional_winners, run_joint_stages
from leo.application.hard60_runner import Hard60Configuration, run_hard60

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location(
    "direct_chain103_for105", HERE.parent / "2026_10_09_position_error_iter103/run.py"
)
direct = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(direct)
core = direct.continuation


def source_compatibility(document):
    reasons = []
    ignored_nonnumeric_mismatches = []
    sources = document["configuration"].get("source_digests", {})
    required = {
        "application/hard60_runner.py",
        "analysis/hard60_score.py",
        "analysis/regional_position_fit.py",
        "analysis/regional_position_bootstrap.py",
        "analysis/regional_position_calibration.py",
        "analysis/regional_position_inputs.py",
    }
    # Input preparation is application-owned; retain its actual public source key.
    required.discard("analysis/regional_position_inputs.py")
    required.add("application/regional_position_inputs.py")
    for name in sorted(required - sources.keys()):
        reasons.append("missing-source-identity:" + name)
    for name, expected in sources.items():
        path = ROOT / "src/leo" / name
        if (
            not path.is_file()
            or "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            if name == "application/regional_position_report.py":
                ignored_nonnumeric_mismatches.append(name)
            else:
                reasons.append("source-mismatch:" + name)
    if core.canonical_digest(document["configuration"]["scores"]["V16"]) != core.canonical_digest(
        core.json_value(core.HARD60_SCORE)
    ):
        reasons.append("score-mismatch")
    if core.canonical_digest(document["configuration"]["run"]) != core.canonical_digest(
        core.json_value(Hard60Configuration())
    ):
        reasons.append("run-configuration-mismatch")
    return dict(
        eligible=not reasons,
        reasons=reasons,
        ignored_nonnumeric_mismatches=ignored_nonnumeric_mismatches,
    )


def load_case(document):
    store = core.ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(document["session_id"])
    finally:
        store.close()
    for field in ("input_manifest_sha256", "analysis_manifest_sha256"):
        assert getattr(source, field) == document[field], field
    prepared = core.prepare_position_windows(source)
    archive = core.TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
    assert snapshot.digest == document["diagnostics"]["snapshot_sha256"]
    payload, _ = core.exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = core.parse_element_sets(payload)
    indices = np.array(
        [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    )
    evidence = core.canonical_digest(
        dict(
            windows=prepared.evidence_sha256,
            tle=snapshot.digest,
            candidates=[int(catalogue.satellite_numbers[i]) for i in indices],
        )
    )
    assert evidence == document["evidence_sha256"]
    prior = core.RegionalPrior(**document["configuration"]["prior"])
    bank, _ = core.build_regional_bank(
        catalogue, indices, prepared.start_utc_ns, prepared.observations, prior, maximum_seconds=180
    )
    assert bank.numbers.tolist() == document["diagnostics"]["bank"]["retained_numbers"]
    score_signature = core.canonical_digest(
        dict(prior=core.json_value(prior), score=core.json_value(core.HARD60_SCORE))
    )
    binding = dict(
        input_digest=document["input_manifest_sha256"],
        evidence_digest=evidence,
        score_signature=score_signature,
        bank_signature=core.canonical_digest(bank.numbers.tolist()),
    )
    return prepared.observations, bank, prior, prepared.bootstrap_tracks, binding


def verify_coarse(observations, bank, prior, original):
    model = core.Hard60Objective(
        observations,
        bank.select(original["bootstrap"]["satellite_indices"]),
        prior,
        core.HARD60_SCORE,
    )
    fit = original["fits"]["V16"]["fit"]
    np.testing.assert_allclose(
        model.evaluate(np.asarray(fit["vector"]))[0], fit["objective"], atol=1e-6, rtol=0
    )
    return model, fit


def recover_calibration(observations, bank, prior, trigger):
    original = trigger["original"]
    model, fit = verify_coarse(observations, bank, prior, original)
    before = None
    if not fit["converged"]:
        before = direct.qualification.qualify(
            model,
            np.asarray(fit["vector"]),
            fit["objective"],
            retained=True,
            stage="calibration-prefit",
            independently_qualified=False,
            maximum_rounds=2,
            maximum_evaluations=100,
        )
        if not before["qualified"]:
            return dict(status="prefit-unqualified", prefit_qualification=before, calibration=None)
        fit = before["fit"]
    point = np.array([float(value) for value in trigger["key"].split(":")[1:]])
    prefit = direct.validated_postfit(model, fit, point)
    after = direct.fresh_calibration(
        observations, model, prior, original["bootstrap"]["satellite_indices"], prefit
    )
    return dict(after, prefit_qualification=before, direct_prefit=core.json_value(prefit))


def recovered_region(observations, bank, prior, trigger, stage):
    key = trigger["key"]
    identity = core.canonical_digest(trigger["identity"])[7:]
    prefix = "recovery105:" + identity + ":"
    calibrated = stage(
        prefix + "calibration", 90, lambda: recover_calibration(observations, bank, prior, trigger)
    )
    if not calibrated["result"] or calibrated["result"]["calibration"] is None:
        return dict(calibrations={}, finals=[], recovery=calibrated)
    calibration = calibrated["result"]["calibration"]
    cal = core._calibration(calibration)
    associated = stage(
        prefix + "association",
        60,
        lambda: core.associate_calibration(
            observations, bank, prior, cal, maximum_seconds=60, orbit_predictor=core.predict_orbits
        ),
    )
    if not associated["result"]:
        return dict(
            calibrations={key: calibration}, finals=[], recovery=calibrated, association=associated
        )
    selected = associated["result"]
    subset = bank.select(selected["selected_indices"])
    model = core.Hard60Objective(
        observations,
        subset,
        prior,
        core.HARD60_SCORE,
        receiver_baseline_hz=cal.receiver_baseline_hz,
    )
    knots = cal.correction.knots_hz
    penalty = float(
        0.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1) ** 2) / 25**2)
    )
    center = np.array([float(value) for value in key.split(":")[1:]])
    radius = trigger["identity"]["local_radius_km"]
    finals = []
    for arm in ("zero-c", "fitted-c"):
        completed = []
        for name in Hard60Configuration().final_starts:
            seed = np.asarray(selected["initial_vector"]).copy()
            if name == "zero-timing":
                seed[7:] = 0
            elif name == "own-continuation" and completed:
                seed = np.asarray(min(completed, key=lambda row: row["objective"])["vector"]).copy()
            before_roundoff_projection = seed.copy()
            for origin, bound in ((np.zeros(2), prior.radius_km), (center, radius)):
                delta = seed[:2] - origin
                distance = np.linalg.norm(delta)
                if bound < distance <= bound + 1e-6:
                    seed[:2] = origin + delta * ((bound - 1e-8) / distance)

            def fit(seed=seed, arm=arm, original_seed=before_roundoff_projection):
                fitted, diagnostics = core.fit_bounded_position(
                    model,
                    seed.copy(),
                    rf_arm=arm,
                    local_center=center,
                    local_radius_km=radius,
                    slope_half_width_hz_s=60,
                    maximum_seconds=20,
                    maximum_iterations=600,
                )
                return dict(
                    fit=fitted,
                    diagnostics=diagnostics,
                    seed_audit=dict(
                        original=original_seed.tolist(),
                        effective=seed.tolist(),
                        position_delta_km=(seed[:2] - original_seed[:2]).tolist(),
                        rule="Existing hard60_runner <=1e-6km boundary-roundoff correction",
                    ),
                )

            receipt = stage(prefix + arm + ":" + name, 20, fit)
            fitted = receipt["result"]["fit"] if receipt["result"] else None
            if fitted:
                if arm == "zero-c":
                    assert fitted["vector"][6] == 0
                completed.append(fitted)
            finals.append(
                dict(
                    basin=key,
                    method="V16",
                    arm=arm,
                    start=name,
                    fit=fitted,
                    reason=receipt["reason"],
                    calibration_penalty=penalty,
                    satellites=subset.numbers.tolist(),
                    association=selected["selection"],
                    seed_audit=receipt["result"].get("seed_audit") if receipt["result"] else None,
                )
            )
    return dict(
        calibrations={key: calibration}, finals=finals, recovery=calibrated, association=associated
    )


def main(label, phase):
    plan_path = HERE / "protocol.json"
    plan = read(plan_path)
    assert plan["slice_seconds"] == 500 and plan["maximum_slices_per_phase"] == 6
    assert plan["maximum_workers"] == 2
    assert plan["b7_policy"] == B7_POLICY
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(variable) == "1", variable
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    member = next(
        row for row in read(HERE / "source-snapshot.json")["members"] if row["label"] == label
    )
    assert label in plan["labels"]
    directory = HERE / "results" / label
    destination = directory / (phase + ".json")
    if destination.exists():
        assert read(destination)["protocol_sha256"] == digest
        return
    baseline_path = directory / "baseline.json"
    baseline = read(baseline_path) if baseline_path.exists() else None
    if baseline is not None:
        assert baseline["protocol_sha256"] == digest
    if phase == "candidate":
        assert baseline is not None and baseline["status"] == "complete"
    slot = claim_slice(directory / "slices", phase, digest)
    if slot is None:
        write(
            destination,
            dict(
                protocol_sha256=digest,
                status="budget-exhausted",
                phase=phase,
                operational=baseline["operational"] if baseline else {},
                fallback_available=bool(baseline),
            ),
        )
        return
    deadline = time.monotonic() + 500
    report = dict(protocol_sha256=digest, label=label, phase=phase, slice=slot)
    try:
        observations, bank, prior, tracks, binding = load_case(member["document"])
        compatibility = source_compatibility(member["document"])
        report.update(input_binding=binding, cache_compatibility=compatibility)
        cache = Overlay(
            directory / "stages",
            digest,
            HERE,
            member["checkpoints"],
            compatible=compatibility["eligible"],
            verify_coarse=lambda original: verify_coarse(observations, bank, prior, original),
            coarse_alias_prefix=core.canonical_digest(core.json_value(Hard60Configuration()))
            if member["source_version"] == "hard60" and compatibility["eligible"]
            else None,
        )

        def stage(key, budget, operation):
            receipt = cache.get(key)
            if receipt is not None:
                return receipt
            if time.monotonic() + budget >= deadline:
                raise core.RegionalSliceExpired(key)
            try:
                value = dict(result=core.json_value(operation()), reason=None)
            except (ValueError, TimeoutError, AssertionError) as error:
                value = dict(result=None, reason=f"{type(error).__name__}: {error}")
            cache.put(key, value)
            return value

        if phase == "baseline":
            regions = {}
            for name, separation in zip(
                ("baseline", "sep25", "sep50"), (12.5, 25.0, 50.0), strict=True
            ):
                config = replace(Hard60Configuration(), basin_separation_km=separation)
                regions[name] = run_hard60(
                    observations,
                    bank,
                    prior,
                    tracks,
                    SharedPoints(cache),
                    configuration=config,
                    maximum_seconds=max(0.001, deadline - time.monotonic()),
                )
            operational, attempts, reasons = run_joint_stages(
                observations,
                bank,
                prior,
                regions,
                lambda key, budget, operation: stage("baseline105:" + key, budget, operation),
            )
            write(
                destination,
                dict(
                    report,
                    status="complete",
                    regions=regions,
                    operational=operational,
                    attempts=attempts,
                    reasons=reasons,
                    source_cache_hits=cache.source_hits,
                    source_coarse_aliases=cache.aliases,
                ),
            )
        else:
            regions = copy.deepcopy(baseline["regions"])
            inventory = regional_triggers(
                regions,
                input_digest=binding["input_digest"],
                score_signature=binding["score_signature"],
                bank_signature=binding["bank_signature"],
                minimum_local_radius_km=Hard60Configuration().minimum_local_radius_km,
            )
            assert len(inventory["candidates"]) <= 3 * Hard60Configuration().basins
            for trigger in inventory["candidates"]:
                name = "direct105:" + core.canonical_digest(trigger["identity"])[7:]
                regions[name] = recovered_region(observations, bank, prior, trigger, stage)
            operational, attempts, reasons = run_joint_stages(
                observations,
                bank,
                prior,
                regions,
                lambda key, budget, operation: stage("candidate105:" + key, budget, operation),
            )
            write(
                destination,
                dict(
                    report,
                    status="complete",
                    inventory=inventory,
                    regions=regions,
                    operational=operational,
                    attempts=attempts,
                    reasons=reasons,
                    baseline_operational=baseline["operational"],
                    regional_before=regional_winners(baseline["regions"]),
                    regional_after=regional_winners(regions),
                ),
            )
        report["status"] = "complete"
    except core.RegionalSliceExpired as error:
        report.update(status="pending", reason=str(error))
    except Exception as error:
        report.update(status="failed", reason=repr(error))
        write(
            destination,
            dict(
                report,
                operational=baseline["operational"] if baseline else {},
                fallback_available=bool(baseline),
            ),
        )
    if report["status"] == "pending" and slot == 6:
        report["status"] = "budget-exhausted"
        write(
            destination,
            dict(
                report,
                status="budget-exhausted",
                operational=baseline["operational"] if baseline else {},
                fallback_available=bool(baseline),
            ),
        )
    write(directory / "slices" / f"{phase}-{slot:02d}.done.json", report)
    print(label, phase, report["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--phase", choices=("baseline", "candidate"), required=True)
    args = parser.parse_args()
    main(args.label, args.phase)
