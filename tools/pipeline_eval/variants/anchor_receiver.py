"""Replay selected IQ windows with an accelerated capture-era detector, then fit v5."""

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path
from statistics import median

from ..__main__ import ROOT, THREAD_ENV, encoded, write
from ..qualification.full_v5_check import BULK, PRODUCERS, _load_case, _sha
from ..qualification.recording_to_v5 import bind_request, digest, save
from . import v5_lean

BOUNDARY = (
    "16 scheduled IQ windows per recording plus the remaining archived detections to v5 position"
)
FLAGS = (
    "-std=c11",
    "-O3",
    "-march=native",
    "-fopenmp-simd",
    "-fno-math-errno",
    "-ffp-contract=fast",
    "-shared",
    "-fPIC",
)
KERNEL = Path(__file__).with_name("anchor_filter.c")


def compile_filter(library):
    subprocess.run(["cc", *FLAGS, str(KERNEL), "-lm", "-o", str(library)], check=True)


def splice_probes(document, replay):
    """Keep scheduled capture authority and replace only the candidate measurements."""
    source = document["source"]
    original_run = document["provenance"]["run_id"]
    rows = replay["rows"]
    visits = {r["visit"] for r in rows}
    if len(visits) != len(rows) or not visits or original_run != replay["producer"]["run_id"]:
        raise ValueError("duplicate visits, empty schedule or different native run")
    if not replay["archive_audit"]["archive_exclusions_equal"] or not all(
        r["equal_status"] for r in rows
    ):
        raise ValueError("partial replay changed the capture exclusions")
    replacements = {}
    for row in rows:
        for p in row["native"]:
            key = (p["visit_index"], p["receiver_id"])
            if (
                key in replacements
                or key[0] != row["visit"]
                or p["valid_start_counter"] != row["sample_start"]
            ):
                raise ValueError("replacement has an unbound visit, receiver or sample interval")
            replacements[key] = p
    complete = []
    changed = 0
    for p in source["probes"]:
        if p["visit_index"] in visits:
            fresh = replacements.pop((p["visit_index"], p["receiver_id"]), None)
            if fresh is None or {k: v for k, v in p.items() if k != "candidates"} != {
                k: v for k, v in fresh.items() if k != "candidates"
            }:
                raise ValueError("original and replacement probe geometry differs")
            changed += int(p != fresh)
            p = fresh
        complete.append(p)
    if replacements:
        raise ValueError("unexpected receivers in the partial replay")
    identity = digest(
        [
            "partial-capture-era-anchor-replay-v1",
            replay["archive_audit"]["archive_sha256"],
            replay["source_sha256"],
            replay["kernel_sha256"],
            [[r["visit"], r["iq_sha256"], r["native"]] for r in rows],
        ]
    )
    provenance = dict(document["provenance"], run_id="replay-" + identity[7:39], scope=BOUNDARY)
    composed = dict(
        document,
        source=dict(source, analysis_manifest_sha256=identity, probes=complete),
        provenance=provenance,
    )
    return composed, changed


def run(case, work_dir):
    work_dir = Path(work_dir).resolve()
    case_id = case["id"]

    def unavailable(reason):
        return dict(
            status="unavailable",
            reason=reason,
            boundary=BOUNDARY,
            metrics={},
            arms={a: {"latlon": None} for a in v5_lean.ARMS},
        )

    if case_id not in PRODUCERS or not PRODUCERS[case_id].root.is_dir():
        return unavailable("capture-era producer is unavailable for this recording")
    frozen = _load_case(case_id)
    if case["regions"] != frozen["regions"] or case.get("session_id") != frozen["session_id"]:
        return unavailable(
            "partial waveform replay requires its verified recording and original region"
        )
    archive = BULK / frozen["native"]["path"]
    if not archive.is_file():
        return unavailable("complete native recording is unavailable for the unselected visits")
    if _sha(archive) != frozen["native"]["sha256"]:
        raise ValueError("native recording changed since benchmark publication")
    library, evidence = work_dir / "anchor_filter.so", work_dir / "detector.json.gz"
    compile_filter(library)
    command = [
        "taskset",
        "-c",
        str(min(os.sched_getaffinity(0))),
        sys.executable,
        "-B",
        "-m",
        "tools.pipeline_eval.qualification.anchor_replay",
        "--case",
        case_id,
        "--library",
        str(library),
        "--out",
        str(evidence),
    ]
    env = dict(os.environ, **THREAD_ENV, PYTHONPATH=f"{PRODUCERS[case_id].root}:{ROOT}")
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    measurement = json.loads(gzip.decompress(evidence.read_bytes()))
    write(work_dir / "waveform-comparison.json", encoded(measurement))
    if (
        measurement["case"] != case_id
        or measurement["archive_audit"]["archive_sha256"] != frozen["native"]["sha256"]
    ):
        raise ValueError("detector evidence belongs to a different recording")
    native, changed = splice_probes(json.loads(archive.read_bytes()), measurement)
    path = work_dir / "composed-native.json"
    save(path, native)
    public = bind_request(frozen, path, work_dir / "bound-request.json")
    result = v5_lean.run(public, work_dir / "fit")
    result["boundary"] = BOUNDARY
    rows = measurement["rows"]
    valid = [r for r in rows if r["policy_status"] == "processed"]
    timing = result["metrics"]
    timing["native_to_v5_wall_s"] = timing.pop("candidate_s", None)
    timing.update(
        scheduled_windows=len(rows),
        valid_windows=len(valid),
        processed_recording_windows=native["provenance"]["processed_windows"],
        fresh_receivers=sum(len(r["native"]) for r in rows),
        fresh_candidates=sum(r["n_candidates"] for r in rows),
        complete_receivers_equal=all(r["equal_receivers"] for r in rows),
        changed_probe_rows=changed,
        compiler_flags=list(FLAGS),
        kernel_source_sha256=_sha(KERNEL),
        detector_wall_s={m: sum(r[m + "_wall_s"] for r in rows) for m in ("production", "native")},
        median_valid_detector_wall_s={
            m: median(r[m + "_wall_s"] for r in valid) if valid else None
            for m in ("production", "native")
        },
    )
    return result
