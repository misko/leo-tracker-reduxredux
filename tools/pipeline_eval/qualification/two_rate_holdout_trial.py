"""Bind matched archived factors and run the installed compact receiver on the fixed replay."""

import argparse
import gzip
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, validate_result
from ..variants import dual_rate, negative_rescue, selective_capture
from . import complete_detector_roster as fixed
from . import one_lane_roster as roster
from . import one_lane_roster_results, support_cross_trial
from .bracketed_position import check_release
from .fractional_runtime_whole import verify_request
from .full_v5_check import BULK, _sha
from .phase_support_results import pack
from .two_rate_holdout import ANCHORS, REPORT, schedule
from .whole_pressure_trial import rows_from

CPUS = (12, 13, 22, 23)
LIMIT = support_cross_trial.LIMIT
MAX_PER_BATCH_AND_CPU = 4
MEMBERSHIP = "4bce76b6197ce4a42b878a2c17fe96dd72b800f4c0709b6986934f909a0b5821"
POLICIES = ("wide", "replace", "fill", "original")
CONTROLS = (
    (
        fixed.REPORT,
        "all-figure-lock.json",
        "2bc3768d2c146adc402992f5bbb5714119c2be77ec1959fa6c16329bdebef73a",
    ),
    (
        roster.FRESH,
        "prediction-lock.json",
        "595af4f12ee101d7632d7d107cf7383c510dec3f1aa54ffaa26ef9e370826991",
    ),
    (
        support_cross_trial.REPORT,
        "prediction-lock.json",
        "41c5be892d959803d75fcd1eaecb3aa74251995071d091b3867d18fe5d177750",
    ),
)
read = whole_iq.read


def sources():
    paths = (
        Path(__file__),
        REPORT / "PROTOCOL.md",
        Path(schedule.__code__.co_filename),
        Path(dual_rate.__file__),
        Path(negative_rescue.__file__),
        Path(selective_capture.__file__),
        Path(roster.__file__),
        Path(one_lane_roster_results.__file__),
        Path(support_cross_trial.__file__),
        Path(support_cross_trial.margin_admission_trial.__file__),
    )
    return {str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): _sha(p) for p in paths}


def inventory():
    return read(whole_iq.checked(REPORT / "membership-lock.json", MEMBERSHIP))


def reuse_controls(groups, release):
    complete, fresh, cross = [
        read(whole_iq.checked(folder / name, digest)) for folder, name, digest in CONTROLS
    ]
    # The complete-roster integration verified the stock receiver identity for its parents.
    fresh_plan = read(fixed.member(roster.FRESH, fresh, "source-lock.json"))
    authoritative = read(fixed.member(fixed.REPORT, complete, "inputs.json"))
    eight = read(
        whole_iq.checked(
            fixed.EIGHT / "eight-figure-lock.json",
            authoritative[str((fixed.EIGHT / "eight-figure-lock.json").relative_to(fixed.SCREEN))],
        )
    )
    raw = read(fixed.member(fixed.EIGHT, eight, "raw-prediction-lock.json"))
    complete_plan = read(fixed.member(fixed.EIGHT, raw, "source-lock.json"))
    if any(plan[k] != v for plan in (fresh_plan, complete_plan) for k, v in release.items()):
        raise ValueError("sealed fast compact fits have a different receiver release")
    cross_plan = read(fixed.member(support_cross_trial.REPORT, cross, "plan.json"))
    if any(cross_plan[k] != release[k] for k in ("receiver", "receiver_files")):
        raise ValueError("sealed original compact fits have a different receiver release")
    wide = one_lane_roster_results.released_stock(groups)
    original = fixed.select(
        rows_from(fixed.member(support_cross_trial.REPORT, cross, "predictions.jsonl.gz")),
        "probe_support_capture",
        ANCHORS,
    )
    return wide, original


def add_census(count, pair):
    passed = [sum(c[negative_rescue.GATE] is True for c in p["candidates"]) for p in pair]
    count.update(
        visits=1,
        positive_visits=any(passed),
        probes=len(pair),
        positive_probes=sum(p > 0 for p in passed),
        passing_candidates=sum(passed),
        candidates=sum(len(p["candidates"]) for p in pair),
    )


