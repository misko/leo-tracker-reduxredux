"""External frozen-renderer versus owned selected-fit presentation oracle."""

import argparse
import hashlib
import json
import sys
import tempfile
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint


def run(args):
    bindings = {}

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        bindings[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    evidence, authority = read(args.evidence), read(args.authority)
    began = time.monotonic()
    # Bind the selected baseline's complete numerical fixture on both sides.
    # This is external qualification IO, not a v3 runtime input contract.
    root = Path(evidence["workspace"])
    z = read(root / "inputs/SCAN.json")
    if z["selected"] or z["gap_selected"] or evidence["terminal"]["candidate"]:
        raise ValueError("This external fixture adapter currently covers retained baseline only")
    inventory = read(z["inventory_path"])
    source = Path(inventory["job"]["root"]) / inventory["job"]["case"]
    for directory in (source, source.parent / "causal_prior" / source.name):
        for path in directory.iterdir():
            if path.is_file():
                bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    read(source.parent / "family_cavity/position" / (source.name + ".json"))
    recovery = read(root / "position/SCAN/result.json")
    if args.side == "reference":
        sys.path[:0] = [
            str(args.renderer / "tools"),
            str(args.renderer / "src"),
            str(args.runtime / "tools"),
            str(args.runtime / "src"),
        ]
        import render_standard_fast as original

        from leo.analysis import position_grid

        sampling = position_grid.sample_position_grid

        def sample(*a, **kwargs):
            return sampling(*a, **dict(kwargs, maximum_seconds=args.grid_seconds))

        position_grid.sample_position_grid = sample
        with tempfile.TemporaryDirectory(prefix="v3-presentation-oracle-") as folder:
            packet = original.replay(evidence, Path(folder), include_grid=True)
        render = original.render
    else:
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from check_algo07v3_fixture_context import owned_context

        from leo.analysis.localization_v3.reassociation_context import adopt_additional
        from leo.analysis.localization_v3.selected_incumbent import reconstruct_incumbent
        from leo.presentation.fast_standard_analysis import render
        from leo.presentation.localization_v3 import prepare_packet

        def fresh():
            return reconstruct_incumbent(
                owned_context(source, bindings),
                z["baseline_arms"],
                z["baseline_owners"],
                selection=None,
                inventory=inventory,
                annotations=[],
                observations=evidence["observations"],
            )

        qualified_addition = recovery["decisions"]["72h_30s"]["status"] == "qualified"
        restored = adopt_additional(
            fresh,
            z["baseline_arms"],
            z["baseline_owners"],
            None,
            recovery,
            read(root / "screen/SCAN/result.json") if qualified_addition else None,
            read(root / "catalogues/SCAN.json") if qualified_addition else None,
            evidence["observations"],
        )
        packet = prepare_packet(
            restored["context"],
            restored["owners"],
            restored["arms"],
            evidence["observations"],
            evidence["tracks"],
            selected_model=authority["selected"]["model_version"],
            position_path=authority["position_path"],
            grid_seconds=args.grid_seconds,
        )
    prepared_seconds = time.monotonic() - began
    products = render(
        packet, title=authority["title"], evaluation_reference=authority["evaluation_reference"]
    )

    def science(value):
        if is_dataclass(value):
            return science(asdict(value))
        if isinstance(value, dict):
            return {k: science(v) for k, v in value.items() if k != "elapsed_seconds"}
        if isinstance(value, (tuple, list)):
            return [science(v) for v in value]
        return value

    result = dict(packet=fingerprint(science(packet)), products={})
    for name, png in products.items():
        path = args.output / (name + ".png")
        path.write_bytes(png)
        result["products"][name] = hashlib.sha256(png).hexdigest()
    (args.output / "result.json").write_text(
        json.dumps(result, sort_keys=True, allow_nan=False) + "\n"
    )

    def bound(path):
        return dict(path=str(path), sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())

    for path, sha in bindings.items():
        if bound(path)["sha256"] != sha:
            raise ValueError("Fixture input changed during rendering: " + path)

    receipt = dict(
        side=args.side,
        seconds=time.monotonic() - began,
        preparation_seconds=prepared_seconds,
        grid_seconds=packet["position_grid"]["elapsed_seconds"],
        grid_budget=args.grid_seconds,
        complete_grid=packet["position_grid"]["complete"],
        evaluated_grid=packet["position_grid"]["evaluated_points"],
        planned_grid=packet["position_grid"]["planned_points"],
        product_count=len(products),
        inputs=bindings,
        tool=bound(__file__),
        modules={
            name: bound(module.__file__)
            for name, module in sys.modules.items()
            if getattr(module, "__file__", None)
            and (
                "/src/leo/" in str(module.__file__)
                or str(module.__file__).startswith(str(args.runtime))
                or str(module.__file__).startswith(str(args.renderer))
                or name.startswith("check_algo07v3_")
            )
        },
        output=bound(args.output / "result.json"),
        scope="Selected fixture to plot evidence, grid and eight PNGs",
        full_pipeline_parity=False,
        publication_qualified=False,
    )
    (args.output / "result.receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in (
                    "side",
                    "seconds",
                    "preparation_seconds",
                    "complete_grid",
                    "evaluated_grid",
                    "product_count",
                    "output",
                )
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["reference", "candidate"], required=True)
    for name in ("evidence", "authority", "output", "runtime", "renderer"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--grid-seconds", type=float, default=300.0)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    run(args)
