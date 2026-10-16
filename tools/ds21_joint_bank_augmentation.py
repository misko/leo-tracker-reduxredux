"""Frozen original-bank repeat versus small common-bank augmentation.

Named-module execution only. No selection, discovery, reference lookup, or
optimizer runs occur when constructing protocols or importing this module.
"""

import argparse
import json
import runpy
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
from ds20_channel_corpus import ADAPTER, digest
from ds21_common import OUTPUT, immutable
from ds21_joint_candidates import (
    candidate_diagnostics,
    candidate_held_prediction,
    candidate_objective,
    loaded_source_hashes,
    validate_archives,
)
from ds21_joint_candidates import scientific_sources as candidate_sources
from ds21_joint_proposals import run as run_proposals
from ds21_omitted_bank_diagnostic import read_bound, validate_inventory

from leo.analysis.hard60_bounded_fit import _parameterization, _Problem
from leo.analysis.joint_association_projection import matched_joint_arm_seeds

VARIANTS = ("original", "augmented")
ARMS = ("fitted-c", "zero-c")
FROZEN_FIELDS = dict(
    schema="ds21-common-bank-augmentation-v1",
    labels=["DS21-005", "DS21-023"],
    variants=list(VARIANTS),
    arms=list(ARMS),
    views=["all"],
    starts=6,
    fit_seconds=20,
    iterations=600,
    local_radius_km=25,
    maximum_slice_seconds=500,
    maximum_new_fit_calls=48,
    maximum_calls_per_condition=12,
    seed_policy="Original six saved physical proposal seeds and applied receiver lifts",
    timing_policy="Catalogue-ID shifts preserved; added common plus zero relative",
    timing_prior="Unchanged common/relative sigma; orthonormal zero-sum relative basis",
    timing_normalization="Existing MAP quadratic penalties; Gaussian dimension constants omitted",
    mixture_policy="Fixed signal/clutter mass; uniform satellite mass 1/K; raw visibility mask",
    candidate_policy="All native alternatives; fixed existing per-cell mass; singleton families",
    selection_usage="Frozen common training-only pool; cap four; empty/incomplete unavailable",
    winner_policy="Minimum stationary training objective, start tie-break",
    held_policy="Own normalized predictive likelihood on identical held rows; frozen state",
    reference_usage="none",
    held_selection="none",
    failed_retry=False,
    oracle_atol=1e-8,
    oracle_rtol=1e-11,
)


def scientific_sources():
    """Preload the adapter's code closure before any data preparation."""
    import ds21_common_bank_selection as selection

    runpy.run_path(str(ADAPTER))
    paths = candidate_sources()
    paths["tools/ds21_joint_bank_augmentation.py"] = Path(__file__)
    paths["tools/ds21_omitted_bank_diagnostic.py"] = Path(read_bound.__code__.co_filename)
    paths["tools/ds21_common_bank_selection.py"] = Path(selection.__file__)
    return paths


def selection_receipt(protocol, terminal):
    """Consume the selector owner's exact policy/coverage/source validator."""
    from ds21_common_bank_selection import validate_selection_receipt

    return validate_selection_receipt(protocol, terminal)


def validate_source_freeze(frozen):
    paths = scientific_sources()
    if frozen["source_sha256"] != {name: digest(path) for name, path in paths.items()}:
        raise ValueError("Bank-control scientific source changed")
    closure = frozen["loaded_source_sha256"]
    if any(closure.get(path) != sha for path, sha in loaded_source_hashes().items()) or any(
        digest(Path(path)) != sha for path, sha in closure.items()
    ):
        raise ValueError("Bank-control loaded source closure changed")
    return paths


def validate_selection(row, metadata_case):
    """Validate the sealed selector's bank mapping, without selecting again."""
    original = metadata_case["proposals"]
    if (
        row["original_numbers"] != original["candidate_numbers"]
        or row["original_full_indices"] != original["candidate_full_indices"]
        or row["source_binding"]["bank_npz_sha256"]
        != (metadata_case["discovery"]["bank_npz"]["sha256"])
    ):
        raise ValueError("Selection original bank authority differs")
    if row["state"] != "selected":
        if row["state"] not in ("unavailable", "failed") or row.get("added_numbers"):
            raise ValueError("Incomplete selection cannot supply additions")
        return False
    numbers, indices = row["added_numbers"], row["added_full_indices"]
    if (
        not 1 <= len(numbers) <= 4
        or numbers != sorted(set(numbers))
        or len(indices) != len(numbers)
        or len(set(indices)) != len(indices)
        or set(numbers) & set(row["original_numbers"])
        or set(indices) & set(row["original_full_indices"])
        or row["augmented_numbers"] != row["original_numbers"] + numbers
        or row["augmented_full_indices"] != row["original_full_indices"] + indices
    ):
        raise ValueError("Selection requires a unique cap-four original-prefix expansion")
    return True


