"""Prespecified five-case fitted-c transfer, using original training inputs only.

Historical archives omit dependencies and the orchestration module changed.
Their bytes are retained, not claimed as a complete historical source closure;
actual saved-state objective/NLL and alpha-one derivative/posterior replay gates
are mandatory before any new optimizer invocation.
"""

import argparse
import ast
import json
import time
from pathlib import Path

import ds21_039_likelihood_tempering as tempering
import ds21_common as common
import numpy as np
from ds20_channel_corpus import bounded, digest
from ds21_fitted_discovery import archive_sources
from ds21_joint import objective

from leo.application.channel_group_holdout import partition_channel_probes
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior

LABELS = tuple(f"DS21-{n:03}" for n in (1, 3, 5, 23, 39))
LAYOUTS = dict(
    zip(
        LABELS,
        ((2562, 39, 46), (2422, 37, 44), (1808, 44, 51), (2384, 33, 40), (2798, 43, 50)),
        strict=True,
    )
)
CONDITIONS = {"alpha-one": 1.0, "alpha-quarter": 0.25}
STARTS = tuple(range(6))
NAMES = tuple(f"{condition}-{start}" for condition in CONDITIONS for start in STARTS)
POLICY = dict(
    schema="ds21-five-case-fitted-transfer-v1",
    labels=list(LABELS),
    arm="fitted-c",
    conditions=CONDITIONS,
    starts=list(STARTS),
    optimizer_calls=12,
    maximum_optimizer_seconds=240,
    fit_seconds=20,
    iterations=600,
    local_radius_km=25,
    internal_seconds=285,
    external_term_seconds=295,
    external_kill_seconds=300,
    failed_retry=False,
    split_seed=20261012,
    block_seconds=20,
    reference_usage="none",
    held_usage="none",
    selector="Minimum own stationary training objective, start index, then origin",
    historical_incumbents="Stationary original endpoints eligible only for alpha-one",
    sampling_lifts="Already included in original endpoints; never applied again",
)


def binding(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=digest(path))


def read_bound(row, *, decode=True):
    path = Path(row["path"])
    if digest(path) != row["sha256"]:
        raise ValueError(f"Transfer bound file changed: {path}")
    return json.loads(path.read_bytes()) if decode else path


def stationary(fit, center, size, nuisance_count=2):
    if "vector" not in fit or "nuisance" not in fit:
        return False
    v, n = np.asarray(fit["vector"], float), np.asarray(fit["nuisance"], float)
    return bool(
        v.shape == (size,)
        and n.shape == (nuisance_count,)
        and np.isfinite(v).all()
        and np.isfinite(n).all()
        and np.isfinite(fit.get("objective", np.inf))
        and np.isfinite(fit.get("likelihood_nll", np.inf))
        and fit.get("converged") is True
        and np.isfinite(fit.get("stationarity", np.inf))
        and fit["stationarity"] <= 0.001
        and np.linalg.norm(v[:2] - np.asarray(center)) <= 25 + 1e-8
        and fit.get("physical_constraints_minimum", -np.inf) >= -1e-7
    )


