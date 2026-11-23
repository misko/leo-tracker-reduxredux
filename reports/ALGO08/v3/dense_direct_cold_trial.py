"""Compare cold direct and buffered reads on a single authenticated member."""

import argparse
from contextlib import contextmanager
from functools import partial
import gzip
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from unittest.mock import patch

from . import full_short_cold as original, signed_ingress_reuse_trial as saved, sparse_cold_input as cold
from .dense_direct_cold import direct_alignment, direct_or_buffered
from .signed_ingress_reuse import AcquisitionCosts, measured_ingress


HERE = Path(__file__).resolve().parent
ORDERS = (("buffered", "direct"), ("direct", "buffered"))
PRIOR_SHA = "456dde712e72899fbd7916865361d26f81ed8a90c1db0dc565d98ac18b58454b"


@contextmanager
def ingress(buffer, costs, stats, direct_member):
    bindings = buffer.__wrapped__.__globals__
    port = "read_regular_descriptor" if "read_regular_descriptor" in bindings else "read_regular"
    stock = bindings[port]

    def read(path, maximum_bytes):
        if path != direct_member:
            return stock(path, maximum_bytes)
        return direct_or_buffered(path, maximum_bytes, stock, stats)

    with patch.dict(bindings, {port: read}), measured_ingress(buffer, costs):
        yield


def worker(mode, request_path, short_binary, output):
    host = original.check_machine()
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    request = json.loads(request_path.read_bytes())
    member = Path(request["entry"]["path"]) / "iq-000000.ci16.zst" if mode == "direct" else None
    if member is not None:
        cold.private_identity(member, request_path.parent)
    stats, costs = {}, AcquisitionCosts()
    frozen_function = cold.frozen_function

    def profiled(specification, name, attribute):
        function = frozen_function(specification, name, attribute)
        if (name, attribute) == ("receiver_ingress.py", "compressed_input_buffer"):
            return partial(ingress, function, costs, stats, member)
        return function

    with patch.object(cold, "frozen_function", profiled), patch.object(cold, "WINDOWS", cold.WINDOWS_PER_MEMBER):
        row = original.scope("full-short", request_path.parent / "assets", short_binary, spec, request, output)
    row.update(mode=mode, machine=host, work=costs.receipt(), direct=stats)
    original.freeze(output.with_suffix(".receipt.json"), row)


def validate(row, chunk, original_arm):
    work = row["work"]
    if (row["sealed_detection_sha256"] != original_arm["sealed_detection_sha256"]
            or row["decoded_iq_hashes"] != original_arm["decoded_iq_hashes"]
            or row["native"]["native_calls"] != original_arm["native"]["native_calls"]
            or work["verified_members"] != original_arm["work"]["verified_members"]
            or work["decoded_members"] != original_arm["work"]["decoded_members"]
            or work["calls"]["compressed_descriptor"] != 1
            or work["calls"]["decoded_sha"] != cold.WINDOWS_PER_MEMBER+1):
        raise ValueError("Measured signed authorities or detector output differs")
    if row["mode"] == "direct":
        direct = row["direct"]
        if (direct.get("fallbacks") or direct.get("accepted_bytes") != chunk.compressed_bytes
                or direct.get("calls", 0) < 1):
            raise ValueError("No qualifying direct read was made")


def run(parent, short_binary, output):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = original.check_machine()
    parent = parent.resolve(strict=True)
    if (Path("/srv/bulk/leo-dev") not in (parent, *parent.parents)
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "xfs"):
        raise ValueError("Use private XFS research staging")
    prior = json.loads(gzip.decompress(cold.verified(HERE / "measurements/dense-zstd-backend.json.gz", PRIOR_SHA)))
    baseline = prior["arms"][0]
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    output.mkdir(exist_ok=False)
    with TemporaryDirectory(dir=parent, prefix="leo-dense-direct-") as folder:
        root = Path(folder)
        with patch.object(cold, "MEMBERS", 1):
            request, (chunk,), (member,), transfer, inventory = saved.stage(root, short_binary)
        if chunk.model_dump(mode="json") != prior["member"] or inventory != prior["inventory"]:
            raise ValueError("The copied source differs from the existing sealed decoder test")
        identity = cold.private_identity(member, root)
        expected = pages(chunk.compressed_bytes, os.sysconf("SC_PAGE_SIZE"))
        fd = os.open(member, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            align = direct_alignment(fd)
        finally:
            os.close(fd)

        def residency(*, evict):
            return cold.cache_pages(member, root, identity, query, cold=evict)

        env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
            HERE.parents[2], cold.RELEASE / "src", cold.RELEASE, cold.PAYLOAD))))
        python = str(cold.RELEASE / "venv/bin/python")
        rows = []
        for trial, modes in enumerate(ORDERS):
            for mode in modes:
                reset_started = perf_counter_ns()
                before = residency(evict=True)
                reset_ns = perf_counter_ns() - reset_started
                if before != 0:
                    raise ValueError("Cache preparation did not produce an empty private payload inode")
                path = root / f"{trial}-{mode}.json"
                command = [python, "-BPs", "-m", __spec__.name, "worker", mode, str(request), str(short_binary), str(path)]
                began = perf_counter_ns()
                subprocess.run(command, env=env, check=True, timeout=30)
                external = perf_counter_ns() - began
                after = residency(evict=False)
                row = json.loads(path.with_suffix(".receipt.json").read_bytes())
                validate(row, chunk, baseline)
                cold.verified(path, row["sealed_detection_sha256"])
                row.update(cache_pages_before=before, cache_pages_after=after, process_wall_ns=external,
                           private_cache_reset_wall_ns=reset_ns)
                rows.append(row)
                original.freeze(output / f"{trial}-{mode}.json", row)
        pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
            "dense-direct-cold-protocol.md", "dense_direct_cold.py", "dense_direct_cold_trial.py",
            "full_short_cold.py", "signed_ingress_reuse.py", "signed_ingress_reuse_trial.py", "sparse_cold_input.py")}
        original.freeze(output / "direct.json", dict(machine=host, arms=rows, orders=ORDERS, stage=transfer,
                        member=chunk.model_dump(mode="json"), inventory=inventory, expected_max_pages=expected,
                        alignment=align, prior_sha256=PRIOR_SHA, source_sha256=pins, release_sha256=cold.RUNTIME,
                        spec_sha256=cold.SPEC_SHA))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pair = sub.add_parser("run")
    for name in ("parent", "short_binary", "output"):
        pair.add_argument(name, type=Path)
    child = sub.add_parser("worker")
    child.add_argument("mode", choices=("buffered", "direct"))
    for name in ("request_path", "short_binary", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else worker)(**args)
