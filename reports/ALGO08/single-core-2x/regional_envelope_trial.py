"""Measure the installed solver's exact regional salvage guard on saved detections."""

import argparse
from contextlib import ExitStack, nullcontext
from hashlib import sha256
import json
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

FROZEN = Path("/opt/leo-algo08/algo08v3")
FINE_SOURCE = "a86e62fed9eb7c286747fcf20e246010b3f06774dc9f79843ea7f8610a0fa7b4"
HERE = Path(__file__).resolve().parent
OVERLAY = HERE.parents[2] / "tools/pipeline_eval/variants/experimental/regional_envelope.py"


def read(path):
    return json.loads(path.read_bytes())


class CensusFinished(Exception):
    pass


def run(pair_path, output, *, mode, alternate_offer):
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    frozen = FROZEN / "payload"
    if Path(publication.__file__).resolve().parents[3] != frozen:
        raise ValueError("Use the installed ALGO08v3 publication module")
    installed = runpy.run_path(str(FROZEN / "run"))
    original_spec = read(frozen / "spec.json")
    spec = installed["checked_spec"](frozen)
    pair = read(pair_path)
    archived_spec = read(pair_path.with_name("candidate-config.json"))
    if (pair["candidate_specification"] != original_spec or archived_spec != original_spec
            or pair["candidate_specification_digest"] != "sha256:" + installed["FINGERPRINT"]):
        raise ValueError("Saved publication used a different ALGO08v3 freeze")

    archive, original_offer = Path(pair["archive"]["root"]), Path(pair["region"])
    region_path = original_offer if alternate_offer is None else alternate_offer
    install = lean_startup.install
    stage = {}
    with TemporaryDirectory(dir=output.parent) as name, ExitStack() as stack:
        root = Path(name)
        args = SimpleNamespace(recording=root / "no-raw-recording", bulk_root=root,
                               archive=archive, region=region_path)

        def install_trial():
            install()
            from leo.application.localization_v3_engine import _json_value
            from leo.contracts.algo08_region import Algo08Region
            from leo.contracts.digests import canonical_digest
            from leo.operations.tle_archive import TleArchiveReader
            from tools import algo08_position, algo08_scan
            from tools.pipeline_eval.variants import v5_core, v5_tiled_salvage

            archive_identity = runpy.run_path(str(HERE / "solver_orbit_support_trial.py"))["archive_identity"]
            candidate = pair["runs"]["candidate"]
            receipt = candidate["receipt"]
            work_dir = pair_path.parent / "candidate" / "fast-scan-automatic-work"
            terminal = read(work_dir / receipt["run_id"] / "terminal.json")
            native_path, = work_dir.glob("*/detections.json")
            native = read(native_path)
            original = Algo08Region.parse(read(original_offer)).document()
            if (original != receipt["region"] or original != terminal["region"]
                    or archive_identity(archive) != pair["archive"]
                    or canonical_digest(terminal) != receipt["terminal_sha256"]
                    or canonical_digest(native) != terminal["native_sha256"]
                    or terminal["session_id"] != receipt["session_id"]
                    or native["source"]["session_id"] != receipt["session_id"]
                    or native["source"]["raw_recording_authority_digest"] != candidate["raw_authority"]):
                raise ValueError("Saved detections, original offer, terminal or archive failed verification")
            overlay = runpy.run_path(str(OVERLAY))
            coarse_trace = []
            stock_context = v5_core.scan_context
            stock_salvage = v5_tiled_salvage.salvage

            def census_context(*inner_args, **kwargs):
                scan = stock_context(*inner_args, **kwargs)
                cases = (("phase15_nominal", 15., 0., 0.),
                         ("phase15_plus_orbit_ball", 15., 10., .02),
                         ("phase30_plus_orbit_ball", 30., 10., .02))
                for strategy, phase, position, velocity in cases:
                    start = process_time()
                    result = overlay["contrast_census"](
                        scan, phase_limit_s=phase, phase_tile_s=5., orbit_position_km=position,
                        orbit_velocity_km_s=velocity,
                    )
                    stage[strategy] = dict(result, cpu_s=process_time() - start)
                raise CensusFinished

            def track_salvage(*inner_args, **kwargs):
                result = stock_salvage(*inner_args, **kwargs)
                coarse_trace.extend(result[2])
                return result

            def analyze(recording, bulk_root, assets, causal_archive, offer):
                if (recording != args.recording or causal_archive != archive
                        or offer.document() != Algo08Region.parse(read(region_path)).document()):
                    raise ValueError("Unexpected saved solver authority")
                overlay_context = (overlay["regional_fine_salvage"](
                    prune=mode == "prune", expected_source_sha256=FINE_SOURCE,
                ) if mode in ("audit", "prune") else nullcontext())
                with ExitStack() as inner:
                    work = inner.enter_context(overlay_context)
                    if mode == "census":
                        inner.enter_context(patch.object(v5_core, "scan_context", census_context))
                    cpu, wall = process_time(), perf_counter()
                    try:
                        decision, packet, policy = algo08_position.solve(
                            native, TleArchiveReader(causal_archive), assets, offer,
                        )
                    except CensusFinished:
                        decision, packet, policy = {}, None, None
                    elapsed = dict(cpu_s=process_time() - cpu, wall_s=perf_counter() - wall)
                if archive_identity(archive) != pair["archive"]:
                    raise ValueError("Causal campaign archive changed during the saved trial")
                terminal = dict(status=decision.get("status"), reason=decision.get("reason"),
                                arms=decision.get("arms"), orbit_policy=policy)
                if packet is not None:
                    terminal.update(
                        owners={arm: p["owner_sha256"] for arm, p in packet["arms"].items()},
                        associated={arm: p["associated_points"] for arm, p in packet["arms"].items()},
                        evidence={key: canonical_digest(packet[key]) for key in (
                            "position_path", "position_grid", "objective_replay")},
                    )
                trace = json.loads(json.dumps(coarse_trace, default=_json_value, allow_nan=False))
                return dict(elapsed=elapsed, terminal=terminal, fine=None if work is None else dict(work), census=stage,
                            trim_fragments=len(trace), trim_digest=canonical_digest(trace),
                            stage_s=decision.get("metrics", {}).get("stage_s"),
                            source_sha256=canonical_digest(native), archive=pair["archive"],
                            offer=offer.document(), baseline_arms=candidate["arms"],
                            regional_guard=decision.get("metrics", {}).get("regional_bound_guard"))

            stack.enter_context(patch.object(algo08_scan, "analyze", analyze))
            stack.enter_context(patch.object(v5_tiled_salvage, "salvage", track_salvage))

        stack.enter_context(patch.object(lean_startup, "install", install_trial))
        result = publication.run(args, spec)
    result.update(mode=mode, specification=pair["candidate_specification_digest"],
                  source_pair=str(pair_path), overlay_sha256=sha256(OVERLAY.read_bytes()).hexdigest())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("stock", "audit", "prune", "census"), required=True)
    parser.add_argument("--alternate-offer", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    result = run(args.pair, args.output, mode=args.mode, alternate_offer=args.alternate_offer)
    with args.output.open("x") as stream:
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False), file=stream)


if __name__ == "__main__":
    main()
