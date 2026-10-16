"""Explicit qualified runtime ports for unchanged fitted-only DS21 A/B/C.

Original namespaces and modules remain untouched. Genuine generic/coverage
qualification occurs once; exact authority bytes and inventories are checked
before and after bounded preparation/fits. No module globals are patched.
"""

import argparse
import json
import os
import time
from pathlib import Path

import ds21_model_a_pipeline_runtime as previous_runtime
import ds21_model_a_timing_locked_control as authority
import ds21_model_a_timing_runtime_v2 as transport
import model_a_prepared_input_cache as prepared_cache
import model_a_verified_manifest as manifest
import numpy as np

original = authority.original
binding, read, immutable = original.binding, original.read, transport.immutable
UNITS, VIEWS = original.UNITS, original.VIEWS
POLICY = dict(
    schema="ds21-qualified-abc-prepared-cache-v2",
    arm="fitted-c",
    units=list(UNITS),
    maximum_optimizer_calls=54,
    fit_seconds=20,
    iterations=600,
    local_radius_km=25,
    preparation_seconds=5,
    preparation_replay_seconds=45,
    preparation_admission_seconds=120,
    expensive_preparation_workers=1,
    preparation_gate=str(prepared_cache.GATE),
    A_seconds=90,
    BC_seconds=165,
    A_term_seconds=105,
    A_kill_seconds=110,
    BC_term_seconds=175,
    BC_kill_seconds=180,
    validation_reserve_seconds=5,
    reference_usage="none",
    held_usage="none",
    selection="Minimum stationary own training objective, then original start index",
    runtime_only=True,
    failed_retry=False,
)


def sources(scientific):
    return {
        **scientific["source_sha256"],
        **{
            str(Path(p).resolve()): binding(p)["sha256"]
            for p in (
                __file__,
                authority.__file__,
                transport.__file__,
                manifest.__file__,
                prepared_cache.__file__,
                previous_runtime.__file__,
            )
        },
    }


def freeze(directory, *, model_directory, runtime_predecessor=None):
    with prepared_cache.admission():
        return _freeze(
            directory, model_directory=model_directory, runtime_predecessor=runtime_predecessor
        )