def build_manifest(label, study=common.OUTPUT):
    """Receipt-only inventory. No input decoding, held access, or inference."""
    if label not in LABELS:
        raise ValueError("Prespecified five development cases only")
    study = Path(study).resolve()
    membership_binding = binding(study / "membership.json")
    membership = read_bound(membership_binding)
    member = next(m for m in membership["members"] if m["label"] == label)
    if member["role"] != "development" or not member["eight_channel"]:
        raise ValueError("Eight-channel development authority required")
    read_bound(member["input"], decode=False)
    parent = study / "local/joint-native-shared-sixstart-v2" / label
    discovery = study / "local/discovery-v2" / label
    proposals = study / "local/shared-proposals-v1" / label
    files = {
        "census": binding(study / "local/census" / f"{label}.json"),
        "parent_protocol": binding(parent / "protocol.json"),
        "parent_terminal": binding(parent / "terminal.json"),
        "receiver_lifts": binding(parent / "receiver-branch-starts.json"),
        "discovery_protocol": binding(discovery / "protocol.json"),
        "discovery_terminal": binding(discovery / "terminal.json"),
        "bank_npz": binding(discovery / "bank.npz"),
        "bank_json": binding(discovery / "bank.json"),
        "proposal_protocol": binding(proposals / "protocol.json"),
        "proposal_terminal": binding(proposals / "terminal.json"),
    }
    protocol, proposal, disc, bank, census, lifts = (
        read_bound(files[k])
        for k in (
            "parent_protocol",
            "proposal_protocol",
            "discovery_protocol",
            "bank_json",
            "census",
            "receiver_lifts",
        )
    )
    numbers, indices = proposal["candidate_numbers"], proposal["candidate_full_indices"]
    windows, satellite_count, size = LAYOUTS[label]
    if (
        protocol["label"] != label
        or protocol["starts"] != 6
        or protocol["policy"] != "joint-native-shared-sixstart-v2"
        or protocol["reference_usage"] != "none"
        or protocol["held_selection"] != "none"
        or protocol["proposal_binding"]["protocol_sha256"] != files["proposal_protocol"]["sha256"]
        or protocol["proposal_binding"]["terminal_sha256"] != files["proposal_terminal"]["sha256"]
        or protocol["shared_discovery_sha256"] != files["discovery_protocol"]["sha256"]
        or disc["membership_sha256"] != membership_binding["sha256"]
        or disc["input_sha256"] != member["input"]["sha256"]
        or disc["seed"] != POLICY["split_seed"]
        or disc["prior"] != membership["prior"]
        or census["membership_sha256"] != membership_binding["sha256"]
        or census["label"] != label
        or census["state"] != "prepared"
        or census["split_seed"] != POLICY["split_seed"]
        or census["views"]["all"]["windows"] != windows
        or census["views"]["all"]["evidence_sha256"] != protocol["prepared"]["all"]
        or proposal["prepared_sha256"]["all"] != protocol["prepared"]["all"]
        or disc["prepared"]["all"] != protocol["prepared"]["all"]
        or bank["sha256"] != files["bank_npz"]["sha256"]
        or numbers != protocol["catalogue_numbers"]
        or len(numbers) != satellite_count
        or [bank["build"]["retained_numbers"][i] for i in indices] != numbers
        or len(set(numbers)) != len(numbers)
        or len(set(indices)) != len(indices)
        or len(lifts) != 6
        or len(protocol["proposal_ids"]) != 6
        or len(set(protocol["proposal_ids"])) != 6
    ):
        raise ValueError("Transfer parent/input/census/bank/proposal authority differs")
    starts = {}
    for index in STARTS:
        attempt_binding = binding(parent / "attempts" / f"all-{index}-fitted-c.json")
        seed_binding = binding(parent / "seeds" / f"all-{index}.json")
        attempt, seed = read_bound(attempt_binding), read_bound(seed_binding)
        fit = attempt["fit"]
        vector, nuisance = np.asarray(fit["vector"]), np.asarray(fit["nuisance"])
        center = seed["seed"]["vector"][:2]
        if (
            attempt["protocol_sha256"] != files["parent_protocol"]["sha256"]
            or seed["protocol_sha256"] != files["parent_protocol"]["sha256"]
            or attempt["proposal_id"] != protocol["proposal_ids"][index]
            or seed["proposal_id"] != attempt["proposal_id"]
            or seed["receiver_branch_lifts"] != lifts[index]
            or vector.shape != (size,)
            or nuisance.shape != (2,)
            or not np.isfinite(vector).all()
            or not np.isfinite(nuisance).all()
            or not np.isfinite(fit["objective"])
            or not np.isfinite(fit["likelihood_nll"])
            or center != proposal["proposals"][index]["point_km"]
            or np.linalg.norm(vector[:2] - center) > 25 + 1e-8
        ):
            raise ValueError("Original endpoint/center/seed/lift identity differs")
        starts[str(index)] = dict(
            start=index,
            proposal_id=attempt["proposal_id"],
            source_fit=fit,
            seed=dict(vector=fit["vector"], nuisance=fit["nuisance"]),
            local_center=center,
            original_seed=seed,
            receiver_branch_lifts=lifts[index],
            attempt=attempt_binding,
            seed_receipt=seed_binding,
            incumbent_eligible=stationary(fit, center, size),
        )
    root = Path(__file__).resolve().parents[1]
    archives = {}
    for filename, sha in protocol["sources"].items():
        archive = binding(parent / "source-snapshot" / Path(filename).name)
        if archive["sha256"] != sha:
            raise ValueError("Historical source archive differs")
        old = Path(filename)
        relative = str(old).split("/src/", 1)
        current = root / "src" / relative[1] if len(relative) == 2 else root / "tools" / old.name
        now = binding(current)
        same = now["sha256"] == sha
        if not same and old.name != "ds21_joint_proposals.py":
            raise ValueError("Historical numerical source changed")
        archives[filename] = dict(archive=archive, current=now, same_bytes=same)
    return dict(
        schema="ds21-five-case-transfer-inputs-v1",
        label=label,
        study=str(study),
        membership=membership_binding,
        member=member,
        source_input=member["input"],
        files=files,
        starts=starts,
        candidate_numbers=numbers,
        candidate_full_indices=indices,
        full_catalogue_numbers=bank["build"]["retained_numbers"],
        prepared_sha256=protocol["prepared"]["all"],
        historical_sources=archives,
        layout=dict(windows=windows, satellites=satellite_count, vector=size, nuisance=2),
        historical_limitation=(
            "Archives omit dependencies; orchestration differs; actual replay required"
        ),
        reference_usage="none",
        held_usage="none",
        sampling_lifts_already_applied=True,
    )


