"""Replay DS29-0082 with the qualified prepared, row-wise and pruned detector."""

import argparse
import gzip
import json
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants.fine_search import FineSearch
from ..variants.original_kernel import PersistentGrid
from . import capture_whole as base
from . import prepared_capture_waveform as prepared
from . import selector_waveform
from .full_v5_check import _sha

IDENT = "DS29-0082"
PREVIOUS = base.REPORT
REPORT = PREVIOUS.parents[1] / "pilot-search-and-region/field-exact-waveform"
PANEL = REPORT.with_name("fine-search")
PANEL_SHA = "905317d53cb7b41a341bc6c121bc99bddf9caf4da1e666f1e3580111184c4895"
WORK = Path("/srv/bulk/leo-dev/field-exact-waveform-ds29-0082-20261119")
CPUS = (0, 1, 4, 5, 6, 7, 20, 21)
METHOD = "original_capture_field_exact_full_iq"
MODULE = "tools.pipeline_eval.qualification.field_exact_waveform"
QUALIFIED_CASES = {"DS26-0237", IDENT, "DS29-0174", "DS29-0519"}
TRACE = "pruned-fine-v1: "
FINE_COUNTERS = ("calls", "fallbacks", "frames", "bins")


@contextmanager
def configured():
    with patch.multiple(base, IDENT=IDENT, REPORT=REPORT, METHOD=METHOD, MODULE=MODULE):
        yield


def freeze(work):
    from .fresh_replay_results import sealed

    destination = REPORT / "source-lock.json"
    if destination.exists() or work.exists():
        raise FileExistsError("this waveform plan or work directory is already frozen")
    panel = sealed(PANEL, "qualification-lock.json", PANEL_SHA)
    study = whole_iq.read(PANEL / "input-lock.json")
    summary = whole_iq.read(PANEL / "summary.json")
    audits = summary["audits"]
    if (
        set(summary["cases"]) != QUALIFIED_CASES
        or {r["case"] for r in audits} != QUALIFIED_CASES
        or len({(r["case"], r["visit"]) for r in audits}) != 16
        or len(audits) != 16
        or any(
            r["evaluated"]["fallbacks"] or r["paired_repeats"] != 5 or r["factor_rows"] != 2
            for r in audits
        )
        or summary["paired_cpu_ms"]["n"] != 80
        or summary["paired_cpu_ms"]["median"] < 15
    ):
        raise ValueError("the all-root qualification did not meet its exact CPU criterion")
    prediction = sealed(PREVIOUS, "prediction-lock.json")
    timing = sealed(PREVIOUS, "timing-lock.json")
    lock = whole_iq.read(PREVIOUS / destination.name)
    archive = whole_iq.read(
        whole_iq.checked(
            base.BULK / lock["original"]["native"]["path"], lock["original"]["native"]["sha256"]
        )
    )
    case = study["cases"][IDENT]
    proof = json.loads(gzip.decompress((PANEL / f"{IDENT}.json.gz").read_bytes()))
    if (
        proof["input_lock_sha256"] != panel["files"]["input-lock.json"]
        or proof["case"] != IDENT
        or (case["root"], case["edge"], case["input_manifest"], case["archive_sha256"])
        != (
            lock["producer"],
            "upper",
            lock["capture"]["input_manifest_sha256"],
            lock["original"]["native"]["sha256"],
        )
        or lock["capture"]["edge"] != "upper"
        or lock["python_sha256"] != study["python_sha256"]
        or any(study["libs"][name] != info for name, info in lock["libraries"].items())
    ):
        raise ValueError("the qualified fine detector does not bind the exact DS29 capture")
    invalid = {row["visit"] for row in archive["provenance"]["excluded_windows"]}
    chunks = sorted(chunk for _, _, rows in lock["workers"] for chunk in rows)
    if (
        len(chunks) != 106
        or sum(row[2] - row[1] for row in chunks) != 6772
        or len(invalid) != 1904
        or len(archive["source"]["probes"]) != 9736
        or sum(len(row["candidates"]) for row in archive["source"]["probes"]) != 42162
    ):
        raise ValueError("the signed original DS29 visit and candidate roster changed")
    held = {r["visit"]: r for r in case["rows"]}
    if set(held) != {r["visit"] for r in proof["rows"]} or len(held) != 4:
        raise ValueError("qualified DS29 signal/miss/gate controls changed")
    smoke = {visit: (segment, first, visit) for segment, first, visit in lock["smoke"]}
    for visit in (*held, min(invalid)):
        segment, _, _, offset = next(c for c in chunks if c[3] + c[1] <= visit < c[3] + c[2])
        smoke[visit] = (segment, visit - offset, visit)
    sources = lock["sources"] | study["sources"] | case["sources"]
    sources.update(
        {
            str(p): _sha(p)
            for p in (
                Path(__file__),
                Path(prepared.__file__),
                Path(selector_waveform.__file__),
                REPORT / "PROTOCOL.md",
                PANEL / "qualification-lock.json",
                PANEL / "summary.json",
                PANEL / "input-lock.json",
                PANEL / f"{IDENT}.json.gz",
            )
        }
    )
    comparisons = {
        name: prediction["files"][name]
        for name in ("audit.json", "native.json.gz", "positions.jsonl.gz", "source-lock.json")
    }
    comparisons.update(
        {
            "timing.csv": timing["files"]["timing.csv"],
            "prediction-lock.json": _sha(PREVIOUS / "prediction-lock.json"),
            "timing-lock.json": _sha(PREVIOUS / "timing-lock.json"),
        }
    )
    evidence_sources = {
        name: digest for name, digest in sources.items() if not Path(name).stat().st_mode & 0o004
    }
    lock.update(
        libraries=study["libs"],
        sources={name: digest for name, digest in sources.items() if name not in evidence_sources},
        evidence_sources=evidence_sources,
        raw_limit_s=720,
        position_limit_s=180,
        workers=base.partition(chunks, invalid, CPUS),
        smoke=[smoke[v] for v in sorted(smoke)],
        held_sha256={str(v): r["iq_sha256"] for v, r in held.items()},
        smoke_invalid=[v for v in smoke if v in invalid],
        comparison=comparisons,
        fine_qualification_sha256=PANEL_SHA,
    )
    for path, digest in sources.items():
        whole_iq.checked(Path(path), digest)
    for info in lock["libraries"].values():
        whole_iq.checked(Path(info["path"]), info["sha256"])
    work.mkdir(mode=0o755)
    for path in (work / destination.name, destination):
        save_json(path, lock)
        path.chmod(0o644)
    print("CPU assignments", [(c, n, len(s)) for c, n, s in lock["workers"]], flush=True)