def _freeze(directory, *, model_directory, runtime_predecessor=None):
    directory, model_directory = Path(directory).resolve(), Path(model_directory).resolve()
    if (directory / "protocol.json").exists():
        value = read_control(directory)
        if value["model_directory"] != str(model_directory):
            raise ValueError("Existing facade scientific parent differs")
        expected = str(Path(runtime_predecessor).resolve()) if runtime_predecessor else None
        if value["runtime_predecessor"] != expected:
            raise ValueError("Existing runtime predecessor differs")
        return value
    provider = authority.parent_provider(model_directory)
    scientific, parent = provider.read_control(model_directory)
    predecessor, failed = None, {}
    if runtime_predecessor is not None:
        predecessor = Path(runtime_predecessor).resolve()
        prior = previous_runtime.read_control(predecessor)
        if prior["scientific_protocol"] != binding(model_directory / "protocol.json"):
            raise ValueError("Runtime predecessor scientific protocol differs")
        for unit in UNITS:
            folder = predecessor / "units" / unit
            if not (folder / "launch.json").exists() or (folder / "terminal.json").exists():
                continue
            status = read(folder / "termination.json")
            if (
                status.get("state") != "failed"
                or status.get("error_type") != "SliceHardStop"
                or any((folder / k).exists() for k in ("calls", "launches", "terminations"))
            ):
                raise ValueError("Only explicit zero-call preparation failures may migrate")
            failed[unit] = {n: binding(folder / n) for n in ("launch.json", "termination.json")}
    # Preserve genuine schema and exact source/parent authority, with a distinct
    # runtime protocol. Never rewrite/relabel an original scientific protocol.
    case_directory = Path(parent["case_directory"])
    if provider is authority.coverage:
        cov = read(Path(parent["stages"]["coverage-discovery"]) / "protocol.json")
        bank_directory = Path(cov["full_bank"]["path"]).parent
    else:
        bank_directory = Path(parent["stages"]["discovery"])
    directories = {
        case_directory,
        bank_directory,
        *(Path(p) for p in parent["stages"].values()),
        model_directory / "source-snapshot",
    }
    if any(
        directory == p or directory.is_relative_to(p) or p.is_relative_to(directory)
        for p in directories | {model_directory}
    ):
        raise ValueError("Runtime namespace overlaps an immutable scientific ancestor")
    case_source = read(case_directory / "source-protocol.json")
    extra = [
        model_directory / "protocol.json",
        case_directory / "protocol.json",
        case_directory / "source-protocol.json",
        *(Path(case_source[k]["path"]) for k in ("membership", "census", "input")),
        Path(read(case_directory / "protocol.json")["snapshot"]["path"]),
    ]
    reused = None
    if (model_directory / "initialization.json").exists():
        original.initialization(model_directory, scientific)
        reused = binding(model_directory / "initialization.json")
        extra.extend(
            model_directory / name
            for name in (
                "initialization.json",
                "initialization-launch.json",
                "initialization-termination.json",
            )
        )
    src = sources(scientific)
    value = dict(
        policy=POLICY,
        runtime_directory=str(directory),
        label=scientific["label"],
        model_directory=str(model_directory),
        scientific_protocol=binding(model_directory / "protocol.json"),
        scientific_schema=scientific["policy"]["schema"],
        scientific=scientific,
        runtime_predecessor=str(predecessor) if predecessor else None,
        predecessor_protocol=binding(predecessor / "protocol.json") if predecessor else None,
        predecessor_preparation_failures=failed,
        original=dict(inputs=scientific["inputs"]),
        case_protocol=binding(case_directory / "protocol.json"),
        case_source_protocol=binding(case_directory / "source-protocol.json"),
        bank_directory=str(bank_directory),
        bank_protocol=binding(bank_directory / "protocol.json"),
        reused_initialization=reused,
        source_sha256=src,
        snapshot_paths=original.discovery.archive_sources(directory, src),
        authority=manifest.pin_qualified_files(directories, source_files=src, extra_files=extra),
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "protocol.json", value)
    return read_control(directory)


def read_control(directory):
    directory = Path(directory).resolve()
    value = read(directory / "protocol.json")
    if (
        value["policy"] != POLICY
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
    ):
        raise ValueError("Facade policy changed")
    original.pool.shape_parent.validate_archives(directory, value)
    manifest.verify_pinned_files(value["authority"])
    if value["runtime_predecessor"] is not None:
        predecessor = Path(value["runtime_predecessor"])
        prior = previous_runtime.read_control(predecessor)
        if (
            binding(predecessor / "protocol.json") != value["predecessor_protocol"]
            or prior["scientific_protocol"] != value["scientific_protocol"]
        ):
            raise ValueError("Runtime predecessor binding differs")
        for unit, receipts in value["predecessor_preparation_failures"].items():
            for receipt in receipts.values():
                original.read_bound(receipt)
            folder = predecessor / "units" / unit
            if (folder / "terminal.json").exists() or any(
                (folder / k).exists() for k in ("calls", "launches", "terminations")
            ):
                raise ValueError("Preserved zero-call preparation failure inventory differs")
    return value


def prepare_case(frozen):
    return prepared_cache.load(frozen["runtime_directory"], frozen)


