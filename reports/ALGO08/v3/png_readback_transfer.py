"""Compare original and guarded RGBA evidence on two sealed official image sets."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import median
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
sys.path[:0] = [str(path) for path in (HERE, PAYLOAD, RELEASE/"src", RELEASE, ROOT)]

NATIVE = Path("/dev/shm/leo-v3-positive-overhead-results-02/unfilter.so")
NATIVE_PIN = "fe439ce97af62706b396bc7af50924867d2512ad61aca41c744268165a3c9be4"
SOURCE_PIN = "c9a981a5379f84afa8885f8152a901c0f32b3dc4d12398a3113fb8edc1506ef1"
SOUTH_RUN = "algo08-v2-e78374a593dc3571bce95aa53d20e25c"
MODES = ("pillow", "no-copy", "native")
SCENES = ("DS30-0016", "South")
ORIGINAL_CHECKS = {
    "DS30-0016": (Path("/dev/shm/leo-v3-history-risk-0016-cairo-score01.json"),
                  "b340a594fadae0b871c42d31ac269efe2cfe0a34d26089038c739e4bb8822e39"),
    "South": (Path("/tmp/leo-v3-successor-south-score01.json"),
              "042cb5bb89f2a4cd523761a74fc4932893474377407f326d922fd6f712257aec"),
}
ORIGINAL_PRODUCTS = {
    "DS30-0016": Path("/dev/shm/leo-v3-history-risk-0016-cairo-result01/candidate"),
    "South": Path("/tmp/leo-v3-successor-south-result01/containing/routed/candidate"),
}
SOURCES = (Path(__file__).name, "png-readback-transfer-protocol.md", "pillow_rgba_evidence.py", "verified_rgba.py",
           "verified_rgba_rows.c", "joint_publication.py", "verified_png_reads.py")


def pinned_sources():
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in SOURCES}


def document(path, pin):
    from empty_bootstrap import checked

    return json.loads(checked(path, pin))


def released_images():
    from leo.contracts.fast_standard_analysis import PLOTS
    from nomination_handoff_south import staged

    results = {scene: document(staged(path), pin) for scene, (path, pin) in ORIGINAL_CHECKS.items()}
    physical, south = results.values()
    weak = physical["native"]
    sim = south["results"]["containing"]["reports"]["candidate"]
    if (not physical["qualified"] or not all(physical["checks"].values()) or not south["qualified"]
            or not south["correct_geography"]["containing"] or sim["decision"] != "fix"
            or weak["route"]["cairo_layout"].get("native_orbit_figures") != 4
            or weak["route"]["cairo_layout"].get("native_residual_figures") != 2):
        raise ValueError("Require both verified current positive figures and the six-Cairo physical path")
    answer = dict(zip(SCENES, (
        dict(run=weak["science"]["receipt"]["run_id"], images=weak["figures"]),
        dict(run=SOUTH_RUN, images=sim["figures"]),
    ), strict=True))
    for scene, plan in answer.items():
        if set(plan["images"]) != set(PLOTS):
            raise ValueError("Require eight independent official figures per scene")
        plan.update(output=str(staged(ORIGINAL_PRODUCTS[scene])), control_sha256=ORIGINAL_CHECKS[scene][1])
    return answer


def now():
    return perf_counter(), process_time()


def clock(start):
    return dict(elapsed_s=perf_counter()-start[0], cpu_s=process_time()-start[1])


def read_artifacts(store, run, ordered, decode):
    output, read, verification = {}, dict(elapsed_s=0., cpu_s=0.), dict(elapsed_s=0., cpu_s=0.)
    encoded_bytes = 0
    for name, expected in ordered:
        start = now()
        body = store.artifact(run, name, expected["sha256"])
        for key, value in clock(start).items():
            read[key] += value
        encoded_bytes += len(body)
        start = now()
        witness = decode(body, expected["sha256"])
        for key, value in clock(start).items():
            verification[key] += value
        output[name] = witness | {"size": list(witness["size"])}
    return output, read, verification, encoded_bytes


def worker(plan_path, plan_pin, scene, mode):
    start = now()
    from PIL import Image
    import numpy
    from joint_publication import figure_evidence
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    job = document(plan_path, plan_pin)
    plan = job["scenes"][scene]
    if job["sources"] != pinned_sources() or job["native_pin"] != NATIVE_PIN:
        raise ValueError("Verifier and launch plan must match the original signed source")
    common = clock(start)
    setup, audit = now(), {}
    decode = figure_evidence
    if mode == "no-copy":
        from pillow_rgba_evidence import evidence as decode
    elif mode == "native":
        from verified_rgba import LIMIT, RgbaEvidence

        # Preserve a tightened Pillow decompression-bomb policy if this port is reused.
        if Image.MAX_IMAGE_PIXELS is None or Image.MAX_IMAGE_PIXELS >= LIMIT//4:
            decode = RgbaEvidence(NATIVE, NATIVE_PIN, figure_evidence, audit)
    binding = clock(setup)
    store = FastStandardAnalysisStore(Path(plan["output"]))
    work = now()
    output, reading, verification, compressed = read_artifacts(store, plan["run"], [(name, plan["images"][name]) for name in PLOTS], decode)
    readback = clock(work)
    if output != plan["images"] or mode == "native" and (audit.get("native") != len(PLOTS) or audit["fallback"]):
        raise ValueError("Independent verifier returned different bytes or did not execute the planned native path")
    print(json.dumps(dict(scene=scene, mode=mode, common=common, binding=binding, store_reads=reading, decode_and_sha=verification,
          full_readback=readback, complete_worker=clock(start), figures=output, bytes=compressed, peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
          native=audit, pillow=Image.__version__, numpy=numpy.__version__), sort_keys=True, allow_nan=False))


def medians(records):
    rows = {}
    for name in ("binding", "store_reads", "decode_and_sha", "full_readback", "complete_worker"):
        rows[name] = {key: median(run["worker"][name][key] for run in records) for key in ("cpu_s", "elapsed_s")}
    rows["process"] = {key: median(run["process"][key] for run in records) for key in ("cpu_s", "elapsed_s")}
    rows["peak_rss_kib"] = [run["worker"]["peak_rss_kib"] for run in records]
    return rows


def run(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from nomination_handoff_south import staged
    from north_direct_multichunk import checked_lease
    from short_raw_diagnostic import measure

    checked_lease()
    machine = host()
    if root.exists() or staged(root.parent) != Path("/tmp"):
        raise ValueError("Use a fresh private tmpfs output")
    checked(staged(NATIVE), NATIVE_PIN)
    if pinned_sources()["verified_rgba_rows.c"] != SOURCE_PIN:
        raise ValueError("The reused native library has unrelated source")
    scenes = released_images()
    root.mkdir(mode=0o700)
    plan = root/"plan.json"
    write(plan, dict(scenes=scenes, sources=pinned_sources(), native_pin=NATIVE_PIN, machine=machine))
    pin = sha256(plan.read_bytes()).hexdigest()
    order = tuple((scene, mode) for scene in SCENES for mode in MODES)
    series = {scene: {mode: [] for mode in MODES} for scene in SCENES}
    env = os.environ | {"TMPDIR": str(root)}
    for pass_number, schedule in enumerate((order, order[::-1]), 1):
        for scene, mode in schedule:
            out = root/f"{pass_number}-{scene}-{mode}"
            args = [sys.executable, "-IB", str(Path(__file__)), "worker", str(plan), "--plan-sha256", pin, "--scene", scene, "--mode", mode]
            timing = measure(args, env, out)
            write(out.with_suffix(".clock.json"), timing)
            if timing["exit_code"]:
                raise ValueError(timing["stderr_tail"])
            worker_data = json.loads(out.with_suffix(".stdout").read_text())
            if worker_data["figures"] != scenes[scene]["images"]:
                raise ValueError("Each fresh process must independently reproduce actual publication bytes and pixels")
            series[scene][mode].append(dict(process=timing, worker=worker_data, command=args))
    write(root/"result.json", dict(plan_sha256=pin, plan=json.loads(plan.read_bytes()), series=series,
          medians={scene: {mode: medians(rows) for mode, rows in modes.items()} for scene, modes in series.items()},
          waveform_reads=0, new_renders=0, new_science_requests=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "worker"))
    cli.add_argument("path", type=Path)
    cli.add_argument("--plan-sha256")
    cli.add_argument("--scene", choices=SCENES)
    cli.add_argument("--mode", choices=MODES)
    args = cli.parse_args()
    if args.action == "run":
        run(args.path)
    else:
        worker(args.path, args.plan_sha256, args.scene, args.mode)
