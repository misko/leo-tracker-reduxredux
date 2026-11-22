"""Verify and solve one saved ALGO08v3 orbit-support failure without raw I/Q."""

import argparse
import json
import runpy
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

OVERLAY = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants/v5_orbit_domain.py"
FAILURE = "ValueError: orbit phase interpolation never extrapolates"


def read(path):
    return json.loads(path.read_bytes())


def archive_identity(path):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    root = path.resolve(strict=True)
    snapshots = {
        ref.path.name: ref.sha256 for ref in TleArchiveReader(root).list_snapshots("space-track")
    }
    return dict(root=str(root), snapshots_sha256=canonical_digest(snapshots))


def verify(frozen, pair_path, specification, archive, region):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    pair = read(pair_path)
    for name, digest in specification["sources"].items():
        source = Path(name)
        if source.is_absolute() or ".." in source.parts:
            raise ValueError(f"Source pin is outside the frozen bundle: {name}")
        if sha256((frozen / source).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen source changed: {name}")
    if (
        specification != pair["candidate_specification"]
        or specification != read(pair_path.with_name("candidate-config.json"))
        or canonical_digest(specification) != pair["candidate_specification_digest"]
        or archive_identity(archive) != pair["archive"]
    ):
        raise ValueError("Candidate specification or causal orbit archive differs from the pair")

    candidate, baseline = (pair["runs"][arm] for arm in ("candidate", "baseline"))
    offer = Algo08Region.parse(read(region)).document()
    if offer != candidate["receipt"]["region"] or offer != baseline["receipt"]["region"]:
        raise ValueError("Regional offer differs from the paired receipts")
    candidate_work, baseline_work = (
        pair_path.parent / arm / "fast-scan-automatic-work" for arm in ("candidate", "baseline")
    )
    failure = candidate["failure_observation"]
    if (
        candidate["receipt"]["decision"] != "solver_failed" or failure["exit_code"] != 1
        or not failure["stderr"].rstrip().endswith(FAILURE)
        or any(candidate_work.glob("*/terminal.json"))
    ):
        raise ValueError("Expected a saved interpolation failure before publication")

    baseline_terminal = read(baseline_work / baseline["receipt"]["run_id"] / "terminal.json")
    candidate_path, = candidate_work.glob("*/detections.json")
    baseline_path, = baseline_work.glob("*/detections.json")
    native, reference_native = read(candidate_path), read(baseline_path)
    session = native["source"]["session_id"]
    raw = native["source"]["raw_recording_authority_digest"]
    if (
        canonical_digest(baseline_terminal) != baseline["receipt"]["terminal_sha256"]
        or baseline_terminal["decision"] != "ok"
        or baseline_terminal["orbit_policy"] != "orbit_support"
        or baseline_terminal["arms"] != baseline["arms"]
        or canonical_digest(reference_native) != baseline_terminal["native_sha256"]
        or session != candidate["receipt"]["session_id"]
        or session != baseline["receipt"]["session_id"]
        or raw != candidate["raw_authority"]
        or raw != baseline["raw_authority"]
        or canonical_digest(native) != candidate["native_sha256"]
    ):
        raise ValueError("Paired terminal or saved observations do not bind to their receipts")
    old_probes, new_probes = (d["source"]["probes"] for d in (reference_native, native))
    return native, offer, dict(
        source_digest=candidate["native_sha256"],
        spec_digest=pair["candidate_specification_digest"],
        archive_digest=pair["archive"]["snapshots_sha256"], raw_authority=raw,
        probe_counts=[len(old_probes), len(new_probes)],
        identical_probe_rows=old_probes == new_probes,
    )


def run(frozen, pair_path, overlay, output, *, verify_only):
    from tools.pipeline_eval.qualification import experimental_publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    if Path(experimental_publication.__file__).resolve().parents[3] != frozen:
        raise ValueError("Import the exact frozen bundle before the installed release")
    specification = read(frozen / "spec.json")
    pair = read(pair_path)
    archive, region = (Path(p) for p in (pair["archive"]["root"], pair["region"]))
    original_install = lean_startup.install
    if verify_only:
        original_install()
        _, _, checks = verify(frozen, pair_path, specification, archive, region)
        return checks

    with TemporaryDirectory(dir=output.parent) as temporary, ExitStack() as stack:
        root = Path(temporary)
        checks, extension = {}, {}
        args = SimpleNamespace(
            recording=root / "missing-IQ", bulk_root=root, archive=archive, region=region,
        )

        def install():
            original_install()
            from leo.operations.tle_archive import TleArchiveReader
            from tools import algo08_position, algo08_scan

            native, region_document, verified = verify(
                frozen, pair_path, specification, archive, region,
            )
            checks.update(verified, overlay_sha256=sha256(overlay.read_bytes()).hexdigest())
            corner_support = runpy.run_path(str(overlay))["corner_support"]

            @contextmanager
            def count_support():
                with corner_support() as work:
                    yield work
                extension.update(work)

            def from_saved(recording, _root, assets, causal_archive, offer):
                if (
                    recording != args.recording or causal_archive != archive
                    or offer.document() != region_document
                ):
                    raise ValueError("Saved solve received different input authority")
                cpu, wall = process_time(), perf_counter()
                result, packet, policy = algo08_position.solve(
                    native, TleArchiveReader(archive), assets, offer,
                )
                return dict(
                    status=result["status"], reason=result.get("reason"), orbit_policy=policy,
                    solver_cpu_s=process_time() - cpu, solver_wall_s=perf_counter() - wall,
                    arms=result["arms"], owners={} if packet is None else {
                        arm: data["owner_sha256"] for arm, data in packet["arms"].items()
                    },
                    associated={} if packet is None else {
                        arm: data["associated_points"] for arm, data in packet["arms"].items()
                    },
                )

            stack.enter_context(patch.object(algo08_position, "corner_support", count_support))
            stack.enter_context(patch.object(algo08_scan, "analyze", from_saved))

        stack.enter_context(patch.object(lean_startup, "install", install))
        result = experimental_publication.run(args, specification)

    from leo.application.localization_v3_engine import _json_value

    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Causal archive changed during the saved solve")
    result.update(verification=checks, orbit_extension=extension)
    baseline = pair["runs"]["baseline"]
    result["comparison"] = dict(
        baseline_decision=baseline["receipt"]["decision"], baseline_arms=baseline["arms"],
        owners_equal=result["owners"] == baseline["owners"],
    )
    return json.loads(json.dumps(result, default=_json_value, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("pair", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overlay", type=Path, default=OVERLAY)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output path already exists: {args.output}")
    record = run(args.frozen.resolve(), args.pair, args.overlay, args.output,
                 verify_only=args.verify_only)
    with args.output.open("x") as out:
        json.dump(record, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