def validate_manifest(manifest):
    if manifest != build_manifest(manifest["label"], manifest["study"]):
        raise ValueError("Frozen transfer input handoff changed")


def load_training_case(manifest):
    """Decode and prepare CH1-8 training only; never visit split.held."""
    validate_manifest(manifest)
    membership = read_bound(manifest["membership"])
    source = common.load_source(manifest["member"], membership)
    split = partition_channel_probes(
        source,
        seed=POLICY["split_seed"],
        block_seconds=POLICY["block_seconds"],
    )
    training = split.training
    prepared = prepare_position_windows(training)
    if (
        prepared.evidence_sha256 != manifest["prepared_sha256"]
        or len(prepared.observations.window_ids) != manifest["layout"]["windows"]
        or set(prepared.observations.channel) != set(range(1, 9))
    ):
        raise ValueError("Original all-training preparation differs")
    bank_file = read_bound(manifest["files"]["bank_npz"], decode=False)
    with np.load(bank_file, allow_pickle=False) as arrays:
        full = PositionOrbitBank(
            *(arrays[k] for k in ("numbers", "nodes_s", "position_km", "velocity_km_s"))
        )
    bank = full.select(manifest["candidate_full_indices"])
    if (
        bank.numbers.tolist() != manifest["candidate_numbers"]
        or full.numbers.tolist() != manifest["full_catalogue_numbers"]
    ):
        raise ValueError("Frozen transfer catalogue identity/order differs")
    case = dict(
        source=training,
        prepared=prepared,
        bank=bank,
        full_bank=full,
        prior=RegionalPrior(**membership["prior"]),
    )
    model, metadata = objective(case, training, prepared.observations)
    if (
        model.size != manifest["layout"]["vector"]
        or len(model.initial_nuisance) != 2
        or metadata["temporal_edges"] != 0
        or metadata["measured_waveform_candidates"] != 0
        or metadata["native_candidates"]
        != manifest["starts"]["0"]["original_seed"]["seed"]["projection"]["native_candidates"]
    ):
        raise ValueError("Original native model/frame/layout differs")
    case.update(model=model, metadata=metadata)
    return case


def source_closure():
    """Bind reachable Python imports, the pinned decoder and loaded orbit binary."""
    from leo.analysis import _regional_orbits

    root = Path(__file__).resolve().parents[1]
    pending, seen = [Path(__file__).resolve(), common.ADAPTER.resolve()], set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_bytes())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    relative = path.relative_to(root / "src")
                    package = list(relative.parts[:-1])
                    module = ".".join(
                        package[: len(package) - node.level + 1] + ([module] if module else [])
                    )
                modules.append(module)
                modules.extend(f"{module}.{alias.name}" for alias in node.names)
        for module in modules:
            parts = module.split(".")
            base = root / ("src" if parts[0] == "leo" else "tools")
            target = base.joinpath(*parts).with_suffix(".py")
            if target.exists():
                pending.append(target.resolve())
            for i in range(1, len(parts) + 1):
                package = base.joinpath(*parts[:i]) / "__init__.py"
                if package.exists():
                    pending.append(package.resolve())
    seen.add(Path(_regional_orbits.__file__).resolve())
    seen.add(root / "src/leo/analysis/_regional_orbits.cpp")
    return {str(p): digest(p) for p in sorted(seen)}


