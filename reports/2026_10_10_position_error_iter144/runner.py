"""Bounded causal catalogue sensitivity; preparation, never a position fitter."""

import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from catalogue_policy import DAY_NS, MAXIMUM_DISTINCT, classify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DESIGN_BUDGET_BYTES = 2 * 1024**3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def snapshot_identity(ref):
    return dict(
        provider=ref.provider,
        collected_utc_ns=ref.collected_utc_ns,
        sha256=ref.sha256,
        byte_size=ref.byte_size,
    )


def choose_snapshot(reader, original, original_records, selected_ids, parse_records):
    """Public reads capped before fetch, with read/parse failures consuming cap."""
    refs = [
        s
        for s in reader.list_snapshots(original.provider)
        if original.collected_utc_ns - DAY_NS <= s.collected_utc_ns < original.collected_utc_ns
    ]
    refs.sort(key=lambda s: (s.collected_utc_ns, s.sha256), reverse=True)
    seen, inspected = {original.sha256}, []
    for ref in refs:
        if ref.sha256 in seen:
            continue
        if len(inspected) == MAXIMUM_DISTINCT:
            break
        seen.add(ref.sha256)
        row = dict(snapshot=snapshot_identity(ref))
        stage = "payload-read-failed"
        try:
            payload = reader.read(ref)
            if not isinstance(payload, str):
                raise TypeError("Public TLE reader must return text")
            row["payload_sha256"] = hashlib.sha256(payload.encode("ascii")).hexdigest()
            stage = "payload-parse-failed"
            records = parse_records(payload)
            categories = classify(original_records, records, selected_ids)
            row.update(status="classified", candidates=categories)
        except Exception as exc:
            row.update(status=stage, error=repr(exc))
            inspected.append(row)
            continue
        inspected.append(row)
        if categories["changed"]:
            return (
                ref,
                payload,
                dict(
                    original=snapshot_identity(original),
                    inspected=inspected,
                    selected=snapshot_identity(ref),
                ),
            )
    return (
        None,
        None,
        dict(original=snapshot_identity(original), inspected=inspected, selected=None),
    )


def prepare_arm(model, endpoint, arm, adapter):
    """One exact ordinary endpoint evaluation through the audited adapter."""
    n, k = len(model.observations.times_s), len(model.bank.numbers)
    p = model.size + len(model.initial_clock)
    estimated = 8 * (4 * n * k * p + 20 * n * k + 4 * p * p + 4096 * p)
    if estimated > DESIGN_BUDGET_BYTES:
        raise MemoryError(f"Conditional-design guard: {estimated} > {DESIGN_BUDGET_BYTES}")
    result = adapter.construct(model, endpoint, arm)
    # Keep both admitted arms before any alternative; release full Jacobian,
    # including the spatial view retaining it, as soon as admission completes.
    result["spatial"] = result["spatial"].copy()
    result.pop("full_jacobian")
    result["estimated_workspace_bytes"] = estimated
    return result


def record_pairs(payload):
    from leo.sky.propagation import parse_element_set_records

    records = parse_element_set_records(payload)
    if len({r.satellite_number for r in records}) != len(records):
        raise ValueError("Duplicate NORAD element records")
    return {r.satellite_number: (r.first_line, r.second_line) for r in records}


