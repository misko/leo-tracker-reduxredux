"""Original fitted-c A/B/C models on generic sealed DS21 physical proposals.

A has dependent low/locked-high/final-all stages, not independent half views.
B/C fit each training view independently. Original per-view physical proposals
are inherited initialization; C additionally shares six all-view receiver lifts.
Only explicit bounded slices are exposed. There is no campaign or held loader.
"""

import argparse
import ast
import json
import time
from pathlib import Path

import ds21_039_likelihood_tempering as native_diagnostic
import ds21_fitted_initialization as pool
import ds21_fitted_transfer as transfer
import ds21_joint as joint
import ds21_joint_proposals as native_proposals
import numpy as np
from ds21_common import immutable, json_value

from leo.analysis.channel_group_calibration import GroupCalibrationObjective, fit_group_calibration
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.research.doppler_shape_shared_proposals import (
    PROPOSAL_IDS,
    decode_physical_correction,
    evaluate_physical_correction,
    project_shared_seed,
)
from leo.analysis.sequential_group_calibration import fit_sequential_path
from leo.application.channel_group_discovery import DiscoverySliceExpired
from leo.application.channel_group_refinement import objective

VIEWS = ("all", "low", "high")
UNITS = tuple([f"A-{i}" for i in range(6)] + [f"{m}-{v}" for m in ("B", "C") for v in VIEWS])
POLICY = dict(
    schema="ds21-generic-fitted-model-composition-v1",
    arm="fitted-c",
    models=["A", "B", "C"],
    units=list(UNITS),
    starts=6,
    fit_seconds=20,
    iterations=600,
    local_radius_km=25,
    maximum_optimizer_calls=54,
    initialization_seconds=90,
    initialization_term_seconds=105,
    initialization_kill_seconds=110,
    path_seconds=90,
    path_term_seconds=105,
    path_kill_seconds=110,
    view_seconds=165,
    view_term_seconds=175,
    view_kill_seconds=180,
    failed_retry=False,
    likelihood_alpha=1,
    reference_usage="none",
    held_usage="none",
    selection="Minimum stationary own training objective, then original start index",
    initialization="Original six physical functions per view; original proposal geography",
    half_view_limitation=(
        "B/C half-view likelihoods use designated observations but inherit shared discovery "
        "bank, geography and physical initialization; "
        "not independent end-to-end half-band pipelines"
    ),
    A_scope="Six low -> locked-high -> final-all paths; final-all selection only",
    C_limitation="Half views inherit six receiver lifts derived once from all training",
)
binding, read, read_bound = pool.binding, pool.read, pool.read_bound
discovery = pool.discovery


class FinalStageUnavailable(Exception):
    """Avoid exporting a failed final stage as a frozen correction function."""


def sources():
    """Static reachable Python closure plus actual native binary and C++ source."""
    from leo.analysis import _regional_orbits

    root = Path(__file__).resolve().parents[1]
    pending, seen = [Path(__file__).resolve(), discovery.ADAPTER.resolve()], set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        modules = []
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    base = root / ("src" if path.is_relative_to(root / "src") else "tools")
                    package = list(path.relative_to(base).parts[:-1])
                    module = ".".join(
                        package[: len(package) - node.level + 1] + ([module] if module else [])
                    )
                modules.extend([module, *(f"{module}.{a.name}" for a in node.names)])
        for module in modules:
            parts = module.split(".")
            base = root / ("src" if parts[0] == "leo" else "tools")
            target = base.joinpath(*parts).with_suffix(".py")
            if target.exists():
                pending.append(target.resolve())
            for n in range(1, len(parts) + 1):
                package = base.joinpath(*parts[:n]) / "__init__.py"
                if package.exists():
                    pending.append(package.resolve())
    seen.update(
        (Path(_regional_orbits.__file__).resolve(), root / "src/leo/analysis/_regional_orbits.cpp")
    )
    return {str(p): binding(p)["sha256"] for p in sorted(seen)}


