"""Replay original post-acquisition rank prefixes through the compact receiver."""

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from math import isfinite
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..scoring import validate_result
from ..variants.selective_capture import visit_pairs
from . import rf_lane_panel as prior_panel
from . import support_cross_trial
from .bracketed_position import check_release
from .broad_search_budget import frozen_inputs
from .full_v5_check import BULK, FROZEN, _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .two_rate_holdout_trial import prepare
from .whole_pressure_trial import rows_from

SCREEN = prior_panel.prior.fixed.SCREEN
REPORT = SCREEN / "retry-and-transfer/first-gate-panel"
ROOF = SCREEN / "secant-full"
ROOF_PIN = "9317d8077292bbd1e2bf2f2908a13f782ddc29042568a371319c448acf30945d"
RF_PIN = "cb91ee6713793a3754bc6adf698385ae16ca35a31b122992f8b782a393faea46"
ANCHORS = ("DS26-0237", "DS29-0082")
CPUS = (8, 9, 10, 11)
LIMIT = 210
GATE = "passed_fractional_margin_gate"
MARGIN = 0.025
RANKS = 8
POLICIES = ("first", "second", "full")
read, checked = whole_iq.read, whole_iq.checked


def choose_cases(inputs):
    ranked = {}
    for dataset in ("DS26", "DS29"):
        pool = (ident for ident in inputs if ident.startswith(dataset) and ident not in ANCHORS)

        def key(ident):
            first = inputs[ident]["recording"]["segments"][0]["sha256"].removeprefix("sha256:")
            return sha256(f"first-gate-panel-v1|{first}".encode("ascii")).digest(), ident

        ranked[dataset] = sorted(pool, key=key)
    return [*ANCHORS, *ranked["DS26"][:2], *ranked["DS29"][:2]], ranked


def prefix(candidates, passes):
    """Keep the complete exported rows reached before the kth pass, including rejected rows."""
    if passes not in (1, 2):
        raise ValueError("the stop policy needs one or two passes")
    for index, row in enumerate(candidates):
        if row[GATE] is True:
            passes -= 1
            if passes == 0:
                return candidates[: index + 1], row["candidate_rank"]
    return candidates, None


def assess_lane(candidates):
    ranks = [row.get("candidate_rank") for row in candidates]
    if any(type(rank) is not int or not 0 <= rank < RANKS for rank in ranks):
        raise ValueError("capture rank is absent or outside the qualified eight-candidate release")
    if sorted(set(ranks)) != ranks:
        raise ValueError("capture candidate order differs from original ascending ranks")
    if any(
        not isfinite(row["fractional_margin"])
        or row[GATE] is not (row["fractional_margin"] >= MARGIN)
        for row in candidates
    ):
        raise ValueError("archived gate disagrees with the original fractional margin")
    passing = [row for row in candidates if row[GATE]]
    winner = max(passing, key=lambda row: row["fractional_margin"], default=None)
    minimum = ranks[-1] + 1 if ranks else 0
    basic = dict(
        lanes=1,
        positive_lanes=winner is not None,
        available_complete=len(candidates),
        proved_unexported_ranks=minimum - len(candidates),
        unknown_trailing_ranks=RANKS - minimum,
        full_final_anchor_calls_lower=minimum,
        full_final_anchor_calls_upper=RANKS,
        original_gate_passes=len(passing),
    )
    edited, counts = {}, {}
    for policy, passes in (("first", 1), ("second", 2)):
        retained, stop_rank = prefix(candidates, passes)
        rival = max(
            (row for row in retained if row[GATE]),
            key=lambda row: row["fractional_margin"],
            default=None,
        )
        if bool(winner) != bool(rival):
            raise ValueError("rank prefix changed the original any-pass result")
        handled_lower = minimum if stop_rank is None else stop_rank + 1
        handled_upper = RANKS if stop_rank is None else stop_rank + 1
        edited[policy] = retained
        flipped = winner != rival
        counts[policy] = dict(
            **basic,
            stopped=stop_rank is not None,
            source_tail_cut=len(candidates) > len(retained),
            retained_complete=len(retained),
            removed_complete_continuous_calls=len(candidates) - len(retained),
            kept_anchor_calls_lower=handled_lower,
            kept_anchor_calls_upper=handled_upper,
            skipped_anchor_calls_lower=minimum - handled_lower,
            skipped_anchor_calls_upper=RANKS - handled_upper,
            winner_rank_flips=flipped,
            selected_cfo_flips=flipped
            and (winner["fractional_tracking_cfo_hz"] != rival["fractional_tracking_cfo_hz"]),
            selected_margin_flips=flipped
            and winner["fractional_margin"] != rival["fractional_margin"],
            compact_observation_flips=flipped
            and any(
                winner[k] != rival[k] for k in ("fractional_tracking_cfo_hz", "fractional_margin")
            ),
        )
    return edited, counts


