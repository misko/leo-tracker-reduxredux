"""Change only the prepared FFT length on a full, previously measured saved-IQ capture."""

import argparse
import gzip
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import batched_waveform as incumbent
from . import capture_whole as base
from . import prepared_capture_waveform as prepared
from . import selector_waveform
from .full_v5_check import _sha

IDENT = incumbent.IDENT
SCREENING = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREENING / "original-schedule/fft-waveform"
PANEL = SCREENING / "coarse-and-navigation/fft-length"
PANEL_SHA = "10eea2f5602dc6ebd948c378808cadc3b3b64a1b446da7ad725a6d287c19a6e4"
LIBRARY = PANEL / "build/planned-256/prepared_measured.so"
LIBRARY_SHA = "40965b750fb0e833fd211f4c069bb3eb0f190a40a0cf65963a2e5ebbe6456286"
PREDECESSOR = incumbent.REPORT
METHOD = "original_capture_fft256_complete_iq"
WORK = Path("/var/tmp/leo-fft-waveform-ds29-0519-20261120")
MODULE = "tools.pipeline_eval.qualification.fft_waveform"
CPUS = incumbent.CPUS
TRACE = incumbent.TRACE
FINE_COUNTERS = incumbent.FINE_COUNTERS


@contextmanager
def configured():
    with patch.multiple(base, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def payload(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def witness_visits(lock, held, invalid):
    chunks = sorted(span for _, _, spans in lock["workers"] for span in spans)
    kinds = {21: "capture-exclusion", 153: "negative", 169: "near-gate"}
    held_by_visit = {r["visit"]: r["input_sha256"] for r in held["rows"]}
    kinds.update(dict.fromkeys(held_by_visit, "independent-order-witness"))
    seen = {r[2] for r in lock["smoke"]} | kinds.keys() | invalid
    ranks = sorted(
        set(range(lock["archival_counts"]["scheduled"])) - seen,
        key=lambda v: base.recording.digest([IDENT, "new-fft256-launch-v1", v]),
    )[:3]
    kinds.update(dict.fromkeys(ranks, "new-sequence-hash"))
    smoke = []
    for visit in sorted(kinds):
        segment, _, _, offset = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke.append((segment, visit - offset, visit))
    return smoke, kinds, held_by_visit


def freeze(work):
    from . import capture_whole_results
    from .fresh_replay_results import sealed

    if work.exists() or (REPORT / "source-lock.json").exists():
        raise FileExistsError("preserve the one first-attempt FFT256 evidence scope")
    stage_lock = sealed(PANEL, "evidence-lock.json", PANEL_SHA)
    previous = sealed(PREDECESSOR, "prediction-lock.json")
    previous_stage = sealed(PREDECESSOR, "timing-lock.json")
    qualifications = whole_iq.read(PANEL / "qualification.json")
    held = payload(PANEL / f"{IDENT}-held.json.gz")
    lock = whole_iq.read(PREDECESSOR / "source-lock.json")
    previous_audit = whole_iq.read(PREDECESSOR / "audit.json")
    if (
        qualifications["length"] != 256
        or qualifications["planner"] != "stored-measure"
        or qualifications["candidate_sha256"] != LIBRARY_SHA
        or qualifications["full_parity"] != qualifications["radio"]
        or qualifications["compared_pairs"] != 40
        or stage_lock["files"][str(LIBRARY.relative_to(PANEL))] != LIBRARY_SHA
        or held["ident"] != IDENT
        or len(held["rows"]) != 2
        or any(not row["same_prepared"] or not row["same_installed"] for row in held["rows"])
        or previous_audit["raw"]["parity"]["classification"] != "exact"
        or previous_audit["raw"]["completed_chunks"] != 106
        or [row[0] for row in lock["workers"]] != list(CPUS)
    ):
        raise ValueError("the signed held FFT and completed 512 controls do not qualify")
    old_base = Path(base.__file__)
    # The shared launcher gained an optional unknown-count guard. All frozen
    # worker counts are concrete. Preserve both byte versions for replay.
    archived_base = (
        SCREENING / "coarse-and-navigation/coarse-waveform/source-snapshot/capture_whole.py"
    )
    whole_iq.checked(archived_base, lock["sources"][str(old_base)])
    lock["evidence_sources"][str(archived_base)] = _sha(archived_base)
    lock["sources"][str(old_base)] = _sha(old_base)
    case, request = whole_iq.binding(IDENT)
    if (
        case["recording"] != lock["recording"]
        or case["native"] != lock["original"]["native"]
        or request["causal_snapshots"] != lock["original"]["causal_snapshots"]
    ):
        raise ValueError("the causal recording differs from the prior matched full control")
    archive = whole_iq.read(
        whole_iq.checked(base.BULK / case["native"]["path"], case["native"]["sha256"])
    )
    invalid = {r["visit"] for r in archive["provenance"]["excluded_windows"]}
    smoke, kinds, held_iq = witness_visits(lock, held, invalid)
    held_iq.update(
        {
            r["visit"]: r["iq_sha256"]
            for r in whole_iq.read(PREDECESSOR / "receipts/smoke.json")["rows"]
            if r["visit"] in kinds
        }
    )
    if kinds.keys() & invalid != {21}:
        raise ValueError("the independent genuine order witnesses changed validity")
    previous_paths = (
        "source-lock.json",
        "audit.json",
        "native.json.gz",
        "positions.jsonl.gz",
        "coarse.csv",
        "fine.csv",
        "receipts/smoke.json",
    )
    paired = {name: previous["files"][name] for name in previous_paths}
    paired["timing.csv"] = previous_stage["files"]["timing.csv"]
    paired.update(
        {name: _sha(PREDECESSOR / name) for name in ("prediction-lock.json", "timing-lock.json")}
    )
    scope = (
        Path(__file__),
        Path(prepared.__file__),
        Path(incumbent.__file__),
        Path(capture_whole_results.__file__),
        REPORT / "PROTOCOL.md",
    )
    lock["sources"].update({str(path): _sha(path) for path in scope})
    provider = (
        PANEL / "evidence-lock.json",
        PANEL / "qualification.json",
        PANEL / "rank-audit.json",
        PANEL / f"{IDENT}-held.json.gz",
    )
    lock["evidence_sources"].update({str(path): _sha(path) for path in provider})
    lock["evidence_sources"].update(
        {str(PREDECESSOR / name): digest for name, digest in paired.items()}
    )
    incumbent_prepared = lock["libraries"]["prepared"]
    runtime = REPORT / "prepared-256.so"
    write(runtime, whole_iq.checked(LIBRARY, LIBRARY_SHA).read_bytes())
    runtime.chmod(0o644)
    lock["evidence_sources"][str(LIBRARY)] = LIBRARY_SHA
    lock["libraries"]["prepared"] = dict(path=str(runtime), sha256=LIBRARY_SHA)
    lock.update(
        original_prepared=incumbent_prepared,
        candidate_sha256=LIBRARY_SHA,
        candidate_qualification_sha256=PANEL_SHA,
        previous_prediction=paired,
        smoke=smoke,
        smoke_invalid=[21],
        witness_kinds=kinds,
        held_sha256=held_iq,
        archival_launch_probes={
            str(v): p for v, p in visit_pairs(archive["source"]["probes"]) if v in kinds
        },
    )
    for source_kind in ("sources", "evidence_sources"):
        for name, digest in lock[source_kind].items():
            whole_iq.checked(Path(name), digest)
    for info in lock["libraries"].values():
        whole_iq.checked(Path(info["path"]), info["sha256"])
    work.mkdir(mode=0o755)
    for out in (work / "source-lock.json", REPORT / "source-lock.json"):
        save_json(out, lock)
        out.chmod(0o644)
    copies = {}
    for path in (old_base, Path(capture_whole_results.__file__)):
        dest = REPORT / "source-snapshot" / path.name
        write(dest, path.read_bytes())
        copies[str(dest.relative_to(REPORT))] = _sha(dest)
    save_json(
        REPORT / "source-snapshot.json",
        dict(source_lock_sha256=_sha(REPORT / "source-lock.json"), files=copies),
    )
    print(
        "Matched 512/256 CPU and chunk assignments",
        [(c, n) for c, n, _ in lock["workers"]],
        "smoke",
        smoke,
        flush=True,
    )


def check_outputs(reference, candidate, valid):
    keys = ("status", "public", "probes", "attempts")
    status = "processed" if valid else "invalid_capture"
    if reference["status"] != status or candidate["status"] != status:
        raise ValueError("one of the two backends changed the original capture validity")
    return {key: encoded(reference[key]) == encoded(candidate[key]) for key in keys}


def smoke(work):
    lock, libs = base.configure(work)
    policy = base.policy_for(lock)
    pinned = lock["original_prepared"]
    old_grid = PersistentGrid(whole_iq.checked(Path(pinned["path"]), pinned["sha256"]))
    new_grid = PersistentGrid(libs["prepared"])
    fine = incumbent.batched_for(lock, libs["batch"])
    observations = []
    try:
        for i, (segment, j, visit) in enumerate(lock["smoke"]):
            (window,) = base.open_span(lock, segment, j, j + 1).windows()
            if window.acquisition["global_visit"] != visit or window.iq_sha256 != lock[
                "held_sha256"
            ].get(str(visit), window.iq_sha256):
                raise ValueError("launch check opened a different original physical visit")
            witness = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
            grids = (("prepared_512", old_grid), ("stored_256", new_grid))
            results = {}
            calls = {}
            with base.exact.refiners(libs), selector_waveform.selector(lock), fine.route():
                for name, grid in grids if not i % 2 else grids[::-1]:
                    start = fine.calls
                    results[name] = base.exact.stages.detector(witness, policy, grid)
                    calls[name] = fine.calls - start
                    grid.calls.clear()
            reference, candidate = (results[name] for name, _ in grids)
            valid = visit not in lock["smoke_invalid"]
            if (
                fine.fallbacks
                or any(bool(n) != valid for n in calls.values())
                or encoded(reference["probes"])
                != encoded(lock["archival_launch_probes"].get(str(visit), []))
            ):
                raise ValueError(
                    f"incumbent baseline or native fine route lost authority at {visit}"
                )
            parity = check_outputs(reference, candidate, valid)
            observations.append(
                dict(
                    visit=visit,
                    status=reference["status"],
                    kind=lock["witness_kinds"][str(visit)],
                    iq_sha256=window.iq_sha256,
                    same=parity,
                    fine_calls=calls,
                    cpu_ns={name: r["cpu_ns"] for name, r in results.items()},
                    wall_ns={name: r["wall_ns"] for name, r in results.items()},
                    hashes={
                        name: {key: base.recording.digest(r[key]) for key in parity}
                        for name, r in results.items()
                    },
                    changed={
                        key: {name: r[key] for name, r in results.items()}
                        for key, same in parity.items()
                        if not same
                    },
                )
            )
    finally:
        old_grid.clear_cache()
        new_grid.clear_cache()
    print(
        encoded(
            dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=observations)
        ).decode(),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "smoke", "raw", "run"))
    parser.add_argument("work", type=local_output, nargs="?", default=WORK)
    parser.add_argument("cpu", type=int, nargs="?", default=CPUS[0])
    args = parser.parse_args()
    with configured():
        if args.action == "freeze":
            freeze(args.work)
        elif args.action == "preflight":
            incumbent.previous.check_evidence(args.work)
            argv = base.service(
                f"leo-fft256-preflight-{uuid4().hex[:8]}",
                100,
                base.command(args.work, args.cpu, "smoke"),
            )
            p = subprocess.run(argv, check=True, stdout=subprocess.PIPE, timeout=110)
            result = json.loads(p.stdout)
            save_json(args.work / "smoke.json", result)
            for row in result["rows"]:
                print(row["visit"], row["kind"], row["same"], flush=True)
        elif args.action == "smoke":
            smoke(args.work)
        elif args.action == "raw":
            incumbent.raw(args.work, args.cpu)
        else:
            incumbent.run(args.work)


if __name__ == "__main__":
    main()