def freeze(directory, *, parent_directory):
    directory, parent_directory = Path(directory).resolve(), Path(parent_directory).resolve()
    parent = pool.read_stage(parent_directory, "six-proposals")
    frozen = parent["frozen"]
    value = dict(
        policy=POLICY,
        label=frozen["policy"]["label"],
        parent_directory=str(parent_directory),
        parent_authority=parent["authority"],
        case_protocol=binding(Path(parent["case_directory"]) / "protocol.json"),
        inputs={
            k: frozen[k]
            for k in (
                "prepared",
                "partition",
                "prior",
                "training_frames",
                "candidate_numbers",
                "candidate_full_indices",
                "proposals",
            )
        },
        source_sha256=sources(),
        reference_usage="none",
        held_usage="none",
    )
    value["snapshot_paths"] = discovery.archive_sources(directory, value["source_sha256"])
    immutable(directory / "protocol.json", value)
    return read(directory / "protocol.json")


def read_control(directory):
    directory = Path(directory).resolve()
    frozen = read(directory / "protocol.json")
    if (
        frozen["policy"] != POLICY
        or frozen["reference_usage"] != "none"
        or frozen["held_usage"] != "none"
    ):
        raise ValueError("Fitted model policy changed")
    pool.shape_parent.validate_archives(directory, frozen)
    if sources() != frozen["source_sha256"]:
        raise ValueError("Fitted model reachable source closure changed")
    parent = pool.read_stage(frozen["parent_directory"], "six-proposals")
    if (
        parent["authority"] != frozen["parent_authority"]
        or binding(Path(parent["case_directory"]) / "protocol.json") != frozen["case_protocol"]
        or parent["frozen"]["policy"]["label"] != frozen["label"]
        or any(parent["frozen"][k] != v for k, v in frozen["inputs"].items())
    ):
        raise ValueError("Fitted model label/physical parent authority changed")
    return frozen, parent


def training_case(parent):
    original = parent["original"]
    case = discovery.prepare_training_case(
        original["member"], original["membership"], original["census"]
    )
    discovery.validate_preparation(case, original["frozen"])
    case["bank"] = original["full_bank"].select(parent["indices"])
    if case["bank"].numbers.tolist() != parent["frozen"]["candidate_numbers"]:
        raise ValueError("Fitted model original candidate bank changed")
    return case


def models_for(case):
    models = {
        "B": {
            v: objective(case["prepared"][v], case["bank"], case["prior"], case["nodes"])
            for v in VIEWS
        }
    }
    models["A"] = dict(
        low=models["B"]["low"],
        high=models["B"]["high"],
        all=GroupCalibrationObjective(
            models["B"]["all"].base,
            case["prepared"]["all"].observations.channel >= 5,
            enabled=False,
        ),
    )
    models["C"] = {}
    for view in VIEWS:
        model, meta = joint.objective(
            case, case["split"].training, case["prepared"][view].observations
        )
        if meta["temporal_edges"] or meta["measured_waveform_candidates"]:
            raise ValueError("Original neutral singleton native model required")
        models["C"][view] = model
    return models


def metadata(model, prepared):
    return dict(
        parameter_count=model.size,
        nuisance_count=len(model.initial_nuisance),
        prepared_sha256=prepared.evidence_sha256,
        windows=len(model.observations.window_ids),
        observation_receivers=sorted(map(int, set(model.observations.receiver))),
    )


