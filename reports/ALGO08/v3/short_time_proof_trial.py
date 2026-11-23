"""Check time-support eligibility on saved evidence and then one complete warm original recording."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from empty_bootstrap import RELEASE, checked
from short_raw_0180 import BINDING, BINDING_SHA, BULK


PRIOR_SCORE = "95c9a45fd63ad76585e9d65c4d8596373560ecbf4b050f9340ca45374e878d13"
WEAK_NATIVE = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
HERE = Path(__file__).resolve().parent


def check_saved(prior, weak, reference):
    from leo.analysis.graph_tracklets import fit_lane
    from leo.analysis.polynomial_tracklets import TrackConfig
    from short_graph_guard import prove, time_support

    graph_file = RELEASE / "src/leo/analysis/graph_tracklets.py"
    if Path(fit_lane.__code__.co_filename).resolve() != graph_file:
        raise ValueError("Require the pinned installed graph")
    old = reference["runs"]["candidate"]
    packet, = prior.glob("candidate/fast-scan-automatic-work/*/detections.json")
    controls = {}
    for label, path, digest in (("0180", packet, old["native"].removeprefix("sha256:")), ("0016", weak, WEAK_NATIVE)):
        native = json.loads(checked(path, digest))
        proof = prove(native, RELEASE / "assets", use_time_support=True)
        if proof.get("proven") != (label == "0180") or not proof.get("release_sources"):
            raise ValueError(f"Incorrect real control for {label}")
        controls[label] = proof
    cfg = TrackConfig(**json.loads((RELEASE / "assets/tracks.json").read_bytes())["config"])
    cases = []
    for gap in (0.1, 0.8, 1., 10., 10.01):
        for count in (7, 8, 12, 20):
            times = [index * gap for index in range(count)]
            frequencies = [120 * t + t*t for t in times]
            rows = [dict(receiver=1, channel=1, actual_rf_hz=11e9, time_s=t) for t in times]
            proven = time_support(rows, cfg.min_points, cfg.min_span_s, cfg.max_gap_s)["proven"]
            tracks = len(fit_lane(times, frequencies, cfg)["tracks"])
            if proven and tracks:
                raise ValueError("False withholding on the installed graph")
            cases.append(dict(gap_s=gap, count=count, proven=proven, tracks=tracks))
    if not any(c["tracks"] for c in cases) or not any(c["proven"] for c in cases):
        raise ValueError("Missing positive or negative graph control")
    return dict(native_controls=controls, installed_comparisons=cases)


def run(root, prior, score_path, weak):
    from aperture_trial import read, write
    from dense_geographic_trial import host
    from empty_bootstrap_trial import document_bytes
    from full_short_physical import environment
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, FastScanStore, cache_residency, measure, require_warm

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Fresh tmpfs output required")
    root.mkdir()
    reference = json.loads(checked(score_path, PRIOR_SCORE))
    old = reference["runs"]["candidate"]
    stock = reference["runs"]["stock"]
    controls = check_saved(prior, weak, reference)
    target = root / "candidate"
    old_cmd = old["process"]["command"]
    recording = Path(old_cmd[old_cmd.index("--recording") + 1])
    signed = json.loads(checked(BINDING, BINDING_SHA))
    segments = tuple((BULK / arg["path"], "sha256:" + arg["sha256"]) for arg in signed["case"]["recording"]["segments"])
    if (recording != segments[0][0].parent.parent or Path(old_cmd[2]).name != "unified_short_bootstrap.py"
            or old_cmd[old_cmd.index("--output")+1] != str(prior / "candidate")):
        raise ValueError("Source recording or candidate identity differs")
    cmd = old_cmd.copy()
    cmd[2] = str(HERE / "unified_short_bootstrap.py")
    cmd[cmd.index("--output")+1] = str(target)
    cmd.append("--prove-graph-time-support")
    env = environment(root)
    env["MPLCONFIGDIR"] = str(prior / "fonts")
    env["TMPDIR"] = str(root)
    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    cache = cache_residency.bound_snapshot(FastScanStore(root), recording, segments, os.sysconf("SC_PAGE_SIZE"), query)
    require_warm(cache)
    clock = measure(cmd, env, target)
    write(root / "clock.json", dict(clock=clock, command=cmd, cache=cache, machine=machine))
    if clock["exit_code"]:
        raise ValueError(clock["stderr_tail"])
    bootstrap = read(target / "unified-short-bootstrap.json")
    if (bootstrap["route"] != "authenticated_installed_graph_ineligible" or bootstrap["native_sha256"] != old["native"]
            or bootstrap["graph_proof"] != controls["native_controls"]["0180"]
            or bootstrap["scientific_imports_after"] or bootstrap["raw_acquisitions"] != 1
            or bootstrap["verified_handoffs"] != 1 or bootstrap["receipt"]["terminal_sha256"] != old["terminal"]):
        raise ValueError("New raw publication differs from the verified saved decision")
    files = {}
    for namespace in ("fast-scan-inputs", "fast-scan-reports", "fast-scan-automatic-work", "fast-scan-standard-v2"):
        expected = document_bytes(prior / "candidate", namespace)
        if expected != document_bytes(target, namespace):
            raise ValueError(f"Standard publication changed in {namespace}")
        files.update(expected)
    write(root / "result.json", dict(machine=machine, cache=cache, clock=clock, controls=controls,
          original_comparison_sha256=PRIOR_SCORE, original=stock["process"]["clock"], ordinary=old["process"]["clock"],
          decision=bootstrap["receipt"]["decision"], native=bootstrap["native_sha256"], files=files,
          phases=bootstrap["phases"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "prior", "score_path", "weak"):
        parser.add_argument(name, type=Path)
    run(**vars(parser.parse_args()))