def freeze_protocol(manifest, path):
    validate_manifest(manifest)
    path = Path(path)
    sources = source_closure()
    snapshots = archive_sources(path.parent, sources)
    common.immutable(
        path,
        dict(
            policy=POLICY,
            tempering_policy=tempering.POLICY,
            inputs=manifest,
            sources=sources,
            snapshot_paths=snapshots,
        ),
    )
    return json.loads(Path(path).read_bytes())


def read_control(manifest, path):
    frozen = json.loads(Path(path).read_bytes())
    validate_manifest(manifest)
    if (
        frozen["policy"] != POLICY
        or frozen["tempering_policy"] != tempering.POLICY
        or frozen["inputs"] != manifest
        or frozen["sources"] != source_closure()
    ):
        raise ValueError("Transfer frozen policy/input/source closure changed")
    if set(frozen["snapshot_paths"]) != set(frozen["sources"]):
        raise ValueError("Transfer new source archive inventory changed")
    for filename, relative in frozen["snapshot_paths"].items():
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid transfer source archive path")
        if digest(Path(path).parent / relative) != frozen["sources"][filename]:
            raise ValueError("Transfer new source archive changed")
    return frozen


def selection(rows, starts):
    selected = {}
    for condition in CONDITIONS:
        eligible = [
            dict(start=r["start"], origin="new-fit", fit=r["fit"])
            for r in rows.values()
            if r["condition"] == condition and r["stationary"]
        ]
        if condition == "alpha-one":
            eligible.extend(
                dict(start=r["start"], origin="source-incumbent", fit=r["source_fit"])
                for r in starts.values()
                if r["incumbent_eligible"]
            )
        selected[condition] = (
            min(
                eligible,
                key=lambda r: (r["fit"]["objective"], r["start"], r["origin"]),
            )
            if eligible
            else None
        )
    return selected


def validate_fit(fit, alpha):
    if "vector" in fit and (
        fit.get("likelihood_alpha") != alpha
        or fit.get("likelihood_kind") != "Scaled composite training cost"
        or fit.get("scaled_likelihood_nll") != fit["likelihood_nll"]
        or fit.get("untempered_likelihood_nll") != fit["likelihood_nll"] / alpha
        or fit.get("normalized_predictive_nll") is not False
        or fit.get("original_conditional_posteriors") is not True
    ):
        raise ValueError("Transfer likelihood receipt changed")


def check_oracle(oracle, sha, starts):
    if (
        oracle["protocol_sha256"] != sha
        or oracle["starts"] != starts
        or set(oracle["checks"]) != set(starts)
        or any(
            not r["passed"]
            or not r["deltas"]
            or any(not np.isfinite(v) or abs(v) > 1e-7 for v in r["deltas"].values())
            for r in oracle["checks"].values()
        )
    ):
        raise ValueError("Transfer all-six source oracle failed or changed")


def checkpoint_rows(directory, sha, manifest):
    rows = {}
    for folder in ("launches", "terminations", "attempts"):
        for path in (directory / folder).glob("*.json"):
            if path.stem not in NAMES:
                raise ValueError("Extra transfer condition/start/arm")
            row = json.loads(path.read_bytes())
            identity = dict(
                protocol_sha256=sha,
                name=path.stem,
                condition=path.stem.rsplit("-", 1)[0],
                start=int(path.stem[-1]),
            )
            if any(row.get(k) != v for k, v in identity.items()):
                raise ValueError("Transfer checkpoint identity changed")
            if not (directory / "attempts" / path.name).exists():
                raise ValueError("Orphan transfer launch/termination; no retry")
            if folder != "attempts":
                continue
            launch, termination = (directory / f / path.name for f in ("launches", "terminations"))
            if not launch.exists() or not termination.exists():
                raise ValueError("Transfer outcome lacks launch/termination")
            if json.loads(launch.read_bytes()) != identity or any(
                json.loads(termination.read_bytes()).get(k) != v for k, v in identity.items()
            ):
                raise ValueError("Transfer launch/termination changed")
            fit = row["fit"]
            validate_fit(fit, CONDITIONS[row["condition"]])
            initial = manifest["starts"][str(row["start"])]
            valid = stationary(fit, initial["local_center"], manifest["layout"]["vector"])
            if row["stationary"] != valid:
                raise ValueError("Transfer cached stationarity/domain changed")
            rows[path.stem] = row
    return rows