def read_freeze(path, label, variant):
    frozen = json.loads(Path(path).read_bytes())
    if (
        any(frozen.get(key) != value for key, value in FROZEN_FIELDS.items())
        or label not in FROZEN_FIELDS["labels"]
        or variant not in VARIANTS
    ):
        raise ValueError("Case/variant/budget outside frozen bank-control scope")
    paths = validate_source_freeze(frozen)
    metadata, membership = validate_inventory(frozen["metadata"])
    selection_protocol, selection = selection_receipt(
        frozen["selection_protocol"], frozen["selection_terminal"]
    )
    if (
        selection_protocol["metadata"] != frozen["metadata"]
        or selection_protocol["fitting_module"] != "ds21_joint_bank_augmentation"
        or selection["schema"] != "common-bank-selection-v1"
        or selection["protocol_sha256"] != frozen["selection_protocol"]["sha256"]
        or selection.get("optimizer_calls") != 0
        or set(selection["cases"]) != set(FROZEN_FIELDS["labels"])
    ):
        raise ValueError("Selection receipt/freeze authority differs")
    physical_protocol = read_bound(frozen["physical_seed_protocol"])
    if physical_protocol["labels"] != FROZEN_FIELDS["labels"] or physical_protocol["starts"] != 6:
        raise ValueError("Original physical-seed protocol differs")
    row, metadata_case = selection["cases"][label], metadata["cases"][label]
    if row["source_binding"]["metadata_sha256"] != frozen["metadata"]["sha256"]:
        raise ValueError("Selection training inventory changed")
    available = validate_selection(row, metadata_case)
    if available and not selection["coverage_complete"]:
        raise ValueError("Incomplete screen cannot authorize fitting")
    parent_binding = physical_protocol["cases"][label]
    parent = validate_physical_parent(parent_binding, metadata_case)
    baseline_sources = validate_baseline_sources(metadata_case)
    oracle = read_bound(frozen["oracle"])
    inputs = {
        key: frozen[key]
        for key in (
            "metadata",
            "selection_protocol",
            "selection_terminal",
            "physical_seed_protocol",
        )
    }
    if (
        not oracle.get("passed")
        or oracle.get("labels") != FROZEN_FIELDS["labels"]
        or oracle.get("input_bindings") != inputs
        or oracle.get("source_sha256") != frozen["source_sha256"]
        or oracle.get("loaded_source_sha256") != frozen["loaded_source_sha256"]
        or oracle.get("atol") != FROZEN_FIELDS["oracle_atol"]
        or oracle.get("rtol") != FROZEN_FIELDS["oracle_rtol"]
    ):
        raise ValueError("Baseline oracle does not bind the frozen bank control")
    for case_rows in oracle["case_results"].values():
        expected = {f"seed-{i}-{arm}" for i in range(6) for arm in ARMS} | {
            f"winner-{arm}" for arm in ARMS
        }
        if (
            {r["state"] for r in case_rows} != expected
            or len(case_rows) != 14
            or not all(r["passed"] for r in case_rows)
        ):
            raise ValueError("Baseline oracle requires both winners and all six arm starts")
    if set(oracle["case_results"]) != set(FROZEN_FIELDS["labels"]):
        raise ValueError("Baseline oracle case coverage differs")
    if any(
        row["baseline_source_sha256"] != baseline_sources for row in oracle["case_results"][label]
    ):
        raise ValueError("Baseline oracle historical source proof differs")
    return frozen, paths, metadata_case, membership, row, parent, available


