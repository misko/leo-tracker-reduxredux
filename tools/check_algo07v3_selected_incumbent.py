"""External original/owned incumbent likelihood reconstruction oracle."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint


def run(args):
    bindings = {}

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    began = time.monotonic()
    if args.mode == "selected":
        z = read(args.input)
        inv = read(z["inventory_path"])
    else:
        inv = read(args.inventory)
        z = dict(
            inventory_path=str(args.inventory),
            selected=None,
            gap_selected=None,
            baseline_arms=inv["policy"],
            baseline_owners={},
        )
        if args.mode == "baseline":
            decision = read(args.decision)
            z["baseline_owners"] = {
                a: row["owners"] for a, row in decision["source_support"].items()
            }
        if args.mode == "gap":
            saved = read(args.trial / "target_0.json")["arms"]
            z.update(
                gap_selected=dict(path=str(args.trial)),
                baseline_arms=saved,
                baseline_owners={a: row["proposed_owners"] for a, row in saved.items()},
            )
    source = Path(inv["job"]["root"]) / inv["job"]["case"]
    # Bind inputs read internally by the old fixture adapters too. Their reads
    # do not all go through common.read, and must not escape the receipt.
    chosen, gap = z["selected"], z["gap_selected"]
    if (chosen and chosen["kind"] != "joint") or gap:
        folder = Path((gap or chosen)["path" if gap else "trial"])
        protocol = read(folder / "protocol.json")
        appended = list(protocol.get("inactive_fragment_sources", []))
        appended += list(protocol.get("graph_bundle_sources", []))
        appended += [r["path"] for r in protocol.get("annotation_receipts", [])]
        for annotation_path in appended:
            annotation = Path(annotation_path)
            target = read(annotation / "protocol.json")["target"]
            read(annotation / "result.json")
            if target.get("native_branch_source"):
                native = Path(target["native_branch_source"])
                read(native)
                read(native.parent / "protocol.json")
    if args.side == "reference":
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        from algo06_science import common

        original_read = common.read
        common.read = read
        try:
            context = common.reconstruct(z)
        finally:
            common.read = original_read
    else:
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3.gap_fragments import gap_context
        from leo.analysis.localization_v3.selected_incumbent import reconstruct_incumbent

        base = owned_context(source, bindings)
        selection, annotations, observations = None, [], []
        selected, gap = z["selected"], z["gap_selected"]
        if selected and gap:
            raise ValueError("Original policy rejects composing a gap with a recovered family")
        if selected and selected["kind"] == "joint":
            trials = {}
            for arm in ("c0", "fitted_c"):
                matches = [
                    Path(k).parent
                    for k in selected.get("source_receipts", {})
                    if k.endswith("/joint-" + arm + "/result.json")
                ]
                path = (
                    matches[0]
                    if len(matches) == 1
                    else Path(z["recovery_path"]) / "joint" / ("joint-" + arm)
                )
                trials[arm] = {k: read(path / (k + ".json")) for k in ("protocol", "result")}
            selection = dict(kind="joint", trials=trials)
        elif selected or gap:
            path = Path((gap or selected)["path" if gap else "trial"])
            protocol = read(path / "protocol.json")
            kind = "gap_conditional" if gap else selected["kind"]
            role = "new_family" if kind == "new_family" else "target_0"
            selection = dict(
                kind=kind, trial=dict(protocol=protocol, **{role: read(path / (role + ".json"))})
            )
            if gap:
                observations = read(source / "observations.json")
                for receipt in protocol["annotation_receipts"]:
                    folder = Path(receipt["path"])
                    annotation = {k: read(folder / (k + ".json")) for k in ("protocol", "result")}
                    target = annotation["protocol"]["target"]
                    original_source = Path(target["native_branch_source"])
                    if (
                        hashlib.sha256(original_source.read_bytes()).hexdigest()
                        != target["native_branch_sha256"]
                    ):
                        raise ValueError("Original native source changed")
                    prepared = dict(
                        protocol=read(original_source.parent / "protocol.json"),
                        **read(original_source),
                    )
                    prepared["protocol"].pop("job")
                    prepared["protocol"].pop("input_sha256")
                    _, rebuilt = gap_context(
                        base, inv, prepared, annotation["result"]["track_id"], observations
                    )
                    for key in set(target) - {"native_branch_source", "native_branch_sha256"}:
                        if fingerprint(target[key]) != fingerprint(rebuilt[key]):
                            raise ValueError("Gap scientific target changed: " + key)
                    annotation["protocol"]["target"] = rebuilt
                    annotation["gap_source"] = prepared
                    annotations.append(annotation)
            else:
                for folder in protocol.get("inactive_fragment_sources", []):
                    annotations.append(
                        {k: read(Path(folder) / (k + ".json")) for k in ("protocol", "result")}
                    )
        if args.preflight:
            from leo.application.localization_v3 import prepare_additional_recovery

            additional = prepare_additional_recovery(
                dict(
                    status="track_recovery_prepared",
                    recovery_context=base,
                    inventory=dict(inventory=inv),
                ),
                dict(tracks=base["scan"].tracks, observations=read(source / "observations.json")),
                read(source.parent / "causal_prior" / source.name / "receipt.json"),
                arms=z["baseline_arms"],
                owners=z["baseline_owners"],
                identities=inv["job"]["identities"],
                selection=selection,
                annotations=annotations,
            )
            context = additional["residual_context"]
        else:
            context = reconstruct_incumbent(
                base,
                z["baseline_arms"],
                z["baseline_owners"],
                selection=selection,
                inventory=inv,
                annotations=annotations,
                observations=observations,
            )
    result = dict(
        checks=context["replay_checks"],
        entries=context["entries"],
        families=[dict(entries=f.entries, prior=f.receipt) for f in context["families"]],
        arms={},
    )
    for arm, (problem, x) in context["problems"].items():
        fresh = context["factory"](arm, problem.reference.copy())
        result["arms"][arm] = dict(
            position=x,
            reference=problem.reference,
            calculation=problem.calculate(x),
            state=problem.state(x),
            reconstructed_factory=fresh.calculate(x),
            offset_calculation=fresh.calculate(x + [0.2, -0.1]),
        )
    if args.preflight:
        tracks = read(source / "tracks.json")
        observations = read(source / "observations.json")
        if args.side == "reference":
            from algo06_science import screen
            from algo06_science.rank import fragment_rows

            fragments, summary = fragment_rows(
                "SCAN",
                tracks,
                observations,
                z["baseline_owners"]["fitted_c"],
                inv["job"]["identities"],
            )
            occupied = set(z["baseline_owners"]["c0"]) | set(z["baseline_owners"]["fitted_c"])
            eligible = [
                r
                for r in fragments
                if r["points"] >= 20
                and r["duration_s"] >= 15
                and not set(r["observation_ids"]) & occupied
            ]
            eligible.sort(key=lambda r: (-r["duration_s"], -r["points"], r["fragment_id"]))
            ranked = dict(
                fragments=fragments,
                summary=summary,
                targets=eligible[:3],
                eligible_targets=len(eligible),
            )
            captured = {}
            # External IO fixture only: execute the original preflight body.
            screen.read = lambda path: dict(z, targets=ranked["targets"])
            screen.reconstruct = lambda packet: context
            screen.write = lambda path, packet: captured.update(packet)
            screen.preflight("SCAN")
            captured.pop("seconds")
            packet = captured
        else:
            ranked, packet = additional["residual_inventory"], additional["preflight"]
        result.update(residual_inventory=ranked, preflight=packet)
    args.output.write_text(json.dumps(fingerprint(result), sort_keys=True, allow_nan=False) + "\n")

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    for directory in (source, source.parent / "causal_prior" / source.name):
        for path in directory.iterdir():
            if path.is_file():
                bindings[str(path)] = binding(path)["sha256"]
    cavity = source.parent / "family_cavity/position" / f"{source.name}.json"
    bindings[str(cavity)] = binding(cavity)["sha256"]
    receipt = dict(
        side=args.side,
        mode=args.mode,
        seconds=time.monotonic() - began,
        scope=(
            "Selected incumbent likelihood reconstruction"
            + (", residual ranking and receiver-corrected preflight" if args.preflight else "")
            + "; no new association or position fit"
        ),
        full_pipeline_parity=False,
        inputs=bindings,
        modules={
            n: binding(m.__file__)
            for n, m in sys.modules.items()
            if getattr(m, "__file__", None)
            and (
                str(m.__file__).startswith(str(args.runtime))
                or "/src/leo/" in str(m.__file__)
                or n
                in (
                    "check_algo07v3_fixture_context",
                    "check_algo07v3_track_preparation",
                    "check_algo07v3_scan_likelihood",
                )
            )
        },
        tool=binding(__file__),
        output=binding(args.output),
    )
    if args.preflight_packet:
        if not args.preflight:
            raise ValueError("Raw packet export requires preflight comparison mode")
        import numpy as np

        args.preflight_packet.write_text(
            json.dumps(
                result["preflight"],
                allow_nan=False,
                default=lambda value: np.asarray(value).tolist(),
            )
            + "\n"
        )
        receipt["preflight_packet"] = binding(args.preflight_packet)
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                side=args.side,
                seconds=receipt["seconds"],
                kind=context["replay_checks"]["c0"]["selected_kind"],
                output=receipt["output"],
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    parser.add_argument("--mode", choices=["baseline", "selected", "gap"], required=True)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--preflight-packet", type=Path)
    for name in ("input", "inventory", "trial", "decision"):
        parser.add_argument("--" + name, type=Path)
    for name in ("runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Reconstruction output exists")
    if args.preflight_packet and args.preflight_packet.exists():
        raise ValueError("Preflight packet output exists")
    run(args)
