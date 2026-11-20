"""Replay the full original detector with independently verified persistent FFT workspaces."""

import argparse
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants.original_kernel import PersistentGrid
from . import capture_whole as base
from . import original_kernel_trial as qualification
from .full_v5_check import BULK, _sha
from .scheduled_capture_waveform import metadata

IDENT = "DS26-0237"
PREVIOUS = base.REPORT
REPORT = PREVIOUS.parents[1] / "original-support/prepared-waveform"
WORK = Path("/var/tmp/leo-prepared-capture-waveform-20261119")
CPUS = tuple(range(8))
METHOD = "original_capture_prepared_full_iq"
MODULE = "tools.pipeline_eval.qualification.prepared_capture_waveform"
TRACE = "prepared-grid-v1: "


def freeze(work, cpus):
    from .fresh_replay_results import sealed

    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("the complete prepared waveform plan is already sealed")
    case, original = whole_iq.binding(IDENT)
    previous = sealed(base.exact.REPORT, "qualification-lock.json")
    known = whole_iq.read(
        whole_iq.checked(
            base.exact.REPORT / "source-lock.json", previous["files"]["source-lock.json"]
        )
    )
    newer = sealed(qualification.REPORT, "qualification-lock.json")
    pinned = whole_iq.read(
        whole_iq.checked(
            qualification.REPORT / "source-lock.json", newer["files"]["source-lock.json"]
        )
    )
    old, current = known["cases"][IDENT], pinned["cases"][IDENT]
    capture = base.capture_release.read_capture(case)
    if (
        (capture["edge"], capture["input_manifest_sha256"], case["native"]["sha256"])
        != (current["edge"], current["input_manifest"], current["archive_sha256"])
        or current["edge"] != "lower"
        or old["root"]["producer"] != current["root"]
    ):
        raise ValueError("fresh release, archived factors and prior exact capture lineage disagree")
    libraries = pinned["libs"]
    for k in ("batched32", "cfo", "fused"):
        if known["libraries"][k] != libraries[k]:
            raise ValueError("earlier or prepared refinement closure changed")
    if libraries["prepared"]["sha256"] != newer["files"]["original_kernel.so"]:
        raise ValueError("actual cache binary was not independently qualified")
    for entry in libraries.values():
        whole_iq.checked(Path(entry["path"]), entry["sha256"])
    before = whole_iq.read(PREVIOUS / "source-lock.json")
    capture.update(case={k: case[k] for k in ("id", "run_id", "session_id")})
    archive = whole_iq.read(
        whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    )
    invalid = frozenset(p["visit"] for p in archive["provenance"]["excluded_windows"])
    sequence, chunks = metadata(case)
    if len(sequence) != 6768 or len(invalid) != 2:
        raise ValueError("scheduled scope differs from the observed 6,766 valid capture visits")
    held = {r["visit"]: r for r in current["rows"] if r["kind"] == "new"}
    old_visits = set(old["root"]["visits"]) | {r["visit"] for r in current["rows"]}
    unseen = min(
        set(range(len(sequence))) - invalid - old_visits,
        key=lambda v: base.recording.digest([IDENT, "whole-prepared-q1", v]),
    )
    smoke = []
    for visit in (*sorted(held), unseen):
        segment, _, _, offset = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke.append((segment, visit - offset, visit))
    sources = known["sources"] | old["root"]["sources"] | pinned["sources"] | current["sources"]
    sources.update(
        {str(p): _sha(p) for p in (Path(__file__), Path(base.__file__), REPORT / "PROTOCOL.md")}
    )
    lock = dict(
        id=IDENT,
        capture=capture,
        recording=case["recording"],
        libraries=libraries,
        original=dict(
            native=case["native"],
            request=case["request"],
            catalog=case["catalog"],
            tile=case["regions"][0],
            causal_snapshots=original["causal_snapshots"],
        ),
        producer=current["root"],
        python=old["python"],
        python_sha256=pinned["python_sha256"],
        sources=sources,
        raw_limit_s=720,
        position_limit_s=180,
        receiver=before["receiver"],
        receiver_files=before["receiver_files"],
        memory_max=whole_iq.MEMORY,
        smoke=smoke,
        held_sha256={str(v): row["iq_sha256"] for v, row in held.items()},
        workers=base.partition(chunks, invalid, cpus),
        prepared_receipt_sha256=_sha(qualification.REPORT / "qualification-lock.json"),
        previous_receipt_sha256=_sha(base.exact.REPORT / "qualification-lock.json"),
    )
    work.mkdir(mode=0o755)
    for p in (work / "source-lock.json", REPORT / "source-lock.json"):
        save_json(p, lock)
        p.chmod(0o644)
    print(
        "Full prepared CPU assignments",
        [(c, n) for c, n, _ in lock["workers"]],
        "smoke",
        smoke,
        flush=True,
    )