def validate_physical_parent(binding, metadata_case):
    parent = Path(binding["native_parent_directory"])
    protocol = read_bound(
        dict(path=str(parent / "protocol.json"), sha256=binding["native_parent_protocol_sha256"])
    )
    if digest(parent / "terminal.json") != binding["native_parent_terminal_sha256"]:
        raise ValueError("Original physical parent terminal changed")
    expected_names = {f"all-{i}.json" for i in range(6)}
    if (
        set(binding["seed_sha256"]) != expected_names
        or binding["catalogue_numbers"] != metadata_case["proposals"]["candidate_numbers"]
        or binding["prepared_all_sha256"] != metadata_case["parent"]["prepared_all_sha256"]
        or binding["bank_npz_sha256"] != metadata_case["discovery"]["bank_npz"]["sha256"]
        or binding["input_sha256"] != metadata_case["source_input"]["sha256"]
        or protocol["catalogue_numbers"] != binding["catalogue_numbers"]
        or protocol["prepared"]["all"] != binding["prepared_all_sha256"]
        or protocol["proposal_binding"]["protocol_sha256"]
        != (metadata_case["proposals"]["protocol"]["sha256"])
        or protocol["shared_discovery_sha256"] != (metadata_case["discovery"]["protocol"]["sha256"])
        or any(
            protocol.get(k) != v
            for k, v in dict(
                starts=6,
                fit_seconds=20,
                iterations=600,
                c_arms=list(ARMS),
                reference_usage="none",
                held_selection="none",
            ).items()
        )
    ):
        raise ValueError("Original physical parent bank/input/objective differs")
    validate_archives(parent, protocol)
    lifts = read_bound(
        dict(
            path=str(parent / "receiver-branch-starts.json"),
            sha256=binding["receiver_branch_starts_sha256"],
        )
    )
    if len(lifts) != 6 or len(set(protocol["proposal_ids"])) != 6:
        raise ValueError("Original six proposal/lift rows required")
    for i in range(6):
        receipt = read_bound(
            dict(
                path=str(parent / "seeds" / f"all-{i}.json"),
                sha256=binding["seed_sha256"][f"all-{i}.json"],
            )
        )
        if (
            receipt["protocol_sha256"] != binding["native_parent_protocol_sha256"]
            or receipt["proposal_id"] != protocol["proposal_ids"][i]
            or receipt["receiver_branch_lifts"] != lifts[i]
        ):
            raise ValueError("Original proposal seed/lift binding differs")
    return parent


def validate_baseline_sources(metadata_case):
    """Bind historical model bytes; changed research wrappers are not the oracle."""
    binding = metadata_case["parent"]["protocol"]
    protocol = read_bound(binding)
    validate_archives(Path(binding["path"]).parent, protocol, require_mapping=True)
    checked = {}
    for name, path in candidate_sources().items():
        if not (
            name.startswith("src/leo/")
            or name.startswith("native-kernel/")
            or name.startswith("input-adapter/")
            or name
            in (
                "tools/ds21_joint_candidates.py",
                "tools/ds21_joint.py",
                "tools/joint_association_candidates_native.py",
                "tools/joint_association_native.py",
            )
        ):
            continue
        historical = [
            filename
            for filename in protocol["sources"]
            if filename.endswith("/" + name) or Path(filename).name == path.name
        ]
        if len(historical) != 1 or protocol["sources"][historical[0]] != digest(path):
            raise ValueError(f"Historical baseline computational source differs: {name}")
        checked[name] = digest(path)
    return checked


def selected_case(case, selection, variant):
    if variant not in VARIANTS:
        raise ValueError("Unknown bank variant")
    numbers = selection[f"{'original' if variant == 'original' else 'augmented'}_numbers"]
    indices = selection[f"{'original' if variant == 'original' else 'augmented'}_full_indices"]
    if case["bank"].numbers.tolist() != selection["original_numbers"] or any(
        not isinstance(i, int) or not 0 <= i < len(case["full_bank"].numbers) for i in indices
    ):
        raise ValueError("Selection bank indices/original ordering differ")
    bank = case["full_bank"].select(indices)
    if bank.numbers.tolist() != numbers:
        raise ValueError("Selection catalogue mapping differs from causal full bank")
    return {**case, "bank": bank}


def bank_objective(case, source, observations):
    return candidate_objective(case, source, observations, variant="all-candidates")


