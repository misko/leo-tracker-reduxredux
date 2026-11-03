"""Frozen all-five joint-band policy; no configured reference read before seal."""
# ruff: noqa: E402

import argparse
import hashlib
import importlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from numpy.testing import assert_allclose, assert_array_equal

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
ROOT = REPORTS.parent
DATA = REPORTS / "2026_10_16_dsx01_fast_association_losses"
COMMON = REPORTS / "2026_10_16_dsx01_models"
JOINT = REPORTS / "2026_10_17_dsx01_iteration5/joint_band_contrast"
PROFILE = REPORTS / "2026_10_17_dsx01_iteration5/band_contrast_audit"
PREVIOUS = REPORTS / "2026_10_16_dsx01_iteration2"
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(JOINT))
sys.path.append(str(PROFILE))
import common
from band_profile import BandProfiles, Grid
from fit import fit_free
from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.shared_scan_model import SharedScanObjective
from leo.application.shared_fast_position import plain, prepare_views
from leo.application.shared_orbit_replay import selected_model
from leo.cli.shared_fast_position import load_input
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.storage.shared_fast_scan import SharedFastScanStore
from model import free_context, predict_joint

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

SOURCES = ("S01", "S02", "S03", "S04", "S05")
ARMS = ("fitted-c", "zero-c")
METHODS = ("fixed", "joint")


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(plain(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def seed_for(fitted, arm):
    if arm not in ARMS:
        raise ValueError("Declared RF arm required")
    v, n = np.array(fitted["vector"], dtype=float), np.array(fitted["nuisance"], dtype=float)
    if arm == "zero-c":
        v[6] = 0.0
    return v, n


def verify_bindings(bindings):
    for path, sha in bindings.items():
        if digest(path) != sha:
            raise ValueError("Frozen source/input changed: " + path)


def source_rows():
    rows = read(DATA / "sources.json")
    return {s: next(r for r in rows if r["source_id"] == s) for s in SOURCES}


def validate_seed(fitted, source, item):
    if (
        fitted["source_id"] != source
        or fitted["arm"] != "fitted-c"
        or fitted["method"] != "profile"
        or fitted.get("mode", "full") != "full"
    ):
        raise ValueError("Exact declared full fitted-profile seed required")
    for key in ("job_id", "tracking_input_sha256", "terminal_sha256", "tle_sha256"):
        if fitted["source"][key] != item[key]:
            raise ValueError("Fitted profile seed source authority mismatch: " + key)


def prepare(source, arm):
    """Original public replay, same ordered bank; no station-reference access."""
    item = source_rows()[source]
    job, document, terminal, stages = SharedFastScanStore(
        "/srv/bulk/leo", "shared-scan-q-v2"
    ).plot_evidence(item["job_id"])
    if (
        job["input_sha256"] != item["tracking_input_sha256"]
        or job["terminal"]["sha256"] != item["terminal_sha256"]
    ):
        raise ValueError("Original public source identity changed")
    inputs = load_input(document)
    prepared, nodes = prepare_views(inputs)
    cache = ROOT / item["report_directory"] / "orbit-bank.npz"
    if cache.exists():
        with np.load(cache, allow_pickle=False) as bank:
            whole = PositionOrbitBank(
                bank["numbers"], bank["nodes"], bank["positions"], bank["velocities"]
            )
    else:
        archive = TleArchiveReader(Path("/var/lib/leo/tle"))
        matches = [
            s
            for s in archive.list_snapshots()
            if s.digest == item["tle_sha256"] and s.collected_utc_ns == item["tle_collected_utc_ns"]
        ]
        if len(matches) != 1:
            raise ValueError("Unique original pinned local TLE snapshot required")
        catalogue = parse_element_sets(archive.read(matches[0]))
        catalogue_index = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        whole, _ = build_regional_bank(
            catalogue,
            [catalogue_index[int(n)] for n in terminal["candidate_numbers"]],
            prepared["all"].start_utc_ns,
            prepared["all"].observations,
            RegionalPrior(**terminal["provenance"]["prior"]),
        )
    lookup = {int(number): i for i, number in enumerate(whole.numbers)}
    bank = whole.select([lookup[int(number)] for number in terminal["candidate_numbers"]])
    assert_array_equal(bank.numbers, terminal["candidate_numbers"])
    prior = RegionalPrior(**terminal["provenance"]["prior"])
    model, original, audit = selected_model(prepared, bank, prior, nodes, terminal, stages)
    if type(model) is not SharedScanObjective or not audit["accepted"]:
        raise ValueError("Genuine original shared model and saved production audit required")
    fitted = read(PREVIOUS / "results" / f"{source}-fitted-c-profile.json")
    validate_seed(fitted, source, item)
    v, n = seed_for(fitted, arm)
    original_v, original_n = seed_for(original, arm)
    ctx = common.Context(
        source,
        model,
        model,
        v,
        n,
        prepared["all"].observations,
        bank,
        prior,
        np.ones(len(model.observations.times_s), bool),
        np.asarray(nodes),
        dict(
            source_id=source,
            job_id=item["job_id"],
            input_sha256=item["tracking_input_sha256"],
            terminal_sha256=item["terminal_sha256"],
            seed_sha256=digest(PREVIOUS / "results" / f"{source}-fitted-c-profile.json"),
        ),
        fixed_c=arm == "zero-c",
    )
    return ctx, (original_v, original_n)


def verify():
    plan = read(HERE / "protocol_v2.json")
    verify_bindings(plan["source_sha256"])
    return plan


def freeze():
    manifest = read(JOINT / "code-handoff.json")
    for name, sha in manifest["hashes"].items():
        if digest(JOINT / name) != sha:
            raise ValueError("Shared B implementation seal changed")
    paths = [
        Path(__file__),
        HERE / "test_run_v2.py",
        HERE / "PROTOCOL.md",
        HERE / "V2_ERRATUM.md",
        JOINT / "model.py",
        JOINT / "fit.py",
        JOINT / "test_model.py",
        JOINT / "code-handoff.json",
        PROFILE / "band_profile.py",
        COMMON / "common.py",
        DATA / "sources.json",
    ]
    for row in source_rows().values():
        cache = ROOT / row["report_directory"] / "orbit-bank.npz"
        if cache.exists():
            paths.append(cache)
        paths.append(PREVIOUS / "results" / f"{row['source_id']}-fitted-c-profile.json")
    for name in (
        "leo.analysis.hard60_bounded_fit",
        "leo.analysis.hard60_score",
        "leo.analysis.shared_scan_model",
        "leo.analysis.regional_position_score",
        "leo.analysis.sequential_group_calibration",
        "leo.analysis.hard60_joint_clock",
        "leo.application.shared_orbit_replay",
        "leo.application.shared_fast_position",
        "leo.application.channel_group_refinement",
        "leo.cli.shared_fast_position",
    ):
        paths.append(Path(importlib.import_module(name).__file__))
    # Include every already-loaded public port dependency, not only top-level wrappers.
    paths += [
        Path(m.__file__)
        for name, m in list(sys.modules.items())
        if name.startswith("leo.")
        and getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py")
    ]
    save(
        HERE / "protocol_v2.json",
        dict(
            source_sha256={str(p): digest(p) for p in set(paths)},
            sources=SOURCES,
            arms=ARMS,
            methods=METHODS,
            outcomes=20,
            maximum_evaluations=1000,
            maximum_seconds=120,
            domain="Broad regional prior; no extra production25km disks",
            seeds="Same iteration2 full fitted-profile complete state; c0 only vector[6]=0",
            profile="Exact fixed coarse +/-10000Hz/500Hz, fine +/-500Hz/25Hz; usually159 calls",
            joint_allowance="Profile calls +2real qualifiers +remaining common.refit",
            reuse="Exact saved state/q/tau validation; active calls/time charged",
            incumbent="Original full and profile seed replayed; feasible points retained",
            selector="Per target finite feasible TRAIN minimum; strict KKT independent",
            evaluation="All20 and selectors sealed before positions/windows; no held experiment",
        ),
    )


def qualify(source):
    verify()
    outputs = []
    for arm in ARMS:
        ctx, original = prepare(source, arm)
        p = _Problem(ctx.model, ctx.vector, rf_arm=arm)
        if not p.feasible(ctx.vector):
            raise ValueError("Raw profile seed outside unchanged regional/physical bounds")
        changed = free_context(ctx)
        original_ev = ctx.model.evaluate_joint(ctx.vector, ctx.nuisance)
        saved_seed = read(PREVIOUS / "results" / f"{source}-fitted-c-profile.json")
        assert len(ctx.observations.times_s) == saved_seed["full_scan"]["observations"]
        if arm == "fitted-c":
            assert_allclose(
                original_ev[3].nll, saved_seed["full_scan"]["likelihood_nll"], atol=1e-7, rtol=0
            )
            assert_allclose(original_ev[0], saved_seed["full_scan"]["objective"], atol=1e-7, rtol=0)
        nested = changed.model.evaluate_joint(changed.vector, changed.nuisance)
        assert_allclose(original_ev[0], nested[0], atol=1e-8, rtol=0)
        assert_allclose(original_ev[1], nested[1], atol=1e-10, rtol=0)
        assert_allclose(original_ev[2], nested[2][: len(ctx.nuisance)], atol=1e-10, rtol=0)
        assert_allclose(
            original_ev[3].responsibilities, nested[3].responsibilities, atol=1e-12, rtol=0
        )
        assert_allclose(
            original_ev[3].clutter_probability, nested[3].clutter_probability, atol=1e-12, rtol=0
        )
        # No optimizer: this finite declared grid is charged later to its joint policy.
        profiler = BandProfiles(ctx, ctx.vector, ctx.nuisance, Grid())
        profile = profiler.fit()
        proposed = free_context(ctx, profile["absolute_offsets_hz"])
        ev = proposed.model.evaluate_joint(proposed.vector, proposed.nuisance)
        assert_allclose(ev[0], profile["training_objective"], atol=1e-8, rtol=0)
        assert_allclose(ev[3].nll, profile["training_nll"], atol=1e-8, rtol=0)
        gradient_checks = []
        for index in range(proposed.model.band_count):
            step = 0.05
            plus, minus = proposed.nuisance.copy(), proposed.nuisance.copy()
            plus[-proposed.model.band_count + index] += step
            minus[-proposed.model.band_count + index] -= step
            observed = (
                proposed.model.evaluate_joint(proposed.vector, plus)[0]
                - proposed.model.evaluate_joint(proposed.vector, minus)[0]
            ) / (2 * step)
            expected = ev[2][-proposed.model.band_count + index]
            assert_allclose(observed, expected, atol=2e-7, rtol=1e-5)
            gradient_checks.append(dict(receiver=index, analytic=expected, central=observed))
        prediction = predict_joint(proposed, proposed.vector, proposed.nuisance, ctx.observations)
        assert_array_equal(prediction["detection_probability"], profiler.q)
        profile.update(
            vector=ctx.vector,
            nuisance=ctx.nuisance,
            q=profiler.q,
            total_timing_s=ctx.vector[7] + ctx.model.basis @ ctx.vector[8:],
        )
        profile_path = HERE / f"profile_{source}_{arm}.json"
        save(profile_path, profile)
        incumbents = {}
        for method in METHODS:
            target = ctx if method == "fixed" else changed
            points = {}
            for label, (v, n) in (
                ("original", original),
                ("profile-seed", (ctx.vector, ctx.nuisance)),
            ):
                if method == "joint":
                    n = target.model.pack(n)
                audit = common.endpoint_status(target, v, n)
                points[label] = dict(vector=v, nuisance=n, audit=audit)
            incumbents[method] = points
        path = HERE / f"qualification_{source}_{arm}.json"
        save(
            path,
            dict(
                passed=True,
                source_id=source,
                arm=arm,
                profile_sha256=digest(profile_path),
                seed_sha256=ctx.source["seed_sha256"],
                vector=ctx.vector,
                nuisance=ctx.nuisance,
                numbers=ctx.bank.numbers,
                observations=len(ctx.observations.times_s),
                same_mask_all_training=bool(ctx.train_mask.all()),
                exact_nesting=True,
                classification_rule="best satellite posterior > clutter unchanged",
                absolute_band_prior_sigma_hz=50000.0,
                band_gradient_checks=gradient_checks,
                unchanged_fixed_contrast_prior=ctx.model.fixed_contrast_prior_penalty,
                incumbents=incumbents,
                independent_qualification_objectives=11,
                charged_profile_calls=profile["diagnostics"]["evaluations"],
                configured_reference_read=False,
                position_or_window_metrics_read=False,
            ),
        )
        outputs += [
            dict(path=str(path), sha256=digest(path)),
            dict(path=str(profile_path), sha256=digest(profile_path)),
        ]
    verify()
    save(HERE / f"qualification_seal_{source}.json", dict(files=outputs))
    print(source, "qualification passed", flush=True)


def qualifications():
    records = []
    for source in SOURCES:
        seal = read(HERE / f"qualification_seal_{source}.json")
        for row in seal["files"]:
            if digest(row["path"]) != row["sha256"]:
                raise ValueError("Qualification source changed")
            records.append(row)
    return records


def run(source, arm, method):
    verify()
    qualifications()
    destination = HERE / f"fit_{source}_{arm}_{method}.json"
    if destination.exists():
        raise FileExistsError("No overwrites or implicit retries")
    ctx, _ = prepare(source, arm)
    qualification = read(HERE / f"qualification_{source}_{arm}.json")
    assert_array_equal(ctx.vector, qualification["vector"])
    assert_array_equal(ctx.nuisance, qualification["nuisance"])
    assert_array_equal(ctx.bank.numbers, qualification["numbers"])
    ctx = replace(ctx, deadline=time.monotonic() + 120)
    if method == "fixed":
        result = common.refit(
            ctx,
            ctx.vector,
            ctx.nuisance,
            max_evaluations=1000,
            max_seconds=120,
            fixed_c=ctx.fixed_c,
        )
        target = ctx
    else:

        def callback(value):
            save(HERE / f"runtime_qualification_{source}_{arm}.json", value)

        result, target, _ = fit_free(
            ctx,
            max_evaluations=1000,
            max_seconds=120,
            reused_profile=read(HERE / f"profile_{source}_{arm}.json"),
            qualification_callback=callback,
        )
    if result["diagnostics"]["evaluations"] > 1000:
        raise ValueError("Inference count exceeded")
    audit = common.endpoint_status(target, result["vector"], result["nuisance"])
    save(
        destination,
        dict(
            result,
            source_id=source,
            arm=arm,
            method=method,
            audit=audit,
            original_offsets_hz=free_context(ctx).model.original_offsets_hz,
            qualification_sha256=digest(HERE / f"qualification_{source}_{arm}.json"),
            independent_audit_calls=1,
            reference_or_window_evaluation=False,
        ),
    )
    print(source, arm, method, result["diagnostics"], "audit", audit, flush=True)


def choose(points):
    feasible = [
        (p["audit"]["training_objective"], label, p)
        for label, p in points.items()
        if p["audit"]["feasible"]
        and np.isfinite(p["audit"].get("training_objective", float("nan")))
    ]
    if not feasible:
        raise ValueError("No eligible finite feasible endpoint")
    _, label, point = min(feasible, key=lambda row: (row[0], row[1]))
    return label, point


def seal():
    verify()
    qualifications()
    records, selectors = [], []
    for source in SOURCES:
        for arm in ARMS:
            q = read(HERE / f"qualification_{source}_{arm}.json")
            for method in METHODS:
                path = HERE / f"fit_{source}_{arm}_{method}.json"
                outcome = read(path)
                if (outcome["source_id"], outcome["arm"], outcome["method"]) != (
                    source,
                    arm,
                    method,
                ):
                    raise ValueError("Exact twenty-outcome inventory required")
                records.append(dict(path=str(path), sha256=digest(path)))
                points = dict(
                    q["incumbents"][method],
                    returned=dict(
                        vector=outcome["vector"],
                        nuisance=outcome["nuisance"],
                        audit=outcome["audit"],
                    ),
                )
                label, point = choose(points)
                selectors.append(
                    dict(
                        source_id=source,
                        arm=arm,
                        method=method,
                        selected=label,
                        point=point,
                        candidates=points,
                    )
                )
    save(
        HERE / "outcomes_seal.json",
        dict(
            records=records,
            selectors=selectors,
            protocol_sha256=digest(HERE / "protocol_v2.json"),
            all20_complete=True,
            selection="Finite feasible TRAIN minimum, strict independent; no window selection",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "qualify", "run", "seal"))
    parser.add_argument("--source", choices=SOURCES)
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--method", choices=METHODS)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    elif args.action == "qualify":
        qualify(args.source)
    elif args.action == "run":
        run(args.source, args.arm, args.method)
    else:
        seal()
