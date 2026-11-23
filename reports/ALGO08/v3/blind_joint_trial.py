"""Measure a blind joint finish under the installed ALGO08v3 evidence and veto."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, CASES, archive_identity, configuration, inputs, machine, write
from blind_joint_route import make_route
from mixture_trial import elapsed, summarize


def publication_roles(packet):
    return {} if packet is None else {
        arm: dict(Counter(row["role"] for row in rows)) for arm, rows in packet["rows"].items()
    }


def trial(case, output, *, repair=False):
    publication, spec = configuration()
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core

    native, archive, offer, expected, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("The saved receiver packet differs from the released binary")
    attempts = []

    def analyze(_recording, _root, assets, archive_root, region):
        installed = v5_core.infer
        reader = TleArchiveReader(archive_root)

        route = make_route(installed, reader, attempts, repair=repair)

        cpu, wall = process_time(), perf_counter()
        with patch.object(v5_core, "infer", route):
            published = algo08_position.solve(native, reader, assets, region)
        charged = elapsed(cpu, wall)
        result, chosen_owners = summarize(*published)
        if attempts[-1]["decision"] == "fallback":
            control, stock_owners, stock_roles = result, chosen_owners, publication_roles(published[1])
            control_clocks = None
        else:
            cpu, wall = process_time(), perf_counter()
            baseline = algo08_position.solve(native, reader, assets, region)
            control_clocks = elapsed(cpu, wall)
            control, stock_owners = summarize(*baseline)
            stock_roles = publication_roles(baseline[1])
        for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
            if control.get(key) != expected.get(key):
                raise ValueError(f"Checked installed v3 {key} changed its archived result")
        changes = {}
        for arm in ARMS:
            before, after = stock_owners.get(arm, {}), chosen_owners.get(arm, {})
            shared = before.keys() & after.keys()
            changes[arm] = dict(shared=len(shared), lost=len(before.keys() - after.keys()),
                                new=len(after.keys() - before.keys()), changed=sum(before[k] != after[k] for k in shared))
        return dict(result=result, control=control, charged=charged, control_clocks=control_clocks,
                    attempts=attempts, published_roles=publication_roles(published[1]),
                    stock_roles=stock_roles, published_owner_changes=changes)

    with TemporaryDirectory() as work:
        scratch = Path(work)
        path = scratch / "offer.json"
        path.write_text(json.dumps(offer))
        root = scratch / "output"
        root.mkdir()
        args = SimpleNamespace(recording=scratch / "saved", bulk_root=root, archive=archive, region=path)
        with patch.object(algo08_scan, "analyze", analyze):
            data = publication.run(args, spec)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the trial")
    data.update(identity=identity, machine=machine(), repair_enabled=repair,
                driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(output, data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repair", action="store_true")
    trial(**vars(parser.parse_args(argv)))


if __name__ == "__main__":
    main()
