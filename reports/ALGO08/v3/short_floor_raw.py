"""A diagnostic substituting known receiver rows inside verified raw input traversal."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
NATIVE_SHA = "6bbbb2575df6a203dd0d183a3ad8390110fbac778504803e275b7493b8422bed"
INPUT_LABEL = "verified raw recording with archived receiver rows"


def rows_for_window(window, rows):
    a, t = window.acquisition, window.target
    visit = a["global_visit"]
    for receiver, row in zip(window.receiver_ids, rows, strict=True):
        if (row["visit_index"] != visit or row["receiver_id"] != receiver
                or row["edge"] != t["edge"] or row["channel"] != t["channel"]
                or row["actual_rf_hz"] != float(a["actual_if_center_hz"] + t["lnb_lo_hz"])
                or row["valid_start_counter"] != a["sample_start"] or row["probe_index"] != 0
                or row["probe_start_ms"] != 0 or row["payload_start_sample"] != visit * (window.sample_rate_hz // 50)):
            raise ValueError("Archived receiver row differs from the authenticated current window")
    return rows


def child(work, saved, recording, region, archive):
    from joint_publication import run

    start = process_time()
    blob = saved.read_bytes()
    if sha256(blob).hexdigest() != NATIVE_SHA:
        raise ValueError("Unexpected source of diagnostic receiver rows")
    probes = json.loads(blob)["source"]["probes"]
    load_cpu = process_time() - start
    index = calls = 0
    lookup_cpu = 0.

    @contextmanager
    def detector(method, edge, **kwargs):
        if method != "cancellation" or edge != probes[0]["edge"]:
            raise ValueError("Unexpected receiver configuration")

        def replay(window):
            nonlocal index, calls, lookup_cpu
            start = process_time()
            rows = rows_for_window(window, probes[index:index + 2])
            index += 2
            calls += 1
            lookup_cpu += process_time() - start
            return rows
        yield replay

    args = SimpleNamespace(recording=recording, region=region, archive=archive, output=work,
                           saved=None, saved_digest=None, signed_finish=True, verify_images=False)
    run(args, detector_override=detector)
    native_file, = (work / "fast-scan-automatic-work").glob("*/detections.json")
    if index != len(probes) or sha256(native_file.read_bytes()).hexdigest() != NATIVE_SHA:
        raise ValueError("Full raw traversal did not reproduce every original detection byte")
    (work / "oracle-cost.json").write_text(json.dumps(dict(calls=calls, rows=index, load_cpu_s=load_cpu,
                                                          lookup_cpu_s=lookup_cpu, native_file_sha256=NATIVE_SHA)))


def measure(work, score):
    from aperture_trial import BENCH, PAYLOAD, RELEASE, machine
    from joint_publication import artifacts
    from short_recording_floor import CASE, PAIR_SHA, bind
    from signed_0374_transfer import pairs, read, write
    from tools.pipeline_eval.qualification import cache_residency
    from leo.storage.fast_scan import FastScanStore

    system = machine()
    if system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"] or set(system["threads"].values()) != {"1"}:
        raise ValueError("Use the shared low-priority single-core Gauss lock")
    prior = read(score)
    pair, stock, saved, region, archive, _ = bind()
    signed = prior["runs"]["signed"]
    if (prior["case"] != CASE or prior["original_pair_sha256"] != PAIR_SHA or not prior["triage_pass"]
            or signed["publication_cpu_s"] >= stock["cpu_s"] / 2):
        raise ValueError("The prespecified short-case accuracy and cost screen failed")
    work.mkdir(exist_ok=False)
    lib = BENCH / "ds30-cache-residency.so"
    if sha256(lib.read_bytes()).hexdigest() != "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab":
        raise ValueError("Cache observer changed")
    recording = Path(pair["recording"])
    pins = [(Path(x["path"]), x["sha256"]) for x in pair["cache_observation"]["manifests"]]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE/"src", RELEASE))),
               MPLCONFIGDIR=str(work / "mplconfig"))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True)
    cache = cache_residency.bound_snapshot(FastScanStore(work), recording, tuple(pins), os.sysconf("SC_PAGE_SIZE"),
                                          cache_residency.load_query(lib))
    output = work / "publication"
    cpu = pairs.child_usage()
    clock = perf_counter()
    subprocess.run([python, "-BPs", str(Path(__file__).resolve()), "child", str(output), str(saved),
                    str(recording), str(region), str(archive)], env=env, timeout=180, check=True)
    wall = perf_counter() - clock
    usage = {k: v - cpu[k] for k, v in pairs.child_usage().items()}
    product = read(output / "joint-research-receipt.json")
    evidence = pairs.evidence(output, product["receipt"], started_ns=0, read_only=True)
    decoded = artifacts(output, product["receipt"])
    matches = {k: evidence[k] == signed[k] for k in ("arms", "raw_authority", "owners", "scientific_digests", "artifacts")}
    matches.update(images=json.loads(json.dumps(decoded)) == signed["evidence"],
                   terminal=product["receipt"]["terminal_sha256"] == signed["receipt"]["terminal_sha256"])
    if (not all(matches.values()) or product["input"] != INPUT_LABEL or product["route"] != signed["route"]
            or not product["solve"]["grid_complete"] or len(decoded["images"]) != 8):
        raise ValueError(f"Raw diagnostic publication changed: {matches}")
    write(work / "floor.json", dict(case=CASE, input=INPUT_LABEL, original_pair_sha256=PAIR_SHA,
         saved_score_sha256=sha256(score.read_bytes()).hexdigest(), machine=system, cache=cache,
         historical_v3=dict(cpu_s=stock["cpu_s"], elapsed_s=stock["elapsed_s"],
                            cache=pair["cache_observation"]["arms"]["candidate"]),
         source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), equality=matches,
         outer=dict(elapsed_s=wall, **usage), oracle=read(output / "oracle-cost.json"),
         publication_cpu_s=product["publication_cpu_s"], publication_elapsed_s=product["publication_elapsed_s"],
         solve=product["solve"], route=product["route"], evidence=decoded, receipt=product["receipt"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for name, fields in (("measure", ("work", "score")), ("child", ("work", "saved", "recording", "region", "archive"))):
        sub = actions.add_parser(name)
        for field in fields:
            sub.add_argument(field, type=Path)
    options = vars(parser.parse_args())
    {"measure": measure, "child": child}[options.pop("action")](**options)