def initialization(directory, frozen):
    if frozen["reused_initialization"] is not None:
        return original.initialization(Path(frozen["model_directory"]), frozen["scientific"])
    value = read(Path(directory) / "initialization.json")
    sha = binding(Path(directory) / "protocol.json")["sha256"]
    if (
        value["protocol_sha256"] != sha
        or value["label"] != frozen["label"]
        or value["lift_derivations"] != 6
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
    ):
        raise ValueError("Facade initialization identity/lifts changed")
    identity = dict(protocol_sha256=sha, label=frozen["label"], optimizer_calls=0)
    if read(Path(directory) / "initialization-launch.json") != identity or read(
        Path(directory) / "initialization-termination.json"
    ) != dict(
        **identity,
        state="complete",
        initialization=binding(Path(directory) / "initialization.json"),
    ):
        raise ValueError("Facade initialization launch/termination changed")
    for name in ("A", "B", "C"):
        for view in VIEWS:
            rows, meta = value["starts"][name][view], value["models"][name][view]
            if len(rows) != 6:
                raise ValueError("Facade requires six original physical starts")
            for i, row in enumerate(rows):
                if (
                    row["start"] != i
                    or row["proposal_id"] != original.PROPOSAL_IDS[i]
                    or np.asarray(row["seed"]["vector"]).shape != (meta["parameter_count"],)
                    or np.asarray(row["seed"]["nuisance"]).shape != (meta["nuisance_count"],)
                    or row["local_center"]
                    != frozen["scientific"]["inputs"]["proposals"][i]["point_km"]
                ):
                    raise ValueError("Facade initialization physical layout/order differs")
                if (
                    not np.isfinite(row["seed"]["vector"]).all()
                    or not np.isfinite(row["seed"]["nuisance"]).all()
                ):
                    raise ValueError("Finite original initialization required")
    return value


def initialize(directory):
    """Use unchanged original seed/lift/projection operations on qualified inputs."""
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    prepared_cache.ensure(directory, frozen)
    if frozen["reused_initialization"] is not None or (directory / "initialization.json").exists():
        return initialization(directory, frozen)
    if (directory / "initialization-launch.json").exists():
        raise ValueError("Facade orphan/failed initialization; no retry")
    identity = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        optimizer_calls=0,
    )
    immutable(directory / "initialization-launch.json", identity)
    begun, status = time.monotonic(), dict(**identity, state="failed")
    try:
        with original.discovery.slice_bound(90):
            case = prepare_case(frozen)
            models = original.models_for(case)
            entries = {
                v: original.read_bound(frozen["scientific"]["parent_authority"][f"seeds/{v}.json"])
                for v in VIEWS
            }
            lifts = [
                original.joint.physical_receiver_branches(
                    models["C"]["all"],
                    original.native_proposals.physical_seed(
                        models["C"]["all"], e, original.evaluate_physical_correction
                    ),
                )
                for e in entries["all"]
            ]
            starts, meta = {}, {}
            for name in ("A", "B", "C"):
                starts[name], meta[name] = {}, {}
                for view in VIEWS:
                    model = models[name][view]
                    meta[name][view] = original.metadata(model, case["prepared"][view])
                    starts[name][view] = []
                    for i, entry in enumerate(entries[view]):
                        seed = (
                            original.native_proposals.proposal_start(
                                model, entry, lifts[i], view=view, index=i
                            )
                            if name == "C"
                            else authority.numerical.unused_seed(entry, model, view)
                            if name == "A" and view != "low"
                            else authority.numerical.seed_for(entry, model)
                        )
                        row = dict(
                            start=i,
                            proposal_id=original.PROPOSAL_IDS[i],
                            proposal=entry,
                            seed=seed,
                            local_center=entry["point_km"],
                        )
                        if name == "C":
                            row["receiver_lifts"] = lifts[i]
                        starts[name][view].append(row)
            read_control(directory)
            immutable(
                directory / "initialization.json",
                dict(
                    **identity,
                    starts=starts,
                    models=meta,
                    receiver_lifts=lifts,
                    lift_derivations=6,
                    reference_usage="none",
                    held_usage="none",
                    elapsed_seconds=time.monotonic() - begun,
                ),
            )
            status = dict(
                **identity,
                state="complete",
                initialization=binding(directory / "initialization.json"),
            )
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(directory / "initialization-termination.json", status)
    return initialization(directory, frozen)