def initialization(directory, frozen):
    directory = Path(directory)
    path = directory / "initialization.json"
    value = read(path)
    identity = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        optimizer_calls=0,
    )
    if (
        read(directory / "initialization-launch.json") != identity
        or read(directory / "initialization-termination.json")
        != dict(**identity, initialization=binding(path))
        or any(value.get(k) != v for k, v in identity.items())
        or value["lift_derivations"] != 6
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
        or len(value["receiver_lifts"]) != 6
        or set(value["starts"]) != {"A", "B", "C"}
        or set(value["models"]) != {"A", "B", "C"}
    ):
        raise ValueError("Fitted initialization authority changed")
    for name in ("A", "B", "C"):
        if set(value["starts"][name]) != set(VIEWS) or set(value["models"][name]) != set(VIEWS):
            raise ValueError("Fitted initialization view inventory changed")
        for view in VIEWS:
            entries = read_bound(frozen["parent_authority"][f"seeds/{view}.json"])
            rows, meta = value["starts"][name][view], value["models"][name][view]
            if len(rows) != 6 or meta["prepared_sha256"] != frozen["inputs"]["prepared"][view]:
                raise ValueError("Fitted initialization training source changed")
            for i, row in enumerate(rows):
                v, n = np.asarray(row["seed"]["vector"]), np.asarray(row["seed"]["nuisance"])
                if (
                    row["start"] != i
                    or row["proposal_id"] != PROPOSAL_IDS[i]
                    or row["proposal"] != entries[i]
                    or row["local_center"] != frozen["inputs"]["proposals"][i]["point_km"]
                    or v[:2].tolist() != row["local_center"]
                    or v.shape != (meta["parameter_count"],)
                    or n.shape != (meta["nuisance_count"],)
                    or not np.isfinite(v).all()
                    or not np.isfinite(n).all()
                    or (name == "C" and row["receiver_lifts"] != value["receiver_lifts"][i])
                ):
                    raise ValueError("Fitted initialization state/center/lift pairing changed")
    return value


def initialize(directory, *, maximum_seconds=90):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 90:
        raise ValueError("Initialization bound must be <=90 seconds")
    directory = Path(directory).resolve()
    begun = time.monotonic()
    frozen, parent = read_control(directory)
    if (directory / "initialization.json").exists():
        return initialization(directory, frozen)
    if any(
        (directory / n).exists()
        for n in ("initialization-launch.json", "initialization-termination.json")
    ):
        raise ValueError("Orphan/failed initialization; no retry")
    identity = dict(
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        label=frozen["label"],
        optimizer_calls=0,
    )
    immutable(directory / "initialization-launch.json", identity)
    status = dict(**identity, state="failed")
    try:
        with discovery.slice_bound(max(0.001, maximum_seconds - (time.monotonic() - begun))):
            case = training_case(parent)
            models = models_for(case)
            entries = {v: read_bound(parent["authority"][f"seeds/{v}.json"]) for v in VIEWS}
            lifts = [
                joint.physical_receiver_branches(
                    models["C"]["all"],
                    native_proposals.physical_seed(
                        models["C"]["all"], e, evaluate_physical_correction
                    ),
                )
                for e in entries["all"]
            ]
            starts, meta = {}, {}
            for name in ("A", "B", "C"):
                starts[name], meta[name] = {}, {}
                for view in VIEWS:
                    model = models[name][view]
                    meta[name][view] = metadata(model, case["prepared"][view])
                    starts[name][view] = []
                    for i, e in enumerate(entries[view]):
                        seed = (
                            native_proposals.proposal_start(model, e, lifts[i], view=view, index=i)
                            if name == "C"
                            else project_shared_seed(e, model)
                        )
                        row = dict(
                            start=i,
                            proposal_id=PROPOSAL_IDS[i],
                            proposal=e,
                            seed=seed,
                            local_center=e["point_km"],
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
                ),
            )
            status = dict(**identity, initialization=binding(directory / "initialization.json"))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(directory / "initialization-termination.json", status)
    return initialization(directory, frozen)


def unit_spec(unit):
    if unit not in UNITS:
        raise ValueError("Explicit original model/path or model/view unit required")
    name, view = unit.split("-")
    return name, view, ("low", "high", "final") if name == "A" else tuple(map(str, range(6)))