def project(fast, original, visits):
    selective_capture.same_support(fast, original)
    selected = {row["visit"]: row["rf_hz"] for row in visits}
    if len(selected) != len(visits):
        raise ValueError("schedule repeated a physical visit")
    streams = {p: [] for p in POLICIES}
    counts, lineage = {}, []
    wide = selective_capture.visit_pairs(fast["source"]["probes"])
    full = selective_capture.visit_pairs(original["source"]["probes"])
    for (visit, short), (_, long) in zip(wide, full, strict=True):
        rf = int(short[0]["actual_rf_hz"])
        offered = visit in selected
        if offered and selected.pop(visit) != rf:
            raise ValueError("original visit schedule changed physical RF")
        budgeted = long if offered else None
        per_rf = counts.setdefault(rf, {p: Counter() for p in POLICIES})
        witness = dict(visit=visit, rf_hz=rf, selected_original=offered)
        for policy in POLICIES:
            pair = dual_rate.select_probes(
                short, long if policy == "original" else budgeted, policy
            )
            streams[policy].extend(pair)
            stat = per_rf[policy]
            add_census(stat, pair)
            donor = [p is o for p, o in zip(pair, long, strict=True)]
            passes = [negative_rescue.positive(p) for p in pair]
            previous = [negative_rescue.positive(p) for p in short]
            stat.update(
                original_probes=sum(donor),
                original_visits=any(donor),
                gained_positive_probes=sum(
                    a and not b for a, b in zip(passes, previous, strict=True)
                ),
                lost_positive_probes=sum(
                    b and not a for a, b in zip(passes, previous, strict=True)
                ),
            )
            if offered:
                witness[policy] = [
                    dict(
                        original=is_donor,
                        positive=hit,
                        candidates_sha256=sha256(encoded(p["candidates"])).hexdigest(),
                    )
                    for p, is_donor, hit in zip(pair, donor, passes, strict=True)
                ]
        if offered:
            lineage.append(witness)
    if selected:
        raise ValueError("original visit schedule refers to unavailable captures")
    return streams, counts, lineage


def bind(ident, archives, bindings, extensions):
    case, request = roster.bind(ident, extensions)
    if bindings[ident] != dict(
        zip(
            fixed.BINDINGS,
            (
                case["native"]["sha256"],
                case["request"]["sha256"],
                case["catalog"]["sha256"],
                case["regions"][0],
            ),
            strict=True,
        )
    ):
        raise ValueError("target original archive differs from the sealed fast request binding")
    path = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    content = path.read_bytes()
    fast = roster.stock_document(archives[ident])
    if fast["provenance"]["detector_sha256"] != "sha256:" + roster.STOCK_SHA:
        raise ValueError("fast packet source is not the released four-region detector")
    original = json.loads(content)
    _, manifests, authority = roster.staggered_reconstruction_trial.tune_plan(case)
    for doc in (fast, original):
        provenance = doc["provenance"]
        if (
            doc["source"]["input_manifest_sha256"] != authority
            or doc["source"]["session_id"] != case["session_id"]
            or provenance["processed_windows"] + len(provenance["excluded_windows"])
            != provenance["window_count"]
            or provenance["window_count"] != case["recording"]["window_count"]
            or len(doc["source"]["probes"]) != 2 * provenance["processed_windows"]
        ):
            raise ValueError("native archive does not represent the full physical capture")
    return case, request, content, fast, original, manifests


def prepare(work, ident, case, original_request, payload, binding, release, policy, **job):
    path = work / ident / policy
    native, request = path / "recording/native.json", path / "recording/request.json"
    write(native, payload)
    digest = whole_iq.recording.bind_request(case, native, request)["native_sha256"]
    verify_request(read(request), original_request, native_path=native, native_sha256=digest)
    save_json(path / "plan.json", dict(receiver=release["receiver"]))
    save_json(path / "raw.json", dict(native_sha256=digest, request_sha256=_sha(request)))
    return dict(
        id=ident,
        condition=policy,
        method=f"two_rate_{policy}",
        mode="matched-tile",
        **binding,
        native_sha256=digest.removeprefix("sha256:"),
        prepared_request_sha256=_sha(request),
        **job,
    )


