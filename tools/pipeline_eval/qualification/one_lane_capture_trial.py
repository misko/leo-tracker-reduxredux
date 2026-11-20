"""Run matched capture-era both-receiver and physical one-receiver fits."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from shutil import copyfile

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import one_lane_schedule
from . import complete_detector_roster as roster
from . import hard_pilots_eval as hard
from . import staggered_reconstruction_trial as staggered
from . import support_cross_trial as runner
from .bracketed_position import check_release
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows

REPORT = hard.SCREEN / "pilot-influence/one-lane-capture"
CASES = (*hard.HARD, *hard.CONTROLS)
MODES = ("capture_both", "capture_one")
CPUS = (6, 3)
read = whole_iq.read


def probe_audit(original, four, ledger):
    selected = {r["visit"]: r["selected_receiver"] for r in ledger}
    counts = {
        part: dict(probes=0, original=0, four=0, original_lost_by_four=0)
        for part in ("selected", "discarded")
    }
    if hard.support(original) != hard.support(four):
        raise ValueError("the native inputs do not share capture support")
    for a, b in zip(original["source"]["probes"], four["source"]["probes"], strict=True):
        if hard.metadata(a) != hard.metadata(b):
            raise ValueError("an authenticated lane probe changed its metadata")
        side = "selected" if a["receiver_id"] == selected[a["visit_index"]] else "discarded"
        row = counts[side]
        capture_winner, four_winner = (hard.factor_cross.winner(p["candidates"]) for p in (a, b))
        row["probes"] += 1
        row["original"] += capture_winner is not None
        row["four"] += four_winner is not None
        if capture_winner is not None:
            target = a["candidates"][capture_winner]
            row["original_lost_by_four"] += (
                hard.classify(target, b["candidates"])["category"] != "physical_gated"
            )
    return counts


def stage(work, ident, cpu, stock, expected, release):
    case, request = whole_iq.binding(ident)
    docs, bindings = hard.resolve(ident, case)
    if (
        bindings != expected["sources"]
        or case["native"]["sha256"] != stock["paired_capture_sha256"]
        or bindings["four"]["native_sha256"] != stock["native_sha256"]
        or case["request"]["sha256"] != stock["original_request_sha256"]
        or case["catalog"]["sha256"] != stock["catalog_sha256"]
        or case["regions"][0] != stock["tile"]
        or request["job"]["search_center"] != stock["tile"]["center"]
    ):
        raise ValueError(f"{ident} native or request disagrees with the original sealed authority")
    rf, manifests, authority = staggered.tune_plan(case)
    for role in ("capture", "four"):
        if docs[role]["source"]["input_manifest_sha256"] != authority:
            raise ValueError(f"{ident} native inputs do not bind the physical RF manifests")
    projected, selected = one_lane_schedule.project(docs["capture"], rf)
    if one_lane_schedule.dispatch(docs["four"], rf) != selected:
        raise ValueError("fixed-four and capture-era one-lane scheduling differ")
    proof = dict(
        id=ident,
        bindings=bindings,
        rf_authority=authority,
        manifests=manifests,
        selected=selected,
        probe_counts=probe_audit(docs["capture"], docs["four"], selected),
    )
    jobs = []
    for mode in MODES:
        out = work / ident / mode
        native, req = (out / "recording" / p for p in ("native.json", "request.json"))
        if mode == "capture_both":
            native.parent.mkdir(parents=True)
            copyfile(bindings["capture"]["path"], native)
            whole_iq.checked(native, stock["paired_capture_sha256"])
        else:
            write(native, encoded(projected) + b"\n")
        digest = whole_iq.recording.bind_request(case, native, req)["native_sha256"]
        verify_request(read(req), request, native_path=native, native_sha256=digest)
        save_json(out / "plan.json", dict(receiver=release["receiver"]))
        save_json(out / "raw.json", dict(native_sha256=digest, request_sha256=_sha(req)))
        jobs.append(
            dict(
                id=ident,
                condition=mode,
                method="one_lane_" + mode,
                mode="matched-tile",
                cpu=cpu,
                native_sha256=digest.removeprefix("sha256:"),
                prepared_request_sha256=_sha(req),
                schedule_sha256=sha256(encoded(selected)).hexdigest(),
                **{key: stock[key] for key in roster.BINDINGS},
            )
        )
    print("staged", ident, cpu, len(selected), flush=True)
    return jobs, proof


def launch(work):
    pin = hard.REPORT / "evidence-lock.json"
    hard_source = roster.member(hard.REPORT, read(pin), "source-lock.json")
    expected = read(hard_source)["cases"]
    release_home = hard.completion.REPORT
    release_lock = release_home / "prediction-lock.json"
    release_src = roster.member(release_home, read(release_lock), "source-lock.json")
    release = read(release_src)
    check_release(release)
    _, _, stock, _ = staggered.load_controls()
    if set(expected) != set(CASES) or (REPORT / "plan.json").exists():
        raise ValueError("the matched physical roster changed or is already frozen")
    work.mkdir()
    schedule, audits = [], []
    for i, ident in enumerate(CASES):
        cpu = CPUS[i // 2 % len(CPUS)]
        jobs, proof = stage(work, ident, cpu, stock[ident], expected[ident], release)
        schedule.extend(jobs if i % 2 == 0 else jobs[::-1])
        audits.append(proof)
    write(REPORT / "schedule-audit.jsonl.gz", compressed_rows(audits))
    sources = (
        pin,
        hard_source,
        release_lock,
        release_src,
        roster.REPORT / "all-figure-lock.json",
        REPORT / "PROTOCOL.md",
        Path(__file__),
        Path(one_lane_schedule.__file__),
        Path(staggered.__file__),
        Path(hard.__file__),
        Path(runner.__file__),
        Path(runner.margin_admission_trial.__file__),
    )
    save_json(
        REPORT / "plan.json",
        dict(
            cases=CASES,
            hard=hard.HARD,
            controls=hard.CONTROLS,
            schedule=schedule,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            limit_s=runner.LIMIT,
            nice=10,
            cpus=CPUS,
            audit_sha256=_sha(REPORT / "schedule-audit.jsonl.gz"),
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
            **{k: release[k] for k in ("receiver", "receiver_files", "native_sources")},
        ),
    )
    print("frozen", _sha(REPORT / "plan.json"), flush=True)

    def lane(cpu):
        for row in schedule:
            if row["cpu"] == cpu:
                runner.service(work, row)

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, CPUS))
    rows = [read(work / r["id"] / r["condition"] / "attempt.json") for r in schedule]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(rows))
    names = ("plan.json", "schedule-audit.jsonl.gz", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=CASES,
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    launch(parser.parse_args().work)
