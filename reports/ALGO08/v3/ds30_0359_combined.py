"""Use the same combined blind worker and a pre-existing exact tmpfs catalogue."""

import argparse
from gzip import decompress
from hashlib import sha256
import json
from pathlib import Path
import sys

from reports.ALGO08.v3 import ds30_0163_combined as combined
from reports.ALGO08.v3.ds30_0173_combined import EARLIER as CONTROL_0163, EARLIER_PIN as CONTROL_0163_PIN, pool_cases
from reports.ALGO08.v3.nomination_handoff_0419_admission import enrollment
from reports.ALGO08.v3.nomination_handoff_0419_local import launch as prepare


CASE = "DS30-0359"
RANK_HASH = "15a8987a30e129e6d4effa29923443760ef8d4384ac6ab798bdbd11e4c1d42f0"
PAIR_PIN = "49b64e6db207b56613be28d89756522c217b277b4c354f72d71b5603d1679ff4"
CONTROL_0173 = Path(__file__).with_name("measurements") / "ds30-0173-combined.json.gz"
CONTROL_0173_PIN = "e2a7eb8a10886c3de720e1ab97d7efbdfd706161b67f06aa6249417083c4c180"
DONORS = tuple(Path("/dev/shm") / name / "tle" for name in ("leo-v3-saved-0316-pair-01", "leo-v3-saved-0402-pair-01"))
INPUTS = dict(
    native_sha256="d3e6871b303bc664a06165cf5acf3aaf8da56648bfa239b8d8076b5de0a10ddf",
    inventory_sha256="8b83a568e5dfd8bc43cfd580ec042d1860ac194983f147549634ea8140021e6b",
    offer_sha256="2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236",
    terminal_sha256="sha256:ab78a4454eb5d89b4840352284fc07fe4345552e17af95ca53fe7027414b1e07",
    archive_sha256="sha256:f1b5b96b2d99eb4b42f45d156763d0fd278e74cf6e0413eb5deb58674841215f",
    frozen_specification="sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f",
    cutoff_utc_ns=1795065144724213783, issued=6774, admitted=5160, probes=10320, factors=4941,
)


def assigned():
    assignment = enrollment(ranked=6, case=CASE, ranking_hash=RANK_HASH, pair_pin=PAIR_PIN)
    return assignment | {"order": assignment["planned_order"], "archived_pair_sha256": PAIR_PIN}


def staged_archive(capture, cutoff, pin):
    from exact_named_route import resident_path
    from leo.operations.tle_archive import TleArchiveReader
    from solver_exception_0022 import selected_refs
    from visit_frame_raw_0016 import resident

    if cutoff != INPUTS["cutoff_utc_ns"] or pin != INPUTS["archive_sha256"]:
        raise ValueError("Archive does not belong to the enrolled input")
    rooms = ((resident_path(donor), TleArchiveReader(donor).list_snapshots("space-track")) for donor in DONORS)
    refs = selected_refs(rooms, capture, cutoff, pin)
    if len(refs) != 47 or sum(ref.byte_size for ref in refs) != 83_998_561:
        raise ValueError("The exact existing archive extent changed")
    resident([resident_path(ref.path) for ref in refs])
    return refs


def launch(output):
    ready = output.with_name(output.name + "-ready")
    prepare(ready, assign=assigned, execute=False, expected_inputs=INPUTS, resident_refs=staged_archive)
    combined.launch_fresh(output, job_root=ready, assign=assigned)


def reduce_pool(current):
    earlier = []
    for path, pin in ((CONTROL_0163, CONTROL_0163_PIN), (CONTROL_0173, CONTROL_0173_PIN)):
        body = decompress(path.read_bytes())
        if sha256(body).hexdigest() != pin:
            raise ValueError("An earlier sealed combined blind control changed")
        earlier.append(json.loads(body))
    return pool_cases((*earlier, current), ("DS30-0163", "DS30-0173", CASE))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("output", type=Path)
    opts = cli.parse_args()
    (launch(opts.output) if opts.action == "launch" else
     combined.score(opts.output, assign=assigned, case=CASE, pair_pin=PAIR_PIN, reduce_pool=reduce_pool))