def verified_control(row, binding, native_sha256, policy, pin):
    if (
        any(row[key] != value for key, value in binding.items())
        or row["native_sha256"] != native_sha256
    ):
        raise ValueError(
            "reused control does not attest the same original binding and detector bytes"
        )
    result = row["result"]
    validate_result(result)
    if result["status"] not in ("ok", "withheld") or set(result["arms"]) != set(ARMS):
        raise ValueError("reused control has no complete pair of calibration arms")
    return dict(
        row, method=f"two_rate_{policy}", condition=policy, reused_prediction_lock_sha256=pin
    )


def stage(work):
    lock = inventory()
    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("choose a separate report directory to stage another experiment")
    whole_iq.checked(REPORT / "PROTOCOL.md", lock["protocol_sha256"])
    groups, media, bindings, extensions, release = roster.inventory()
    if lock["stock_archives"] != media or lock["prior_roster_membership"] != groups:
        raise ValueError("earlier raw archive has changed since roster freeze")
    wide, archived = reuse_controls(groups, release)
    work.mkdir(parents=True, exist_ok=False)
    jobs, reused, audits = [], [], {}
    for ident in lock["selected"]:
        case, request, content, fast, original, manifests = bind(ident, media, bindings, extensions)
        scheduled = whole_iq.checked(
            REPORT / "schedules" / f"{ident}.json", lock["schedule_sha256"][ident]
        )
        if encoded(read(scheduled)) != encoded(schedule(fast)):
            raise ValueError(
                "loaded physical visit schedule differs from the preregistered schedule"
            )
        original_sha = case["native"]["sha256"]
        wide_sha = media[ident]["native_sha256"]
        streams, counts, lineage = project(fast, original, read(scheduled)["selected"])
        witness = REPORT / "lineage" / f"{ident}.jsonl.gz"
        pack(witness, lineage)
        if Path(media[ident]["path"]).is_relative_to(Path("/var/tmp")):
            sealed = REPORT / "stock" / f"{ident}.json.gz"
            write(sealed, gzip.compress(Path(media[ident]["path"]).read_bytes(), mtime=0))
            preserved = dict(path=str(sealed), file_sha256=_sha(sealed), native_sha256=wide_sha)
        else:
            preserved = media[ident]
        baseline = 1 if ident in groups["fresh"] else 0
        reused.append(
            verified_control(wide[ident], bindings[ident], wide_sha, "wide", CONTROLS[baseline][2])
        )
        if ident in archived:
            reused.append(
                verified_control(
                    archived[ident], bindings[ident], original_sha, "original", CONTROLS[2][2]
                )
            )
        for policy in (*(() if ident in archived else ("original",)), "replace", "fill"):
            if policy == "original":
                payload = content
            else:
                fingerprint = whole_iq.recording.digest(
                    [
                        "two-rate-holdout/v1",
                        policy,
                        wide_sha,
                        original_sha,
                        lock["schedule_sha256"][ident],
                    ]
                )
                provenance = dict(
                    fast["provenance"],
                    run_id="two-rate-" + fingerprint[7:33],
                    scope="Offline fixed two-rate packet replay",
                )
                provenance.pop("detector_sha256")
                doc = dict(
                    fast,
                    source=dict(
                        fast["source"], probes=streams[policy], analysis_manifest_sha256=fingerprint
                    ),
                    provenance=provenance,
                )
                payload = encoded(doc) + b"\n"
            cpu = CPUS[len(jobs) % len(CPUS)]
            batch = len(jobs) // (len(CPUS) * MAX_PER_BATCH_AND_CPU)
            jobs.append(
                prepare(
                    work,
                    ident,
                    case,
                    request,
                    payload,
                    bindings[ident],
                    release,
                    policy,
                    cpu=cpu,
                    batch=batch,
                )
            )
        audits[ident] = dict(
            original_path=case["native"]["path"],
            original_native_sha256=original_sha,
            fast_archive=preserved,
            counts_per_rf=counts,
            schedule_sha256=lock["schedule_sha256"][ident],
            selected_lineage_sha256=_sha(witness),
            complete_output_probes_sha256={
                p: sha256(encoded(q)).hexdigest() for p, q in streams.items()
            },
            clocks_sha256=sha256(
                encoded(
                    [fast[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")]
                )
            ).hexdigest(),
            excluded_windows_sha256=sha256(
                encoded(fast["provenance"]["excluded_windows"])
            ).hexdigest(),
            physical_manifests=manifests,
            physical_visit_fields_sha256=sha256(
                encoded(
                    [{k: v for k, v in p.items() if k != "candidates"} for p in streams["wide"]]
                )
            ).hexdigest(),
            causal_history=request["causal_snapshots"],
            **bindings[ident],
        )
        print("staged", ident, len(lineage), "scheduled visits", flush=True)
    save_json(REPORT / "packet-audit.json", audits)
    pack(REPORT / "reused-controls.jsonl.gz", reused)
    plan = dict(
        membership_sha256=MEMBERSHIP,
        sources=sources(),
        jobs=jobs,
        cpus=CPUS,
        limit_s=LIMIT,
        max_batch_s=LIMIT * MAX_PER_BATCH_AND_CPU,
        memory_bytes=whole_iq.MEMORY,
        swap_bytes=0,
        reused_controls_sha256=_sha(REPORT / "reused-controls.jsonl.gz"),
        packet_audit_sha256=_sha(REPORT / "packet-audit.json"),
        control_locks={
            str((folder / name).relative_to(ROOT)): digest for folder, name, digest in CONTROLS
        },
        **release,
    )
    save_json(REPORT / "source-lock.json", plan)
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(REPORT / "source-lock.json")))