def audit_member(
    model,
    case,
    endpoints,
    reader,
    adapter,
    projected,
    *,
    propagate,
    parse_catalogue,
    bank_type,
    predictor,
    snapshot_sink=None,
    progress=None,
):
    """No optimizer, no reference inputs, original endpoint arms independent."""
    progress = {} if progress is None else progress
    progress["admissions"] = {}
    designs = {}
    for arm in ("fitted-c", "zero-c"):
        try:
            designs[arm] = prepare_arm(model, endpoints[arm], arm, adapter)
            progress["admissions"][arm] = dict(
                status="complete", objective_delta=designs[arm].get("objective_delta")
            )
        except Exception as exc:
            progress["admissions"][arm] = dict(status="failed", error=repr(exc))
            raise
    original = reader.select_latest_before(case["prepared"].start_utc_ns - 505_000_000_000)
    if original.digest != case["model_identity"]["snapshot_sha256"]:
        raise ValueError("Pinned causal snapshot changed")
    payload = reader.read(original)
    selected, earlier_payload, selection = choose_snapshot(
        reader, original, record_pairs(payload), model.bank.numbers.tolist(), record_pairs
    )
    if snapshot_sink is not None:
        snapshot_sink(selection)
    progress["snapshots"] = selection
    if selected is None:
        return dict(
            status="complete",
            outcome="no-earlier-changed-snapshot",
            snapshots=selection,
            arms={},
            optimizer_calls=0,
            ordinary_endpoint_evaluations=2,
        )
    catalogue = parse_catalogue(earlier_payload)
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    common = [int(n) for n in model.bank.numbers if int(n) in lookup]
    indices = [lookup[n] for n in common]
    position, velocity, valid = propagate(
        catalogue, indices, case["prepared"].start_utc_ns, model.bank.nodes_s, np.array([0.0])
    )
    valid_ids = [int(catalogue.satellite_numbers[i]) for i in valid]
    progress["propagation"] = dict(
        original_ids=model.bank.numbers.tolist(),
        common_ids=common,
        valid_ids=valid_ids,
        filtered_ids=[n for n in common if n not in valid_ids],
    )
    if not valid_ids:
        raise ValueError("No common candidates survived public propagation filters")
    bank = bank_type(np.asarray(valid_ids), model.bank.nodes_s, position[:, 0], velocity[:, 0])
    original_lookup = {int(n): i for i, n in enumerate(model.bank.numbers)}
    columns = np.asarray([original_lookup[n] for n in valid_ids], int)
    arms = {}
    for arm in ("fitted-c", "zero-c"):
        endpoint, design = endpoints[arm], designs[arm]
        vector = np.asarray(endpoint["vector"])
        shifts = vector[7] + model.basis @ vector[8:]
        alt, alt_visible, _, _ = predictor(
            bank, model.observations, model.prior, vector[:2], shifts[columns], derivatives=False
        )
        original_geom, original_visible, _, _ = predictor(
            model.bank, model.observations, model.prior, vector[:2], shifts, derivatives=False
        )
        delta = alt - original_geom[:, columns]
        n, k = design["observations"], design["satellites"]
        nuisance = design["nuisance"].reshape(n, k, -1)[:, columns].reshape(n * len(columns), -1)
        spatial = design["spatial"].reshape(n, k, 2)[:, columns].reshape(-1, 2)
        weights = design["weights"].reshape(n, k)
        energies = projected(
            delta.ravel(), spatial, nuisance, weights[:, columns].ravel(), original_row_count=n * k
        )
        normalizer_delta = None
        if len(valid_ids) == len(model.bank.numbers):
            q = model.score.detection_budget / len(valid_ids)

            def log_event(visible, q=q):
                log_p0 = -model.score.clutter_rate + visible.sum(axis=1) * np.log1p(-q)
                return log_p0 - np.log(-np.expm1(log_p0))

            normalizer_delta = float(-np.sum(log_event(alt_visible) - log_event(original_visible)))
        arms[arm] = dict(
            projection=energies,
            common_valid_ids=valid_ids,
            original_ids=model.bank.numbers.tolist(),
            propagation_filtered_ids=[n for n in common if n not in valid_ids],
            omitted_original_weight=float(weights.sum() - weights[:, columns].sum()),
            original_weight=float(weights.sum()),
            prediction_delta_rms_hz=float(np.sqrt(np.mean(delta**2))),
            visibility_changes=int(np.count_nonzero(alt_visible != original_visible[:, columns])),
            event_normalizer_nll_delta=normalizer_delta,
            event_normalizer_scope="Full original bank"
            if normalizer_delta is not None
            else "Unavailable: missing or propagation-filtered candidates",
            estimated_workspace_bytes=design["estimated_workspace_bytes"],
            scope="Valid common candidates only; original responsibilities/visibility "
            "frozen for span weights",
        )
        progress["arms"] = arms
        del designs[arm]
    return dict(
        status="complete",
        outcome="catalogue-sensitivity",
        snapshots=selection,
        arms=arms,
        optimizer_calls=0,
        ordinary_endpoint_evaluations=2,
    )