def calls(directory, unit, sha):
    _, _, names = unit_spec(unit)
    folder = Path(directory) / "units" / unit
    rows = {}
    for kind in ("calls", "launches", "terminations"):
        if not {p.stem for p in (folder / kind).glob("*.json")} <= set(names):
            raise ValueError("Extra model call/arm inventory")
    for key in names:
        path, launch, done = (
            folder / k / f"{key}.json" for k in ("calls", "launches", "terminations")
        )
        identity = dict(protocol_sha256=sha, unit=unit, call=key, arm="fitted-c")
        if path.exists():
            row = read(path)
            if (
                not launch.exists()
                or not done.exists()
                or read(launch) != identity
                or read(done) != dict(**identity, call_receipt=binding(path))
                or any(row.get(k) != v for k, v in identity.items())
                or row["stationary"]
                != transfer.stationary(
                    row["fit"], row["local_center"], row["parameter_count"], row["nuisance_count"]
                )
            ):
                raise ValueError("Fitted call authority/domain changed")
            rows[key] = row
        elif launch.exists() or done.exists():
            raise ValueError("Orphan fitted call; no retry")
    return rows


def slices(folder, sha, unit):
    launches = list((folder / "slices").glob("*-launch.json"))
    expected = {p.with_name(p.name.replace("-launch", "-termination")) for p in launches}
    if set((folder / "slices").glob("*-termination.json")) != expected:
        raise ValueError("Orphan/failed fitted slice; no retry")
    complete = False
    for path in launches:
        claim, status = (
            read(path),
            read(path.with_name(path.name.replace("-launch", "-termination"))),
        )
        identity = dict(protocol_sha256=sha, unit=unit, slice_id=claim["slice_id"])
        if (
            claim != identity
            or type(claim["slice_id"]) is not int
            or claim["slice_id"] < 0
            or path.name != f"{claim['slice_id']:03d}-launch.json"
            or any(status.get(k) != v for k, v in identity.items())
            or status["state"] not in ("complete", "checkpointed")
        ):
            raise ValueError("Orphan/failed fitted slice; no retry")
        complete |= status["state"] == "complete"
    return complete


def select(rows):
    eligible = [r for r in rows if r["stationary"]]
    return min(eligible, key=lambda r: (r["fit"]["objective"], r["start"])) if eligible else None


def diagnose(name, model, fit):
    if name == "C":
        wrapped, _ = native_diagnostic.build_tempered_model(dict(model=model), 1.0)
        result = native_diagnostic.diagnose_tempered_state(
            wrapped, np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
        )
        nll = result["untempered_likelihood_nll"]
    else:
        value, _, _, terms = model.evaluate_joint(
            np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
        )
        nll = terms.nll
        result = dict(objective=value, likelihood_nll=nll)
    if (
        not np.isfinite([result["objective"], nll]).all()
        or abs(result["objective"] - fit["objective"]) > 1e-7
        or abs(nll - fit["likelihood_nll"]) > 1e-7
    ):
        raise ValueError("Selected original objective/NLL replay differs")
    return json_value(result)