def transport_seed(seed, original, target):
    """Embed unchanged physical timing in the new orthonormal zero-sum basis."""
    result = deepcopy(seed)
    vector, nuisance = np.asarray(seed["vector"], float), np.asarray(seed["nuisance"], float)
    if (
        vector.shape != (original.size,)
        or nuisance.shape != original.initial_nuisance.shape
        or not np.isfinite(vector).all()
        or not np.isfinite(nuisance).all()
        or original.frame != target.frame
        or original.score != target.score
        or original.prior != target.prior
        or original.clock_count
        or target.clock_count
        or original.observations.window_ids != target.observations.window_ids
        or not np.array_equal(original.base.native_design, target.base.native_design)
        or not np.array_equal(original.group_design, target.group_design)
        or not np.array_equal(original.group_precision, target.group_precision)
    ):
        raise ValueError("Seed transport changed physical correction/prior/frame")
    old_numbers, new_numbers = original.bank.numbers.tolist(), target.bank.numbers.tolist()
    if not set(old_numbers) <= set(new_numbers):
        raise ValueError("Augmentation removed an original satellite")
    if old_numbers == new_numbers:
        return result
    relative = original.basis @ vector[8:]
    by_number = dict(zip(old_numbers, relative, strict=True))
    desired = np.asarray([by_number.get(number, 0.0) for number in new_numbers])
    lifted = np.r_[vector[:8], target.basis.T @ desired]
    reconstructed = target.basis @ lifted[8:]
    if not np.allclose(reconstructed, desired, atol=1e-12, rtol=1e-12):
        raise ValueError("Catalogue timing transport failed zero-sum closure")
    result["vector"] = lifted
    result["timing_transport"] = dict(
        original_numbers=old_numbers,
        target_numbers=new_numbers,
        original_shifts_s=(vector[7] + relative).tolist(),
        target_shifts_s=(lifted[7] + reconstructed).tolist(),
        maximum_relative_closure_s=float(np.max(abs(reconstructed - desired))),
        relative_penalty_delta=float(
            (reconstructed @ reconstructed - relative @ relative)
            / (2 * original.score.relative_sigma_s**2)
        ),
        common_preserved=True,
        correction_preserved=True,
    )
    return result


def baseline_replay(case, metadata_case, parent):
    """Evaluation-only oracle: all six actual arm starts plus two training winners."""
    source_proof = validate_baseline_sources(metadata_case)
    obs, source = case["prepared"]["all"].observations, case["split"].training
    old, _ = candidate_objective(case, source, obs, variant="all-candidates")
    proposal = metadata_case["proposals"]
    original_case = selected_case(
        case,
        dict(
            original_numbers=proposal["candidate_numbers"],
            original_full_indices=proposal["candidate_full_indices"],
        ),
        "original",
    )
    new, _ = bank_objective(original_case, source, obs)
    for field in ("numbers", "nodes_s", "position_km", "velocity_km_s"):
        if not np.array_equal(getattr(old.bank, field), getattr(new.bank, field)):
            raise ValueError("Independent original-bank reconstruction changed ephemerides")
    states = []
    for i in range(6):
        seed = json.loads((Path(parent) / "seeds" / f"all-{i}.json").read_bytes())["seed"]
        carried = transport_seed(seed, old, new)
        for arm, initial in matched_joint_arm_seeds(seed).items():
            target = matched_joint_arm_seeds(carried)[arm]
            kwargs = dict(
                rf_arm=arm,
                local_center=initial["vector"][:2],
                local_radius_km=25,
                slope_half_width_hz_s=60,
            )

            def actual_initial(model, vector, kwargs=kwargs):
                z, _, _, matrix, constant = _parameterization(_Problem(model, vector, **kwargs))
                return constant + matrix @ z

            v0 = actual_initial(old, initial["vector"])
            v1 = actual_initial(new, target["vector"])
            n0 = initial["nuisance"] / old.group_scales * old.group_scales
            n1 = target["nuisance"] / new.group_scales * new.group_scales
            states.append((f"seed-{i}-{arm}", v0, n0, v1, n1))
    for arm in ARMS:
        winner = metadata_case["winners"][arm]
        if winner["state"] != "selected":
            raise ValueError("Baseline replay requires both original training winners")
        fit = winner["fit"]
        if arm == "zero-c" and fit["vector"][6] != 0:
            raise ValueError("Historical zero-c winner does not have exact zero c")
        states.append(
            (f"winner-{arm}", fit["vector"], fit["nuisance"], fit["vector"], fit["nuisance"])
        )
    rows = []
    for name, v0, n0, v1, n1 in states:
        previous, current = (
            old.evaluate_joint(np.asarray(v0), np.asarray(n0)),
            (new.evaluate_joint(np.asarray(v1), np.asarray(n1))),
        )
        arrays = (
            [(v0, v1), (n0, n1)]
            + [(previous[i], current[i]) for i in range(3)]
            + [
                (getattr(previous[3], attr), getattr(current[3], attr))
                for attr in (
                    "nll",
                    "responsibilities",
                    "clutter_probability",
                    "candidate_responsibilities",
                    "posterior_native_residual_rms_hz",
                )
            ]
        )
        receipt_deltas = {}
        if name.startswith("winner-"):
            fit = metadata_case["winners"][name.removeprefix("winner-")]["fit"]
            arrays += [(fit["objective"], current[0]), (fit["likelihood_nll"], current[3].nll)]
            receipt_deltas = dict(
                objective=float(current[0] - fit["objective"]),
                likelihood_nll=float(current[3].nll - fit["likelihood_nll"]),
            )
        differences = [
            float(np.max(abs(np.asarray(a) - np.asarray(b)), initial=0))
            for a, b in arrays
            if a is not None and b is not None
        ]
        passed = all(
            (a is None and b is None)
            or (
                a is not None
                and b is not None
                and np.allclose(
                    a, b, atol=FROZEN_FIELDS["oracle_atol"], rtol=FROZEN_FIELDS["oracle_rtol"]
                )
            )
            for a, b in arrays
        )
        rows.append(
            dict(
                state=name,
                passed=passed,
                maximum_absolute_difference=max(differences, default=0.0),
                historical_scalar_deltas=receipt_deltas,
                baseline_source_sha256=source_proof,
            )
        )
    return rows


