"""Select two new roof waveforms and replay them blindly through the public receiver."""

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from time import time

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import capture_release, raw_robust, whole_band_trial
from .full_v5_check import FROZEN, _sha

REPORT = whole_band_trial.REPORT.parent.parent / "acquisition-support/fresh-waveform"
WORK = Path("/srv/bulk/leo-dev/whole-band-BCw8KqMY/fresh-waveform")
RECEIVER = WORK.parent / "receiver-phase-release"
FAMILIES = ("DS26", "DS29")
CPUS = [14, 15]
LIMIT = 360
METHOD = "fresh_wide_four_full_iq"


def ranked_cases(rows, family, prior):
    return sorted(
        (
            row
            for row in rows
            if row["id"].startswith(family) and row.get("recording") and row["id"] not in prior
        ),
        key=lambda row: (row["recording"]["segments"][0]["sha256"], row["id"]),
    )


def source_gate(case, producer):
    code = """
import json, sys
from pathlib import Path
from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import analyze_window
from leo.storage.fast_scan import FastSegmentSource
from tools.pipeline_eval.qualification.full_v5_check import Producer, _bind_producer

case, root, digest = json.loads(sys.argv[1])
root = Path(root)
for method in (NativeShortWindow.analyze, analyze_window, FastSegmentSource.windows):
    if not Path(method.__code__.co_filename).is_relative_to(root):
        raise ValueError("raw replay imported outside the installed producer")
print(json.dumps(_bind_producer(case, Producer(root, digest), FastScanPolicyV2())))
"""
    arguments = [
        "sudo",
        "-n",
        "-u",
        "leo",
        "--",
        "env",
        f"PYTHONPATH={producer.root}:{ROOT}",
        *(f"{key}={value}" for key, value in whole_iq.recording.SINGLE_THREAD.items()),
        str(whole_iq.recording.ARCHIVE_PYTHON),
        "-B",
        "-c",
        code,
        json.dumps([case, str(producer.root), producer.input_manifest_sha256]),
    ]
    run = subprocess.run(
        arguments, cwd=ROOT, capture_output=True, text=True, check=False, timeout=20
    )
    if run.returncode:
        raise ValueError(
            run.stderr.strip().splitlines()[-1] if run.stderr else "producer gate failed"
        )
    return json.loads(run.stdout)


def select():
    frozen = whole_iq.read(FROZEN / "provenance.json")
    digest = frozen["files"]["inputs.jsonl"]
    inputs = whole_iq.checked(FROZEN / "inputs.jsonl", digest)
    rows = list(map(json.loads, inputs.read_bytes().splitlines()))
    ordinary = whole_iq.read(raw_robust.ORDINARY_RECEIPT)["recordings"]
    prior = sorted(set(ordinary) | set(whole_band_trial.SCHEDULE))
    selected, audit = {}, {}
    for family in FAMILIES:
        choices = ranked_cases(rows, family, prior)
        checked = []
        audit[family] = dict(pool=len(choices), checked=checked)
        for rank, case in enumerate(choices, 1):
            ident = case["id"]
            entry = dict(
                id=ident, rank=rank, first_manifest=case["recording"]["segments"][0]["sha256"]
            )
            checked.append(entry)
            try:
                capture = capture_release.read_capture(case)
                producer = capture_release.producer(case, capture)
                original, request = whole_iq.binding(ident)
                if original != case:
                    raise ValueError("public request and prospective input inventory differ")
                production = source_gate(
                    {key: case[key] for key in ("id", "session_id", "run_id")}, producer
                )
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                entry["reason"] = str(error)
                continue
            selected[ident] = dict(
                cpus=CPUS,
                cohort="fresh waveform",
                ordinary_sha256=None,
                capture_era_native_sha256=case["native"]["sha256"],
                request_sha256=case["request"]["sha256"],
                catalog_sha256=case["catalog"]["sha256"],
                clock_authority=capture["input_manifest_sha256"],
                capture=capture,
                producer={**asdict(producer), "root": str(producer.root)},
                source_gate=production,
                tile=case["regions"][0],
                recording=case["recording"],
                history=request["causal_snapshots"],
                track_config=request["job"]["track_config"],
            )
            entry["selected"] = True
            break
        else:
            raise ValueError(f"no eligible fresh {family} capture under the public receiver")
    return dict(cases=selected, eligibility=audit, prior=prior, frozen_inputs_sha256=digest)


def launch(work, report):
    path = report / "source-lock.json"
    if path.exists() or work.exists():
        raise FileExistsError("fresh waveform replay already locked or attempted")
    folder, digest = whole_band_trial.BINARIES["wide"]
    detector = whole_iq.checked(
        whole_band_trial.BUILD / folder / "libleo-adaptive-detector.so", digest
    )
    study = dict(
        **select(),
        detectors={"wide": {"path": str(detector), "sha256": digest}},
        receiver=str(RECEIVER),
        receiver_files=whole_iq.receiver_identity(RECEIVER),
        native_sources=whole_iq.native_sources(RECEIVER),
        memory_max=whole_iq.MEMORY,
        swap_max=0,
        limit_s=LIMIT,
        sources={
            str(p.relative_to(ROOT)): _sha(p)
            for p in (
                Path(whole_iq.__file__),
                Path(whole_iq.recording.__file__),
                Path(whole_iq.raw.__file__),
                Path(capture_release.__file__),
                Path(__file__),
                raw_robust.ORDINARY_RECEIPT,
                report / "PROTOCOL.md",
            )
        },
    )
    save_json(path, study)
    save_json(work / "launch-lock.json", {"source_sha256": _sha(path)})
    for ident in study["cases"]:
        print(f"{ident} starting full wide replay", flush=True)
        out = work / ident / "wide"
        try:
            whole_iq.evaluate(ident, detector, digest, RECEIVER, out, CPUS, LIMIT)
        except (OSError, ValueError, RuntimeError) as error:
            save_json(
                out.with_name("wide-failure.json"), dict(error=str(error), time_unix_s=time())
            )
            print(f"{ident} failed: {error}", flush=True)
        else:
            print(f"{ident} completed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("--out", type=local_output, default=REPORT)
    args = parser.parse_args()
    launch(args.work, args.out)