def run_slice(directory, unit, *, slice_id, maximum_seconds=None):
    name, view, names = unit_spec(unit)
    cap = 90 if name == "A" else 165
    maximum_seconds = cap if maximum_seconds is None else maximum_seconds
    if (
        type(slice_id) is not int
        or slice_id < 0
        or not np.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= cap
    ):
        raise ValueError("Explicit slice id and original bounded slice required")
    directory = Path(directory).resolve()
    begun = time.monotonic()
    frozen, parent = read_control(directory)
    sha = binding(directory / "protocol.json")["sha256"]
    folder = directory / "units" / unit
    if (folder / "finalized-failure.json").exists():
        return sealed_unit(directory, unit, frozen)
    initial = initialization(directory, frozen)
    rows = calls(directory, unit, sha)
    slices(folder, sha, unit)
    if (folder / "terminal.json").exists():
        return sealed_unit(directory, unit, frozen)
    launch = folder / "slices" / f"{slice_id:03d}-launch.json"
    launch.parent.mkdir(parents=True, exist_ok=True)
    identity = dict(protocol_sha256=sha, unit=unit, slice_id=slice_id)
    with launch.open("x") as stream:
        json.dump(identity, stream)
    status = dict(**identity, state="failed")
    try:
        with discovery.slice_bound(max(0.001, maximum_seconds - (time.monotonic() - begun))):
            case = training_case(parent)
            models = models_for(case)
            if {
                m: {v: metadata(models[m][v], case["prepared"][v]) for v in VIEWS} for m in models
            } != initial["models"]:
                raise ValueError("Fitted training model layout changed")

            stage_values = {}

            def stage_fit(key, model, vector, nuisance, options):
                index = int(view) if name == "A" else int(key)
                center = frozen["inputs"]["proposals"][index]["point_km"]
                call_identity = dict(protocol_sha256=sha, unit=unit, call=key, arm="fitted-c")
                expected = dict(
                    options=options,
                    seed=dict(vector=json_value(vector), nuisance=json_value(nuisance)),
                    local_center=center,
                    parameter_count=model.size,
                    nuisance_count=len(model.initial_nuisance),
                    start=index,
                )
                if key not in rows:
                    if time.monotonic() - begun + 20 >= maximum_seconds:
                        raise DiscoverySliceExpired(key)
                    path = folder / "calls" / f"{key}.json"
                    immutable(folder / "launches" / path.name, call_identity)
                    try:
                        fit = fit_group_calibration(
                            model,
                            np.array(vector, float, copy=True),
                            np.array(nuisance, float, copy=True),
                            **options,
                        )
                    except (ValueError, TimeoutError) as error:
                        fit = dict(
                            converged=False, error_type=type(error).__name__, reason=str(error)
                        )
                    row = dict(
                        **call_identity,
                        **expected,
                        fit=fit,
                        stationary=transfer.stationary(
                            fit, center, model.size, len(model.initial_nuisance)
                        ),
                    )
                    immutable(path, row)
                    immutable(
                        folder / "terminations" / path.name,
                        dict(**call_identity, call_receipt=binding(path)),
                    )
                    rows[key] = read(path)
                    print(
                        json.dumps(
                            dict(
                                label=frozen["label"],
                                unit=unit,
                                call=key,
                                stationary=row["stationary"],
                            )
                        ),
                        flush=True,
                    )
                row = rows[key]
                if any(row[k] != json_value(v) for k, v in expected.items()):
                    raise ValueError("Cached physical seed/options/center changed")
                # Core A gates downstream stages on convergence; require its
                # actual numerical/domain stationarity before donating a fit.
                stage_values[key] = dict(row["fit"], converged=row["stationary"])
                if name == "A" and key == "final" and not row["stationary"]:
                    raise FinalStageUnavailable()
                return stage_values[key]

            options = dict(arm="fitted-c", seconds=20, iterations=600, local_radius_km=25)
            path_receipt, diagnostic = None, None
            if name == "A":
                i = int(view)
                starts = {v: initial["starts"]["A"][v][i] for v in VIEWS}
                high_base = objective(
                    case["prepared"]["high"],
                    case["bank"],
                    case["prior"],
                    case["nodes"],
                    common_clock=False,
                ).base
                try:
                    path = fit_sequential_path(
                        models["A"]["low"],
                        high_base,
                        models["B"]["all"].base,
                        *(np.asarray(starts[v]["seed"]["vector"]) for v in ("low", "high", "all")),
                        low_nuisance=np.asarray(starts["low"]["seed"]["nuisance"]),
                        high_correction_seed=decode_physical_correction(starts["high"]["proposal"]),
                        local_center=starts["low"]["local_center"],
                        stage_fit=stage_fit,
                        **options,
                    )
                except FinalStageUnavailable:
                    path = dict(status="final-nonstationary", **stage_values)
                path_receipt = json_value(
                    {k: v for k, v in path.items() if k not in ("frozen", "shift", "final_model")}
                )
                if "shift" in path:
                    path_receipt.update(
                        fixed_shift_receivers=list(path["shift"].receivers),
                        fixed_shift_hz=path["shift"].offsets_hz.tolist(),
                    )
                winner = rows.get("final") if path["status"] == "complete" else None
                if winner is not None:
                    diagnostic = diagnose("A", path["final_model"], winner["fit"])
            else:
                model = models[name][view]
                for key in names:
                    start = initial["starts"][name][view][int(key)]
                    stage_fit(
                        key,
                        model,
                        np.asarray(start["seed"]["vector"]),
                        np.asarray(start["seed"]["nuisance"]),
                        dict(**options, local_center=start["local_center"]),
                    )
                winner = select(list(rows.values()))
                if winner is not None:
                    if name == "B":
                        freeze_group_calibration(model, winner["fit"])
                    diagnostic = diagnose(name, model, winner["fit"])
            read_control(directory)
            immutable(
                folder / "terminal.json",
                dict(
                    protocol_sha256=sha,
                    label=frozen["label"],
                    unit=unit,
                    state="complete",
                    initialization=binding(directory / "initialization.json"),
                    calls=rows,
                    optimizer_calls=len(rows),
                    skipped_calls=[k for k in names if k not in rows],
                    path=path_receipt,
                    selection=winner,
                    diagnostics=diagnostic,
                    reference_usage="none",
                    held_usage="none",
                ),
            )
            status["state"] = "complete"
    except DiscoverySliceExpired as error:
        status.update(state="checkpointed", next_call=str(error))
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error))
        raise
    finally:
        immutable(launch.with_name(launch.name.replace("-launch", "-termination")), status)
    if status["state"] == "checkpointed":
        return dict(**status, optimizer_calls=len(rows))
    return sealed_unit(directory, unit, frozen)


