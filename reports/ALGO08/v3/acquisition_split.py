"""Time stock stereo detector callbacks during one complete authenticated DS30-0008 acquisition."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import runpy
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ASSIGNED = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications/DS30-0008/pair.json")
ASSIGNED_SHA = "b2a0a7b73a245731ae2c21bdb3e44664a402397bb65cad6c42b66c8e2989b919"
PAIR_SHA = "0d2ec8bfd30a71142c9f88dcbcf2bcdef0d5f4188e8f6b42cb280bdaa06b6312"
QUERY_SHA = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"


def checked(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError(f"Changed frozen input: {path.name}")
    return data


def summarize(visits, probes, anchors):
    ordered = [row["visit_index"] for row in probes if row["receiver_id"] == 0]
    if [index for index, _, _ in visits] != ordered or len(set(ordered)) != len(ordered):
        raise ValueError("Per-visit timers do not cover the original stereo opportunities")
    counts = dict(anchors=0, nonanchors=0)
    for row in probes:
        counts["anchors" if row["visit_index"] in anchors else "nonanchors"] += len(row["candidates"])
    result = {}
    for name, keep in (("anchors", True), ("nonanchors", False)):
        rows = [r for r in visits if (r[0] in anchors) == keep]
        result[name] = dict(visits=len(rows), selections=counts[name], cpu_s=sum(r[1] for r in rows)/1e9,
                            wall_s=sum(r[2] for r in rows)/1e9)
    return result


def trial(out):
    from aperture_trial import archive_identity, configuration, machine, write

    assignment = json.loads(checked(ASSIGNED, ASSIGNED_SHA))
    pair = json.loads(checked(HERE / "measurements/bounds-DS30-0008-pair.json", PAIR_SHA))
    witness = pair["runs"]["baseline"]["witnesses"]
    publication, spec = configuration()
    from anchor_orbit_census import choose_anchors
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from tools import algo08_scan

    args = SimpleNamespace(recording=Path(assignment["recording"]), archive=Path(assignment["archive"]["root"]),
                           region=Path(assignment["region"]), bulk_root=out)
    checked(args.region, pair["region_file_sha256"])
    if archive_identity(args.archive) != assignment["archive"] or spec["detector_sha256"] != witness["detector_sha256"]:
        raise ValueError("Archive or installed detector differs from the sealed comparison")
    out.mkdir(exist_ok=False)
    cache_lib = Path("/tmp/leo-algo08v2-2x-bench/ds30-cache-residency.so")
    checked(cache_lib, QUERY_SHA)
    cache = runpy.run_path(str(HERE.parents[2] / "tools/pipeline_eval/qualification/cache_residency.py"))
    pins = tuple((Path(row["path"]), row["sha256"]) for row in assignment["cache_observation"]["manifests"])
    resident = cache["bound_snapshot"](FastScanStore(out), args.recording, pins, os.sysconf("SC_PAGE_SIZE"),
                                       cache["load_query"](cache_lib))
    observations = []
    clock = {}
    native = None

    class ReachedSolver(Exception):
        pass

    def intercept(native_input, *_args, **_kwargs):
        nonlocal native
        clock["handoff_cpu"], clock["handoff_wall"] = process_time_ns(), perf_counter_ns()
        native = native_input
        raise ReachedSolver

    analyze = algo08_scan.analyze

    def instrument(*analyze_args, **kwargs):
        detector = algo08_scan.detector

        @contextmanager
        def timed(*setup_args, **setup_kwargs):
            with detector(*setup_args, **setup_kwargs) as run:
                def visit(w):
                    cpu, wall = process_time_ns(), perf_counter_ns()
                    rows = run(w)
                    observations.append((w.acquisition["global_visit"], process_time_ns()-cpu, perf_counter_ns()-wall))
                    return rows
                yield visit

        with patch.object(algo08_scan, "detector", timed), patch.object(algo08_scan, "solve", intercept):
            return analyze(*analyze_args, **kwargs)

    settings = machine()
    use = resource.getrusage(resource.RUSAGE_SELF)
    with patch.object(algo08_scan, "analyze", instrument):
        start_cpu, start_wall = process_time_ns(), perf_counter_ns()
        try:
            publication.run(args, spec)
        except ReachedSolver:
            pass
        else:
            raise ValueError("Stock analysis did not reach the solver boundary")
    end = resource.getrusage(resource.RUSAGE_SELF)
    native_file, = (out / "fast-scan-automatic-work").glob("*/detections.json")
    if (canonical_digest(native) != witness["detection_sha256"]
            or sha256(native_file.read_bytes()).hexdigest() != witness["detection_file_sha256"]):
        raise ValueError("Acquisition differs from the signed full-run v3 witness")
    rows = native["source"]["probes"]
    groups = summarize(observations, rows, choose_anchors(rows))
    cpu = (clock["handoff_cpu"] - start_cpu)/1e9
    wall = (clock["handoff_wall"] - start_wall)/1e9
    receipt = dict(source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), assignment_sha256=ASSIGNED_SHA,
                   paired_publication_sha256=PAIR_SHA, cache=resident, machine=settings,
                   detection_sha256=witness["detection_sha256"], detection_file_sha256=witness["detection_file_sha256"],
                   raw_authority=native["source"]["raw_recording_authority_digest"], ordered_probes=len(rows),
                   detector_groups=groups, in_process_to_solver_cpu_s=cpu, in_process_to_solver_wall_s=wall,
                   outside_detector_cpu_s=cpu-sum(g["cpu_s"] for g in groups.values()),
                   outside_detector_wall_s=wall-sum(g["wall_s"] for g in groups.values()),
                   charged_input_blocks=end.ru_inblock-use.ru_inblock)
    write(out / "acquisition-split.json", receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    trial(**vars(parser.parse_args()))
