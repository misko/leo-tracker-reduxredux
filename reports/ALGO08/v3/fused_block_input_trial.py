"""Measure native block delivery on the pinned first DS30-0008 member."""

import argparse
from collections import Counter
from functools import partial
import gzip
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
import resource
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from unittest.mock import patch

from . import full_short_cold as original, signed_ingress_reuse_trial as saved, sparse_cold_input as cold
from .dense_zstd_backend_trial import BUNDLED_SHA
from .fused_block_input import Native, fused_windows
from .native_verified_drain import ZSTD, ZSTD_SHA
from .signed_ingress_reuse import AcquisitionCosts, measured_ingress


HERE = Path(__file__).resolve().parent
ORDERS = (("release", "fused"), ("fused", "release"))
PRIOR_SHA = "456dde712e72899fbd7916865361d26f81ed8a90c1db0dc565d98ac18b58454b"


def build(target):
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    paired = cold.PAYLOAD / "paired-sha256.so"
    cold.verified(paired, spec["paired_sha256"]["sha256"])
    cold.verified(ZSTD, ZSTD_SHA)
    source = HERE / "fused_block_input.c"
    command = ["cc", "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
               str(source), str(ZSTD), str(paired), "-Wl,-z,defs", f"-Wl,-rpath,{paired.parent}", "-o", str(target)]
    subprocess.run(command, check=True)
    return dict(command=command, binary_sha256=sha256(target.read_bytes()).hexdigest(),
                source_sha256=sha256(source.read_bytes()).hexdigest(), paired_sha256=spec["paired_sha256"]["sha256"],
                zstd_sha256=ZSTD_SHA)


def worker(mode, request_path, short_binary, decoder_binary, decoder_pin, output):
    import zstandard.backend_c as backend
    from tools.pipeline_eval.variants.experimental import paired_sha256

    host = original.check_machine()
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    cold.verified(Path(backend.__file__), BUNDLED_SHA)
    cold.verified(decoder_binary, decoder_pin)
    request = json.loads(request_path.read_bytes())
    native = Native(decoder_binary)
    counters, costs = Counter(), AcquisitionCosts()
    frozen_function = cold.frozen_function

    def profiled(specification, name, attribute):
        function = frozen_function(specification, name, attribute)
        if (name, attribute) == ("receiver_ingress.py", "compressed_input_buffer"):
            return partial(measured_ingress, function, costs)
        return function

    digests = paired_sha256.paired_decoded_hashes if mode == "release" else partial(fused_windows, native, stats=counters)
    with (patch.object(cold, "frozen_function", profiled), patch.object(cold, "WINDOWS", cold.WINDOWS_PER_MEMBER),
          patch.object(paired_sha256, "paired_decoded_hashes", digests)):
        row = original.scope("full-short", request_path.parent / "assets", short_binary, spec, request, output)
    row.update(mode=mode, machine=host, work=costs.receipt(), fused=dict(counters),
               peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    original.freeze(output.with_suffix(".receipt.json"), row)


def validate(row, chunk, reference):
    checked = row["work"]
    if (row["sealed_detection_sha256"] != reference["sealed_detection_sha256"]
            or row["decoded_iq_hashes"] != reference["decoded_iq_hashes"]
            or row["native"]["native_calls"] != reference["native"]["native_calls"]
            or checked["verified_members"] != reference["work"]["verified_members"]
            or checked["calls"].get("compressed_descriptor") != 1):
        raise ValueError("The original signed detector or reader scope changed")
    if row["mode"] == "fused":
        stats = row["fused"]
        if (stats.get("fallbacks") or stats.get("fused_frames") != 1 or stats.get("windows") != chunk.window_count
                or stats.get("decoded_member") != chunk.uncompressed_sha256 or stats.get("steps", 0) < chunk.window_count):
            raise ValueError("Native fused route or complete member validation missing")
    elif checked["decoded_members"] != [chunk.uncompressed_sha256]:
        raise ValueError("Original complete member validation missing")


def run(parent, short_binary, output):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = original.check_machine()
    parent = parent.resolve(strict=True)
    if (Path("/srv/bulk/leo-dev") not in (parent, *parent.parents)
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "xfs"):
        raise ValueError("Expected local private XFS staging")
    prior = json.loads(gzip.decompress(cold.verified(HERE / "measurements/dense-zstd-backend.json.gz", PRIOR_SHA)))
    first = prior["arms"][0]
    query = load_query(cold.CACHE_LIBRARY)
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    output.mkdir(exist_ok=False)
    with TemporaryDirectory(dir=parent, prefix="leo-fused-block-input-") as folder:
        root = Path(folder)
        library = root / "fused.so"
        recipe = build(library)
        with patch.object(cold, "MEMBERS", 1):
            request, (chunk,), (member,), transfer, inventory = saved.stage(root, short_binary)
        if chunk.model_dump(mode="json") != prior["member"] or inventory != prior["inventory"]:
            raise ValueError("Copied input differs from the pinned signed member")
        identity = cold.private_identity(member, root)
        expected = pages(chunk.compressed_bytes, os.sysconf("SC_PAGE_SIZE"))

        def residency():
            return cold.cache_pages(member, root, identity, query, cold=False)

        env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
            HERE.parents[2], cold.RELEASE / "src", cold.RELEASE, cold.PAYLOAD))))
        python = str(cold.RELEASE / "venv/bin/python")
        rows = []
        for trial, modes in enumerate(ORDERS):
            for mode in modes:
                path = root / f"{trial}-{mode}.json"
                command = [python, "-BPs", "-m", __spec__.name, "worker", mode, str(request), str(short_binary),
                           str(library), recipe["binary_sha256"], str(path)]
                before = residency()
                if before != expected:
                    raise ValueError("The signed payload is not fully resident")
                started = perf_counter_ns()
                subprocess.run(command, env=env, check=True, timeout=30)
                external = perf_counter_ns() - started
                after = residency()
                row = json.loads(path.with_suffix(".receipt.json").read_bytes())
                row.update(process_wall_ns=external, cache_pages_before=before, cache_pages_after=after)
                original.freeze(output / f"{trial}-{mode}.json", row)
                validate(row, chunk, first)
                if after != expected:
                    raise ValueError("Resident input pages changed")
                cold.verified(path, row["sealed_detection_sha256"])
                rows.append(row)
    pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "fused-block-input-protocol.md", "fused_block_input.c", "fused_block_input.py", "fused_block_input_trial.py")}
    original.freeze(output / "fused.json", dict(machine=host, orders=ORDERS, arms=rows, build=recipe, stage=transfer,
                    inventory=inventory, member=chunk.model_dump(mode="json"), prior_sha256=PRIOR_SHA, source_pins=pins,
                    runtime_sha256=cold.RUNTIME, specification_sha256=cold.SPEC_SHA))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pair = sub.add_parser("run")
    for name in ("parent", "short_binary", "output"):
        pair.add_argument(name, type=Path)
    child = sub.add_parser("worker")
    child.add_argument("mode", choices=("release", "fused"))
    for name in ("request_path", "short_binary", "decoder_binary"):
        child.add_argument(name, type=Path)
    child.add_argument("decoder_pin")
    child.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else worker)(**args)
