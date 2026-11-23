"""Compare the released decoder, native member arena, and bounded history."""

import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from unittest.mock import patch

from . import fused_block_input_trial as fused, signed_ingress_reuse_trial as saved
from . import full_short_cold as original, sparse_cold_input as cold
from .fused_window_ring import Ring, ring_windows
from .native_verified_drain import ZSTD, ZSTD_SHA


HERE = Path(__file__).resolve().parent
PRIOR_SHA = "c4da2bd7ff14fcdaeb2479343d0ef06ecea1318ca132b76f5374d0c825a09c3f"
ORDERS = (("release", "arena", "ring"), ("ring", "arena", "release"))


def build(target):
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    paired = cold.PAYLOAD / "paired-sha256.so"
    cold.verified(paired, spec["paired_sha256"]["sha256"])
    cold.verified(ZSTD, ZSTD_SHA)
    source = HERE / "fused_window_ring.c"
    command = ["cc", "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
               str(source), str(ZSTD), str(paired), "-Wl,-z,defs", f"-Wl,-rpath,{paired.parent}", "-o", str(target)]
    subprocess.run(command, check=True)
    return dict(command=command, binary_sha256=sha256(target.read_bytes()).hexdigest(),
                source_sha256=sha256(source.read_bytes()).hexdigest(), paired_sha256=spec["paired_sha256"]["sha256"],
                zstd_sha256=ZSTD_SHA)


def worker(mode, request_path, short_binary, library, pin, output):
    if mode == "ring":
        with patch.object(fused, "Native", Ring), patch.object(fused, "fused_windows", ring_windows):
            fused.worker("fused", request_path, short_binary, library, pin, output)
    else:
        fused.worker("release" if mode == "release" else "fused", request_path, short_binary, library, pin, output)


def run(short_binary, output):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = original.check_machine()
    parent = output.parent.resolve(strict=True)
    if (Path("/dev/shm") not in (parent, *parent.parents)
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "tmpfs"):
        raise ValueError("Use a fresh private tmpfs output")
    prior = json.loads(gzip.decompress(cold.verified(HERE / "measurements/fused-block-input.json.gz", PRIOR_SHA)))
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    output.mkdir(mode=0o700, exist_ok=False)
    with TemporaryDirectory(dir=output, prefix="member-") as directory:
        root = Path(directory)
        libraries = {mode: root / f"{mode}.so" for mode in ("arena", "ring")}
        recipes = {"arena": fused.build(libraries["arena"]), "ring": build(libraries["ring"])}
        if recipes["arena"]["binary_sha256"] != prior["build"]["binary_sha256"]:
            raise ValueError("Could not reproduce the original native member arena")
        with patch.object(cold, "MEMBERS", 1):
            request, (chunk,), (member,), stage, inventory = saved.stage(root, short_binary)
        if inventory != prior["inventory"] or chunk.model_dump(mode="json") != prior["member"]:
            raise ValueError("The authorized member changed")
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
                binary = "ring" if mode == "ring" else "arena"
                command = [python, "-BPs", "-m", __spec__.name, "worker", mode, str(request), str(short_binary),
                           str(libraries[binary]), recipes[binary]["binary_sha256"], str(path)]
                before = residency()
                if before != expected:
                    raise ValueError("The private payload is not fully resident")
                started = perf_counter_ns()
                subprocess.run(command, env=env, check=True, timeout=25)
                external = perf_counter_ns()-started
                after = residency()
                row = json.loads(path.with_suffix(".receipt.json").read_bytes())
                row.update(process_wall_ns=external, cache_pages_before=before, cache_pages_after=after, requested=mode)
                original.freeze(output / f"{trial}-{mode}.json", row)
                fused.validate(row, chunk, prior["arms"][0])
                if mode == "ring":
                    stats = row["fused"]
                    if (stats.get("wraps", 0) == 0 or stats.get("copied_bytes") != chunk.uncompressed_bytes
                            or stats.get("ring_bytes", chunk.uncompressed_bytes) >= chunk.uncompressed_bytes):
                        raise ValueError("Expected the bounded circular history on the archived member")
                if after != expected:
                    raise ValueError("Payload residency changed")
                cold.verified(path, row["sealed_detection_sha256"])
                row["mode"] = mode
                rows.append(row)
    pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "fused-window-ring-protocol.md", "fused_window_ring.c", "fused_window_ring.py", "fused_window_ring_trial.py",
        "fused_block_input.c", "fused_block_input.py", "fused_block_input_trial.py", "dense_zstd_backend.py")}
    original.freeze(output / "ring.json", dict(machine=host, build=recipes, orders=ORDERS, arms=rows, stage=stage,
                    filesystem="tmpfs", expected_resident_pages=expected, inventory=inventory,
                    member=chunk.model_dump(mode="json"), prior_sha256=PRIOR_SHA, source_pins=pins))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pair = sub.add_parser("run")
    pair.add_argument("short_binary", type=Path)
    pair.add_argument("output", type=Path)
    child = sub.add_parser("worker")
    child.add_argument("mode", choices=("release", "arena", "ring"))
    for name in ("request_path", "short_binary", "library"):
        child.add_argument(name, type=Path)
    child.add_argument("pin")
    child.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else worker)(**args)
