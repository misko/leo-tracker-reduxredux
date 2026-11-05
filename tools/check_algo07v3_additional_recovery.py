"""External frozen/owned conditional-addition oracle on an explicit fixture.

This tool consumes historical selected fixtures only for qualification. The
production controller accepts values and cannot read these paths or old workers.
"""

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
    z = read(args.input)
    inventory = read(z["inventory_path"])
    source = Path(inventory["job"]["root"]) / inventory["job"]["case"]
    screen, catalogue = read(args.screen), read(args.catalogue)
    # Historical population fixtures retain the original screen's dataset label
    # while their selected input is renamed SCAN. Scope the external packet to
    # that explicit input, as a fresh production preflight already does.
    screen = dict(screen, case=z["case"])
    observations = read(Path(z["native_path"]) / "observations.json")
    # Deliberately bounded fixture adapter. Other incumbent branches have their
    # own reconstruction oracle and must be added explicitly before using here.
    if z["gap_selected"] or z["selected"]["kind"] != "new_family":
        raise ValueError("This fixture oracle currently requires one selected new family")
    folder = Path(z["selected"]["trial"])
    protocol = read(folder / "protocol.json")
    if any(
        protocol.get(key)
        for key in ("graph_bundle_sources", "annotation_receipts", "measurement_refinements")
    ):
        raise ValueError("Unsupported annotated fixture in additional-family oracle")
    annotations = [
        {key: read(Path(path) / (key + ".json")) for key in ("protocol", "result")}
        for path in protocol.get("inactive_fragment_sources", [])
    ]
    selection = dict(
        kind="new_family",
        trial=dict(protocol=protocol, new_family=read(folder / "new_family.json")),
    )
    if args.side == "reference":
        sys.path[:0] = [str(args.runtime / "src"), str(args.runtime / "tools")]
        from algo06_science import common, position

        # Execute the actual original controller, including its independent
        # target ordering and paired control gates. Only its IO is redirected.
        common.read = read
        captured = {}

        def routed_read(path):
            path = Path(path)
            if path == position.ROOT / "inputs" / (z["case"] + ".json"):
                return z
            if path == position.ROOT / "screen" / z["case"] / "result.json":
                return screen
            if path == position.ROOT / "catalogues" / (z["case"] + ".json"):
                return catalogue
            return read(path)

        def capture(path, value):
            if Path(path).name == "result.json":
                captured.update(value)

        position.read = routed_read
        position.write = capture
        position.POLICIES = {"72h_30s": position.POLICIES["72h_30s"]}
        position.one(z["case"])
        result = captured
        result.pop("seconds")
    else:
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3.additional_recovery import recover_additional
        from leo.analysis.localization_v3.selected_incumbent import reconstruct_incumbent

        def fresh():
            return reconstruct_incumbent(
                owned_context(source, bindings),
                z["baseline_arms"],
                z["baseline_owners"],
                selection=selection,
                inventory=inventory,
                annotations=annotations,
                observations=observations,
            )

        result = recover_additional(
            fresh,
            z["baseline_owners"],
            screen,
            catalogue,
            observations,
            family_count=1,
            clock=time.monotonic,
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
        scope="Selected incumbent reconstruction, matched control and one additional-family fit",
        full_pipeline_parity=False,
        inputs=bindings,
        tool=binding(__file__),
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
                decisions=result["decisions"],
                output=receipt["output"],
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    for name in ("input", "screen", "catalogue", "runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".receipt.json").exists():
        raise ValueError("Comparison output already exists")
    run(args)
