"""Time two libzstd builds on the same first signed DS30-0008 member."""

import argparse
from collections import Counter
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
from .dense_zstd_backend import Backend, local_resolver, timed_decoder
from .native_verified_drain import ZSTD, ZSTD_SHA
from .signed_ingress_reuse import AcquisitionCosts


HERE = Path(__file__).resolve().parent
BUNDLED_SHA = "7eb41c8b36cd99ed6c67e39f8574e42472687a14c6038c512bb3a90b7082616d"
SYSTEM_STATIC = Path("/usr/lib/x86_64-linux-gnu/libzstd.a")
SYSTEM_STATIC_SHA = "eb4f645520aefe163b0a9e209e4efe4c1bc36b303235a7430425d0ad3cccd977"
PRIOR_SHA = "2632873af2697761fff90fa846aae2cdba8278a5d99f75eeaa302d41cb234439"
ORDERS = (("release", "bundled", "system"), ("system", "bundled", "release"))
ASM = "usingDTable_internal_fast_asm_loop"


def worker(mode, request_path, short_binary, output):
    import zstandard
    import zstandard.backend_c as cext

    host = original.check_machine()
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    cext_path = Path(cext.__file__)
    cold.verified(cext_path, BUNDLED_SHA)
    cold.verified(ZSTD, ZSTD_SHA)
    cold.verified(SYSTEM_STATIC, SYSTEM_STATIC_SHA)
    if zstandard.backend != "cext" or zstandard.ZSTD_VERSION != (1, 5, 7):
        raise ValueError("Unexpected installed Python Zstandard backend")

    backend = None
    if mode == "bundled":
        backend = Backend(local_resolver(cext_path))
    if mode == "system":
        backend = Backend.system(ZSTD)
    if backend is not None and backend.version != 10507:
        raise ValueError("Unexpected direct decoder version")

    calls, costs = Counter(), AcquisitionCosts()
    frozen_function = cold.frozen_function

    def profiled(specification, name, attribute):
        function = frozen_function(specification, name, attribute)
        if (name, attribute) == ("receiver_ingress.py", "compressed_input_buffer"):
            return partial(timed_decoder, function, costs, backend, calls)
        return function

    request = json.loads(request_path.read_bytes())
    with patch.object(cold, "frozen_function", profiled), patch.object(cold, "WINDOWS", cold.WINDOWS_PER_MEMBER):
        row = original.scope("full-short", request_path.parent / "assets", short_binary, spec, request, output)
    row.update(mode=mode, machine=host, work=costs.receipt(), bridge=dict(calls), backend_version=zstandard.ZSTD_VERSION,
               python_zstandard_version=zstandard.__version__, cext=str(cext_path), system=str(ZSTD.resolve()))
    original.freeze(output.with_suffix(".receipt.json"), row)


def verify(row, chunk, expected_windows):
    expected_members = [[chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256],
                        [chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256]]
    work = row["work"]
    if (work["verified_members"] != expected_members or work["decoded_members"] != [chunk.uncompressed_sha256]
            or row["decoded_iq_hashes"] != expected_windows or row["visits"] != cold.WINDOWS_PER_MEMBER
            or work["calls"]["zstd_read"] != cold.WINDOWS_PER_MEMBER + 1
            or work["calls"]["decoded_sha"] != cold.WINDOWS_PER_MEMBER + 1
            or row["native"]["native_calls"] != {"full": 16, "short_primary": 112} or row["overlap"]["submitted"]):
        raise ValueError("Signed member verification or detector results differ from the frozen scope")
    if row["mode"] != "release":
        counts = row["bridge"]
        if (counts.get("standard_frames") != 1 or counts.get("layout_fallbacks") or counts.get("error_fallbacks")
                or counts.get("steps", 0) < cold.WINDOWS_PER_MEMBER):
            raise ValueError("Bridge did not decode the full member")


