"""Frozen/owned final-stage handoff, likelihood and RF-influence oracle."""

import argparse
import hashlib
import json
import sys
import tempfile
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


def final_comparison(args, context, packet, catalogue, arms, owners, ranking, targets, read):
    """Complete frozen final worker versus owned admission/history/fit controller."""
    root = args.input.parent.parent
    history_bank = read(root / "history-bank.json")
    terminal = read(root / "exports" / packet["case"] / "published-algo06.json")
    if args.side == "reference":
        from algo07_science import runner

        if terminal == dict(research_only=True, public_terminal_available=False):
            # Historical research canary has no WebUI terminal. Qualify the
            # complete numerical controller, explicitly excluding publication.
            runner.preflight_public = lambda *a: dict(
                research_only=True, public_terminal_available=False
            )

        with tempfile.TemporaryDirectory(prefix="v3-final-oracle-") as directory:
            output = Path(directory)
            baseline = runner.published_baseline(root, packet["case"])
            runner.write(output / "protocol.json", dict(baselines={packet["case"]: baseline}))
            result = runner.run_worker(packet["case"], root, output)
            result["trigger"] = json.loads((output / packet["case"] / "trigger.json").read_text())
            for path in list(read.bindings):
                if path.startswith(directory):
                    del read.bindings[path]
    else:
        from leo.analysis.localization_v3.reassociation_admission import admit
        from leo.analysis.localization_v3.reassociation_history import select_history
        from leo.analysis.localization_v3.reassociation_recovery import (
            baseline_from_selected,
            recover,
        )

        retained = {}

        def retain_selected(state, pair):
            retained.update(context=state, pair=pair)

        admission = admit(context, owners, targets, catalogue, packet["scan_receipt"])
        result = recover(
            context,
            owners,
            baseline_from_selected(arms, owners),
            admission,
            catalogue,
            packet["scan_receipt"],
            lambda request: select_history(history_bank, request),
            on_selected=retain_selected,
        )
        if result["selected"] is not None:
            from leo.analysis.localization_v3.reassociation_context import objective

            for arm, (problem, x) in retained["context"]["problems"].items():
                row = retained["pair"][arm]
                if not np.array_equal(x, row["x"]):
                    raise ValueError("Retained endpoint changed")
                delta = objective(problem, retained["context"], x) - row["objective"]
                if not np.isfinite(delta) or abs(delta) > 1e-4:
                    raise ValueError("Retained selected likelihood changed")
        # The frozen worker exposes this diagnostic through persisted JSON.
        # Match that representation without rounding or tolerance changes.
        result["trigger"] = json.loads(
            json.dumps(
                dict(ranking=ranking, selected=targets),
                default=lambda value: np.asarray(value).tolist(),
            )
        )
        result.pop("control_fits", None)
        result.pop("candidate_fits", None)
    excluded = {
        "seconds",
        "case",
        "protocol_sha256",
        "fits_path",
        "catalogue_path",
        "catalogue_sha256",
        "input_path",
        "input_sha256",
    }

    def scientific(value):
        if isinstance(value, dict):
            return {k: scientific(v) for k, v in value.items() if k not in excluded}
        if isinstance(value, (tuple, list)):
            return [scientific(v) for v in value]
        return value

    return scientific(result)


