"""Recompute both position arms from a sealed ALGO08v3 detector document."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch


BASELINE = Path("/opt/leo-algo08/algo08v3/run")
FROZEN = "6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_bytes())


def trial(pair_path, output, *, reuse, no_audit, plain):
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    launcher = runpy.run_path(str(BASELINE))
    payload = BASELINE.parent / "payload"
    specification = launcher["checked_spec"](payload, FROZEN)
    if Path(publication.__file__).resolve() != (
        payload / "tools/pipeline_eval/qualification/experimental_publication.py"
    ):
        raise ValueError("Expected the installed publication")
    lean_startup.install()
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan

    pair = read(pair_path)
    archived = pair["runs"]["candidate"]
    receipt = archived["receipt"]
    if pair["candidate_specification_digest"] != "sha256:" + FROZEN:
        raise ValueError("Expected an archived ALGO08v3 decision")
    archive, offer = Path(pair["archive"]["root"]), Path(pair["region"])
    snapshots = {ref.path.name: ref.sha256
                 for ref in TleArchiveReader(archive).list_snapshots("space-track")}
    saved = pair_path.parent / "candidate/fast-scan-automatic-work"
    terminal_path, = (path for path in saved.glob("*/terminal.json")
                      if path.parent.name == receipt["run_id"])
    terminal = read(terminal_path)
    native_path, = saved.glob("*/detections.json")
    native = read(native_path)
    if (canonical_digest(snapshots) != pair["archive"]["snapshots_sha256"]
            or Algo08Region.parse(read(offer)).document() != receipt["region"]
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["region"] != receipt["region"]
            or canonical_digest(native) != terminal["native_sha256"]
            or native["source"]["session_id"] != terminal["session_id"]
            or terminal["session_id"] != receipt["session_id"]):
        raise ValueError("Sealed saved inputs differ from their archived evidence")

    layout = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants/algo08_incremental_layout.py"
    install = runpy.run_path(str(layout))["install"]

    def from_saved(recording, _root, assets, causal_archive, region):
        start_cpu, start_wall = process_time(), perf_counter()
        decision, packet, policy = algo08_position.solve(
            native, TleArchiveReader(causal_archive), assets, region,
        )
        cpu, wall = process_time() - start_cpu, perf_counter() - start_wall
        if packet is None or decision["status"] != "ok":
            raise ValueError("Saved input did not reach the original decision")
        # Strip publication binding and runtime fields exactly as the paired
        # acquisition/publication receipt does.
        science = {name: canonical_digest({k: v for k, v in packet[f"position_{name}"].items()
                                          if k not in ("binding", "elapsed_seconds")})
                   for name in ("path", "grid")}
        return dict(
            status=decision["status"], reason=decision.get("reason"), orbit_policy=policy,
            arms=decision["arms"], scientific_digests=science,
            owners={arm: packet["arms"][arm]["owner_sha256"] for arm in ARMS},
            associated={arm: packet["arms"][arm]["associated_points"] for arm in ARMS},
            objective_replay=packet["objective_replay"], solver_cpu_s=cpu, solver_wall_s=wall,
        )

    specification["startup"] = "stock"  # Already installed before science imports.
    with TemporaryDirectory() as scratch:
        args = SimpleNamespace(recording=Path(scratch) / "sealed-detector",
                               bulk_root=Path(scratch), archive=archive, region=offer)
        overlay = (nullcontext({}) if plain else
                   install(publication, specification, args, reuse=reuse, audit=not no_audit))
        with patch.object(algo08_scan, "analyze", from_saved), overlay as counts:
            result = publication.run(args, specification)
    for key in ("arms", "owners", "scientific_digests", "reason"):
        if result[key] != archived[key]:
            raise ValueError(f"Changed archived {key}\n{result[key]!r}\n{archived[key]!r}")
    if result["orbit_policy"] != terminal["orbit_policy"]:
        raise ValueError("Changed archived orbit policy")
    result.update(
        incremental_layout=dict(counts), mode="plain" if plain else "reuse" if reuse else "audit",
        diagnosed=not plain and not no_audit,
        overlay_sha256=None if plain else sha256(layout.read_bytes()).hexdigest(),
        specification="sha256:" + FROZEN, native_sha256=terminal["native_sha256"],
        pair_sha256=sha256(pair_path.read_bytes()).hexdigest(),
        region=receipt["region"], archive=pair["archive"],
    )
    with output.open("x") as stream:
        print(json.dumps(result, default=_json_value, sort_keys=True, indent=2, allow_nan=False),
              file=stream)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair_path", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--no-audit", action="store_true")
    parser.add_argument("--plain", action="store_true")
    trial(**vars(parser.parse_args()))