def qualify(directory):
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    prepared_cache.ensure(directory, frozen)
    prepared_cache.qualify_equivalence(directory, frozen)
    launch, done = (
        directory / "qualification-launch.json",
        directory / "qualification-termination.json",
    )
    if launch.exists() or done.exists():
        return qualification(directory)
    identity = dict(
        protocol=binding(directory / "protocol.json"),
        cache=binding(directory / "training-cache.json"),
        cache_arrays=binding(directory / "training-cache.npz"),
        optimizer_calls=0,
        predictor_calls=0,
        objective_calls=0,
    )
    with launch.open("x") as stream:
        json.dump(identity, stream)
        stream.flush()
        os.fsync(stream.fileno())
    status = dict(**identity, state="failed")
    try:
        value = _qualify(directory)
        status = dict(
            **identity, state="complete", qualification=binding(directory / "qualification.json")
        )
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(done, status)
    return value


def qualification(directory):
    directory = Path(directory).resolve()
    identity = dict(
        protocol=binding(directory / "protocol.json"),
        cache=binding(directory / "training-cache.json"),
        cache_arrays=binding(directory / "training-cache.npz"),
        optimizer_calls=0,
        predictor_calls=0,
        objective_calls=0,
    )
    value = read(directory / "qualification.json")
    prepared_cache.equivalence_result(directory)
    if (
        read(directory / "qualification-launch.json") != identity
        or read(directory / "qualification-termination.json")
        != dict(
            **identity, state="complete", qualification=binding(directory / "qualification.json")
        )
        or any(value.get(k) != v for k, v in identity.items())
        or value["stage_seconds"]["preparation_seconds"] > 5
    ):
        raise ValueError("Successful source-bound zero-fit qualification required")
    return value


def _qualify(directory):
    stages, start = {}, time.monotonic()
    frozen = read_control(directory)
    stages["authority_before_seconds"] = time.monotonic() - start
    start = time.monotonic()
    with original.discovery.slice_bound(5):
        case = prepare_case(frozen)
    stages["preparation_seconds"] = time.monotonic() - start
    start = time.monotonic()
    read_control(directory)
    stages["authority_after_seconds"] = time.monotonic() - start
    value = dict(
        protocol=binding(directory / "protocol.json"),
        cache=binding(directory / "training-cache.json"),
        cache_arrays=binding(directory / "training-cache.npz"),
        label=frozen["label"],
        stage_seconds=stages,
        optimizer_calls=0,
        predictor_calls=0,
        objective_calls=0,
        training_windows={v: len(case["prepared"][v].observations.window_ids) for v in VIEWS},
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "qualification.json", value)
    return value


def select_unit(unit, rows):
    name, _, names = original.unit_spec(unit)
    if name != "A":
        if set(rows) != set(names):
            raise ValueError("Facade half/full view must retain all six attempts")
        return original.select(list(rows.values()))
    expected = (
        {"low"}
        if not rows.get("low", {}).get("stationary")
        else {"low", "high"}
        if not rows.get("high", {}).get("stationary")
        else {"low", "high", "final"}
    )
    if set(rows) != expected:
        raise ValueError("Facade sequential prerequisite call inventory differs")
    return rows.get("final") if rows.get("final", {}).get("stationary") else None