def main():
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if any(
        os.environ.get(k) != "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("Single-thread environment required")
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    if (
        len(plan["members"]) != 12
        or len({m["label"] for m in plan["members"]}) != 12
        or plan["maximum_workers"] != 1
        or plan["ordinary_endpoint_calls_per_member"] != 2
        or plan["design_budget_bytes"] != DESIGN_BUDGET_BYTES
        or plan["optimizer_calls"] != 0
        or plan["earlier_distinct_payload_cap"] != 10
        or plan["earlier_window_hours"] != 24
        or plan["threads"] != 1
    ):
        raise ValueError("Unexpected diagnostic scope")
    for group in ("sources", "inputs"):
        for path, expected in plan[group].items():
            if sha(ROOT / path) != expected:
                raise ValueError("Frozen diagnostic binding changed")
    bindings = [m for m in plan["members"] if m["label"] == args.label]
    if len(bindings) != 1:
        raise ValueError("Outside fixed cohort")
    binding = bindings[0]
    directory = HERE / "results"
    directory.mkdir(exist_ok=True)
    identity = dict(label=args.label, protocol_sha256=sha(protocol))
    output = directory / (args.label + ".json")
    with output.with_suffix(".claim.json").open("x") as stream:
        json.dump(identity, stream)
    began = time.monotonic()
    counters = dict(ordinary_endpoint_evaluations=0, reconstruction_completed=False)
    progress = {}
    try:
        clean = module(
            "clean131_for144", HERE.parent / "2026_10_09_position_error_iter131/inference_loader.py"
        )
        construction = module(
            "clean132_for144", HERE.parent / "2026_10_10_position_error_iter132/audit.py"
        )
        entry_folder = HERE.parent / "2026_10_09_position_error_iter116"
        sys.path.insert(0, str(entry_folder))
        entry = module("entry116_for144", entry_folder / "entrypoint.py")
        case_binding = binding["case_binding"]
        backend = entry.make_loader(
            ROOT,
            dict(
                case_binding,
                loader_source=entry.LOADER,
                loader_sha256=plan["sources"][entry.LOADER],
            ),
        )
        model, _, case = construction.build_model(
            case_binding,
            clean.InferenceLoader(ROOT, backend.load_case),
            construction.numerical_components(),
        )
        counters["reconstruction_completed"] = True
        progress["reconstruction_work"] = dict(
            control_endpoint_evaluations=1,
            bank_reductions=1,
            scope="Fixed inherited construction; separate from two saved endpoint admissions",
        )
        case["model_identity"] = case_binding["model_identity"]
        endpoint_path = ROOT / binding["endpoints_path"]
        endpoints = json.loads(endpoint_path.read_text())["endpoints"]
        ordinary = model.evaluate_joint

        def counted(vector, clock):
            if counters["ordinary_endpoint_evaluations"] >= 2:
                raise ValueError("Ordinary endpoint evaluation cap exceeded")
            counters["ordinary_endpoint_evaluations"] += 1
            return ordinary(vector, clock)

        model.evaluate_joint = counted
        adapter = module(
            "adapter111_for144", HERE.parent / "2026_10_09_position_error_iter111/adapter.py"
        )
        projected = module("projection144_streamed", HERE / "streamed_projection.py")
        from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
        from leo.analysis.hard60_score import predict_orbits
        from leo.contracts.regional_position import PositionOrbitBank
        from leo.operations.tle_archive import TleArchiveReader
        from leo.sky.propagation import parse_element_sets

        def snapshot_sink(selection):
            receipt = dict(identity, selection=selection)
            with output.with_suffix(".snapshots.json").open("x") as stream:
                json.dump(receipt, stream, indent=2, allow_nan=False)
                stream.write("\n")

        result = audit_member(
            model,
            case,
            endpoints,
            TleArchiveReader(Path("/var/lib/leo/tle")),
            adapter,
            projected.streamed_decompose,
            propagate=propagate_candidate_states,
            parse_catalogue=parse_element_sets,
            bank_type=PositionOrbitBank,
            predictor=predict_orbits,
            snapshot_sink=snapshot_sink,
            progress=progress,
        )
        result = dict(progress, **result)
    except Exception as exc:
        result = dict(progress, status="failed", error=repr(exc), optimizer_calls=0)
    result.update(identity, **counters, elapsed_s=time.monotonic() - began)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
