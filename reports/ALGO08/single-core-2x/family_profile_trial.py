"""Run one cold Gaussian proposal with the frozen ALGO08v3 fallback."""

import argparse
import runpy
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

SPECIFICATION = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"


def trial(pair_path, frozen, native, terminal_path, output, *, verify_only=False):
    from tools.pipeline_eval.variants.experimental import lean_startup

    source = Path(__file__).resolve()
    helpers = runpy.run_path(str(source.with_name("residual_attribution_trial.py")))
    read, write = helpers["read"], helpers["write"]
    pair = read(pair_path)
    archived = pair["runs"]["candidate"]
    spec = frozen / "spec.json"
    offer, archive = Path(pair["region"]), Path(pair["archive"]["root"])
    install = lean_startup.install
    details = {}

    with TemporaryDirectory() as tmp, ExitStack() as stack:
        def install_profile():
            install()
            from leo.analysis.localization_v3.region import SearchRegion
            from leo.contracts.algo08_region import Algo08Region
            from leo.contracts.digests import canonical_digest
            from leo.operations.tle_archive import TleArchiveReader
            from tools.pipeline_eval.variants import v5_core

            launcher = source.parents[1] / "v3/run"
            runpy.run_path(str(launcher))["checked_spec"](frozen)
            snapshots = {ref.path.name: ref.sha256
                         for ref in TleArchiveReader(archive).list_snapshots("space-track")}
            if (pair["candidate_specification_digest"] != SPECIFICATION
                    or canonical_digest(snapshots) != pair["archive"]["snapshots_sha256"]
                    or Algo08Region.parse(read(offer)).document() != archived["receipt"]["region"]):
                raise ValueError("Expected the unchanged causal ALGO08v3 comparison inputs")
            receipt = archived["receipt"]
            terminal = read(terminal_path)
            detections = read(native)
            if (canonical_digest(terminal) != receipt["terminal_sha256"]
                    or canonical_digest(detections) != terminal["native_sha256"]
                    or detections["source"]["session_id"] != receipt["session_id"]
                    or terminal["region"] != receipt["region"]):
                raise ValueError("Expected the detector packet sealed by the archived run")
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

        if verify_only:
            install_profile()
            return
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
    for name in ("pair_path", "frozen", "native", "terminal_path", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    trial(**vars(parser.parse_args()))