def failure_inventory(directory, unit):
    directory = Path(directory)
    folder = directory / "units" / unit
    paths = [
        directory / "protocol.json",
        *(p for p in directory.glob("initialization*.json")),
        *(p for p in folder.rglob("*.json") if p.name != "finalized-failure.json"),
    ]
    return {str(p.relative_to(directory)): binding(p) for p in sorted(paths)}


def finalize_failure(directory, unit, *, reason, process_terminal_confirmed=False):
    """Explicit terminal-process attestation; never turn validation errors into misses."""
    unit_spec(unit)
    directory = Path(directory).resolve()
    frozen, _ = read_control(directory)
    folder = directory / "units" / unit
    if process_terminal_confirmed is not True or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Verified terminal process and explicit failure reason required")
    if (folder / "terminal.json").exists():
        raise ValueError("Success/failure outcome coexistence refused")
    value = dict(
        state="finalized-failure",
        label=frozen["label"],
        unit=unit,
        reason=reason,
        process_terminal_confirmed=True,
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        inventory=failure_inventory(directory, unit),
        reference_usage="none",
        held_usage="none",
    )
    immutable(folder / "finalized-failure.json", value)
    return sealed_unit(directory, unit, frozen)


def sealed_unit(directory, unit, frozen):
    name, view, names = unit_spec(unit)
    directory = Path(directory)
    folder = directory / "units" / unit
    sha = binding(directory / "protocol.json")["sha256"]
    if (folder / "finalized-failure.json").exists():
        value = read(folder / "finalized-failure.json")
        if (
            (folder / "terminal.json").exists()
            or value["state"] != "finalized-failure"
            or value["label"] != frozen["label"]
            or value["unit"] != unit
            or value["protocol_sha256"] != sha
            or value["process_terminal_confirmed"] is not True
            or not value["reason"].strip()
            or value["inventory"] != failure_inventory(directory, unit)
            or value["reference_usage"] != "none"
            or value["held_usage"] != "none"
        ):
            raise ValueError("Finalized failure inventory/coexistence changed")
        return value
    initial = initialization(directory, frozen)
    rows = calls(directory, unit, sha)
    value = read(folder / "terminal.json")
    for key, row in rows.items():
        index = int(view) if name == "A" else int(key)
        target_view = "all" if key == "final" else key if name == "A" else view
        meta = initial["models"][name][target_view]
        center = frozen["inputs"]["proposals"][index]["point_km"]
        options = dict(arm="fitted-c", seconds=20, iterations=600)
        if name == "A" and key == "high":
            options["fixed_position"] = True
            nuisance_count = len(meta["observation_receivers"])
            seed_vector = np.array(initial["starts"][name]["high"][index]["seed"]["vector"])
            seed_vector[:2], seed_vector[2:7] = rows["low"]["fit"]["vector"][:2], 0
            expected_seed = dict(vector=seed_vector.tolist(), nuisance=row["seed"]["nuisance"])
        elif name == "A" and key == "final":
            options.update(local_center=center, local_radius_km=25)
            nuisance_count = meta["nuisance_count"]
            expected_seed = row["seed"]
            if (
                row["seed"]["vector"][:2] != rows["low"]["fit"]["vector"][:2]
                or row["seed"]["vector"][7:] != rows["high"]["fit"]["vector"][7:]
            ):
                raise ValueError("Sequential final carried geometry/timing changed")
            if "calibration_projection" in value["path"]:
                coefficients = value["path"]["calibration_projection"]["coefficients"]
                if (
                    row["seed"]["vector"][2:7] != coefficients[:5]
                    or row["seed"]["nuisance"] != coefficients[5:]
                ):
                    raise ValueError("Sequential final physical projection changed")
        else:
            options.update(local_center=center, local_radius_km=25)
            nuisance_count = meta["nuisance_count"]
            seed = initial["starts"][name][target_view][index]["seed"]
            expected_seed = {k: seed[k] for k in ("vector", "nuisance")}
        if (
            row["start"] != index
            or row["local_center"] != center
            or row["options"] != options
            or row["parameter_count"] != meta["parameter_count"]
            or row["nuisance_count"] != nuisance_count
            or row["seed"] != expected_seed
            or np.asarray(row["seed"]["nuisance"]).shape != (nuisance_count,)
            or not np.isfinite(row["seed"]["nuisance"]).all()
        ):
            raise ValueError("Cached fitted call original options/seed/domain changed")
    expected_winner = (
        select(list(rows.values()))
        if name != "A"
        else rows.get("final")
        if value["path"]["status"] == "complete"
        else None
    )
    if name == "A":
        status = (
            "low-nonstationary"
            if not rows.get("low", {}).get("stationary")
            else "high-nonstationary"
            if not rows.get("high", {}).get("stationary")
            else "final-nonstationary"
            if not rows.get("final", {}).get("stationary")
            else "complete"
        )
        if value["path"]["status"] != status:
            raise ValueError("Sequential prerequisite/skip status changed")
        expected_calls = (
            {"low"}
            if value["path"]["status"] == "low-nonstationary"
            else {"low", "high"}
            if value["path"]["status"] == "high-nonstationary"
            else set(names)
        )
        for key in rows:
            # High core adds descriptive diagnostics after fitting.
            if value["path"][key] != dict(rows[key]["fit"], converged=rows[key]["stationary"]) and (
                key != "high"
                or any(
                    value["path"][key].get(k) != v
                    for k, v in dict(rows[key]["fit"], converged=rows[key]["stationary"]).items()
                )
            ):
                raise ValueError("Sequential path/call diagnostic changed")
    else:
        expected_calls = set(names)
    if (
        value["protocol_sha256"] != sha
        or value["label"] != frozen["label"]
        or value["unit"] != unit
        or value["state"] != "complete"
        or value["calls"] != rows
        or set(rows) != expected_calls
        or value["optimizer_calls"] != len(rows)
        or value["skipped_calls"] != [k for k in names if k not in rows]
        or value["selection"] != expected_winner
        or (expected_winner is not None and not expected_winner["stationary"])
        or value["initialization"] != binding(directory / "initialization.json")
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
        or not slices(folder, sha, unit)
    ):
        raise ValueError("Fitted unit coverage/selection seal changed")
    # Initialization is authority-checked even when no stationary state exists.
    assert initial["optimizer_calls"] == 0
    diagnostic = value["diagnostics"]
    if expected_winner is None:
        if diagnostic is not None:
            raise ValueError("Unavailable fitted selection has diagnostics")
    else:
        nll = (
            diagnostic["untempered_likelihood_nll"] if name == "C" else diagnostic["likelihood_nll"]
        )
        if (
            not np.isfinite([diagnostic["objective"], nll]).all()
            or abs(diagnostic["objective"] - expected_winner["fit"]["objective"]) > 1e-7
            or abs(nll - expected_winner["fit"]["likelihood_nll"]) > 1e-7
            or (name == "C" and diagnostic["alpha"] != 1)
        ):
            raise ValueError("Selected fitted scalar diagnostic seal changed")
    return value