def build_audit(cext):
    bundled = subprocess.check_output(["nm", "--defined-only", cext], text=True)
    system = subprocess.check_output(["nm", "--defined-only", str(SYSTEM_STATIC)], text=True)
    bundled_bmi2 = sorted({s.split()[-1] for s in bundled.splitlines() if "HUF_decompress" in s and "bmi2" in s})
    system_asm = sorted({s.split()[-1] for s in system.splitlines() if ASM in s})
    if ASM in bundled or not bundled_bmi2 or not system_asm:
        raise ValueError("The frozen Huffman assembly build distinction changed")
    return dict(bundled_bmi2=bundled_bmi2, system_static_huf_asm=system_asm,
                system_package=subprocess.check_output(["dpkg-query", "-W", "libzstd1", "libzstd-dev"], text=True))


def run(parent, short_binary, output):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = original.check_machine()
    parent = parent.resolve(strict=True)
    if (Path("/srv/bulk/leo-dev") not in (parent, *parent.parents)
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "xfs"):
        raise ValueError("Use private XFS research staging")
    prior = json.loads(gzip.decompress(cold.verified(HERE / "measurements/dense-ingress-attribution.json.gz", PRIOR_SHA)))
    expected_windows = prior["arms"][0]["decoded_iq_hashes"][:cold.WINDOWS_PER_MEMBER]
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    output.mkdir(exist_ok=False)
    with TemporaryDirectory(dir=parent, prefix="leo-dense-zstd-") as folder:
        root = Path(folder)
        with patch.object(cold, "MEMBERS", 1):
            request, (chunk,), (member,), transfer, inventory = saved.stage(root, short_binary)
        if chunk.model_dump(mode="json") != prior["verified_chunks"][0] or inventory != prior["inventory"]:
            raise ValueError("The staged member differs from the previously verified prefix")
        identity = cold.private_identity(member, root)
        expected = pages(chunk.compressed_bytes, os.sysconf("SC_PAGE_SIZE"))

        def cache_pages():
            return cold.cache_pages(member, root, identity, query, cold=False)

        env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
            HERE.parents[2], cold.RELEASE / "src", cold.RELEASE, cold.PAYLOAD))))
        python = str(cold.RELEASE / "venv/bin/python")
        rows = []
        for trial, modes in enumerate(ORDERS):
            for mode in modes:
                before = cache_pages()
                if before != expected:
                    raise ValueError("Measured arms need resident compressed pages")
                path = root / f"{trial}-{mode}.json"
                command = [python, "-BPs", "-m", __spec__.name, "worker", mode, str(request), str(short_binary), str(path)]
                began = perf_counter_ns()
                subprocess.run(command, env=env, check=True, timeout=30)
                external = perf_counter_ns() - began
                row = json.loads(path.with_suffix(".receipt.json").read_bytes())
                verify(row, chunk, expected_windows)
                cold.verified(path, row["sealed_detection_sha256"])
                after = cache_pages()
                if after != expected:
                    raise ValueError("Compressed cache residency changed")
                row.update(cache_pages_before=before, cache_pages_after=after, process_wall_ns=external)
                rows.append(row)
        if len({row["sealed_detection_sha256"] for row in rows}) != 1:
            raise ValueError("The measured signed detector packets differ")
        build = build_audit(rows[0]["cext"])
        source_names = ("dense-zstd-backend-protocol.md", "dense_zstd_backend.py", "dense_zstd_backend_trial.py",
                        "full_short_cold.py", "signed_ingress_reuse.py", "signed_ingress_reuse_trial.py")
        pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in source_names}
        original.freeze(output / "backend.json", dict(machine=host, orders=ORDERS, arms=rows, stage=transfer,
                        member=chunk.model_dump(mode="json"), inventory=inventory, original_prefix_sha256=PRIOR_SHA,
                        build=build, bundled_sha256=BUNDLED_SHA, system_sha256=ZSTD_SHA, system_static_sha256=SYSTEM_STATIC_SHA,
                        source_sha256=pins, release_sha256=cold.RUNTIME, spec_sha256=cold.SPEC_SHA))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pair = sub.add_parser("run")
    for name in ("parent", "short_binary", "output"):
        pair.add_argument(name, type=Path)
    child = sub.add_parser("worker")
    child.add_argument("mode", choices=("release", "bundled", "system"))
    for name in ("request_path", "short_binary", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else worker)(**args)
