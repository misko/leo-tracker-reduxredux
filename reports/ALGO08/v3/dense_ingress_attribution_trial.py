"""Measure dense signed ingress attribution on one authenticated 192-visit prefix."""

import argparse
from functools import partial
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
from .dense_ingress_attribution import attributed_ingress, batch_rows, breakdown, line_rows
from .signed_ingress_reuse import AcquisitionCosts


HERE = Path(__file__).resolve().parent
ORDERS = (("line", "batch"), ("batch", "line"))


def worker(mode, request_path, short_binary, output):
    host = original.check_machine()
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, expected in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), expected)
    request = json.loads(request_path.read_bytes())
    costs = AcquisitionCosts()
    parse = line_rows if mode == "line" else batch_rows
    frozen_function = cold.frozen_function

    def profiled(specification, source, attribute):
        function = frozen_function(specification, source, attribute)
        if (source, attribute) == ("receiver_ingress.py", "compressed_input_buffer"):
            return partial(attributed_ingress, function, costs, parse)
        return function

    before = resource.getrusage(resource.RUSAGE_SELF)
    with patch.object(cold, "frozen_function", profiled):
        row = original.scope("full-short", request_path.parent / "assets", short_binary, spec, request, output)
    after = resource.getrusage(resource.RUSAGE_SELF)
    row.update(mode=mode, machine=host, work=costs.receipt(),
               minor_faults=after.ru_minflt-before.ru_minflt, major_faults=after.ru_majflt-before.ru_majflt)
    row["disjoint_cpu_ns"] = breakdown(row)
    original.freeze(output.with_suffix(".receipt.json"), row)


def run(parent, short_binary, output):
    from tools.pipeline_eval.qualification.cache_residency import load_query, pages

    host = original.check_machine()
    parent = parent.resolve(strict=True)
    if (Path("/srv/bulk/leo-dev") not in (parent, *parent.parents)
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", parent], text=True).strip() != "xfs"):
        raise ValueError("Use private XFS research staging")
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    output.mkdir(exist_ok=False)
    with TemporaryDirectory(dir=parent, prefix="leo-dense-ingress-") as folder:
        root = Path(folder)
        request, chunks, members, transfer, inventory = saved.stage(root, short_binary)
        identities = [cold.private_identity(path, root) for path in members]
        expected = [pages(chunk.compressed_bytes, os.sysconf("SC_PAGE_SIZE")) for chunk in chunks]

        def cache_pages():
            return [cold.cache_pages(path, root, identity, query, cold=False)
                    for path, identity in zip(members, identities, strict=True)]

        env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
            HERE.parents[2], cold.RELEASE / "src", cold.RELEASE, cold.PAYLOAD))))
        python = str(cold.RELEASE / "venv/bin/python")
        rows = []
        for pair, modes in enumerate(ORDERS):
            for mode in modes:
                before = cache_pages()
                if before != expected:
                    raise ValueError("Measured arms require a resident signed prefix")
                raw = root / f"{pair}-{mode}.json"
                command = [python, "-BPs", "-m", __spec__.name, "worker", mode,
                           str(request), str(short_binary), str(raw)]
                start = perf_counter_ns()
                subprocess.run(command, env=env, check=True, timeout=30)
                external_wall = perf_counter_ns() - start
                row = json.loads(raw.with_suffix(".receipt.json").read_bytes())
                saved.verify(row, chunks)
                calls = row["work"]["calls"]
                if (calls.get("index_model") != cold.MEMBERS or calls.get("zstd_read") != cold.WINDOWS + cold.MEMBERS
                        or calls.get("retune_json") != cold.WINDOWS or calls.get("support_gate") != cold.WINDOWS
                        or calls.get("detection_authority") != 1 or calls.get("iq_authority") != 1):
                    raise ValueError("Expected attribution scopes did not run")
                cold.verified(raw, original.PRIOR_SHORT_DETECTION_SHA)
                after = cache_pages()
                if after != expected:
                    raise ValueError("Signed prefix residency changed")
                row.update(start_cache_pages=before, end_cache_pages=after, process_wall_ns=external_wall)
                rows.append(row)
    if any(row["decoded_iq_hashes"] != rows[0]["decoded_iq_hashes"] for row in rows):
        raise ValueError("Per-window decoded authority differs")
    pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "dense-ingress-attribution-protocol.md", "dense_ingress_attribution.py", "dense_ingress_attribution_trial.py",
        "full_short_cold.py", "signed_ingress_reuse.py", "signed_ingress_reuse_trial.py")}
    original.freeze(output / "acquisition.json", dict(machine=host, orders=ORDERS, arms=rows, staged=transfer,
                    expected_pages=expected, inventory=inventory, source_sha256=pins, spec_sha256=cold.SPEC_SHA,
                    archived_stock_sha256=cold.ARCHIVED_DETECTION_SHA, runtime_sha256=cold.RUNTIME,
                    verified_chunks=[chunk.model_dump(mode="json") for chunk in chunks]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pair = sub.add_parser("run")
    for name in ("parent", "short_binary", "output"):
        pair.add_argument(name, type=Path)
    child = sub.add_parser("worker")
    child.add_argument("mode", choices=("line", "batch"))
    for name in ("request_path", "short_binary", "output"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else worker)(**args)
