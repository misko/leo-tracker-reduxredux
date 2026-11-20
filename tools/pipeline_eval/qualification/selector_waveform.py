"""Replay the complete prepared DS26-0237 waveform with only its peak selector replaced."""

import argparse
import gzip
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants import prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import prepared_capture_waveform as prepared
from .full_v5_check import _sha

BASE = prepared.base
PREVIOUS = prepared.REPORT
REPORT = PREVIOUS.parents[1] / "receiver-deadline/selector-waveform"
WORK = Path("/srv/bulk/leo-dev/selector-waveform-20261119")
QUALIFIED = WORK.with_name("prepared-hotpath-20261119") / "select"
METHOD = "original_capture_prepared_lane_selector_full_iq"
MODULE = "tools.pipeline_eval.qualification.selector_waveform"


@contextmanager
def configured():
    with patch.multiple(BASE, IDENT=prepared.IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def freeze(work):
    from . import capture_whole_results
    from .fresh_replay_results import sealed

    destination = REPORT / "source-lock.json"
    if destination.exists():
        raise FileExistsError(destination)
    prediction = sealed(PREVIOUS, "prediction-lock.json")
    timing = sealed(PREVIOUS, "timing-lock.json")
    lock = whole_iq.read(
        whole_iq.checked(PREVIOUS / destination.name, prediction["files"][destination.name])
    )
    qualified = QUALIFIED / "input-lock.json"
    study = whole_iq.read(qualified)
    panel = QUALIFIED / "DS26-0237.json.gz"
    receipt = json.loads(gzip.decompress(panel.read_bytes()))
    case = study["cases"][prepared.IDENT]
    code = Path(prepared_hotpath_peaks.__file__)
    if (
        receipt["input_lock_sha256"] != _sha(qualified)
        or receipt["case"] != prepared.IDENT
        or study["sources"][str(code)] != _sha(code)
        or case["root"] != lock["producer"]
        or case["input_manifest"] != lock["capture"]["input_manifest_sha256"]
        or case["archive_sha256"] != lock["original"]["native"]["sha256"]
        or study["python_sha256"] != lock["python_sha256"]
        or study["libs"] != lock["libraries"]
        or [worker[0] for worker in lock["workers"]] != list(prepared.CPUS)
        or len(receipt["rows"]) != 4
        or any(len(row["clocks"]["lane"]) != study["repeats"] for row in receipt["rows"])
    ):
        raise ValueError("selector panel and authenticated complete prepared replay do not match")
    lock["sources"].update(
        {
            str(p): _sha(p)
            for p in (
                code,
                Path(__file__),
                Path(capture_whole_results.__file__),
                REPORT / "PROTOCOL.md",
            )
        }
    )
    lock["comparison"] = dict(
        prepared={
            str(PREVIOUS / name): digest
            for name, digest in prediction["files"].items()
            if name
            in (
                "audit.json",
                "cache.csv",
                "native.json.gz",
                "positions.jsonl.gz",
                "scores.csv",
                "timing.csv",
                "source-lock.json",
            )
        }
        | {
            str(PREVIOUS / name): _sha(PREVIOUS / name)
            for name in ("prediction-lock.json", "timing-lock.json")
        },
        timing_sha256=timing["files"]["timing.csv"],
        qualified={str(qualified): _sha(qualified), str(panel): _sha(panel)},
    )
    for name, digest in lock["comparison"]["prepared"].items():
        whole_iq.checked(Path(name), digest)
    work.mkdir(mode=0o755)
    for path in (work / destination.name, destination):
        save_json(path, lock)
        path.chmod(0o644)
    BASE.configure(work)


def selector(lock):
    from leo.analysis.starlink import acquisition

    source = Path(acquisition.__file__)
    if not source.is_relative_to(lock["producer"]) or str(source) not in lock["sources"]:
        raise ValueError("the installed acquisition producer must own the patched selector binding")
    return patch.object(
        acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
    )


def smoke(work):
    lock, libs = BASE.configure(work)
    policy = BASE.policy_for(lock)
    kernel = PersistentGrid(libs["prepared"])
    rows = []
    try:
        for segment, first, visit in lock["smoke"]:
            (window,) = BASE.open_span(lock, segment, first, first + 1).windows()
            if window.acquisition["global_visit"] != visit or window.iq_sha256 != lock[
                "held_sha256"
            ].get(str(visit), window.iq_sha256):
                raise ValueError("preflight visit or held IQ digest changed")
            observed = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
            with BASE.exact.refiners(libs):
                baseline = BASE.exact.stages.detector(observed, policy, kernel)
                with selector(lock):
                    current = BASE.exact.stages.detector(observed, policy, kernel)
            if current["status"] != "processed" or any(
                current[k] != baseline[k] for k in ("status", "public", "probes", "attempts")
            ):
                raise ValueError(f"prepared and selector detector paths disagree at visit {visit}")
            rows.append(
                dict(
                    visit=visit,
                    iq_sha256=window.iq_sha256,
                    prepared_cpu_ns=baseline["cpu_ns"],
                    selector_cpu_ns=current["cpu_ns"],
                    probes_sha256=BASE.recording.digest(current["probes"]),
                )
            )
            kernel.calls.clear()
    finally:
        kernel.clear_cache()
    print(
        BASE.recording.encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=rows)),
        flush=True,
    )


def raw(work, cpu):
    lock, _ = BASE.configure(work)
    with selector(lock):
        prepared.raw(work, cpu)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "raw", "run"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=0)
    args = parser.parse_args()
    with configured():
        if args.action == "freeze":
            freeze(args.work)
        elif args.action == "preflight":
            output = subprocess.run(
                BASE.command(args.work, args.cpu, "smoke"),
                stdout=subprocess.PIPE,
                check=True,
                timeout=75,
            ).stdout
            save_json(args.work / "smoke.json", json.loads(output))
            print(output.decode(), end="")
        elif args.action == "smoke":
            smoke(args.work)
        elif args.action == "raw":
            raw(args.work, args.cpu)
        else:
            BASE.run(args.work)


if __name__ == "__main__":
    main()