def validate_unit(directory, unit, frozen):
    directory = Path(directory).resolve()
    value = read(directory / "units" / unit / "terminal.json")
    if (
        value["protocol_sha256"] != binding(directory / "protocol.json")["sha256"]
        or value["unit"] != unit
        or value["label"] != frozen["label"]
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
    ):
        raise ValueError("Facade unit identity differs")
    if value["state"] in {
        "recovered-metadata-only",
        "reused-sealed-original",
        "reused-sealed-runtime",
    }:
        if value["state"] == "reused-sealed-runtime":
            manifest.verify_pinned_files(value["runtime_unit_inventory"])
        for receipt in value["original_receipts"].values():
            original.read_bound(receipt)
        rows = value["calls"]
        for key, row in rows.items():
            if original.read_bound(value["original_receipts"][f"calls/{key}.json"]) != row:
                raise ValueError("Facade recovered numerical call fields changed")
    elif value["state"] == "complete":
        folder = directory / "units" / unit
        rows = original.calls(directory, unit, value["protocol_sha256"])
        if rows != value["calls"]:
            raise ValueError("Facade scientific call rows changed")
        termination = read(folder / "termination.json")
        identity = dict(protocol_sha256=value["protocol_sha256"], unit=unit)
        if (
            read(folder / "launch.json") != identity
            or termination["state"] != "complete"
            or any(termination.get(k) != v for k, v in identity.items())
            or termination["terminal"] != binding(folder / "terminal.json")
            or value["optimizer_calls"] != len(rows)
            or value["reused_optimizer_calls"] != 0
        ):
            raise ValueError("Facade outer completion differs")
    else:
        raise ValueError("Unknown facade unit outcome")
    if value["selection"] != select_unit(unit, rows):
        raise ValueError("Facade own training selector differs")
    name, view, _ = original.unit_spec(unit)
    for key, row in rows.items():
        expected = dict(arm="fitted-c", seconds=20, iterations=600)
        if name == "A" and key == "high":
            expected["fixed_position"] = True
        else:
            expected.update(local_radius_km=25, local_center=row["local_center"])
        index = int(view) if name == "A" else int(key)
        if (
            row["options"] != expected
            or row["start"] != index
            or row["local_center"] != frozen["scientific"]["inputs"]["proposals"][index]["point_km"]
        ):
            raise ValueError("Facade original call options/center differ")
    return value


def recover(directory, unit, *, process_receipt):
    """Recover declared complete A call triples without scientific evaluations."""
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    name, _, names = original.unit_spec(unit)
    if name != "A":
        raise ValueError("This initial recovery scope requires a complete A path")
    process_receipt = binding(process_receipt)
    process = original.read_bound(process_receipt)
    process_launch = binding(Path(process_receipt["path"]).with_name("launch.json"))
    job = original.read_bound(process_launch)["job"]
    argv = job["argv"]
    if (
        process.get("status") not in {"failed", "timeout"}
        or "--unit" not in argv
        or argv[argv.index("--unit") + 1] != unit
        or process.get("id") != job["id"]
    ):
        raise ValueError("Explicit terminal-process receipt required")
    target = Path(argv[3]).resolve()
    if target != Path(frozen["model_directory"]):
        review = read(target / "protocol.json")
        if review.get("model_directory") != frozen["model_directory"]:
            raise ValueError("Terminal process belongs to another scientific namespace")
    parent = Path(frozen["model_directory"])
    rows = original.calls(parent, unit, frozen["scientific_protocol"]["sha256"])
    if set(rows) != set(names) or any(not r["stationary"] for r in rows.values()):
        raise ValueError("Recovery requires three complete stationary original calls")
    index = int(unit.split("-")[1])
    for key, row in rows.items():
        expected = dict(arm="fitted-c", seconds=20, iterations=600)
        if key == "high":
            expected["fixed_position"] = True
        else:
            expected.update(local_radius_km=25, local_center=row["local_center"])
        if (
            row["options"] != expected
            or row["start"] != index
            or row["local_center"] != frozen["scientific"]["inputs"]["proposals"][index]["point_km"]
            or row["stationary"]
            != original.transfer.stationary(
                row["fit"], row["local_center"], row["parameter_count"], row["nuisance_count"]
            )
        ):
            raise ValueError("Recovered original call options/stationarity differ")
    initial = initialization(directory, frozen)
    low = initial["starts"]["A"]["low"][index]
    if rows["low"]["seed"] != low["seed"] and (
        rows["low"]["seed"]["vector"] != low["seed"]["vector"]
        or rows["low"]["seed"]["nuisance"] != low["seed"]["nuisance"]
    ):
        raise ValueError("Recovered low physical seed differs")
    if (
        rows["high"]["seed"]["vector"][:2] != rows["low"]["fit"]["vector"][:2]
        or rows["final"]["seed"]["vector"][:2] != rows["low"]["fit"]["vector"][:2]
        or rows["final"]["seed"]["vector"][7:] != rows["high"]["fit"]["vector"][7:]
    ):
        raise ValueError("Recovered own-path stage dependency differs")
    receipts = {
        "process": process_receipt,
        "process_launch": process_launch,
        **{
            str(p.relative_to(parent / "units" / unit)): binding(p)
            for p in (parent / "units" / unit).rglob("*.json")
        },
    }
    value = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        unit=unit,
        state="recovered-metadata-only",
        original_receipts=receipts,
        calls=rows,
        selection=rows["final"],
        optimizer_calls=0,
        reused_optimizer_calls=3,
        recovery_predictor_calls=0,
        recovery_objective_calls=0,
        unavailable_diagnostics=["offset_timing_diagnostic", "calibration_projection"],
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "units" / unit / "terminal.json", value)
    return validate_unit(directory, unit, frozen)


