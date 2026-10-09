"""Fresh downstream ablations from immutable production/regional inputs."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from dependencies import (
    HARD60_SCORE,
    DynamicRFObjective,
    Hard60Objective,
    InitialClockObjective,
    JointClockObjective,
    SlopePrior,
    arm_selected,
    error_km,
    initial_fit,
    json_value,
    load,
    read,
    reduce_bank,
    rf_fit,
    select_documents,
    timing_fit,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")
STAGES = ("B0", "B1", "B2", "B3", "C3", "B4", "C4", "B4W", "C5", "B5", "C6", "B6", "B7")


def write(path, value):
    assert not path.exists(), f"Preserve receipt {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_value(value), indent=2) + "\n")


def archived(selected, stage):
    return dict(
        stage=stage,
        error_km=selected["horizontal_error_m"] / 1000,
        posterior_rms_hz=selected["posterior_rms_hz"],
        converged=selected["converged"],
        objective=selected["objective"],
        archived=True,
        selected=selected,
    )


def setup(case, document):
    selected = arm_selected(document, "fitted-c")
    start = next(
        r["fit"]
        for r in document["diagnostics"]["final_starts"]
        if r["arm"] == "fitted-c"
        and r["basin"] == selected["source_basin"]
        and r["fit"]
        and r["fit"]["converged"]
        and abs(r["fit"]["objective"] - selected["objective"]) < 1e-9
    )
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    cal = document["diagnostics"]["calibrations"][selected["source_basin"]]
    base = Hard60Objective(
        case.prepared.observations,
        case.bank.select([lookup[n] for n in selected["satellites"]]),
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
    )
    seed = np.asarray(start["vector"])
    # Verify reused physical baseline, without selecting by reference error.
    np.testing.assert_allclose(base.evaluate(seed)[0], start["objective"], atol=1e-6, rtol=0)
    return base, cal["correction"], seed


def evaluate(binding, digest):
    member = binding["member"]
    label = member["inventory_label"]
    destination = HERE / "results" / f"{label}.json"
    if destination.exists():
        assert read(destination)["protocol_sha256"] == digest
        return
    started = time.monotonic()
    stages, raw, reasons = {}, {}, {}
    try:
        case, baseline, _ = load(binding["loader_binding"])
        loaded = time.monotonic()
        documents = dict(baseline=baseline)
        for name in ("sep25", "sep50"):
            doc = read(ROOT / binding["regions"][name])
            for key in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
                assert doc[key] == baseline[key]
            documents[name] = doc
        selected, sources = select_documents(documents)
        stages["B0"] = {a: archived(arm_selected(baseline, a), "B0") for a in ARMS}
        stages["B1"] = {a: archived(selected[a], "B1") for a in ARMS}

        def run(name, model, seed, clock, fallback, fitter, document):
            rows = {}
            for arm in ARMS:
                path = HERE / "attempts" / label / f"{name}-{arm}.json"
                if path.exists():
                    saved = read(path)
                    assert saved["protocol_sha256"] == digest
                    row = saved["fit"]
                else:
                    kwargs = dict(arm=arm, maximum_seconds=90, maximum_iterations=600)
                    if clock is not None:
                        kwargs["clock_seed"] = np.asarray(clock).copy()
                    try:
                        row = json_value(fitter(model, np.asarray(seed).copy(), **kwargs))
                        if arm == "zero-c":
                            assert row["vector"][6] == 0
                        if arm == "zero-c" or getattr(model, "fixed_rf_drift", False):
                            assert all(x == 0 for x in row.get("rf_drift_coefficients", []))
                        row.update(
                            stage=name,
                            arm=arm,
                            error_km=error_km(case.prior, row["vector"], document),
                        )
                    except Exception as error:
                        row = dict(converged=False, stage=name, arm=arm, failure=repr(error))
                    write(path, dict(protocol_sha256=digest, fit=row))
                rows[arm] = row
            raw[name] = rows
            stages[name] = {a: rows[a] if rows[a]["converged"] else fallback[a] for a in ARMS}
            return rows

        base0, correction0, seed0 = setup(case, baseline)
        run(
            "B2",
            InitialClockObjective(base0, correction0["nodes_s"], correction0["knots_hz"], 2),
            seed0,
            None,
            stages["B0"],
            initial_fit,
            baseline,
        )
        document = documents[sources["fitted-c"]]
        base, correction, seed = setup(case, document)
        nodes, knots = correction["nodes_s"], correction["knots_hz"]
        joint = run(
            "B3",
            InitialClockObjective(base, nodes, knots, 2),
            seed,
            None,
            stages["B1"],
            initial_fit,
            document,
        )
        if not joint["fitted-c"]["converged"]:
            raise Prerequisite("B3 fitted-c unqualified", "B3")
        chosen = joint["fitted-c"]
        seed, clock = np.asarray(chosen["vector"]), chosen["clock_coefficients"]
        run(
            "C3",
            JointClockObjective(base, nodes, knots, 2),
            seed,
            clock,
            stages["B3"],
            timing_fit,
            document,
        )
        try:
            subset, seed, removed = reduce_bank(base, seed, 5)
        except ValueError as error:
            raise Prerequisite(str(error), "B3") from error
        pruned = run(
            "B4",
            JointClockObjective(subset, nodes, knots, 2),
            seed,
            clock,
            stages["B3"],
            timing_fit,
            document,
        )
        if not pruned["fitted-c"]["converged"]:
            raise Prerequisite("B4 fitted-c unqualified", "B4")
        chosen = pruned["fitted-c"]
        seed, clock = np.asarray(chosen["vector"]), chosen["clock_coefficients"]
        run(
            "C4",
            JointClockObjective(subset, nodes, knots, 2),
            seed,
            clock,
            stages["B4"],
            timing_fit,
            document,
        )
        wide = run(
            "B4W",
            JointClockObjective(subset, nodes, knots, 4),
            seed,
            clock,
            stages["B4"],
            timing_fit,
            document,
        )
        chosen = wide["fitted-c"] if wide["fitted-c"]["converged"] else chosen
        seed = np.asarray(chosen["vector"])
        clock = np.r_[chosen["clock_coefficients"], 0.0, 0.0]
        run(
            "C5",
            DynamicRFObjective(subset, nodes, knots, 0),
            seed,
            clock,
            stages["B4W"],
            rf_fit,
            document,
        )
        dynamic = run(
            "B5",
            DynamicRFObjective(subset, nodes, knots, 50),
            seed,
            clock,
            stages["B4W"],
            rf_fit,
            document,
        )
        if dynamic["fitted-c"]["converged"]:
            seed = np.asarray(dynamic["fitted-c"]["vector"])
            clock = np.asarray(dynamic["fitted-c"]["clock_coefficients"])
        control = DynamicRFObjective(subset, nodes, knots, 50)
        _, _, _, terms = control.evaluate_joint(seed, clock)
        mass = terms.responsibilities.sum(axis=0)
        centers = np.divide(
            terms.responsibilities.T @ subset.observations.times_s,
            mass,
            out=np.full(len(mass), subset.observations.time_center_s),
            where=mass > 1e-12,
        )
        run("C6", control, seed, clock, stages["B5"], rf_fit, document)
        for name, sigma in (("B6", 0.25), ("B7", 0.5)):
            model = SlopePrior(subset, nodes, knots, centers, sigma)
            run(name, model, seed, model.expand_clock(clock), stages["C6"], rf_fit, document)
        reasons["removed_satellites"] = removed
    except Prerequisite as error:
        for name in STAGES:
            if name not in stages:
                stages[name] = stages[error.fallback]
                reasons[name] = str(error)
    except Exception as error:
        write(
            destination,
            dict(
                status="failed",
                member=member,
                error=repr(error),
                protocol_sha256=digest,
                stages=stages,
                raw=raw,
            ),
        )
        print(label, "FAILED", repr(error), flush=True)
        return
    assert set(stages) == set(STAGES)
    write(
        destination,
        dict(
            status="complete",
            member=member,
            protocol_sha256=digest,
            stages=stages,
            raw=raw,
            reasons=reasons,
            region_sources=sources,
            load_seconds=loaded - started,
            elapsed_s=time.monotonic() - started,
        ),
    )
    print(label, "complete", flush=True)


class Prerequisite(Exception):
    def __init__(self, reason, fallback):
        super().__init__(reason)
        self.fallback = fallback


def main(shard):
    plan = read(HERE / "protocol.json")
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert 0 <= shard < 2
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for i, binding in enumerate(plan["members"]):
        if i % 2 == shard:
            evaluate(binding, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