def project(document, *, retain=False):
    original = document["source"]["probes"]
    streams = {policy: [] for policy in POLICIES[:2]}
    counts = {policy: Counter() for policy in streams}
    valid = []
    for visit, pair in visit_pairs(original):
        valid.append(visit)
        positive = False
        for row in pair:
            edited, facts = assess_lane(row["candidates"])
            positive |= bool(facts["first"]["positive_lanes"])
            for policy, statistic in facts.items():
                counts[policy].update(statistic)
                if retain:
                    streams[policy].append(dict(row, candidates=edited[policy]))
        for total in counts.values():
            total.update(valid_visits=1, positive_visits=int(positive))
    provenance = document["provenance"]
    excluded = [row["visit"] for row in provenance["excluded_windows"]]
    if len(valid) != provenance["processed_windows"] or sorted(valid + excluded) != list(
        range(provenance["window_count"])
    ):
        raise ValueError(
            "expected every valid and invalid capture visit in the original native input"
        )
    for total in counts.values():
        total.update(
            invalid_visits=len(excluded),
            # At most one miss can retry, and then the partner's primary hit always survives.
            unobserved_primary_calls_upper=RANKS * total["positive_visits"],
        )
    return streams, counts


def archive(item):
    path = BULK / item["native"]["path"]
    content = path.read_bytes()
    if sha256(content).hexdigest() != item["native"]["sha256"]:
        raise ValueError("capture-era input differs from its immutable native hash")
    document = json.loads(content)
    if (
        document["source"]["session_id"] != item["session_id"]
        or document["provenance"]["window_count"] != item["recording"]["window_count"]
    ):
        raise ValueError("the archived detector does not cover this physical recording")
    return content, document


def inputs():
    roof_lock = read(checked(ROOF / "prediction-lock.json", ROOF_PIN))
    cases = frozen_inputs()
    if set(roof_lock["cases"]) != cases.keys():
        raise ValueError("the accounting roster differs from the authenticated roof-135 panel")
    return cases


def sealed_controls():
    folder = prior_panel.REPORT
    lock = read(checked(folder / "prediction-lock.json", RF_PIN))
    plan = read(checked(folder / "source-lock.json", lock["files"]["source-lock.json"]))
    release = {k: plan[k] for k in ("receiver", "receiver_files", "native_sources")}
    check_release(release)
    rows = rows_from(checked(folder / "positions.jsonl.gz", lock["files"]["positions.jsonl.gz"]))
    return release, {r["id"]: r for r in rows if r["condition"] == "original"}


def sources(report):
    paths = (
        Path(__file__),
        Path(prior_panel.__file__),
        Path(support_cross_trial.__file__),
        Path(support_cross_trial.margin_admission_trial.__file__),
        Path(prepare.__code__.co_filename),
        FROZEN / "inputs.jsonl",
        report / "PROTOCOL.md",
    )
    return {str(p): _sha(p) for p in paths}