def run(work, batch):
    source_sha = read(work / "launch-lock.json")["source_lock_sha256"]
    plan = read(whole_iq.checked(REPORT / "source-lock.json", source_sha))
    if plan["sources"] != sources():
        raise ValueError("staged replay code has changed")
    check_release(plan)
    jobs = [row for row in plan["jobs"] if row["batch"] == batch]
    if not jobs:
        raise ValueError("no positions in the chosen fixed batch")

    def worker(cpu):
        for job in jobs:
            if job["cpu"] == cpu:
                yield support_cross_trial.service(work, job)

    with (
        patch.object(support_cross_trial, "LIMIT", LIMIT),
        ThreadPoolExecutor(max_workers=len(CPUS)) as pool,
    ):
        rows = [row for lane in pool.map(lambda cpu: list(worker(cpu)), CPUS) for row in lane]
    archive = REPORT / f"batch-{batch}-positions.jsonl.gz"
    for row in rows:
        if row["position_resources"]:
            for mark in ("start", "end"):
                sample = row["position_resources"][mark]
                if (
                    sample["cpus"] != [row["cpu"]]
                    or sample["memory.max"] != whole_iq.MEMORY
                    or sample["memory.swap.max"]
                    or sample["memory.swap.current"]
                ):
                    raise ValueError(
                        "position escaped its assigned core or 512 MiB/zero-swap service"
                    )
        path = work / row["id"] / row["condition"] / "service.log"
        write(
            REPORT / "logs" / f"{row['id']}-{row['condition']}.log.gz",
            gzip.compress(path.read_bytes(), mtime=0),
        )
    pack(archive, sorted(rows, key=lambda row: (row["id"], row["condition"])))
    save_json(
        REPORT / f"batch-{batch}-lock.json",
        dict(source_lock_sha256=source_sha, positions_sha256=_sha(archive)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("--work", required=True, type=local_output)
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--batch", required=False, type=int, default=0)
    args = parser.parse_args()
    REPORT = args.report
    stage(args.work) if args.action == "stage" else run(args.work, args.batch)
