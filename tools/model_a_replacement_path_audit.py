"""Bounded zero-fit sequential path/association audit on a replaced bank."""

import argparse
import json
import time
from pathlib import Path

import ds21_model_a_pipeline_cached_v2 as cached
import ds21_model_a_sealed_path_audit as paths
import model_a_union_preparation as preparation
import model_a_union_transport as transport
import model_a_verified_manifest as manifest
import numpy as np

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.hard60_score import likelihood, predict_orbits
from leo.analysis.sequential_group_calibration import (
    SequentialHighObjective,
    SequentialShift,
    fixed_shift_objective,
)

original = cached.original
binding, read, immutable = cached.binding, cached.read, cached.immutable
POLICY = dict(
    schema="model-a-replaced-bank-path-audit-v1",
    internal_seconds=120,
    preparation_seconds=15,
    external_term_seconds=135,
    external_kill_seconds=140,
    optimizer_calls=0,
    held_usage="none",
    reference_usage="Post-seal retrospective path audit only; never a selector",
    added_timing_rule="Original saved common timing, zero relative shift",
    maximum_objectives=20,
    maximum_explicit_predictors=22,
)


def freeze(directory, before, after):
    directory = Path(directory).resolve()
    parents = dict(before=str(Path(before).resolve()), after=str(Path(after).resolve()))
    if (directory / "protocol.json").exists():
        frozen = read_control(directory)
        if frozen["parents"] != parents:
            raise ValueError("Audit parents differ")
        return frozen
    authorities, sources = [], {}
    for parent in parents.values():
        p = Path(parent)
        if directory == p or directory.is_relative_to(p) or p.is_relative_to(directory):
            raise ValueError("Audit namespace overlaps immutable scientific parent")
        frozen = cached.read_control(p)
        cached.qualification(p)
        if not (p / "terminal.json").exists():
            raise ValueError("Complete matrices must already be sealed")
        cached.seal(p)
        authorities.append(frozen)
        sources.update(frozen["source_sha256"])
    if authorities[0]["label"] != authorities[1]["label"]:
        raise ValueError("Same case required")
    for p in (
        __file__,
        paths.__file__,
        preparation.__file__,
        transport.__file__,
        manifest.__file__,
    ):
        sources[str(Path(p).resolve())] = binding(p)["sha256"]
    value = dict(
        policy=POLICY,
        parents=parents,
        label=authorities[0]["label"],
        source_sha256=sources,
        snapshot_paths=original.discovery.archive_sources(directory, sources),
        authority=manifest.pin_qualified_files(
            [*parents.values(), *(d for f in authorities for d in f["authority"]["directories"])],
            source_files=sources,
            extra_files=[p for f in authorities for p in f["authority"]["files"]],
        ),
    )
    immutable(directory / "protocol.json", value)
    return read_control(directory)


def read_control(directory):
    frozen = read(Path(directory) / "protocol.json")
    if frozen["policy"] != POLICY:
        raise ValueError("Audit policy changed")
    original.pool.shape_parent.validate_archives(directory, frozen)
    manifest.verify_pinned_files(frozen["authority"])
    return frozen


def replacement_seed(seed, source, union, target):
    """Drop omitted timings only after exact union transport and frame proof."""
    carried = transport.transport(seed, source, union)
    # Reverse inclusion port proves target calibration/clock/score compatibility.
    transport.transport(
        dict(vector=np.zeros(target.size), nuisance=np.zeros_like(target.initial_nuisance)),
        target,
        union,
    )
    shifts = carried["vector"][7] + union.basis @ carried["vector"][8:]
    lookup = dict(zip(union.bank.numbers.tolist(), shifts, strict=True))
    desired = np.asarray([lookup[int(n)] for n in target.bank.numbers])
    common = float(desired.mean())
    vector = np.r_[carried["vector"][:7], common, target.basis.T @ (desired - common)]
    error = float(
        np.max(
            abs(
                source.correction(np.asarray(seed["vector"]), np.asarray(seed["nuisance"]))
                - target.correction(vector, carried["nuisance"])
            ),
            initial=0,
        )
    )
    timing_error = float(np.max(abs(vector[7] + target.basis @ vector[8:] - desired), initial=0))
    if error > 1e-7 or timing_error > 1e-12:
        raise ValueError("Replacement physical transport closure failed")
    return dict(
        vector=vector,
        nuisance=carried["nuisance"],
        correction_closure_hz=error,
        timing_closure_s=timing_error,
        union_transport=carried["timing_transport"],
    )


