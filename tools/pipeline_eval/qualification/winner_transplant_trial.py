"""Prepare and fit the sealed, capture-winner transplant from stored detector factors."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from . import complete_detector_roster as roster
from . import hard_pilots_eval as hard
from . import support_cross_trial as runner
from . import winner_transplant_intervention as experiment
from .bracketed_position import check_release
from .factor_cross import GATE, winner
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows
from .staggered_reconstruction_trial import load_controls, unavailable

REPORT = hard.SCREEN / "pilot-influence/winner-transplant"
CASES = (*hard.HARD, *hard.CONTROLS)
LANES = (8, 9, 10, 11)
MODES = experiment.MODES
LAUNCH_LIMIT_S = 720
PREFIX = "winner_transplant_"
read = whole_iq.read


def authority():
    stage_lock = hard.REPORT / "evidence-lock.json"
    hard_lock = roster.member(hard.REPORT, read(stage_lock), "source-lock.json")
    present = read(hard_lock)["cases"]
    if set(present) != set(CASES):
        raise ValueError("hard pilot roster changed before the geographic trial")
    _, _, stock, fifth = load_controls()
    release_lock = hard.completion.REPORT / "source-lock.json"
    release = read(
        roster.member(
            release_lock.parent,
            read(release_lock.with_name("prediction-lock.json")),
            release_lock.name,
        )
    )
    check_release(release)
    inputs = (
        stage_lock,
        hard_lock,
        release_lock,
        roster.REPORT / "all-figure-lock.json",
        REPORT / "PROTOCOL.md",
        Path(__file__),
        Path(experiment.__file__),
        Path(hard.__file__),
        Path(hard.factor_cross.__file__),
        Path(runner.__file__),
        Path(runner.margin_admission_trial.__file__),
    )
    bindings = {str(path.relative_to(ROOT)): _sha(path) for path in inputs}
    return present, stock, fifth, release, bindings


def prepare(work, ident, cpu, present, stock, fifth, release):
    case, original = whole_iq.binding(ident)
    docs, bindings = hard.resolve(ident, case)
    if (
        bindings != present["sources"]
        or bindings["capture"]["native_sha256"] != stock["paired_capture_sha256"]
        or bindings["four"]["native_sha256"] != stock["native_sha256"]
        or bindings["five"]["native_sha256"] != fifth["native_sha256"]
        or case["request"]["sha256"] != stock["original_request_sha256"]
        or case["catalog"]["sha256"] != stock["catalog_sha256"]
        or original["job"]["search_center"] != stock["tile"]["center"]
    ):
        raise ValueError(f"{ident} source differs from hard-pilot or position authority")
    selections, matched_pairs, placebo_eligible = experiment.select(ident, docs)
    exclusions = sum(len(selections[k]) for k in ("availability", "conflicts"))
    if exclusions != present["counts"]["missing_both"]:
        raise ValueError("exclusive physical missingness does not reproduce the original census")
    control = docs["four"]
    stock_positive = sum(winner(p["candidates"]) is not None for p in control["source"]["probes"])
    rows = []
    for mode, selected in selections.items():
        payload = experiment.transplant(control, docs["capture"], selected, mode)
        lineage = whole_iq.recording.digest(
            [experiment.SALT, mode, bindings["capture"]["native_sha256"], stock["native_sha256"]]
        )
        payload["source"]["analysis_manifest_sha256"] = lineage
        payload["provenance"] = dict(
            payload["provenance"],
            scope="Diagnostic transplant of authenticated capture-era winners",
            run_id="winner-transplant-" + lineage[7:32],
        )
        payload["provenance"].pop("detector_sha256")
        folder = work / ident / mode
        native, request = (folder / "recording" / name for name in ("native.json", "request.json"))
        write(native, encoded(payload) + b"\n")
        digest = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
        verify_request(read(request), original, native_path=native, native_sha256=digest)
        save_json(folder / "plan.json", dict(receiver=release["receiver"]))
        save_json(folder / "raw.json", dict(native_sha256=digest, request_sha256=_sha(request)))
        probes = payload["source"]["probes"]
        observed = sum(winner(p["candidates"]) is not None for p in probes)
        expected = stock_positive + (len(selected) if mode != "conflicts" else 0)
        if observed != expected:
            raise ValueError("strict availability/identity separation did not hold")
        rows.append(
            dict(
                id=ident,
                method=PREFIX + mode,
                condition=mode,
                cpu=cpu,
                mode="matched-tile",
                native_sha256=digest.removeprefix("sha256:"),
                prepared_request_sha256=_sha(request),
                stock_native_sha256=stock["native_sha256"],
                fifth_native_sha256=fifth["native_sha256"],
                changed=len(selected),
                positive_probes=observed,
                positive_candidates=sum(c[GATE] is True for p in probes for c in p["candidates"]),
                **{key: stock[key] for key in roster.BINDINGS},
            )
        )
    proof = dict(
        id=ident,
        bindings=bindings,
        stock_positive=stock_positive,
        selections=selections,
        matched_pairs=matched_pairs,
        placebo_eligible=placebo_eligible,
    )
    print(ident, {k: len(v) for k, v in selections.items()}, flush=True)
    return rows, proof


def launch(work):
    present, stock, fifth, release, dependencies = authority()
    work.mkdir(exist_ok=False)
    if (REPORT / "plan.json").exists():
        raise FileExistsError("winner-transplant protocol already froze this schedule")
    schedule, witnesses = [], []
    for ordinal, ident in enumerate(CASES):
        pin = LANES[ordinal % len(LANES)]
        prepared, proof = prepare(
            work, ident, pin, present[ident], stock[ident], fifth[ident], release
        )
        shift = ordinal % len(MODES)
        schedule.extend(prepared[shift:] + prepared[:shift])
        witnesses.append(proof)
    write(REPORT / "selections.jsonl.gz", compressed_rows(witnesses))
    plan = dict(
        cases=list(CASES),
        challenge=list(hard.HARD),
        controls=list(hard.CONTROLS),
        schedule=schedule,
        sources=dependencies,
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        service_limit_s=runner.LIMIT,
        launch_limit_s=LAUNCH_LIMIT_S,
        selection_sha256=_sha(REPORT / "selections.jsonl.gz"),
        **{k: release[k] for k in ("receiver", "receiver_files", "native_sources")},
    )
    save_json(REPORT / "plan.json", plan)
    digest = _sha(REPORT / "plan.json")
    print("prospective lock", digest, flush=True)
    start = monotonic()

    def run(row):
        if monotonic() - start >= LAUNCH_LIMIT_S:
            return unavailable(row, "prospective wall-time launch horizon reached")
        return runner.service(work, row)

    def lane(cpu):
        return [run(r) for r in schedule if r["cpu"] == cpu]

    with ThreadPoolExecutor(len(LANES)) as pool:
        outcomes = [r for group in pool.map(lane, LANES) for r in group]
    write(REPORT / "predictions.jsonl.gz", compressed_rows(outcomes))
    names = ("plan.json", "selections.jsonl.gz", "predictions.jsonl.gz")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(CASES),
            attempted=sum(row["terminal"] != "not-launched" for row in outcomes),
            elapsed_s=monotonic() - start,
            files={name: _sha(REPORT / name) for name in names},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    launch(parser.parse_args().work)