def freeze(report, work):
    if (report / "membership-lock.json").exists():
        raise FileExistsError("choose a new output for a separate frozen first gate panel")
    work.mkdir(exist_ok=False, parents=True)
    cases = inputs()
    cases_fit, ranked = choose_cases(cases)
    save_json(
        report / "membership-lock.json",
        dict(
            accounting=sorted(cases),
            fits=cases_fit,
            anchors=list(ANCHORS),
            rank_order=ranked,
            archive_native_sha256={
                ident: item["native"]["sha256"] for ident, item in cases.items()
            },
            roof_prediction_lock_sha256=ROOF_PIN,
            protocol_sha256=_sha(report / "PROTOCOL.md"),
        ),
    )
    release, previous = sealed_controls()
    jobs, reused, audit = {}, [], {}
    for ident in cases_fit:
        case, request = whole_iq.binding(ident)
        content, original = archive(case)
        crops, counts = project(original, retain=True)
        binding = dict(
            paired_capture_sha256=case["native"]["sha256"],
            original_request_sha256=case["request"]["sha256"],
            catalog_sha256=case["catalog"]["sha256"],
            tile=case["regions"][0],
        )
        matches = previous.get(ident)
        if matches:
            if any(matches[k] != v for k, v in binding.items()) or (
                matches["native_sha256"] != case["native"]["sha256"]
            ):
                raise ValueError("reused full-original factors or requests differ")
            validate_result(matches["result"])
            reused.append(
                dict(
                    matches,
                    condition="full",
                    method="first_gate_full",
                    reused_full_original_lock_sha256=RF_PIN,
                )
            )
        for policy in (*POLICIES[:2], *(() if matches else ("full",))):
            if policy == "full":
                payload = content
            else:
                analysis = whole_iq.recording.digest(
                    ["capture-first-gate/v1", policy, case["native"]["sha256"]]
                )
                document = dict(
                    original,
                    source=dict(
                        original["source"], probes=crops[policy], analysis_manifest_sha256=analysis
                    ),
                    provenance=dict(
                        original["provenance"],
                        scope="Archived fractional GLRT rank prefix",
                        run_id="capture-prefix-" + analysis[7:33],
                    ),
                )
                document["provenance"].pop("detector_sha256", None)
                payload = encoded(document) + b"\n"
            jobs[ident, policy] = dict(
                prepare(work, ident, case, request, payload, binding, release, policy),
                method=f"first_gate_{policy}",
            )
        audit[ident] = dict(
            **binding,
            counts=counts,
            causal_snapshots=request["causal_snapshots"],
            probes_sha256={policy: prior_panel.digest(probes) for policy, probes in crops.items()}
            | {"full": prior_panel.digest(original["source"]["probes"])},
        )
        print(ident, "prefixes staged", flush=True)
    ordered = [
        jobs[ident, policy] for policy in POLICIES for ident in cases_fit if (ident, policy) in jobs
    ]
    for idx, job in enumerate(ordered):
        job["cpu"] = CPUS[idx % len(CPUS)]
    save_json(report / "position-input-audit.json", audit)
    pack(report / "reused-controls.jsonl.gz", reused)
    files = (
        "membership-lock.json",
        "position-input-audit.json",
        "reused-controls.jsonl.gz",
        "PROTOCOL.md",
    )
    save_json(
        report / "source-lock.json",
        dict(
            cases=cases_fit,
            jobs=ordered,
            sources=sources(report),
            limit_s=LIMIT,
            memory_bytes=whole_iq.MEMORY,
            cpus=CPUS,
            files={name: _sha(report / name) for name in files},
            **release,
        ),
    )
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(report / "source-lock.json")))


def fit(report, work):
    plan = read(
        checked(report / "source-lock.json", read(work / "launch-lock.json")["source_lock_sha256"])
    )
    check_release(plan)
    if plan["sources"] != sources(report) or plan["limit_s"] != support_cross_trial.LIMIT:
        raise ValueError("frozen replay source or cap changed")
    for name, fingerprint in plan["files"].items():
        checked(report / name, fingerprint)

    def lane(cpu):
        return [
            prior_panel.attempt(work, report, row, plan)
            for row in plan["jobs"]
            if row["cpu"] == cpu
        ]

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        completed = [row for group in pool.map(lane, CPUS) for row in group]
    complete = completed + rows_from(report / "reused-controls.jsonl.gz")
    indexed = prior_panel.columns(complete)
    expected = [(ident, policy) for ident in plan["cases"] for policy in POLICIES]
    if len(complete) != len(expected) or indexed.keys() != set(expected):
        raise ValueError("position ledger must retain every case and policy")
    pack(report / "positions.jsonl.gz", [indexed[key] for key in expected])
    names = ("source-lock.json", "positions.jsonl.gz")
    files = dict(plan["files"], **{name: _sha(report / name) for name in names})
    files.update({str(p.relative_to(report)): _sha(p) for p in (report / "logs").glob("*.gz")})
    save_json(report / "prediction-lock.json", dict(cases=plan["cases"], files=files))


def accounting(report):
    enrollment_path = report / "membership-lock.json"
    enrollment = read(enrollment_path)
    cases = inputs()
    if set(enrollment["accounting"]) != cases.keys() or enrollment["archive_native_sha256"] != {
        i: c["native"]["sha256"] for i, c in cases.items()
    }:
        raise ValueError("archived accounting input hashes changed")
    rows = []
    for index, ident in enumerate(enrollment["accounting"]):
        _, document = archive(cases[ident])
        _, counts = project(document)
        rows.extend(dict(id=ident, policy=policy, **data) for policy, data in counts.items())
        if index % 25 == 24:
            print(index + 1, "recordings audited", flush=True)
    path = report / "archive-accounting.csv"
    csv_file(path, rows)
    save_json(
        report / "accounting-lock.json",
        dict(
            cases=enrollment["accounting"],
            files={p.name: _sha(p) for p in (enrollment_path, path, report / "PROTOCOL.md")},
            sources=sources(report),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "fit", "account"))
    parser.add_argument("--work", type=local_output)
    parser.add_argument("--report", default=REPORT, type=local_output)
    cli = parser.parse_args()
    if cli.action == "account":
        return accounting(cli.report)
    if cli.work is None:
        parser.error("--work is required for compact replay")
    return {"freeze": freeze, "fit": fit}[cli.action](cli.report, cli.work)


if __name__ == "__main__":
    main()
