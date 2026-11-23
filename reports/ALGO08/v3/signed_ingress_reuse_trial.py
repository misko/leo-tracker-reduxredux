"""Compare fresh released and compressed-buffer reuse acquisitions on one signed prefix."""

import argparse
from functools import partial
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import full_short_cold as original
from . import sparse_cold_input as cold
from .signed_ingress_reuse import AcquisitionCosts, CompressedSlots, measured_ingress


HERE = Path(__file__).resolve().parent
ORDERS = (("control", "reuse"), ("reuse", "control"))


def worker(arm, request_path, short_binary, output):
    host = original.check_machine()
    specification = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    request = json.loads(request_path.read_bytes())
    costs = AcquisitionCosts()
    pool = CompressedSlots(request["capacity"]) if arm == "reuse" else None
    frozen_function = cold.frozen_function

    def profiled(spec, source, attribute):
        function = frozen_function(spec, source, attribute)
        if (source, attribute) == ("receiver_ingress.py", "compressed_input_buffer"):
            return partial(measured_ingress, function, costs, pool)
        return function

    before = resource.getrusage(resource.RUSAGE_SELF)
    with patch.object(cold, "frozen_function", profiled):
        row = original.scope("full-short", request_path.parent / "assets", short_binary, specification, request, output)
    after = resource.getrusage(resource.RUSAGE_SELF)
    row.update(arm=arm, machine=host, work=costs.receipt(), buffers=dict(pool.counts) if pool is not None else {},
               minor_faults=after.ru_minflt-before.ru_minflt, major_faults=after.ru_majflt-before.ru_majflt)
    original.freeze(output.with_suffix(".receipt.json"), row)


def stage(root, short_binary):
    from leo.contracts.digests import canonical_digest

    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    receiver = cold.PAYLOAD / "receiver.so"
    cold.verified(receiver, spec["detector_sha256"])
    cold.verified(short_binary, original.SHORT_SHA)
    cold.verified(cold.PAYLOAD / "paired-sha256.so", spec["paired_sha256"]["sha256"])
    stock_path, = (cold.ARCHIVE / "fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(cold.verified(stock_path, cold.ARCHIVED_DETECTION_SHA))
    session = native["source"]["session_id"]
    inventory = json.loads((cold.ARCHIVE / "fast-scan-inputs" / f"{session}.json").read_bytes())
    entry = inventory["segments"][0]
    inventory_sha = canonical_digest(inventory)
    binding = json.loads(cold.verified(cold.BINDING, cold.BINDING_SHA))["case"]["recording"]["segments"][0]
    if (inventory_sha != native["source"]["input_manifest_sha256"] or
            Path(entry["path"]) / "manifest.json" != Path("/srv/bulk") / binding["path"]
            or entry["manifest_digest"] != "sha256:" + binding["sha256"]):
        raise ValueError("The private copy is outside the frozen acquisition inventory")
    assets = root / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(receiver)
    pilot = cold.RELEASE / "assets/lower.f32"
    cold.verified(pilot, original.PILOT_SHA["lower"])
    (assets / "lower.f32").symlink_to(pilot)
    begin = perf_counter_ns(), process_time_ns()
    staged, chunks, members = cold.copy_prefix(root, entry)
    transfer = dict(wall_ns=perf_counter_ns()-begin[0], cpu_ns=process_time_ns()-begin[1])
    request = root / "request.json"
    original.freeze(request, dict(entry=staged, session=session, inventory_digest=inventory_sha,
                                  capacity=max(chunk.compressed_bytes for chunk in chunks)))
    return request, chunks, members, transfer, inventory_sha


def verify(row, chunks):
    member_pins = [[name, size, digest] for chunk in chunks for name, size, digest in (
        (chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256),
        (chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256),
    )]
    audited = row["work"]
    if (row["sealed_detection_sha256"] != original.PRIOR_SHORT_DETECTION_SHA
            or audited["verified_members"] != member_pins
            or audited["decoded_members"] != [c.uncompressed_sha256 for c in chunks]
            or audited["calls"]["decoded_sha"] != cold.WINDOWS + cold.MEMBERS
            or audited["calls"]["compressed_descriptor"] != cold.MEMBERS
            or len(row["decoded_iq_hashes"]) != cold.WINDOWS
            or row["native"]["native_calls"] != {"full": 48, "short_primary": 336}
            or row["overlap"]["submitted"] != cold.MEMBERS-1):
        raise ValueError("Signed science, validation, or acquisition scope differs")


def run(parent, short_binary, output):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = original.check_machine()
    parent = parent.resolve(strict=True)
    if (Path("/srv/bulk/leo-dev") not in (parent, *parent.parents)
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "xfs"):
        raise ValueError("Use the existing private XFS staging area")
    query = load_query(cold.CACHE_LIBRARY)
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    output.mkdir(exist_ok=False)
    with TemporaryDirectory(dir=parent, prefix="leo-signed-ingress-") as folder:
        root = Path(folder)
        request, chunks, members, transfer, inventory = stage(root, short_binary)
        identities = [cold.private_identity(path, root) for path in members]
        expected = [pages(chunk.compressed_bytes, os.sysconf("SC_PAGE_SIZE")) for chunk in chunks]

        def cache():
            return [cold.cache_pages(path, root, identity, query, cold=False)
                    for path, identity in zip(members, identities, strict=True)]

        order, rows = [], []
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
            HERE.parents[2], cold.RELEASE/"src", cold.RELEASE, cold.PAYLOAD))))
        python = str(cold.RELEASE/"venv/bin/python")
        for pair, modes in enumerate(ORDERS):
            order.append(modes)
            paired = {}
            for mode in modes:
                begin_pages = cache()
                if begin_pages != expected:
                    raise ValueError("The private signed prefix was not resident before a timed arm")
                raw = root / f"{pair}-{mode}.json"
                command = [python, "-BPs", "-m", __spec__.name, "worker", mode,
                           str(request), str(short_binary), str(raw)]
                began = perf_counter_ns()
                subprocess.run(command, env=environment, check=True, timeout=30)
                external = perf_counter_ns()-began
                row = json.loads(raw.with_suffix(".receipt.json").read_bytes())
                verify(row, chunks)
                cold.verified(raw, original.PRIOR_SHORT_DETECTION_SHA)
                end_pages = cache()
                if end_pages != expected:
                    raise ValueError("The signed prefix's page residency changed during a measured arm")
                row.update(start_cache_pages=begin_pages, end_cache_pages=end_pages, process_wall_ns=external)
                paired[mode] = row
            rows.append(paired)
    digests = [r["decoded_iq_hashes"] for paired in rows for r in paired.values()]
    if any(hashes != digests[0] for hashes in digests):
        raise ValueError("Decoded I/Q digests differ between the verified arms")
    pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "signed-ingress-reuse-protocol.md", "signed_ingress_reuse.py", "signed_ingress_reuse_trial.py", "full_short_cold.py")}
    original.freeze(output / "acquisition.json", dict(machine=host, orders=order, pairs=rows, staged=transfer,
                    expected_pages=expected, inventory=inventory, source_sha256=pins, spec_sha256=cold.SPEC_SHA,
                    archived_stock_sha256=cold.ARCHIVED_DETECTION_SHA, runtime_sha256=cold.RUNTIME,
                    verified_chunks=[c.model_dump(mode="json") for c in chunks]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    pair = subs.add_parser("run")
    for name in ("parent", "short_binary", "output"):
        pair.add_argument(name, type=Path)
    child = subs.add_parser("worker")
    child.add_argument("arm", choices=("control", "reuse"))
    for name in ("request_path", "short_binary", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else worker)(**args)
