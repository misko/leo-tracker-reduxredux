"""Source-frozen zero-fit actual qualification; deliberately has no fit command."""
# ruff: noqa: E402

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import ports
import stencils
from numpy.testing import assert_allclose, assert_array_equal

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
MODEL = HERE.parent / "coherent_model"
DENSITY = HERE.parent / "coherent_density"
BLOCKED = REPORTS / "2026_10_17_dsx01_iteration5/blocked_cold"
ATTEMPT = BLOCKED / "S03-block20-parity0"
DATA = REPORTS / "2026_10_16_dsx01_fast_association_losses"
sys.path.insert(0, str(BLOCKED))
from leo.analysis.hard60_bounded_fit import _Problem
from leo.application.shared_fast_position import plain
from training_context import load_training_context


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(plain(value), stream, indent=2, allow_nan=False)
        stream.write("\n")


def freeze():
    # Bind actual sealed manifests, without changing either component folder.
    component_binding = {}
    for directory in (MODEL, DENSITY):
        manifest_path = directory / "manifest.json"
        manifest = read(manifest_path)
        component_binding[str(manifest_path)] = digest(manifest_path)
        for row in manifest["files"]:
            path = directory / row["path"]
            if digest(path) != row["sha256"]:
                raise ValueError("Sealed component file changed: " + str(path))
            component_binding[str(path)] = row["sha256"]
        for path, sha in manifest.get("authority_sha256", {}).items():
            if digest(path) != sha:
                raise ValueError("Sealed component authority changed: " + path)
            component_binding[path] = sha
    module("coherent_pilot_freeze_adapter", MODEL / "adapter.py")
    paths = [
        HERE / n
        for n in (
            "qualify.py",
            "ports.py",
            "stencils.py",
            "test_ports.py",
            "test_stencils.py",
            "test_qualify.py",
            "PROTOCOL.md",
            "ROOT_GATE.md",
        )
    ]
    paths += [
        BLOCKED / "training_context.py",
        BLOCKED / "derive_blocks.py",
        ATTEMPT / "training-input.json",
        ATTEMPT / "derivation.json",
        ATTEMPT / "output/terminal.json",
        REPORTS / "2026_10_16_dsx01_models/common.py",
        DATA / "context-observations.jsonl",
    ]
    paths += sorted((ATTEMPT / "output/stages").glob("*.json"))
    paths += [
        REPORTS / "2026_10_17_dsx01_iteration4/cold_pipeline" / n
        for n in ("evaluate.py", "support_diagnostics.py")
    ]
    binding = {str(p): digest(p) for p in paths}
    binding.update(component_binding)
    # Preserve the imported installed scientific runtime, rather than a moving
    # /opt package name alone. No preparation or numerical objective is run here.
    for name, loaded in tuple(sys.modules.items()):
        path = getattr(loaded, "__file__", None)
        if name.startswith("leo.") and path and Path(path).is_file():
            binding[str(Path(path).resolve())] = digest(path)
    save(
        HERE / "source_freeze.json",
        dict(
            source_sha256=binding,
            eta=0.1,
            epsilon=0.12,
            source="S03 public TRAIN-only original terminal",
            observations=2073,
            candidates=45,
            policies=["independent", "automatic"],
            RFarms=["fitted-c", "zero-c"],
            fits=0,
            maximum_seconds=180,
            external_term_seconds=180,
            external_kill_seconds=185,
            scaled_steps=stencils.STEPS,
            FDgate="max(.001,1e-5*abs(analytic),32ULP(J)/abs(h))",
            source_cell_stencils="Central or second-order same-cell side; preselected",
            actual_call_inventory="All four coordinate layouts persisted before new-model scoring",
            no_held_CFO_score=True,
            no_station_reference=True,
            root_fit_gate_required=True,
        ),
    )


def verify():
    for path, sha in read(HERE / "source_freeze.json")["source_sha256"].items():
        if digest(path) != sha:
            raise ValueError("Frozen source/input changed: " + path)


def cells(context, vector):
    tau = vector[7] + context.model.basis @ vector[8:]
    query = context.model.scored_observations.times_s[:, None] + tau[None, :]
    bank = context.bank
    step = bank.nodes_s[1] - bank.nodes_s[0]
    if query.min() < bank.nodes_s[0] or query.max() > bank.nodes_s[-1]:
        return None
    return np.minimum(np.floor((query - bank.nodes_s[0]) / step).astype(int), len(bank.nodes_s) - 2)


