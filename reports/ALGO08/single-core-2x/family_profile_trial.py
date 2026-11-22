"""Run one cold Gaussian proposal with the frozen ALGO08v3 fallback."""

import argparse
import runpy
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

SPECIFICATION = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"


def trial(pair_path, frozen, output):
    from tools.pipeline_eval.variants.experimental import lean_startup

    source = Path(__file__).resolve()
    helpers = runpy.run_path(str(source.with_name("residual_attribution_trial.py")))
    read, write = helpers["read"], helpers["write"]
    pair = read(pair_path)
    archived = pair["runs"]["candidate"]
    spec = frozen / "spec.json"
    offer, archive = Path(pair["region"]), Path(pair["archive"]["root"])
    native, = (pair_path.parent / "candidate/fast-scan-automatic-work").glob("*/detections.json")
    install = lean_startup.install
    details = {}

    with TemporaryDirectory() as tmp, ExitStack() as stack:
        def install_profile():
            install()
            from leo.analysis.localization_v3.region import SearchRegion
            from leo.contracts.digests import canonical_digest
            from tools.pipeline_eval.qualification.paired_publication import (
                archive_identity,
                verify_sources,
            )
            from tools.pipeline_eval.variants import v5_core

            expected = read(spec)
            if (canonical_digest(expected) != SPECIFICATION
                    or pair["candidate_specification_digest"] != SPECIFICATION
                    or archive_identity(archive) != pair["archive"]
                    or read(offer) != archived["receipt"]["region"]):
                raise ValueError("Expected the unchanged causal ALGO08v3 comparison inputs")
            verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate",
                           expected["sources"])
            helpers["saved_native"](pair_path, "candidate", archived)
            variant = source.parents[3] / "tools/pipeline_eval/variants/algo08_family_profile.py"
            propose = runpy.run_path(str(variant))["propose"]
            stock = v5_core.infer

            def infer(prepared, region: SearchRegion, *args, **kwargs):
                cpu, wall = process_time(), perf_counter()
                proposal = propose(prepared, region)
                details["proposal_cpu_s"] = process_time() - cpu
                details["proposal_wall_s"] = perf_counter() - wall
                details["proposal"] = proposal
                if not proposal["fallback"]:
                    return dict(status="ok", reason=None, arms=proposal["arms"])
                cpu, wall = process_time(), perf_counter()
                result = stock(prepared, region, *args, **kwargs)
                details["fallback_cpu_s"] = process_time() - cpu
                details["fallback_wall_s"] = perf_counter() - wall
                return result

            stack.enter_context(patch.object(v5_core, "infer", infer))

        work = Path(tmp) / "saved-solve.json"
        stack.enter_context(patch.object(lean_startup, "install", install_profile))
        helpers["worker"](native, spec, archive, offer, work, include_evidence=True)
        result = read(work)
    if details["proposal"]["fallback"] and (
        result["arms"] != archived["arms"] or result["owners"] != archived["owners"]
    ):
        raise ValueError("Full fallback changed the archived decision evidence")
    result.pop("evidence", None)
    write(output, dict(result=result, audit=details, archived_arms=archived["arms"],
                       specification=SPECIFICATION, session=archived["receipt"]["session_id"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pair_path", "frozen", "output"):
        parser.add_argument(name, type=Path)
    trial(**vars(parser.parse_args()))
