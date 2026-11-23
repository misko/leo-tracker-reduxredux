"""Run the ALGO08v3 numerical decision from its verified detector and region."""

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, process_time, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

from incremental_layout_trial import ARMS, BASELINE, FROZEN, read


def inference_stage():
    frame = sys._getframe(1)
    while frame:
        if (frame.f_code.co_name == "infer"
                and frame.f_globals.get("__name__") == "tools.pipeline_eval.variants.v5_core"):
            return ("initial", "conservative", "family", "signed", "cavity", "evidence")[
                len(frame.f_locals["stage_s"])]
        frame = frame.f_back
    return "other"


@contextmanager
def profile_bound(owner_type):
    """Measure the C call within the original complete dispatch and fallback."""
    underlying = owner_type.__call__
    stages = defaultdict(lambda: defaultdict(Counter))

    def call(owner, *args, **kwargs):
        stage = inference_stage()
        activated = owner.counts["activated"]
        operation = owner.run
        kernel_ns = 0

        def timed(*kernel):
            nonlocal kernel_ns
            start = process_time_ns()
            status = operation(*kernel)
            kernel_ns += process_time_ns() - start
            return status

        owner.run = timed
        start = process_time_ns()
        try:
            result = underlying(owner, *args, **kwargs)
            cpu_ns = process_time_ns() - start
        finally:
            owner.run = operation
        route = "native" if owner.counts["activated"] > activated else "fallback"
        row = stages[stage][route]
        row.update(calls=1, cpu_ns=cpu_ns, kernel_ns=kernel_ns,
                   updates=result["precision_iterations"],
                   weighted_rows=len(args[0]) * result["precision_iterations"])
        return result

    with patch.object(owner_type, "__call__", call):
        yield stages


def trial(pair_path, output, library=None, offer=None, reverse=False, audit=False):
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    payload = BASELINE.parent / "payload"
    if Path(publication.__file__).resolve() != payload / "tools/pipeline_eval/qualification/experimental_publication.py":
        raise ValueError("Expected the installed ALGO08v3 publication")
    specification = runpy.run_path(str(BASELINE))["checked_spec"](payload, FROZEN)
    lean_startup.install()
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan

    repository = Path(__file__).resolve().parents[3]
    overlay = runpy.run_path(str(repository / "tools/pipeline_eval/variants/algo08_profiled_gamma.py"))
    pair = read(pair_path)
    archived = pair["runs"]["candidate"]
    receipt = archived["receipt"]
    if pair["candidate_specification_digest"] != "sha256:" + FROZEN:
        raise ValueError("Expected archived installed ALGO08v3 decision")
    archive, original_offer = Path(pair["archive"]["root"]), Path(pair["region"])
    snapshots = {ref.path.name: ref.sha256
                 for ref in TleArchiveReader(archive).list_snapshots("space-track")}
    saved = pair_path.parent / "candidate/fast-scan-automatic-work"
    terminal = read(saved / receipt["run_id"] / "terminal.json")
    native_path, = saved.glob("*/detections.json")
    native = read(native_path)
    if (canonical_digest(snapshots) != pair["archive"]["snapshots_sha256"]
            or Algo08Region.parse(read(original_offer)).document() != receipt["region"]
            or canonical_digest(terminal) != receipt["terminal_sha256"]
            or terminal["region"] != receipt["region"]
            or canonical_digest(native) != terminal["native_sha256"]
            or native["source"]["session_id"] != terminal["session_id"]
            or terminal["session_id"] != receipt["session_id"]):
        raise ValueError("Sealed saved inputs differ from their archived evidence")

    def from_saved(_recording, _root, assets, causal_archive, region):
        cpu, wall = process_time(), perf_counter()
        decision, packet, policy = algo08_position.solve(native, TleArchiveReader(causal_archive), assets, region)
        result = dict(solver_cpu_s=process_time() - cpu, solver_wall_s=perf_counter() - wall,
                      status=decision["status"], reason=decision.get("reason"), orbit_policy=policy,
                      arms=decision["arms"], metrics=decision.get("metrics"))
        if packet is not None:
            science = {name: {k: v for k, v in packet[f"position_{name}"].items()
                              if k not in ("binding", "elapsed_seconds")}
                       for name in ("path", "grid")}
            result.update(scientific_digests={name: canonical_digest(value)
                                             for name, value in science.items()},
                          owners={arm: packet["arms"][arm]["owner_sha256"] for arm in ARMS},
                          associated={arm: packet["arms"][arm]["associated_points"] for arm in ARMS},
                          objective_replay=packet["objective_replay"], evidence=science)
        return result

    specification["startup"] = "stock"
    results = {}
    modes = ("control", "profiled") if library else ("control",)
    for mode in (reversed(modes) if reverse else modes):
        with TemporaryDirectory() as scratch:
            args = SimpleNamespace(recording=Path(scratch) / "sealed-detector",
                                   bulk_root=Path(scratch), archive=archive, region=offer or original_offer)
            binding = (overlay["profiled_gamma"](algo08_position, library)
                       if mode == "profiled" else nullcontext({}))
            cpu, wall = process_time(), perf_counter()
            profile = profile_bound(algo08_position.NativeBound) if audit else nullcontext({})
            with profile as bound_cost, patch.object(algo08_scan, "analyze", from_saved), binding as counts:
                try:
                    result = publication.run(args, specification)
                except (ValueError, AssertionError) as error:
                    result = dict(status="exception", reason=str(error), error_type=type(error).__name__,
                                  solver_cpu_s=process_time() - cpu, solver_wall_s=perf_counter() - wall)
            results[mode] = dict(result, profiled_gamma=dict(counts), bound_cost=dict(bound_cost))
    control = results["control"]
    if offer is None and any(control.get(key) != archived[key]
                             for key in ("arms", "owners", "scientific_digests", "reason")):
        raise ValueError("Control did not reproduce archived installed ALGO08v3 evidence")
    if offer is None and control["orbit_policy"] != terminal["orbit_policy"]:
        raise ValueError("Control changed its archived orbit policy")
    result = dict(runs=results, order=list(results), specification="sha256:" + FROZEN,
                  pair=str(pair_path), pair_sha256=hashlib.sha256(pair_path.read_bytes()).hexdigest(),
                  native_sha256=terminal["native_sha256"],
                  region=Algo08Region.parse(read(offer or original_offer)).document(), archive=pair["archive"])
    with output.open("x") as stream:
        json.dump(result, stream, default=_json_value, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair_path", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--offer", type=Path)
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    trial(**vars(args))
