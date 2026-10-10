"""One bounded continuation slice; no implicit freeze or automatic retry."""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

from retained_adapter import continue_branch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_search_entrypoint():
    folder = ROOT / "reports/2026_10_09_position_error_iter116"
    for name in ("driver", "corpus_port", "adapter"):
        existing = sys.modules.get(name)
        if existing is not None and Path(existing.__file__).resolve() != folder / (name + ".py"):
            raise ValueError("ambient source collision: " + name)
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("search116_for123", folder / "entrypoint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", choices=("native", "fixed"))
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError("single-thread environment required")
    plan = json.loads(args.protocol.read_text())
    for group in ("source_sha256", "input_sha256"):
        for name, expected in plan[group].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("source/input changed: " + name)
    entry = load_search_entrypoint()
    loader = entry.make_loader(ROOT, plan["binding"])
    backend = loader.load_case.__globals__
    core = backend["core"]
    digest = core.canonical_digest(plan)
    directory = args.output / args.branch
    destination = directory / "result.json"
    if destination.exists():
        existing = backend["read"](destination)
        if existing["protocol_sha256"] != digest:
            raise ValueError("foreign completed branch")
        print(args.branch, existing["status"], flush=True)
        return
    phase = "baseline" if args.branch == "native" else "candidate"
    slot = backend["claim_slice"](directory / "slices", phase, digest, maximum=6)
    if slot is None:
        raise ValueError("slice budget exhausted without terminal receipt")
    begun = time.monotonic()
    deadline = begun + 500
    report = dict(protocol_sha256=digest, branch=args.branch, slice=slot, fallback_available=False)
    try:
        case = loader(plan["binding"])
        from driver import case_identity

        if case_identity(case) != plan["identity"]:
            raise ValueError("reconstructed physical case changed")
        binding = dict(
            input_digest=case["identity"]["input_manifest_sha256"],
            score_signature=core.canonical_digest(
                dict(prior=core.json_value(case["prior"]), score=core.json_value(core.HARD60_SCORE))
            ),
            bank_signature=core.canonical_digest(case["bank"].numbers.tolist()),
        )
        triggers = []
        for region in plan["branches"][args.branch]:
            key = "point:" + ":".join(str(x) for x in region["point"])
            identity = dict(
                binding,
                basin=key,
                original_sha256=core.canonical_digest(region["original"]),
                local_radius_km=25.0,
            )
            triggers.append(dict(key=key, identity=identity, original=region["original"]))

        def stage(key, budget, operation):
            path = directory / "stages" / (core.canonical_digest({"key": key})[7:] + ".json")
            if path.exists():
                row = backend["read"](path)
                if row["protocol_sha256"] != digest or row["key"] != key:
                    raise ValueError("foreign stage receipt")
                return row["value"]
            claim = path.with_suffix(".claim.json")
            if claim.exists():
                raise ValueError("claimed stage without receipt; no silent retry")
            if time.monotonic() + budget >= deadline:
                raise core.RegionalSliceExpired(key)
            backend["write"](claim, dict(protocol_sha256=digest, key=key, budget_s=budget))
            started = time.monotonic()
            try:
                value = dict(result=core.json_value(operation()), reason=None)
            except (ValueError, TimeoutError, AssertionError) as error:
                value = dict(result=None, reason=f"{type(error).__name__}: {error}")
            backend["write"](
                path,
                dict(
                    protocol_sha256=digest,
                    key=key,
                    value=value,
                    elapsed_s=time.monotonic() - started,
                ),
            )
            return value

        result = continue_branch(
            case,
            triggers,
            stage,
            recover=backend["recovered_region"],
            joint=backend["run_joint_stages"],
        )
        report.update(result, status="complete", input_binding=binding)
    except core.RegionalSliceExpired as error:
        report.update(status="budget-exhausted" if slot == 6 else "pending", reason=str(error))
    except Exception as error:
        report.update(status="failed", reason=f"{type(error).__name__}: {error}")
    report["elapsed_s"] = time.monotonic() - begun
    backend["write"](directory / "slices" / f"{args.branch}-{slot:02d}.done.json", report)
    if report["status"] != "pending":
        backend["write"](destination, report)
    print(args.branch, report["status"], flush=True)


if __name__ == "__main__":
    main()