def score_state(model, fit, counter, *, replay=True):
    vector, nuisance = np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
    counter["objective"] += 1
    value, gradient, ng, terms = model.evaluate_joint(vector, nuisance)
    if not np.isfinite(gradient).all() or not np.isfinite(ng).all():
        raise ValueError("Nonfinite replay gradient")
    if replay and (
        abs(value - fit["objective"]) > 1e-6 or abs(terms.nll - fit["likelihood_nll"]) > 1e-6
    ):
        raise ValueError("Saved objective/likelihood replay differs")
    counter["explicit_predictor"] += 1
    prediction, visible, *_ = predict_orbits(
        model.bank,
        model.observations,
        model.prior,
        vector[:2],
        vector[7] + model.basis @ vector[8:],
        derivatives=False,
    )
    prediction += model.correction(vector, nuisance)[:, None]
    bands = {}
    for band, mask in (
        ("low", model.observations.channel < 5),
        ("high", model.observations.channel >= 5),
    ):
        if not mask.any():
            continue
        counter["band_likelihood"] += 1
        term = likelihood(
            model.observations.measured_hz[mask], prediction[mask], visible[mask], model.score
        )
        mass = term.responsibilities.sum(axis=0)
        bands[band] = dict(
            windows=int(mask.sum()),
            likelihood_nll=float(term.nll),
            signal_mass=float(mass.sum()),
            posterior_rms_hz=None
            if mass.sum() == 0
            else float(np.sqrt(np.sum(term.responsibilities * term.residual_hz**2) / mass.sum())),
            candidate_mass=[
                dict(number=int(model.bank.numbers[i]), mass=float(mass[i]))
                for i in np.argsort(-mass)
            ],
            dominant_signal_windows=int(np.sum(term.responsibilities.sum(axis=1) > 0.5)),
        )
    delta = float(sum(b["likelihood_nll"] for b in bands.values()) - terms.nll)
    if abs(delta) > 1e-7:
        raise ValueError("Band NLL sum differs")
    return dict(
        objective=float(value),
        likelihood_nll=float(terms.nll),
        objective_replay_delta=None if not replay else float(value - fit["objective"]),
        bands=bands,
        band_sum_delta=delta,
        gradient_maximum=float(np.max(abs(gradient), initial=0)),
        nuisance_gradient_maximum=float(np.max(abs(ng), initial=0)),
        _posterior=terms.responsibilities,
        _window_ids=model.observations.window_ids,
    )


def association_change(source, target):
    lookup = {w: i for i, w in enumerate(target["_window_ids"])}
    index = [lookup[w] for w in source["_window_ids"]]
    a, b = source["_posterior"], target["_posterior"][index]
    if a.shape != b.shape:
        raise ValueError("Association comparison requires identical candidate bank")
    supported = (a.sum(axis=1) > 0.5) & (b.sum(axis=1) > 0.5)
    return dict(
        windows=len(index),
        supported_both=int(supported.sum()),
        dominant_candidate_disagreements=int(
            np.sum((a.argmax(axis=1) != b.argmax(axis=1)) & supported)
        ),
        mean_candidate_posterior_l1=float(np.mean(np.sum(abs(a - b), axis=1))),
    )


def clean(value):
    return {k: v for k, v in value.items() if not k.startswith("_")}


def a_models(case):
    models = {
        v: original.objective(case["prepared"][v], case["bank"], case["prior"], case["nodes"])
        for v in original.VIEWS
    }
    models["all"] = GroupCalibrationObjective(
        models["all"].base, case["prepared"]["all"].observations.channel >= 5, enabled=False
    )
    return models