def run(directory, unit):
    directory = Path(directory).resolve()
    name, view, names = original.unit_spec(unit)
    cap = 90 if name == "A" else 165
    begun, frozen = time.monotonic(), read_control(directory)
    qualification(directory)
    initial = initialization(directory, frozen)
    folder = directory / "units" / unit
    if (folder / "terminal.json").exists():
        return validate_unit(directory, unit, frozen)
    if (folder / "launch.json").exists():
        raise ValueError("Facade failed/orphan unit; no retry")
    if any(
        (Path(frozen["model_directory"]) / "units" / unit / k).exists()
        for k in ("terminal.json", "launches", "slices")
    ):
        raise ValueError("Original unit attempted; explicit reuse/recovery required")
    sha = binding(directory / "protocol.json")["sha256"]
    identity = dict(protocol_sha256=sha, unit=unit)
    immutable(folder / "launch.json", identity)
    rows, stage_values, status = {}, {}, dict(**identity, state="failed")
    try:
        with original.discovery.slice_bound(5):
            case = prepare_case(frozen)
        with original.discovery.slice_bound(max(0.001, cap - (time.monotonic() - begun))):
            models = original.models_for(case)
            if {
                m: {v: original.metadata(models[m][v], case["prepared"][v]) for v in VIEWS}
                for m in models
            } != initial["models"]:
                raise ValueError("Facade original ABC model metadata differs")

            def stage_fit(key, model, vector, nuisance, options):
                index = int(view) if name == "A" else int(key)
                center = frozen["scientific"]["inputs"]["proposals"][index]["point_km"]
                if time.monotonic() - begun + 20 + 5 >= cap:
                    raise TimeoutError("Insufficient original unit budget; no retry")
                path = folder / "calls" / f"{key}.json"
                claim = dict(**identity, call=key, arm="fitted-c")
                immutable(folder / "launches" / path.name, claim)
                try:
                    fit = original.fit_group_calibration(
                        model,
                        np.array(vector, float, copy=True),
                        np.array(nuisance, float, copy=True),
                        **options,
                    )
                except (ValueError, TimeoutError) as error:
                    fit = dict(converged=False, error_type=type(error).__name__, reason=str(error))
                row = dict(
                    **claim,
                    options=options,
                    seed=dict(vector=vector, nuisance=nuisance),
                    local_center=center,
                    parameter_count=model.size,
                    nuisance_count=len(model.initial_nuisance),
                    start=index,
                    fit=fit,
                    stationary=original.transfer.stationary(
                        fit, center, model.size, len(model.initial_nuisance)
                    ),
                )
                immutable(path, row)
                immutable(
                    folder / "terminations" / path.name, dict(**claim, call_receipt=binding(path))
                )
                rows[key] = read(path)
                stage_values[key] = dict(rows[key]["fit"], converged=rows[key]["stationary"])
                if name == "A" and key == "final" and not rows[key]["stationary"]:
                    raise original.FinalStageUnavailable()
                return stage_values[key]

            options = dict(arm="fitted-c", seconds=20, iterations=600, local_radius_km=25)
            path_receipt, diagnostic = None, None
            if name == "A":
                starts = {v: initial["starts"]["A"][v][int(view)] for v in VIEWS}
                high_base = original.objective(
                    case["prepared"]["high"],
                    case["bank"],
                    case["prior"],
                    case["nodes"],
                    common_clock=False,
                ).base
                try:
                    path = original.fit_sequential_path(
                        models["A"]["low"],
                        high_base,
                        models["B"]["all"].base,
                        *(np.asarray(starts[v]["seed"]["vector"]) for v in ("low", "high", "all")),
                        low_nuisance=np.asarray(starts["low"]["seed"]["nuisance"]),
                        high_correction_seed=original.decode_physical_correction(
                            starts["high"]["proposal"]
                        ),
                        local_center=starts["low"]["local_center"],
                        stage_fit=stage_fit,
                        **options,
                    )
                except original.FinalStageUnavailable:
                    path = dict(status="final-nonstationary", **stage_values)
                path_receipt = {
                    k: v for k, v in path.items() if k not in ("frozen", "shift", "final_model")
                }
                if "shift" in path:
                    path_receipt.update(
                        fixed_shift_receivers=list(map(int, path["shift"].receivers)),
                        fixed_shift_hz=path["shift"].offsets_hz,
                    )
                winner = select_unit(unit, rows)
                if winner is not None:
                    diagnostic = original.diagnose("A", path["final_model"], winner["fit"])
            else:
                model = models[name][view]
                for key in names:
                    start = initial["starts"][name][view][int(key)]
                    stage_fit(
                        key,
                        model,
                        np.asarray(start["seed"]["vector"]),
                        np.asarray(start["seed"]["nuisance"]),
                        dict(options, local_center=start["local_center"]),
                    )
                winner = select_unit(unit, rows)
                if winner is not None:
                    if name == "B":
                        original.freeze_group_calibration(model, winner["fit"])
                    diagnostic = original.diagnose(name, model, winner["fit"])
            read_control(directory)
            value = dict(
                **identity,
                label=frozen["label"],
                state="complete",
                calls=rows,
                optimizer_calls=len(rows),
                reused_optimizer_calls=0,
                path=path_receipt,
                diagnostics=diagnostic,
                selection=winner,
                reference_usage="none",
                held_usage="none",
            )
            immutable(folder / "terminal.json", value)
            status = dict(
                **identity,
                state="complete",
                terminal=binding(folder / "terminal.json"),
                elapsed_seconds=time.monotonic() - begun,
            )
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(folder / "termination.json", status)
    return validate_unit(directory, unit, frozen)