def inventory(context):
    model = context.model
    v, n = context.vector, context.nuisance
    problem = _Problem(model, v, rf_arm="zero-c" if context.fixed_c else "fitted-c")
    limits = np.r_[np.full(model.clock_count, 2000.0), model.group_limits]
    scales = np.r_[np.full(model.clock_count, 50.0), model.group_scales]
    reference = cells(context, v)

    def feasible(a, b):
        return (
            np.all(a >= problem.lower - 1e-10)
            and np.all(a <= problem.upper + 1e-10)
            and np.min(problem.constraints(a), initial=0) >= -1e-10
            and np.all(abs(b) <= limits + 1e-10)
        )

    if not feasible(v, n):
        raise ValueError("Unmodified source endpoint infeasible in declared broad domain")
    assert_allclose(model.basis.T @ model.basis, np.eye(model.basis.shape[1]), atol=1e-12, rtol=0)
    directions = []
    for index in range(7):
        if context.fixed_c and index == 6:
            continue
        dv = np.zeros_like(v)
        dv[index] = problem.scales[index]
        directions.append((f"physical[{index}]", dv, np.zeros_like(n)))
    for index, number in enumerate(context.bank.numbers):
        dv = np.zeros_like(v)
        dv[7] = 1 / len(context.bank.numbers)
        dv[8:] = model.basis[index]
        directions.append((f"total_tau[{int(number)}]", dv, np.zeros_like(n)))
    for index, scale in enumerate(scales):
        dn = np.zeros_like(n)
        dn[index] = scale
        directions.append((f"nuisance[{index}]", np.zeros_like(v), dn))
    records = []
    for name, dv, dn in directions:

        def valid(h, _dv=dv, _dn=dn):
            a, b = v + h * _dv, n + h * _dn
            if not feasible(a, b):
                return False
            shifted = cells(context, a)
            return shifted is not None and np.array_equal(shifted, reference)

        selected = stencils.choose(valid)
        records.append(dict(name=name, dv=dv, dn=dn, stencil=selected))
    return dict(
        vector=v,
        nuisance=n,
        labels=model.labels,
        coordinate_stencils=records,
        directions=len(records),
        FDobjectives=1 + 2 * len(records),
        source_cells=reference,
        fitter_constructor_margin_max_vector_difference=float(np.max(abs(problem.start - v))),
    )