def audit(directory):
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    identity = dict(protocol=binding(directory / "protocol.json"), optimizer_calls=0)
    if (directory / "launch.json").exists():
        raise ValueError("Already attempted audit; no retry")
    immutable(directory / "launch.json", identity)
    begun, counter = time.monotonic(), dict(objective=0, explicit_predictor=0, band_likelihood=0)
    status = dict(**identity, state="failed")
    try:
        with original.discovery.slice_bound(POLICY["internal_seconds"]):
            with original.discovery.slice_bound(POLICY["preparation_seconds"]):
                prepared = preparation.prepare(
                    **{f"{k}_directory": v for k, v in frozen["parents"].items()}
                )
            cases = {k: p["case"] for k, p in prepared["parents"].items()}
            models = {k: a_models(c) for k, c in cases.items()}
            science, outcomes, nodes, selected = paths.validated_case(frozen["parents"]["after"])
            from ds21_evaluate import reference

            path_rows = paths.audit_paths(science, outcomes, nodes, selected, reference())
            scored, results = {}, []
            for path in path_rows:
                unit = f"A-{path['start']}"
                outcome = outcomes[unit]
                base = models["after"]
                replay_models = dict(low=base["low"])
                if "high" in outcome["calls"]:
                    replay_models["high"] = SequentialHighObjective(
                        base["high"].base,
                        freeze_group_calibration(base["low"], outcome["calls"]["low"]["fit"]),
                        set(base["low"].observations.receiver),
                    )
                if "final" in outcome["calls"]:
                    replay_models["final"] = fixed_shift_objective(
                        base["all"].base,
                        SequentialShift(
                            tuple(outcome["path"]["fixed_shift_receivers"]),
                            np.asarray(outcome["path"]["fixed_shift_hz"]),
                        ),
                    )
                replay = {
                    stage: score_state(replay_models[stage], row["fit"], counter)
                    for stage, row in outcome["calls"].items()
                    if "vector" in row["fit"]
                }
                changes = (
                    association_change(replay["low"], replay["final"])
                    if "final" in replay
                    else None
                )
                scored[path["start"]] = replay
                results.append(
                    dict(
                        **path,
                        replayed={k: clean(v) for k, v in replay.items()},
                        low_to_final_association_change=changes,
                    )
                )
            old = cached.seal(frozen["parents"]["before"])["selections"]["A-all"]
            carried_result = dict(state="unavailable")
            if old is not None:
                unit = f"A-{old['start']}"
                previous = cached.validate_unit(
                    frozen["parents"]["before"], unit, prepared["parents"]["before"]["frozen"]
                )
                shift = SequentialShift(
                    tuple(previous["path"]["fixed_shift_receivers"]),
                    np.asarray(previous["path"]["fixed_shift_hz"]),
                )
                source = fixed_shift_objective(models["before"]["all"].base, shift)
                target = fixed_shift_objective(models["after"]["all"].base, shift)
                union = fixed_shift_objective(a_models(prepared["union_case"])["all"].base, shift)
                seed = replacement_seed(old["fit"], source, union, target)
                centers = np.asarray([p["point_km"] for p in science["inputs"]["proposals"]])
                distances = np.linalg.norm(centers - seed["vector"][:2], axis=1)
                nearest = int(np.argmin(distances))
                domain = transport.validate_domain(seed, target, centers[nearest])
                counter["explicit_predictor"] += 2
                oldpred, oldvis, *_ = predict_orbits(
                    source.bank,
                    source.observations,
                    source.prior,
                    np.asarray(old["fit"]["vector"])[:2],
                    np.asarray(old["fit"]["vector"])[7]
                    + source.basis @ np.asarray(old["fit"]["vector"])[8:],
                    derivatives=False,
                )
                newpred, newvis, *_ = predict_orbits(
                    target.bank,
                    target.observations,
                    target.prior,
                    seed["vector"][:2],
                    seed["vector"][7] + target.basis @ seed["vector"][8:],
                    derivatives=False,
                )
                common = sorted(set(source.bank.numbers) & set(target.bank.numbers))
                oi = [source.bank.numbers.tolist().index(n) for n in common]
                ni = [target.bank.numbers.tolist().index(n) for n in common]
                closure = float(np.max(abs(oldpred[:, oi] - newpred[:, ni]), initial=0))
                if closure > 1e-7 or not np.array_equal(oldvis[:, oi], newvis[:, ni]):
                    raise ValueError(
                        "Common-candidate orbital prediction/visibility closure differs"
                    )
                carried_result = dict(
                    state="qualified",
                    original_start=old["start"],
                    nearest_current_start=nearest,
                    minimum_current_center_distance_km=float(distances[nearest]),
                    domain=domain,
                    seed=seed,
                    common_candidates=len(common),
                    common_prediction_closure_hz=closure,
                    before_original_score=clean(score_state(source, old["fit"], counter)),
                    current_bank_score=clean(score_state(target, seed, counter, replay=False)),
                    cross_bank_ranking=False,
                    selection=(
                        "Original BEFORE training winner; no optimization or reference selection"
                    ),
                )
            if counter["objective"] > 20 or counter["explicit_predictor"] > 22:
                raise ValueError("Prespecified diagnostic call bound exceeded")
            read_control(directory)
            value = dict(
                **identity,
                label=frozen["label"],
                paths=results,
                transported_before_winner=carried_result,
                calls=counter,
                elapsed_seconds=time.monotonic() - begun,
                reference_usage=POLICY["reference_usage"],
                held_usage="none",
            )
            immutable(directory / "audit.json", cached.transport.native_json(value))
            status.update(state="complete", audit=binding(directory / "audit.json"))
            return value
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        status.update(elapsed_seconds=time.monotonic() - begun, calls=counter)
        immutable(directory / "termination.json", status)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("freeze", "audit"))
    p.add_argument("directory", type=Path)
    p.add_argument("--before", type=Path)
    p.add_argument("--after", type=Path)
    a = p.parse_args()
    if a.command == "freeze" and (a.before is None or a.after is None):
        p.error("Both sealed scientific parents required")
    value = freeze(a.directory, a.before, a.after) if a.command == "freeze" else audit(a.directory)
    print(json.dumps(cached.transport.native_json(value), allow_nan=False))


if __name__ == "__main__":
    main()
