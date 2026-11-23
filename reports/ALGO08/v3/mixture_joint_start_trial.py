"""Time the mixture handoff and the repaired control on sealed detector packets."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import CASES, archive_identity, configuration, inputs, machine, write
from blind_joint_route import make_route
from blind_joint_trial import publication_roles
from mixture_trial import elapsed, summarize


def trial(case, output, *, candidate):
    publication, specification = configuration()
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from mixture_joint_start import cold_start

    native, archive, offer, expected, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + specification["detector_sha256"]:
        raise ValueError("Saved input detector differs from installed v3")

    def analyze(_recording, _root, assets, archive_root, region):
        attempts, fallback = [], []
        reader = TleArchiveReader(archive_root)
        repaired = make_route(v5_core.infer, reader, fallback if candidate else attempts, repair=True)
        route = make_route(repaired, reader, attempts, repair=True, cold_start=cold_start) if candidate else repaired
        cpu, wall = process_time(), perf_counter()
        with patch.object(v5_core, "infer", route):
            decision, packet, policy = algo08_position.solve(native, reader, assets, region)
        charged = elapsed(cpu, wall)
        result, owners = summarize(decision, packet, policy)
        repaired_attempts = fallback if candidate else attempts
        if repaired_attempts and repaired_attempts[-1]["decision"] == "fallback":
            for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
                if result.get(key) != expected.get(key):
                    raise ValueError(f"Installed fallback changed its archived {key}")
        return dict(result=result, owners=owners, owner_roles=publication_roles(packet), charged=charged,
                    attempts=attempts, repaired_fallback_attempts=fallback)

    with TemporaryDirectory() as directory:
        root = Path(directory)
        offer_path = root / "offer.json"
        offer_path.write_text(json.dumps(offer))
        destination = root / "output"
        destination.mkdir()
        args = SimpleNamespace(recording=root / "saved", bulk_root=destination, archive=archive, region=offer_path)
        with patch.object(algo08_scan, "analyze", analyze):
            result = publication.run(args, specification)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the trial")
    source = Path(__file__).resolve().parent
    names = ("mixture_joint_start.py", "mixture_position.py", "blind_joint_finish.py",
             "blind_joint_route.py", "blind_joint_repair.py", "mixture_joint_start_trial.py")
    result.update(identity=identity, machine=machine(), candidate=candidate,
                  source_sha256={name: sha256((source / name).read_bytes()).hexdigest() for name in names})
    write(output, result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--candidate", action="store_true")
    trial(**vars(parser.parse_args()))