def validate_attempts(directory, protocol_sha, identifiers):
    """An optimizer launch without its outcome is never automatically retried."""
    allowed = {f"all-{i}-{arm}.json" for i in range(6) for arm in ARMS}
    for folder in ("attempts", "launches"):
        paths = list((directory / folder).glob("*.json"))
        if any(path.name not in allowed for path in paths):
            raise ValueError("Checkpoint has a call outside the twelve fixed attempts")
        for path in paths:
            row = json.loads(path.read_bytes())
            i = int(path.name.split("-")[1])
            if row["protocol_sha256"] != protocol_sha or row["proposal_id"] != identifiers[i]:
                raise ValueError("Checkpoint optimizer/proposal protocol differs")
            if (
                folder == "attempts"
                and row["fit"].get("converged")
                and (
                    not np.isfinite(row["fit"].get("objective", float("inf")))
                    or not np.isfinite(row["fit"].get("stationarity", float("inf")))
                    or row["fit"]["stationarity"] > 0.001
                )
            ):
                raise ValueError("Checkpoint convergence lacks finite stationary objective")
            if folder == "launches" and not (directory / "attempts" / path.name).exists():
                raise ValueError("Orphan optimizer launch preserved; no retry permitted")
            if folder == "attempts" and not (directory / "launches" / path.name).exists():
                raise ValueError("Checkpoint outcome lacks its optimizer launch receipt")


def validate_terminal(directory, terminal, frozen_path, case, variant):
    protocol_path = directory / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    identifiers = [p["id"] for p in case["proposal_seeds"]["all"]]
    if (
        terminal["protocol_sha256"] != digest(protocol_path)
        or protocol["scientific_control"]["frozen_protocol_sha256"] != digest(frozen_path)
        or protocol["scientific_control"]["variant"] != variant
        or protocol["catalogue_numbers"] != case["bank"].numbers.tolist()
        or protocol["proposal_ids"] != identifiers
        or protocol["label"] != directory.name
        or protocol["policy"] != f"joint-common-bank-{variant}-v1"
        or protocol["effective_views"] != ["all"]
        or protocol["prepared"]["all"] != case["prepared"]["all"].evidence_sha256
        or protocol["proposal_binding"] != {k: str(v) for k, v in case["proposal_binding"].items()}
        or terminal["reference_usage"] != "none"
        or any(
            protocol[k] != v
            for k, v in dict(fit_seconds=20, iterations=600, starts=6, c_arms=list(ARMS)).items()
        )
    ):
        raise ValueError("Sealed bank-control inputs/seed/budget differ")
    validate_archives(directory, protocol, require_mapping=True)
    validate_attempts(directory, digest(protocol_path), identifiers)
    result = terminal["results"]["all"]
    for arm in ARMS:
        rows = result["attempts"][arm]
        if len(rows) != 6 or [r["start"] for r in rows] != list(range(6)):
            raise ValueError("Sealed bank-control requires all twelve outcomes")
        for i, row in enumerate(rows):
            receipt = json.loads((directory / "attempts" / f"all-{i}-{arm}.json").read_bytes())
            if row["fit"] != receipt["fit"] or row["proposal_id"] != identifiers[i]:
                raise ValueError("Sealed outcome differs from its immutable checkpoint")
        eligible = [r for r in rows if r["fit"]["converged"]]
        selected = result["selected"][arm]
        if not eligible:
            if selected.get("state") != "unavailable":
                raise ValueError("Sealed selection promotes a failed path")
        else:
            winner = min(eligible, key=lambda r: (r["fit"]["objective"], r["start"]))
            if (
                any(selected[k] != winner[k] for k in ("start", "proposal_id", "fit"))
                or not selected["fit"]["stationarity"] <= 0.001
                or tuple(selected["held_prediction"]["window_ids"])
                != tuple(case["held"]["all"].window_ids)
            ):
                raise ValueError("Sealed training winner/held rows differ")