def sealed_receipts(directory, frozen):
    """Pure receipt checks: no training preparation or numerical replay on cache."""
    directory = Path(directory)
    terminal = json.loads((directory / "terminal.json").read_bytes())
    protocol = json.loads((directory / "protocol.json").read_bytes())
    manifest = frozen["inputs"]
    sha = terminal["protocol_sha256"]
    if protocol != dict(protocol_sha256=sha, policy=POLICY, starts=manifest["starts"]):
        raise ValueError("Sealed transfer protocol changed")
    oracle_path = directory / "source-oracle.json"
    check_oracle(json.loads(oracle_path.read_bytes()), sha, manifest["starts"])
    rows = checkpoint_rows(directory, sha, manifest)
    if (
        terminal["policy"] != POLICY
        or terminal["inputs"] != manifest
        or terminal["optimizer_calls"] != 12
        or set(rows) != set(NAMES)
        or rows != terminal["attempts"]
        or terminal["reference_usage"] != "none"
        or terminal["held_usage"] != "none"
        or terminal["source_oracle_sha256"] != digest(oracle_path)
        or terminal["selection"] != selection(rows, manifest["starts"])
    ):
        raise ValueError("Sealed transfer coverage/attempt/selection changed")
    for condition, winner in terminal["selection"].items():
        if winner is None:
            continue
        diagnostic = terminal["diagnostics"][condition]
        fit = winner["fit"]
        if (
            diagnostic["alpha"] != CONDITIONS[condition]
            or abs(diagnostic["objective"] - fit["objective"]) > 1e-7
            or abs(diagnostic["scaled_likelihood_nll"] - fit["likelihood_nll"]) > 1e-7
            or diagnostic["untempered_likelihood_nll"]
            != diagnostic["scaled_likelihood_nll"] / CONDITIONS[condition]
        ):
            raise ValueError("Sealed transfer selected diagnostic changed")
    return terminal