def qualify():
    started = time.monotonic()
    verify()
    adapter = module("coherent_pilot_adapter", MODEL / "adapter.py")
    base = load_training_context()
    if len(base.observations.times_s) != 2073 or len(base.bank.numbers) != 45:
        raise ValueError("Exact declared TRAIN source required")
    contexts = {}
    plans = {}
    for arm in ("fitted-c", "zero-c"):
        v = base.vector.copy()
        if arm == "zero-c":
            v[6] = 0.0
        source = replace(base, vector=v, nuisance=base.nuisance.copy(), fixed_c=arm == "zero-c")
        for policy in ("independent", "automatic"):
            key = policy + "_" + arm
            contexts[key] = adapter.make_context(source, policy=policy, eta=0.1, epsilon=0.12)
            plans[key] = inventory(contexts[key])
    maximum = sum(p["FDobjectives"] for p in plans.values()) + 2
    save(
        HERE / "actual_inventory.json",
        dict(
            cases=plans,
            maximum_objectives=maximum,
            additional_explicit_predictor_calls=8,
            public_preparation_additional=True,
            fits=0,
            held_CFO_scored=False,
        ),
    )
    calls = 0
    results = []
    predictions = {}

    def evaluate(ctx, v, n):
        nonlocal calls
        if calls >= maximum or time.monotonic() - started >= 178:
            raise TimeoutError("Declared whole qualification bound")
        calls += 1
        return ctx.model.evaluate_details(v, n)

    for key, ctx in contexts.items():
        v, n = ctx.vector, ctx.nuisance
        plan = plans[key]
        ev, details = evaluate(ctx, v, n)
        assert_array_equal(details["interpolation_cells"], plan["source_cells"])
        assert_allclose(
            ev[3].responsibilities.sum(axis=1) + ev[3].clutter_probability, 1.0, atol=1e-12, rtol=0
        )
        assert_allclose(details["group_nll"].sum(), ev[3].nll, atol=1e-8, rtol=0)
        group = ports.partition(ctx.model.labels, ctx.model.scored_observations)
        if key.startswith("automatic"):
            if group["maximum_length"] > 24 or group["groups"] == 2073:
                raise ValueError("Automatic coherent partition must be bounded and nontrivial")
            if "row_nll" in details:
                raise ValueError("No fictional coherent per-row NLL permitted")
        else:
            assert group["groups"] == 2073
        errors = []
        for coordinate in plan["coordinate_stencils"]:
            dv, dn = np.array(coordinate["dv"]), np.array(coordinate["dn"])
            stencil = coordinate["stencil"]
            values = [evaluate(ctx, v + h * dv, n + h * dn)[0][0] for h in stencil["offsets"]]
            observed = stencils.finite_difference(ev[0], values, stencil)
            analytic = float(ev[1] @ dv + ev[2] @ dn)
            allowed = stencils.tolerance(ev[0], analytic, stencil)
            errors.append(
                dict(
                    name=coordinate["name"],
                    analytic=analytic,
                    FD=observed,
                    absolute_error=abs(observed - analytic),
                    allowed=allowed,
                    stencil=stencil,
                )
            )
            if abs(observed - analytic) > allowed:
                save(HERE / f"failed_direction_{key}.json", errors[-1])
                raise AssertionError(
                    "Actual full-gradient gate failed: " + key + " " + coordinate["name"]
                )
        predictions[key] = details["prediction_hz"].copy()
        if key.startswith("independent"):
            singleton = replace(ctx, model=ctx.full_model)
            other = evaluate(singleton, v, n)[0]
            for a, b in zip(ev[:3], other[:3], strict=True):
                assert_array_equal(a, b)
            assert_array_equal(ev[3].responsibilities, other[3].responsibilities)
        results.append(
            dict(
                case=key,
                passed=True,
                partition=group,
                base_objective=float(ev[0]),
                base_training_nll=float(ev[3].nll),
                prior_penalty=details["prior_penalty"],
                FDdirections=errors,
                maximum_absolute_error=max(r["absolute_error"] for r in errors),
                calls_so_far=calls,
                held_CFO_scored=False,
            )
        )
    for arm in ("fitted-c", "zero-c"):
        a, b = contexts["independent_" + arm], contexts["automatic_" + arm]
        assert_array_equal(a.vector, b.vector)
        assert_array_equal(a.nuisance, b.nuisance)
        assert_array_equal(predictions["independent_" + arm], predictions["automatic_" + arm])
    # Read only metadata fields; never score or construct groups from held CFO.
    fields = ("observation_id", "time_s", "actual_rf_hz", "receiver", "channel")
    metadata = []
    for line in (DATA / "context-observations.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["source_id"] == "S03":
            metadata.append({k: row[k] for k in fields})
    blank = ports.metadata_only(metadata)
    changed = ports.metadata_only(metadata, dummy_cfo=123456.0)
    roles = ports.role_masks(blank.window_ids, read(ATTEMPT / "derivation.json")["membership"])
    if {k: int(v.sum()) for k, v in roles.items()} != {"train": 2073, "held": 1909, "boundary": 6}:
        raise ValueError("Exact metadata/role inventory required")
    transport = []
    for key, ctx in contexts.items():
        a = adapter.predict_coherent(ctx, ctx.vector, ctx.nuisance, blank)
        b = adapter.predict_coherent(ctx, ctx.vector, ctx.nuisance, changed)
        ports.same_predictions(a, b)
        use = roles["train"]
        assert_array_equal(np.asarray(blank.window_ids)[use], ctx.observations.window_ids)
        assert_allclose(a["prediction_hz"][use], predictions[key], atol=1e-9, rtol=0)
        transport.append(dict(case=key, held_CFO_blind=True, TRAINphysics_transport=True))
    verify()
    save(
        HERE / "qualification.json",
        dict(
            passed=True,
            cases=results,
            transport=transport,
            objectives=calls,
            maximum_objectives=maximum,
            explicit_predictor_calls=8,
            elapsed_seconds=time.monotonic() - started,
            fits=0,
            held_CFO_scored=False,
            root_fit_authorization_required=True,
            partition_conditioning_disclosed=True,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "qualify"))
    action = parser.parse_args().action
    if action == "freeze":
        freeze()
    else:
        try:
            qualify()
        except Exception as error:
            save(
                HERE / "qualification_failure.json",
                dict(
                    type=type(error).__name__,
                    reason=str(error),
                    fits=0,
                    partial_checks_preserved=True,
                    root_fit_gate=False,
                ),
            )
            raise