def history_comparison(args, context, packet, catalogue, read):
    """External history exports are oracle inputs, never production prerequisites."""
    from contextlib import ExitStack

    exports = [read(args.history_export)]
    hypothesis = None
    if args.history_proposal:
        proposals = read(args.history_screen)["proposals"]
        hypothesis = next(h for h in proposals if h["name"] == args.history_proposal)
        exports.append(read(args.proposal_history_export))
    requests = []

    def collect(request):
        export = exports[len(requests)]
        if request != export["request"]:
            raise ValueError("Frozen history request differs")
        requests.append(request)
        return export["export"]

    with ExitStack() as stack:
        if args.side == "reference":
            from algo07_science import engine

            root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="v3-history-")))
            engine.collect_history = collect
            engine.OUT = root
            ledger = engine.rec.causal_records(packet["case"], packet)
            ledger_path = root / "ledgers" / packet["case"] / "tle-ledger.json"
            ledger_path.parent.mkdir(parents=True)
            ledger_path.write_text(json.dumps(dict(causal=ledger)))

            def complete(d, ids, name):
                return engine.complete_history(d, packet, packet["case"], ids, root / name)

            def remap(d):
                return engine.remap(d, packet, packet["case"], hypothesis)

            def fit_rows(d, starts, allowed, name):
                return engine.fit_rows(d, packet, starts, allowed, root / (name + ".json"))

            def build(d, arm, ref):
                return engine.build(d, packet, arm, ref)

            active = engine.active_ids(context)
            objective = engine.objective

            def previous(scan):
                return dict(
                    text=scan.previous_tle_path.read_text(),
                    sources=json.loads(
                        (scan.previous_tle_path.parent / "previous_receipt.json").read_text()
                    )["sources"],
                )
        else:
            from leo.analysis.localization_v3 import reassociation_context as ctx
            from leo.analysis.localization_v3.reassociation_fit import fit_rows as owned_fits
            from leo.analysis.localization_v3.reassociation_history import complete_history
            from leo.analysis.localization_v3.reassociation_remap import remap as owned_remap

            ledger = catalogue["elements"]

            def complete(d, ids, name):
                return complete_history(d, ids, ledger, packet["scan_receipt"], collect)

            def remap(d):
                return owned_remap(d, hypothesis, ledger)

            def fit_rows(d, starts, allowed, name):
                return owned_fits(d, packet["baseline_owners"], starts, allowed)

            build = ctx.build
            objective = ctx.objective
            active = ctx.active_ids(context)

            def previous(scan):
                return dict(text=scan.previous_tle, sources=scan.previous_sources)

        def snapshot(d):
            result = dict(
                previous=previous(d["scan"]),
                means=d["means"],
                node=d["node"],
                entries=d["entries"],
                family_entries=[f.entries for f in d["families"]],
                norads=d["scan"].norads,
                sky=d["scan"].sky,
                arms={},
            )
            for arm, (p, x) in d["problems"].items():
                q, dd = build(d, arm, p.reference)
                result["arms"][arm] = dict(
                    reference=p.reference,
                    labels=p.labels,
                    state=p.state(x),
                    calculation=p.calculate(x),
                    objective=objective(p, d, x),
                    rebuilt=objective(q, dd, x),
                    offset=objective(q, dd, x + np.array([0.2, -0.1])),
                )
            return result

        before = snapshot(context)
        updated, info = complete(context, active, "incumbent")
        result = dict(incumbent_info=info, incumbent=snapshot(updated), before=before)
        if args.history_fits:
            screen = read(args.history_screen)
            starts = dict(
                published=context["problems"]["fitted_c"][1].tolist(),
                family_omitted=screen["cavity"]["fitted_c"]["x"],
            )
            result["control_fits"] = without_elapsed(fit_rows(updated, starts, set(), "control"))
        if hypothesis:
            candidate, info = complete(updated, set(hypothesis["mapping"].values()), "candidate")
            candidate = remap(candidate)
            result.update(candidate_info=info, candidate=snapshot(candidate))
            if args.history_fits:
                old = {
                    r["candidate_norad"]
                    for r in context["problems"]["fitted_c"][0].rows
                    if r["component"] in hypothesis["mapping"]
                }
                result["candidate_fits"] = without_elapsed(
                    fit_rows(candidate, starts, old, "candidate")
                )
        result["original_after"] = snapshot(context)
        result["requests"] = requests
        if args.side == "reference":
            # Generated intermediate receipts are represented by the complete
            # before/after snapshots, not external inputs that survive the run.
            for path in list(read.bindings):
                if path.startswith(str(root)):
                    del read.bindings[path]
        return result


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

    read.bindings = bindings

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
        ranking, targets = (
            ([], []) if args.screen_target or args.history_export else engine.rank_families(d, z)
        )

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
        ranking, targets = (
            ([], []) if args.screen_target or args.history_export else owned.rank_families(d)
        )
        z = dict(original, baseline_arms=arms, baseline_owners=owners)

        def build(arm, ref, omit=None):
            return owned.build(d, arm, ref, omit=omit)

        objective = owned.objective
    probes = {}
    for arm, (problem, x) in (
        []
        if args.screen_target or args.history_export or args.complete_final
        else d["problems"].items()
    ):
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
    if args.history_export:
        result["history"] = history_comparison(args, d, z, catalogue, read)
    if args.complete_final:
        result["complete_final"] = final_comparison(
            args, d, z, catalogue, arms, owners, ranking, targets, read
        )
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
            "Complete guarded final worker from selected incumbent"
            if args.complete_final
            else "Causal history completion, remapping and likelihood replay"
            if args.history_export
            else (
                "Selected handoff, causal propagation, family-omitted screen "
                "and primary receiver guard"
            )
            if args.screen_target
            else (
                "Selected additional handoff, final-stage likelihood probes "
                "and RF influence trigger"
            )
        ),
        full_pipeline_parity=False,
        publication_qualified=False,
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
    parser.add_argument("--history-export", type=Path)
    parser.add_argument("--complete-final", action="store_true")
    parser.add_argument("--history-fits", action="store_true")
    parser.add_argument("--history-screen", type=Path)
    parser.add_argument("--history-proposal")
    parser.add_argument("--proposal-history-export", type=Path)
    for name in ("input", "screen", "catalogue", "recovery", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Reassociation comparison output exists")
    run(args)
