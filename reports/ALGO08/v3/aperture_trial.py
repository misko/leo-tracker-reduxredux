"""Run a masked archived packet through the installed ALGO08v3 solver."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import runpy
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from incremental_layout_trial import ARMS, BASELINE, FROZEN, read


RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = BASELINE.parent / "payload"
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
DENSE = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0008-pair/pair.json")
CASES = ("DS30-0008", "north-containing", "north-far", "south-containing", "south-far")
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def write(path, result):
    from leo.application.localization_v3_engine import _json_value

    with path.open("x") as stream:
        json.dump(result, stream, default=_json_value, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def configuration():
    launcher = runpy.run_path(str(BASELINE))
    specification = launcher["checked_spec"](PAYLOAD, FROZEN)
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    if Path(publication.__file__).resolve() != PAYLOAD / "tools/pipeline_eval/qualification/experimental_publication.py":
        raise ValueError("Load the pinned ALGO08v3 tooling first")
    lean_startup.install()
    specification["startup"] = "stock"
    return publication, specification


def archive_identity(path):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    root = path.resolve(strict=True)
    snapshots = {ref.path.name: ref.sha256 for ref in TleArchiveReader(root).list_snapshots("space-track")}
    return dict(root=str(root), snapshots_sha256=canonical_digest(snapshots))


def inputs(case):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    dense = case == "DS30-0008"
    site = case.split("-")[0]
    pair_path = DENSE if dense else BENCH / f"exact-curved-lookahead-{site}-inside/pair.json"
    pair = read(pair_path)
    method = "baseline" if dense else "candidate"
    archived = pair["runs"][method]
    receipt = archived["receipt"]
    spec = (archived["build"]["frozen_specification"] if dense else pair["candidate_specification_digest"])
    if spec != "sha256:" + FROZEN:
        raise ValueError("Expected an existing v3 publication")
    root = pair_path.parent / method / "fast-scan-automatic-work"
    terminal = read(root / receipt["run_id"] / "terminal.json")
    native_path, = root.glob("*/detections.json")
    native = read(native_path)
    native_digest = canonical_digest(native)
    archive = Path(pair["archive"]["root"])
    offer = receipt["region"]
    original_offer = Path(pair["region_file"] if dense else pair["region"])
    if (native_digest != terminal["native_sha256"] or canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["region"] != Algo08Region.parse(read(original_offer)).document()
            or terminal["region"] != offer or terminal["session_id"] != receipt["session_id"]
            or native["source"]["session_id"] != receipt["session_id"]
            or native["source"]["raw_recording_authority_digest"] != archived["raw_authority"]
            or archive_identity(archive) != pair["archive"]):
        raise ValueError("Archived detector, terminal, offer or archive changed")
    expected = dict(arms=archived["arms"], owners=archived["owners"], reason=archived["reason"],
                    status="ok" if receipt["decision"] == "complete" else "withheld",
                    orbit_policy=terminal["orbit_policy"], science=archived["scientific_digests"])
    offer_pin = sha256(original_offer.read_bytes()).hexdigest()
    if case.endswith("-far"):
        off_path = BENCH / f"exact-curved-lookahead-{site}-offers.json"
        far = read(off_path)
        if (far["specification"] != spec or far["archive"] != pair["archive"]
                or far["native_sha256"] != native_digest
                or far["pair_sha256"] != sha256(pair_path.read_bytes()).hexdigest()):
            raise ValueError("Displaced offer does not use this receiver packet and archive")
        expected = far["results"][case]
        offer = Algo08Region.parse(expected["offer"]).document()
        offer_pin = sha256(off_path.read_bytes()).hexdigest()
    identity = dict(
        case=case, specification=spec, pair_sha256=sha256(pair_path.read_bytes()).hexdigest(),
        detector_sha256=native["provenance"]["detector_sha256"], native_sha256=native_digest,
        raw_authority=native["source"]["raw_recording_authority_digest"],
        archive=pair["archive"], offer=offer, offer_source_sha256=offer_pin,
    )
    return native, archive, offer, expected, identity


def solve(publication, specification, native, archive, offer):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan

    def analyze(_recording, _root, assets, causal_archive, region):
        cpu, wall = process_time(), perf_counter()
        decision, packet, policy = algo08_position.solve(native, TleArchiveReader(causal_archive), assets, region)
        elapsed = dict(cpu_s=process_time() - cpu, elapsed_s=perf_counter() - wall)
        result = dict(status=decision["status"], reason=decision.get("reason"), orbit_policy=policy,
                      arms=decision["arms"], **elapsed)
        if packet is not None:
            summaries = packet["arms"]
            result.update(
                owners={arm: summaries[arm]["owner_sha256"] for arm in ARMS},
                owner_rows={arm: sorted([r["receiver"], r["channel"], r["time_s"], r["measured_cfo_hz"], r["norad"]]
                                        for r in packet["rows"][arm]) for arm in ARMS},
                science={name: canonical_digest({k: v for k, v in packet[f"position_{name}"].items()
                                                if k not in ("binding", "elapsed_seconds")})
                         for name in ("path", "grid")},
                associated={arm: summaries[arm]["associated_points"] for arm in ARMS},
                families={arm: summaries[arm]["satellites"] for arm in ARMS},
                tracks={arm: summaries[arm]["tracks"] for arm in ARMS},
                input_observations=len(packet["observations"]),
                objective_replay=packet["objective_replay"],
                grid_points=packet["position_grid"]["evaluated_points"],
            )
        return result

    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        offer_path = scratch / "offer.json"
        offer_path.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "archived-detector", bulk_root=root,
                               archive=archive, region=offer_path)
        with patch.object(algo08_scan, "analyze", analyze):
            return publication.run(args, specification)


def machine():
    return dict(cpu=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
                ionice=subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip(),
                threads={key: os.environ[key] for key in THREADS})


def trial(case, mode, output, *, reselect):
    publication, specification = configuration()
    from aperture_mask import masked
    from leo.contracts.digests import canonical_digest

    native, archive, offer, expected, identity = inputs(case)
    if native["provenance"]["detector_sha256"] != "sha256:" + specification["detector_sha256"]:
        raise ValueError("Saved packet uses a different receiver")
    candidate, audit = masked(native, mode, reselect=reselect)
    _, restricted = masked(native, mode, reselect=True) if not reselect else (candidate, audit)
    started_cpu, started_wall = process_time(), perf_counter()
    try:
        result = solve(publication, specification, candidate, archive, offer)
    except (AssertionError, ValueError) as exc:
        if mode == "full" and not reselect:
            raise
        result = dict(status="failed", reason=f"{type(exc).__name__}: {exc}", arms={},
                      cpu_s=process_time() - started_cpu, elapsed_s=perf_counter() - started_wall)
    if mode == "full" and not reselect:
        for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
            if result.get(key) != expected.get(key):
                raise ValueError(f"Full solver replay changed archived {key}: {result.get(key)!r}")
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the replay")
    result.update(identity=identity, mask=audit, restricted=restricted, machine=machine(),
                  input_sha256=canonical_digest(candidate),
                  peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    write(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("mode", choices=("full", "fixed", "guarded"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--reselect", action="store_true")
    trial(**vars(parser.parse_args()))
