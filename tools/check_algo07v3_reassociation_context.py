"""Frozen/owned final-stage handoff, likelihood and RF-influence oracle."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint


def without_elapsed(value):
    """Exclude only wall-clock metadata; retain every numerical/decision field."""
    if isinstance(value, dict):
        return {k: without_elapsed(v) for k, v in value.items() if k != "seconds"}
    if isinstance(value, (list, tuple)):
        return [without_elapsed(v) for v in value]
    return value


def screen_comparison(args, context, packet, catalogue, owners):
    target = args.screen_target
    if args.side == "reference":
        from algo07_science import engine, propagation, validation
        from algo07_science.runner import destination_owned, propagation_eligible
        from algo07_science.uniqueness import from_additional_checks

        ledger = engine.rec.causal_records(packet["case"], packet)
        nums, bank, failures = engine.rec.bank_for(ledger, packet["scan_receipt"]["origin_utc_ns"])
        audit = propagation.audit(packet["case"], args.catalogue, args.input, "elements")
        audit = {
            k: v
            for k, v in audit.items()
            if k not in ("catalogue_path", "catalogue_sha256", "input_path", "input_sha256")
        }
        eligible = (
            propagation_eligible(audit, failures)
            and len(nums) + len(failures) == len(ledger)
            and np.isfinite(bank["position_km"]).all()
            and np.isfinite(bank["velocity_km_s"]).all()
        )
        engine.rec.write = lambda *a: None

        def screen():
            return engine.rec.screen(
                context, packet, target, nums, bank, Path("unused-oracle-output")
            )

        def shared(screened, new):
            return validation.receiver_shared_check(context, packet, screened, target, new, ledger)

        def occupied(new):
            return destination_owned(packet, new)
    else:
        from leo.analysis.localization_v3.reassociation_admission import admit
        from leo.analysis.localization_v3.reassociation_catalogue import prepare_catalogue

        # Extra preparation fingerprints the complete bank in this external
        # oracle only. Production admission prepares the catalogue once.
        prepared = prepare_catalogue(catalogue, packet["scan_receipt"])
        admission = admit(context, owners, [target], catalogue, packet["scan_receipt"])
        return without_elapsed(
            dict(
                catalogue_audit=admission["catalogue_eligibility"],
                propagation_failures=admission["propagation_failures"],
                eligible=admission["status"] != "propagation_fallback",
                nums=prepared["nums"],
                bank=prepared["bank"],
                screen=admission["screens"].get(str(target)),
                shared=admission["shared"].get(str(target)),
                guards=admission["guards"],
                admitted=[row["hypothesis"] for row in admission["admitted"]],
            )
        )

    result = dict(
        catalogue_audit=audit,
        propagation_failures=failures,
        eligible=bool(eligible),
        nums=nums,
        bank=bank,
        screen=None,
        shared=None,
        guards={},
        admitted=[],
    )
    if not eligible:
        return without_elapsed(result)
    screened = screen()
    result["screen"] = screened
    proposals = [
        h
        for h in screened.get("proposals", [])
        if "prediction_limit" not in h
        and set(map(int, h["mapping"].values())) == {int(h["norad"])}
        and int(h["norad"]) != int(target)
        and all(h["predictive"][arm]["pass_check"] for arm in ("c0", "fitted_c"))
    ]
    for proposal in proposals:
        if occupied(proposal["norad"]):
            result["guards"][proposal["name"]] = dict(
                passed=False,
                status="rejected",
                model="receiver_offset",
                reason="destination_already_owned",
            )
            continue
        if result["shared"] is None:
            result["shared"] = shared(screened, proposal["norad"])
        guard = from_additional_checks(dict(result["shared"], new=proposal["norad"]))
        result["guards"][proposal["name"]] = guard
        if guard["passed"]:
            result["admitted"].append(proposal)
    return without_elapsed(result)


def run(args):
    bindings = {}

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    began = time.monotonic()
    original = read(args.input)
    inventory = read(original["inventory_path"])
    source = Path(inventory["job"]["root"]) / inventory["job"]["case"]
    screen, catalogue, recovery = read(args.screen), read(args.catalogue), read(args.recovery)
    observations = read(Path(original["native_path"]) / "observations.json")
    selected = original["selected"]
    if original["gap_selected"] or (selected and selected["kind"] != "new_family"):
        raise ValueError(
            "Fixture adapter currently covers baseline or single new-family incumbents"
        )
    selection, annotations = None, []
    if selected:
        folder = Path(selected["trial"])
        protocol = read(folder / "protocol.json")
        if any(
            protocol.get(k)
            for k in ("graph_bundle_sources", "annotation_receipts", "measurement_refinements")
        ):
            raise ValueError("Unsupported fixture annotations")
        annotations = [
            {k: read(Path(p) / (k + ".json")) for k in ("protocol", "result")}
            for p in protocol.get("inactive_fragment_sources", [])
        ]
        selection = dict(
            kind="new_family",
            trial=dict(protocol=protocol, new_family=read(folder / "new_family.json")),
        )
    if args.side == "reference":
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        from algo06_science import common
        from algo07_science import engine

        root = args.input.parent.parent

        def routed(path):
            path = Path(path)
            if path == root / "position" / original["case"] / "result.json":
                return recovery
            if path == root / "screen" / original["case"] / "result.json":
                return screen
            if path == root / "catalogues" / (original["case"] + ".json"):
                return catalogue
            return read(path)

        common.read = read
        engine.read = routed
        engine.position.read = routed
        engine.rec.read = routed
        engine.rec.CATALOGUES = root / "catalogues"
        engine.ROOTS = {original["case"][:4]: root}
        d, z, replay = engine.load_case(original["case"])
        arms, owners = z["baseline_arms"], z["baseline_owners"]
        active = engine.active_ids(d)
        ranking, targets = ([], []) if args.screen_target else engine.rank_families(d, z)

        def build(arm, ref, omit=None):
            return engine.build(d, z, arm, ref, omit=omit)

        objective = engine.objective
    else:
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3 import reassociation_context as owned
        from leo.analysis.localization_v3.selected_incumbent import reconstruct_incumbent

        def fresh():
            return reconstruct_incumbent(
                owned_context(source, bindings),
                original["baseline_arms"],
                original["baseline_owners"],
                selection=selection,
                inventory=inventory,
                annotations=annotations,
                observations=observations,
            )

        restored = owned.adopt_additional(
            fresh,
            original["baseline_arms"],
            original["baseline_owners"],
            selection,
            recovery,
            screen,
            catalogue,
            observations,
        )
        d, arms, owners, replay = (restored[k] for k in ("context", "arms", "owners", "replay"))
        active = owned.active_ids(d)
        ranking, targets = ([], []) if args.screen_target else owned.rank_families(d)
        z = dict(original, baseline_arms=arms, baseline_owners=owners)

        def build(arm, ref, omit=None):
            return owned.build(d, arm, ref, omit=omit)

        objective = owned.objective
    probes = {}
    for arm, (problem, x) in [] if args.screen_target else d["problems"].items():
        probes[arm] = []
        for omitted in (None, *targets):
            p, view = build(arm, problem.reference.copy(), omitted)
            probes[arm].append(
                dict(
                    omitted=omitted,
                    state=p.state(x),
                    calculation=p.calculate(x),
                    objective=objective(p, view, x),
                    offset_objective=objective(p, view, x + np.array([0.2, -0.1])),
                    entries=view["entries"],
                    family_entries=[f.entries for f in view["families"]],
                )
            )
    result = dict(
        replay=replay,
        arms=arms,
        owners=owners,
        active=sorted(active),
        ranking=ranking,
        targets=targets,
        probes=probes,
    )
    if args.screen_target:
        result["screening"] = screen_comparison(args, d, z, catalogue, owners)
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    for directory in (source, source.parent / "causal_prior" / source.name):
        for path in directory.iterdir():
            if path.is_file():
                bindings[str(path)] = binding(path)["sha256"]
    path = source.parent / "family_cavity/position" / (source.name + ".json")
    bindings[str(path)] = binding(path)["sha256"]
    receipt = dict(
        side=args.side,
        seconds=time.monotonic() - began,
        scope=(
            "Selected handoff, causal propagation, family-omitted screen and primary receiver guard"
            if args.screen_target
            else (
                "Selected additional handoff, final-stage likelihood probes "
                "and RF influence trigger"
            )
        ),
        full_pipeline_parity=False,
        tool=binding(__file__),
        inputs=bindings,
        modules={
            name: binding(module.__file__)
            for name, module in sys.modules.items()
            if getattr(module, "__file__", None)
            and (
                str(module.__file__).startswith(str(args.runtime))
                or "/src/leo/" in str(module.__file__)
                or name.startswith("check_algo07v3_")
            )
        },
        output=binding(args.output),
    )
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                side=args.side,
                seconds=receipt["seconds"],
                targets=targets,
                owner_counts={arm: len(row) for arm, row in owners.items()},
                output=receipt["output"],
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    parser.add_argument(
        "--screen-target",
        type=int,
        help="External component fixture only: compare a declared target's complete screen",
    )
    for name in ("input", "screen", "catalogue", "recovery", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Reassociation comparison output exists")
    run(args)
