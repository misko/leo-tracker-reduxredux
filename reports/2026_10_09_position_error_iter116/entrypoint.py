"""Explicit preflight or one search slice. No implicit preparation or auto-retry."""

import argparse
import hashlib
import importlib.util
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np
from corpus_port import BoundCorpusLoader
from driver import ClaimedWithoutReceipt, append, case_identity, read, run_slice, verify_plan

from leo.contracts.digests import canonical_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = "scan-fw-f1a32cacd910c005"
LOADER = "reports/2026_10_09_position_error_iter105/run.py"


def runtime():
    return dict(python=platform.python_version(), numpy=np.__version__)


def verify_spec(spec, repository):
    if spec.get("mode") != "preflight" or spec["binding"]["session_id"] != PILOT:
        raise ValueError("wrong preflight mode/member")
    if spec["binding"]["loader_source"] != LOADER:
        raise ValueError("unapproved corpus loader")
    for group in ("source_sha256", "input_sha256"):
        if not spec[group]:
            raise ValueError("empty preflight closure")
        for name, expected in spec[group].items():
            if hashlib.sha256((Path(repository) / name).read_bytes()).hexdigest() != expected:
                raise ValueError("preflight source/input mismatch: " + name)
    for path_field, hash_field, group in (
        ("document_path", "document_sha256", "input_sha256"),
        ("loader_source", "loader_sha256", "source_sha256"),
        ("imports_path", "imports_sha256", "input_sha256"),
    ):
        if spec[group].get(spec["binding"][path_field]) != spec["binding"][hash_field]:
            raise ValueError("preflight binding outside verified closure")
    return canonical_digest(spec)


def make_loader(repository, binding):
    """Import immutable105 under its own name, rejecting ambient module aliases."""
    root = Path(repository)
    path = (root / binding["loader_source"]).resolve()
    if (
        binding["loader_source"] != LOADER
        or hashlib.sha256(path.read_bytes()).hexdigest() != binding["loader_sha256"]
    ):
        raise ValueError("loader identity changed")
    for name in ("inventory", "overlay"):
        existing = sys.modules.get(name)
        if existing is not None and Path(existing.__file__).resolve() != path.with_name(
            name + ".py"
        ):
            raise ValueError("ambient research module collision: " + name)
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("verified_corpus105_for116", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return BoundCorpusLoader(root, module.load_case)


def preflight(spec, repository, output, *, loader_factory=make_loader, clock=time.monotonic):
    digest = verify_spec(spec, repository)
    directory = Path(output)
    claim, result = directory / "claim.json", directory / "result.json"
    if result.exists():
        row = read(result)
        if row.get("spec_sha256") != digest or row.get("status") not in ("complete", "failed"):
            raise ValueError("preflight result mismatch")
        return row
    if claim.exists():
        raise ClaimedWithoutReceipt(str(claim))
    append(
        claim,
        dict(
            spec_sha256=digest,
            session_id=PILOT,
            scope="reconstruction only; no objective or fitting",
        ),
    )
    begun = clock()
    try:
        loader = loader_factory(repository, spec["binding"])
        case = loader(spec["binding"])
        identity = case_identity(case)
        row = dict(
            status="complete",
            identity=identity,
            runtime=runtime(),
            bank_count=len(case["bank"].numbers),
            observations_count=len(case["observations"].window_ids),
        )
    except Exception as error:
        row = dict(status="failed", error=f"{type(error).__name__}: {error}", runtime=runtime())
    row.update(
        spec_sha256=digest,
        session_id=PILOT,
        elapsed_s=clock() - begun,
        cost_scope=(
            "loader import, public input preparation, orbit bank reconstruction "
            "and identity hashing; no likelihood or fit"
        ),
    )
    append(result, row)
    return row


def main(argv=None):
    if any(
        os.environ.get(name) != "1"
        for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError(
            "OPENBLAS_NUM_THREADS, OMP_NUM_THREADS and MKL_NUM_THREADS must all equal 1"
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "run"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    plan = read(args.protocol)
    if args.mode == "preflight":
        row = preflight(plan, ROOT, args.output)
    else:
        if plan.get("mode") != "search" or plan["binding"]["session_id"] != PILOT:
            raise ValueError("wrong search protocol")
        verify_plan(plan, ROOT)
        if plan.get("preflight_runtime") != runtime():
            raise ValueError("runtime differs from verified preflight")

        def loader(binding):
            return make_loader(ROOT, binding)(binding)

        row = run_slice(plan, ROOT, args.output, loader)
    print({key: row.get(key) for key in ("status", "elapsed_s", "slices", "reason", "error")})
    return 0 if row["status"] in ("complete", "pending") else 1


if __name__ == "__main__":
    raise SystemExit(main())