def run(manifest, directory, *, frozen_protocol, maximum_seconds=285, case=None):
    begun = time.monotonic()
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 285:
        raise ValueError("Transfer slice requires at most285 internal seconds")
    frozen = read_control(manifest, frozen_protocol)
    sha, directory = digest(Path(frozen_protocol)), Path(directory)
    starts = manifest["starts"]
    common.immutable(
        directory / "protocol.json", dict(protocol_sha256=sha, policy=POLICY, starts=starts)
    )
    rows = checkpoint_rows(directory, sha, manifest)
    if (directory / "terminal.json").exists():
        terminal = sealed_receipts(directory, frozen)
        if terminal["protocol_sha256"] != sha:
            raise ValueError("Transfer terminal belongs to another frozen control")
        return terminal
    calls = 0
    with bounded(max(0.001, maximum_seconds - (time.monotonic() - begun))):
        case = load_training_case(manifest) if case is None else case
        models = {}
        for condition, alpha in CONDITIONS.items():
            models[condition], metadata = tempering.build_tempered_model(case, alpha)
            common.immutable(directory / f"model-{condition}.json", metadata)

        def guard():
            if time.monotonic() - begun >= maximum_seconds:
                raise TimeoutError("Transfer calculation budget exhausted")

        oracle_path = directory / "source-oracle.json"
        if not oracle_path.exists():
            checks = {}
            for index, initial in starts.items():
                fit = initial["source_fit"]
                checks[index] = tempering.replay_alpha1(
                    models["alpha-one"],
                    np.asarray(fit["vector"]),
                    np.asarray(fit["nuisance"]),
                    fit=fit,
                    guard=guard,
                )
            common.immutable(oracle_path, dict(protocol_sha256=sha, starts=starts, checks=checks))
        check_oracle(json.loads(oracle_path.read_bytes()), sha, starts)
        for condition in CONDITIONS:
            for index in STARTS:
                name = f"{condition}-{index}"
                if name in rows:
                    continue
                if time.monotonic() - begun + 20 >= maximum_seconds:
                    return dict(
                        state="checkpointed",
                        next=name,
                        optimizer_calls_this_slice=calls,
                        elapsed_s=time.monotonic() - begun,
                    )
                guard()
                initial = starts[str(index)]
                identity = dict(protocol_sha256=sha, name=name, condition=condition, start=index)
                launch = directory / "launches" / f"{name}.json"
                launch.parent.mkdir(parents=True, exist_ok=True)
                with launch.open("x") as stream:
                    json.dump(identity, stream, allow_nan=False)
                termination = dict(optimizer_returned=False)
                calls += 1
                try:
                    fit = tempering.fit_tempered_calibration(
                        models[condition],
                        np.array(initial["seed"]["vector"], float, copy=True),
                        np.array(initial["seed"]["nuisance"], float, copy=True),
                        arm="fitted-c",
                        fixed_position=False,
                        seconds=20,
                        iterations=600,
                        local_center=np.asarray(initial["local_center"]),
                        local_radius_km=25,
                    )
                    termination["optimizer_returned"] = True
                    validate_fit(fit, CONDITIONS[condition])
                except (ValueError, TimeoutError) as error:
                    fit = dict(converged=False, reason=str(error))
                    termination.update(error_type=type(error).__name__, reason=str(error))
                except BaseException as error:
                    termination.update(error_type=type(error).__name__, reason=str(error))
                    raise
                finally:
                    common.immutable(
                        directory / "terminations" / launch.name, {**identity, **termination}
                    )
                path = directory / "attempts" / launch.name
                common.immutable(
                    path,
                    dict(
                        **identity,
                        fit=fit,
                        stationary=stationary(
                            fit,
                            initial["local_center"],
                            manifest["layout"]["vector"],
                        ),
                    ),
                )
                rows[name] = json.loads(path.read_bytes())
                print(
                    json.dumps(
                        dict(
                            label=manifest["label"],
                            name=name,
                            stationary=rows[name]["stationary"],
                            calls=calls,
                        )
                    ),
                    flush=True,
                )
        selected, diagnostics = selection(rows, starts), {}
        for condition, winner in selected.items():
            if winner is None:
                continue
            fit = winner["fit"]
            diagnostic = tempering.diagnose_tempered_state(
                models[condition],
                np.asarray(fit["vector"]),
                np.asarray(fit["nuisance"]),
                guard=guard,
            )
            if (
                abs(diagnostic["objective"] - fit["objective"]) > 1e-7
                or abs(diagnostic["scaled_likelihood_nll"] - fit["likelihood_nll"]) > 1e-7
            ):
                raise ValueError("Selected transfer objective/NLL replay differs")
            diagnostic["active_bounds"] = dict(
                boundary=fit.get("boundary"),
                physical_constraints_minimum=fit.get("physical_constraints_minimum"),
                nuisance_indices=np.flatnonzero(
                    abs(np.asarray(fit["nuisance"])) >= models[condition].group_limits - 1e-7
                ).tolist(),
            )
            diagnostics[condition] = diagnostic
    read_control(manifest, frozen_protocol)
    result = dict(
        schema=POLICY["schema"],
        label=manifest["label"],
        protocol_sha256=sha,
        policy=POLICY,
        inputs=manifest,
        attempts=rows,
        selection=selected,
        diagnostics=diagnostics,
        optimizer_calls=12,
        source_oracle_sha256=digest(oracle_path),
        reference_usage="none",
        held_usage="none",
        elapsed_s=time.monotonic() - begun,
    )
    common.immutable(directory / "terminal.json", result)
    return sealed_receipts(directory, frozen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "freeze", "run"))
    parser.add_argument("--label", choices=LABELS, required=True)
    parser.add_argument("--study", type=Path, default=common.OUTPUT)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--maximum-seconds", type=float, default=285)
    args = parser.parse_args()
    if args.command == "inventory":
        common.immutable(args.manifest, build_manifest(args.label, args.study))
        print(json.dumps(dict(label=args.label, state="inventoried", optimizer_calls=0)))
        return
    manifest = json.loads(args.manifest.read_bytes())
    if manifest["label"] != args.label:
        parser.error("Manifest label differs")
    if args.protocol is None:
        parser.error("--protocol required for freeze/run")
    if args.command == "freeze":
        freeze_protocol(manifest, args.protocol)
        print(json.dumps(dict(label=args.label, state="frozen", optimizer_calls=0)))
    else:
        if args.directory is None:
            parser.error("--directory required for run")
        result = run(
            manifest,
            args.directory,
            frozen_protocol=args.protocol,
            maximum_seconds=args.maximum_seconds,
        )
        print(
            json.dumps(
                dict(
                    label=args.label,
                    state=result.get("state", "sealed"),
                    elapsed_s=result["elapsed_s"],
                )
            )
        )


if __name__ == "__main__":
    main()