def reuse(directory, unit):
    """Reuse an already sealed original outcome without scientific calculations."""
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    parent = Path(frozen["model_directory"])
    outcome, _ = authority.receipt_review.validate_unit(parent, unit, frozen["scientific"])
    if outcome["state"] != "complete":
        raise ValueError("Genuinely sealed original unit required")
    folder = parent / "units" / unit
    value = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        unit=unit,
        state="reused-sealed-original",
        calls=outcome["calls"],
        selection=outcome["selection"],
        optimizer_calls=0,
        reused_optimizer_calls=outcome["optimizer_calls"],
        original_receipts={str(p.relative_to(folder)): binding(p) for p in folder.rglob("*.json")},
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "units" / unit / "terminal.json", value)
    return validate_unit(directory, unit, frozen)


def reuse_runtime(directory, unit):
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    if frozen["runtime_predecessor"] is None:
        raise ValueError("Explicit frozen runtime predecessor required")
    predecessor = Path(frozen["runtime_predecessor"])
    outcome = previous_runtime.validate_unit(
        predecessor, unit, previous_runtime.read_control(predecessor)
    )
    folder = predecessor / "units" / unit
    receipts = {
        "runtime_protocol": frozen["predecessor_protocol"],
        "runtime_terminal": binding(folder / "terminal.json"),
        **outcome.get("original_receipts", {}),
    }
    for key in outcome["calls"]:
        path = folder / "calls" / f"{key}.json"
        if path.exists():
            receipts[f"calls/{key}.json"] = binding(path)
    value = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        unit=unit,
        state="reused-sealed-runtime",
        calls=outcome["calls"],
        selection=outcome["selection"],
        optimizer_calls=0,
        reused_optimizer_calls=len(outcome["calls"]),
        original_receipts=receipts,
        runtime_unit_inventory=manifest.pin_qualified_files([folder], source_files=[]),
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "units" / unit / "terminal.json", value)
    return validate_unit(directory, unit, frozen)


