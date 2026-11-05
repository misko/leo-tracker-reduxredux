"""Frozen/owned final-stage handoff, likelihood and RF-influence oracle."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint


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
        engine.ROOTS = {original["case"][:4]: root}
        d, z, replay = engine.load_case(original["case"])
        arms, owners = z["baseline_arms"], z["baseline_owners"]
        active = engine.active_ids(d)
        ranking, targets = engine.rank_families(d, z)
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
        ranking, targets = owned.rank_families(d)
        def build(arm, ref, omit=None):
            return owned.build(d, arm, ref, omit=omit)
        objective = owned.objective
    probes = {}
    for arm, (problem, x) in d["problems"].items():
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
        scope="Selected additional handoff, final-stage likelihood probes and RF influence trigger",
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
    for name in ("input", "screen", "catalogue", "recovery", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Reassociation comparison output exists")
    run(args)