def seal(directory):
    directory = Path(directory).resolve()
    frozen, _ = read_control(directory)
    outcomes = {u: sealed_unit(directory, u, frozen) for u in UNITS}
    a_rows = [
        outcomes[u]["selection"]
        for u in UNITS[:6]
        if outcomes[u]["state"] == "complete" and outcomes[u]["selection"] is not None
    ]
    selected = {"A-all": select(a_rows)}
    selected.update({u: o.get("selection") for u, o in outcomes.items() if not u.startswith("A-")})
    value = dict(
        label=frozen["label"],
        protocol_sha256=binding(directory / "protocol.json")["sha256"],
        outcomes=outcomes,
        selections=selected,
        optimizer_calls=sum(
            o.get("optimizer_calls", sum(1 for p in o.get("inventory", {}) if "/launches/" in p))
            for o in outcomes.values()
        ),
        maximum_optimizer_calls=54,
        terminals={
            u: binding(
                directory
                / "units"
                / u
                / ("terminal.json" if o["state"] == "complete" else "finalized-failure.json")
            )
            for u, o in outcomes.items()
        },
        reference_usage="none",
        held_usage="none",
    )
    immutable(directory / "terminal.json", value)
    return read(directory / "terminal.json")


def evaluate(directory):
    directory = Path(directory).resolve()
    terminal = seal(directory)
    frozen = read(directory / "protocol.json")
    from ds21_evaluate import coordinates, distance_km, reference

    from leo.contracts.regional_position import RegionalPrior

    expected = reference()
    prior, rows = RegionalPrior(**frozen["inputs"]["prior"]), []
    for key, winner in terminal["selections"].items():
        name, view = key.split("-")
        row = dict(model=name, view=view, state="unavailable", below_0_5km=False)
        if winner is not None:
            location = coordinates(prior, winner["fit"]["vector"][:2])
            error = distance_km(location, expected)
            row.update(
                state="estimated",
                start=winner["start"],
                proposal_id=PROPOSAL_IDS[winner["start"]],
                coordinates_deg=list(location),
                error_km=error,
                below_0_5km=error < 0.5,
                common_c_hz_per_ghz=winner["fit"]["vector"][6],
            )
        rows.append(row)
    value = dict(
        label=frozen["label"],
        arm="fitted-c",
        rows=rows,
        terminal=binding(directory / "terminal.json"),
        evaluator=binding(__file__),
        reference_usage="After all six A paths and all B/C view outcomes sealed",
        limitation=POLICY["A_scope"]
        + "; "
        + POLICY["half_view_limitation"]
        + "; "
        + POLICY["C_limitation"]
        + "; configured reference, not independently surveyed",
    )
    immutable(directory / "development-errors.json", value)
    return read(directory / "development-errors.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("freeze", "initialize", "run-slice", "seal", "evaluate")
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--parent-directory", type=Path)
    parser.add_argument("--unit", choices=UNITS)
    parser.add_argument("--slice-id", type=int)
    parser.add_argument("--maximum-seconds", type=float)
    args = parser.parse_args()
    if args.command == "freeze":
        if args.parent_directory is None:
            parser.error("--parent-directory required")
        result = freeze(args.directory, parent_directory=args.parent_directory)
    elif args.command == "initialize":
        result = initialize(args.directory, maximum_seconds=args.maximum_seconds or 90)
    elif args.command == "run-slice":
        if args.unit is None or args.slice_id is None:
            parser.error("--unit and --slice-id required")
        result = run_slice(
            args.directory, args.unit, slice_id=args.slice_id, maximum_seconds=args.maximum_seconds
        )
    else:
        result = seal(args.directory) if args.command == "seal" else evaluate(args.directory)
    print(
        json.dumps(
            dict(
                label=result.get("label"),
                command=args.command,
                state=result.get("state", "sealed"),
                optimizer_calls=result.get("optimizer_calls", 0),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