def seal(directory):
    directory = Path(directory).resolve()
    frozen = read_control(directory)
    outcomes = {u: validate_unit(directory, u, frozen) for u in UNITS}
    selections = {
        "A-all": original.select(
            [
                o["selection"]
                for u, o in outcomes.items()
                if u.startswith("A-") and o["selection"] is not None
            ]
        ),
        **{u: o["selection"] for u, o in outcomes.items() if not u.startswith("A-")},
    }
    new = sum(o["optimizer_calls"] for o in outcomes.values())
    reused = sum(o["reused_optimizer_calls"] for o in outcomes.values())
    if new + reused > 54:
        raise ValueError("Original 54-call budget exceeded")
    value = dict(
        protocol=binding(directory / "protocol.json"),
        label=frozen["label"],
        units={u: binding(directory / "units" / u / "terminal.json") for u in UNITS},
        selections=selections,
        new_optimizer_calls=new,
        reused_optimizer_calls=reused,
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "terminal.json", value)
    return value


def evaluate(directory):
    directory = Path(directory).resolve()
    terminal, frozen = seal(directory), read_control(directory)
    source = original.read_bound(frozen["case_source_protocol"])
    if source["member"]["role"] != "development":
        raise ValueError("Development-only reference join")
    from ds21_evaluate import coordinates, distance_km, reference

    from leo.contracts.regional_position import RegionalPrior

    expected, rows = reference(), []
    prior = RegionalPrior(**frozen["scientific"]["inputs"]["prior"])
    for key, winner in terminal["selections"].items():
        row = dict(model_view=key, arm="fitted-c", state="unavailable")
        if winner is not None:
            location = coordinates(prior, winner["fit"]["vector"][:2])
            error = distance_km(location, expected)
            row.update(
                state="estimated",
                start=winner["start"],
                coordinates_deg=list(location),
                error_km=error,
                below_0_5km=error < 0.5,
            )
        rows.append(row)
    value = dict(
        label=frozen["label"],
        terminal=binding(directory / "terminal.json"),
        rows=rows,
        reference_usage="After all twelve unit outcomes sealed",
        half_scope=original.POLICY["half_view_limitation"],
    )
    immutable(directory / "development-errors.json", value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "freeze",
            "initialize",
            "qualify",
            "recover",
            "reuse",
            "reuse-runtime",
            "run",
            "seal",
            "evaluate",
        ),
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--runtime-predecessor", type=Path)
    parser.add_argument("--unit", choices=UNITS)
    parser.add_argument("--process-receipt", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.model_directory is None:
            parser.error("--model-directory required")
        result = freeze(
            args.directory,
            model_directory=args.model_directory,
            runtime_predecessor=args.runtime_predecessor,
        )
    elif args.command in {"recover", "reuse", "reuse-runtime", "run"}:
        if args.unit is None:
            parser.error("--unit required")
        if args.command == "recover" and args.process_receipt is None:
            parser.error("--process-receipt required")
        result = (
            reuse_runtime(args.directory, args.unit)
            if args.command == "reuse-runtime"
            else reuse(args.directory, args.unit)
            if args.command == "reuse"
            else (
                recover(args.directory, args.unit, process_receipt=args.process_receipt)
                if args.command == "recover"
                else run(args.directory, args.unit)
            )
        )
    elif args.command in {"seal", "evaluate"}:
        result = seal(args.directory) if args.command == "seal" else evaluate(args.directory)
    else:
        result = (
            initialize(args.directory) if args.command == "initialize" else qualify(args.directory)
        )
    print(json.dumps(transport.native_json(result), allow_nan=False))


if __name__ == "__main__":
    main()