def run(label, variant, frozen_protocol, *, maximum_seconds=500):
    import ds21_joint_proposals as common
    import ds21_shared_proposals as shared

    begun = time.monotonic()
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 500:
        raise ValueError("Bank-control slice must be at most 500 seconds")
    frozen, paths, metadata_case, _, selection, parent, available = read_freeze(
        frozen_protocol, label, variant
    )
    policy = f"joint-common-bank-{variant}-v1"
    directory = OUTPUT / "local" / policy / label
    if not available:
        result = dict(
            state="unavailable",
            reason="Frozen common selection unavailable",
            optimizer_calls=0,
            label=label,
            variant=variant,
            frozen_protocol_sha256=digest(Path(frozen_protocol)),
            selection=selection,
        )
        immutable(directory / "terminal.json", result)
        return result
    case = shared.load_case_with_proposals(label)
    if (
        case["member"]["input"] != metadata_case["source_input"]
        or case["prepared"]["all"].evidence_sha256 != metadata_case["parent"]["prepared_all_sha256"]
        or case["protocol_sha256"] != metadata_case["discovery"]["protocol"]["sha256"]
        or case["proposal_binding"]["protocol_sha256"]
        != metadata_case["proposals"]["protocol"]["sha256"]
        or case["proposal_binding"]["terminal_sha256"]
        != metadata_case["proposals"]["terminal"]["sha256"]
    ):
        raise ValueError("Prepared original case differs from frozen training/proposals")
    validate_source_freeze(frozen)
    original, _ = bank_objective(case, case["split"].training, case["prepared"]["all"].observations)
    case = selected_case(case, selection, variant)
    target, _ = bank_objective(case, case["split"].training, case["prepared"]["all"].observations)

    def stored_seed(view, index):
        if view != "all" or index not in range(6):
            raise ValueError("Seed outside original six all-channel proposals")
        row = json.loads((parent / "seeds" / f"all-{index}.json").read_bytes())
        return transport_seed(row["seed"], original, target), row["receiver_branch_lifts"]

    def validate_seed(view, index, seed, lifts):
        expected, expected_lifts = stored_seed(view, index)

        def encode(value):
            return json.loads(json.dumps(value, default=lambda a: a.tolist()))

        if encode(seed) != encode(expected) or lifts != expected_lifts:
            raise ValueError("Bank-control original physical seed/lift changed")

    terminal_path, protocol_path = directory / "terminal.json", directory / "protocol.json"
    if protocol_path.exists():
        protocol = json.loads(protocol_path.read_bytes())
        if protocol["scientific_control"]["frozen_protocol_sha256"] != digest(
            Path(frozen_protocol)
        ):
            raise ValueError("Checkpoint belongs to another bank-control freeze")
        validate_attempts(
            directory, digest(protocol_path), [p["id"] for p in case["proposal_seeds"]["all"]]
        )
    if terminal_path.exists():
        terminal = json.loads(terminal_path.read_bytes())
        validate_terminal(directory, terminal, Path(frozen_protocol), case, variant)
        for i in range(6):
            row = json.loads((directory / "seeds" / f"all-{i}.json").read_bytes())
            if (
                row["protocol_sha256"] != digest(protocol_path)
                or row["proposal_id"] != case["proposal_seeds"]["all"][i]["id"]
            ):
                raise ValueError("Local saved seed wrapper differs from proposal/protocol")
            validate_seed("all", i, row["seed"], row["receiver_branch_lifts"])
        return terminal
    pending = [
        (i, arm)
        for i in range(6)
        for arm in ARMS
        if not (directory / "attempts" / f"all-{i}-{arm}.json").exists()
    ]
    fitter = common.fit_group_calibration

    def guarded_fit(model, vector, nuisance, **kwargs):
        index, arm = pending.pop(0)
        if (
            kwargs["arm"] != arm
            or kwargs["seconds"] != 20
            or kwargs["iterations"] != 600
            or kwargs["local_radius_km"] != 25
        ):
            raise ValueError("Optimizer call differs from matched fixed budget")
        immutable(
            directory / "launches" / f"all-{index}-{arm}.json",
            dict(
                protocol_sha256=digest(protocol_path),
                proposal_id=case["proposal_seeds"]["all"][index]["id"],
                start=index,
                arm=arm,
                fit_seconds=20,
                iterations=600,
                local_radius_km=25,
            ),
        )
        termination = dict(optimizer_returned=False)
        try:
            fit = fitter(model, vector, nuisance, **kwargs)
            termination["optimizer_returned"] = True
            if fit.get("converged") and (
                not np.isfinite(fit.get("stationarity", float("inf")))
                or fit["stationarity"] > 0.001
                or not np.isfinite(fit.get("objective", float("inf")))
            ):
                fit = {
                    **fit,
                    "converged": False,
                    "reported_converged": True,
                    "reason": "Stationarity/objective guard rejected fitter convergence flag",
                }
            return fit
        except BaseException as error:
            termination.update(error_type=type(error).__name__, reason=str(error))
            raise
        finally:
            immutable(
                directory / "terminations" / f"all-{index}-{arm}.json",
                dict(
                    protocol_sha256=digest(protocol_path),
                    proposal_id=case["proposal_seeds"]["all"][index]["id"],
                    **termination,
                ),
            )

    def diagnostics(model, fit):
        terms = model.evaluate_joint(np.asarray(fit["vector"]), np.asarray(fit["nuisance"]))[3]
        return candidate_diagnostics(model, terms, model.candidate_inventory_metadata)

    source_paths = tuple(
        dict.fromkeys((*paths.values(), *(Path(p) for p in frozen["loaded_source_sha256"])))
    )
    with patch.object(common, "fit_group_calibration", guarded_fit):
        result = run_proposals(
            label,
            maximum_seconds=maximum_seconds,
            policy=policy,
            views=("all",),
            objective_port=bank_objective,
            held_port=lambda c, s, o, m, f: candidate_held_prediction(
                c, s, o, m, f, variant="all-candidates"
            ),
            extra_sources=source_paths,
            case_input=case,
            started_at=begun,
            stored_seed_port=stored_seed,
            validate_seed=validate_seed,
            fit_diagnostics=diagnostics,
            fit_diagnostics_key="candidate_diagnostics",
            scientific_protocol=dict(
                frozen_protocol_path=str(Path(frozen_protocol).resolve()),
                frozen_protocol_sha256=digest(Path(frozen_protocol)),
                variant=variant,
                model_changes="Bank only: uniform satellite mixture and expanded timing basis",
                selection=selection,
                metadata_binding=frozen["metadata"],
                physical_seed_parent=frozen["physical_seed_protocol"],
                oracle=frozen["oracle"],
                loaded_source_sha256=frozen["loaded_source_sha256"],
                timing_prior=FROZEN_FIELDS["timing_prior"],
                satellite_mass=1 / len(case["bank"].numbers),
                projection_diagnostics="Inherited projection; catalogue timing closure recorded",
            ),
        )
    validate_source_freeze(frozen)
    if "results" in result:
        validate_terminal(directory, result, Path(frozen_protocol), case, variant)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=FROZEN_FIELDS["labels"], required=True)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--frozen-protocol", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=float, default=500)
    args = parser.parse_args()
    result = run(
        args.label, args.variant, args.frozen_protocol, maximum_seconds=args.maximum_seconds
    )
    print(
        json.dumps(
            dict(state=result.get("state", "sealed"), label=args.label, variant=args.variant)
        ),
        flush=True,
    )