def smoke(work):
    lock, libs = base.configure(work)
    policy = base.policy_for(lock)
    out = []
    kernel = PersistentGrid(libs["prepared"])
    try:
        for segment, first, visit in lock["smoke"]:
            (window,) = base.open_span(lock, segment, first, first + 1).windows()
            if window.acquisition["global_visit"] != visit or window.iq_sha256 != lock[
                "held_sha256"
            ].get(str(visit), window.iq_sha256):
                raise ValueError("preflight sequence or prior held IQ provenance changed")
            observed = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
            original, parent = (
                base.exact.trial(observed, policy, mode, libs) for mode in ("installed", "combined")
            )
            with base.exact.refiners(libs):
                prepared = base.exact.stages.detector(observed, policy, kernel)
            for control in (original, parent):
                if prepared["status"] != "processed" or any(
                    prepared[k] != control[k] for k in ("public", "probes", "attempts")
                ):
                    raise ValueError(
                        f"the three whole acquisition paths disagree on launch visit {visit}"
                    )
            out.append(
                dict(
                    visit=visit,
                    iq_sha256=window.iq_sha256,
                    installed_cpu_ns=original["cpu_ns"],
                    parent_cpu_ns=parent["cpu_ns"],
                    prepared_cpu_ns=prepared["cpu_ns"],
                    probes_sha256=base.recording.digest(prepared["probes"]),
                )
            )
            kernel.calls.clear()
    finally:
        kernel.clear_cache()
    print(
        base.recording.encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=out)),
        flush=True,
    )


class VisitGridRecords(list):
    """Record grid costs immediately before the existing replay clears each visit's scope."""

    def __init__(self):
        super().__init__()
        self.ordinal = 0

    def clear(self):
        record = dict(
            ordinal=self.ordinal,
            calls=len(self),
            cache_hits=sum(r["filter_ffts"] == 0 for r in self),
            cold_builds=sum(r["filter_ffts"] > 0 for r in self),
            filter_ffts=sum(r["filter_ffts"] for r in self),
            input_ffts=sum(r["input_ffts"] for r in self),
            inverse_ffts=sum(r["inverse_ffts"] for r in self),
            spans=sum(r["epochs"] * r["cfo_lanes"] for r in self),
            coarse_cpu_ns=sum(r["config_cpu_ns"] + r["native_cpu_ns"] for r in self),
            peak_workspace=max((r["buffer_bytes"] for r in self), default=0),
        )
        print(TRACE + base.recording.encoded(record), file=sys.stderr, flush=True)
        self.ordinal += 1
        super().clear()


def raw(work, cpu):
    _, libs = base.configure(work)
    kernel = PersistentGrid(libs["prepared"])
    kernel.calls = VisitGridRecords()

    def prepared(previous_library):
        if previous_library != libs["batched32"]:
            raise ValueError("unexpected original predecessor before persistent replacement")
        return kernel

    try:
        with patch.object(base.exact.capture_fft, "FullGrid", prepared):
            base.raw(work, cpu)
    finally:
        kernel.clear_cache()


@contextmanager
def configured():
    with patch.multiple(base, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "raw", "run"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=0)
    parser.add_argument("--cpus", type=int, nargs="+", default=CPUS)
    args = parser.parse_args()
    with configured():
        if args.action == "freeze":
            freeze(args.work, args.cpus)
        elif args.action == "preflight":
            p = subprocess.run(
                base.command(args.work, args.cpu, "smoke"),
                stdout=subprocess.PIPE,
                check=True,
                timeout=75,
            )
            save_json(args.work / "smoke.json", json.loads(p.stdout))
            print(p.stdout.decode(), end="")
        elif args.action == "smoke":
            smoke(args.work)
        elif args.action == "raw":
            raw(args.work, args.cpu)
        else:
            base.run(args.work)


if __name__ == "__main__":
    main()