def fine_for(lock, library):
    from leo.analysis.starlink import acquisition

    source = Path(acquisition.__file__)
    if str(source) not in lock["sources"] or not source.is_relative_to(lock["producer"]):
        raise ValueError("pruned fine CFO must use the signed original acquisition producer")
    fine = FineSearch(library, acquisition)
    if not fine.compatible:
        raise ValueError("pruned fine CFO failed the installed FFT arithmetic sentinel")
    return fine


def check_evidence(work):
    lock, _ = base.configure(work)
    for path, digest in lock["evidence_sources"].items():
        whole_iq.checked(Path(path), digest)


def smoke(work):
    lock, libs = base.configure(work)
    policy = base.policy_for(lock)
    grid = PersistentGrid(libs["prepared"])
    rows = []
    try:
        fine = fine_for(lock, libs["fine"])
        scoped = base.exact.stages.detector
        for segment, first, visit in lock["smoke"]:
            (window,) = base.open_span(lock, segment, first, first + 1).windows()
            if window.acquisition["global_visit"] != visit or window.iq_sha256 != lock[
                "held_sha256"
            ].get(str(visit), window.iq_sha256):
                raise ValueError("launch visit or signed held IQ digest changed")
            observed = SimpleNamespace(**vars(window), receiver_ids=(0, 1))
            stock = base.exact.trial(observed, policy, "installed", libs)
            results = {"installed": stock}
            before = fine.calls
            with base.exact.refiners(libs), selector_waveform.selector(lock):
                for mode, route in (("row_wise", nullcontext), ("pruned", fine.route)):
                    with route():
                        results[mode] = scoped(observed, policy, grid)
            valid = visit not in lock["smoke_invalid"]
            expected = "processed" if valid else "invalid_capture"
            if (
                stock["status"] != expected
                or fine.fallbacks
                or (fine.calls > before) != valid
                or any(
                    base.recording.encoded(result[k]) != base.recording.encoded(stock[k])
                    for result in results.values()
                    for k in ("status", "public", "probes", "attempts")
                )
            ):
                raise ValueError(f"installed, row-wise and pruned outputs disagree at {visit}")
            rows.append(
                dict(
                    visit=visit,
                    status=expected,
                    iq_sha256=window.iq_sha256,
                    clocks={mode: result["cpu_ns"] for mode, result in results.items()},
                    public_sha256=base.recording.digest(stock["public"]),
                    probes_sha256=base.recording.digest(stock["probes"]),
                    attempts_sha256=base.recording.digest(stock["attempts"]),
                    fine_calls=fine.calls - before,
                )
            )
            grid.calls.clear()
    finally:
        grid.clear_cache()
    print(
        base.recording.encoded(dict(source_lock_sha256=_sha(work / "source-lock.json"), rows=rows)),
        flush=True,
    )


def fine_counts(fine):
    return tuple(getattr(fine, key) for key in FINE_COUNTERS)


class VisitRecords(prepared.VisitGridRecords):
    def __init__(self, fine):
        super().__init__()
        self.fine = fine
        self.previous = fine_counts(fine)

    def clear(self):
        current = fine_counts(self.fine)
        counts = {
            key: end - start
            for key, end, start in zip(FINE_COUNTERS, current, self.previous, strict=True)
        }
        line = base.recording.encoded(
            dict(ordinal=self.ordinal, workspace_bytes=self.fine.workspace_bytes, **counts)
        )
        print(TRACE + line, file=sys.stderr, flush=True)
        self.previous = current
        super().clear()


def raw(work, cpu):
    lock, libs = base.configure(work)
    fine = fine_for(lock, libs["fine"])
    with (
        selector_waveform.selector(lock),
        fine.route(),
        patch.object(prepared, "VisitGridRecords", lambda: VisitRecords(fine)),
    ):
        prepared.raw(work, cpu)


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
            check_evidence(args.work)
            command = base.service(
                f"leo-field-exact-preflight-{uuid4().hex[:8]}",
                75,
                base.command(args.work, args.cpu, "smoke"),
            )
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, timeout=85)
            save_json(args.work / "smoke.json", json.loads(result.stdout))
            print(result.stdout.decode(), end="")
        elif args.action == "smoke":
            smoke(args.work)
        elif args.action == "raw":
            raw(args.work, args.cpu)
        else:
            check_evidence(args.work)
            base.run(args.work)


if __name__ == "__main__":
    main()
