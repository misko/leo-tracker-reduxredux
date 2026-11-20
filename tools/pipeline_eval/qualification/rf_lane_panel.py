"""Freeze and replay one complete original-detector RF per recording."""

import argparse
import gzip
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import rf_routing, selective_capture
from . import two_rate_holdout
from . import two_rate_holdout_trial as prior
from .bracketed_position import check_release
from .full_v5_check import _sha
from .phase_support_results import pack

REPORT = prior.fixed.SCREEN / "pilot-search-and-region/rf-lane-panel"
PARENT_PREDICTIONS = "360af28d5e65513fa6d8cd01efc794a85968a73d286fa6179bd635eec81c8f15"
POLICIES = ("whole", "spread", "fast", "original")
CPUS = (16, 17, 18, 19)
LIMIT = 210
read = whole_iq.read
checked = whole_iq.checked


def digest(value):
    return sha256(encoded(value)).hexdigest()


def rank(kind, manifest, *parts):
    fields = (kind, manifest.removeprefix("sha256:").lower(), *map(str, parts))
    return sha256("|".join(fields).encode("ascii")).digest()


def enroll(parent):
    retained = parent["selected"]
    manifests = parent["physical_manifest_sha256"]
    if len(retained) != 8 or len(manifests) != 22 or len(set(manifests.values())) != 22:
        raise ValueError("enrollment requires the sealed eight and 22 distinct eligible manifests")
    ranked = {}
    for dataset in ("DS26", "DS29"):
        ranked[dataset] = sorted(
            (ident for ident in manifests.keys() - set(retained) if ident.startswith(dataset)),
            key=lambda ident: (rank("whole-rf-panel-v1", manifests[ident]), ident),
        )
    return [*retained, *(group[0] for group in ranked.values())], ranked


def spread_visits(visits_by_rf, total, manifest):
    """Spend equal original visit counts on a final-census-stratified archive control."""
    count = sum(len(visits) for visits in visits_by_rf.values())
    if not 0 <= total <= count or not count:
        raise ValueError("invalid original-visit allocation")
    quota = {rf: divmod(total * len(visits), count) for rf, visits in visits_by_rf.items()}
    allocations = {rf: floor for rf, (floor, _) in quota.items()}
    remaining = total - sum(allocations.values())
    for rf in sorted(quota, key=lambda rf: (-quota[rf][1], rf))[:remaining]:
        allocations[rf] += 1
    return {
        visit
        for rf, visits in visits_by_rf.items()
        for visit in sorted(
            visits, key=lambda visit: (rank("whole-rf-spread-v1", manifest, rf, visit), visit)
        )[: allocations[rf]]
    }


def schedule(doc, centers):
    provenance = doc["provenance"]
    manifest = doc["source"]["input_manifest_sha256"]
    selected_rf = rf_routing.choose_rf(manifest, centers.values())
    visits_by_rf = {rf: [] for rf in sorted(set(centers.values()))}
    visits = []
    for visit, pair in selective_capture.visit_pairs(doc["source"]["probes"]):
        rf = pair[0]["actual_rf_hz"]
        if any(centers[p["channel"], p["edge"]] != rf or p["actual_rf_hz"] != rf for p in pair):
            raise ValueError("the stereo pair differs from its configured physical RF")
        visits_by_rf[int(rf)].append(visit)
        visits.append((visit, int(rf)))
    invalid = [row["visit"] for row in provenance["excluded_windows"]]
    if len(visits) != provenance["processed_windows"] or sorted(
        [*invalid, *(v for v, _ in visits)]
    ) != list(range(provenance["window_count"])):
        raise ValueError("invalid and assigned pairs must partition all physical visits")
    whole = visits_by_rf[selected_rf]
    spread = spread_visits(visits_by_rf, len(whole), manifest)
    return dict(
        assigned_rf_hz=selected_rf,
        physical_manifest_sha256=manifest,
        valid_visits_by_rf={rf: len(group) for rf, group in visits_by_rf.items()},
        visits=visits,
        invalid=invalid,
        whole_original_visits=whole,
        spread_original_visits=sorted(spread),
    )


def project(fast, original, plan):
    selective_capture.same_support(fast, original)
    choices = {policy: set(plan[f"{policy}_original_visits"]) for policy in ("whole", "spread")}
    streams = {policy: [] for policy in POLICIES}
    counts, lineage = {}, []
    parents = (selective_capture.visit_pairs(doc["source"]["probes"]) for doc in (fast, original))
    for (visit, short), (_, long), (scheduled_visit, rf) in zip(
        *parents, plan["visits"], strict=True
    ):
        if (visit, short[0]["actual_rf_hz"]) != (scheduled_visit, rf):
            raise ValueError("a valid visit changed its scheduled physical RF")
        baseline = [prior.negative_rescue.positive(p) for p in short]
        per_rf = counts.setdefault(rf, {policy: Counter() for policy in POLICIES})
        witness = dict(
            visit=visit,
            rf_hz=rf,
            whole_original=visit in choices["whole"],
            spread_original=visit in choices["spread"],
            fast_pair_sha256=digest(short),
            original_pair_sha256=digest(long),
        )
        lineage.append(witness)
        for policy in POLICIES:
            use_original = policy == "original" or (policy in choices and visit in choices[policy])
            pair = long if use_original else short
            streams[policy].extend(pair)
            stat = per_rf[policy]
            prior.add_census(stat, pair)
            passed = [prior.negative_rescue.positive(p) for p in pair]
            stat.update(
                original_visits=int(use_original),
                gained_positive_probes=sum(
                    a and not b for a, b in zip(passed, baseline, strict=True)
                ),
                lost_positive_probes=sum(
                    b and not a for a, b in zip(passed, baseline, strict=True)
                ),
            )
    return streams, counts, lineage


def source_files(report):
    sources = (
        Path(__file__),
        Path(rf_routing.__file__),
        Path(selective_capture.__file__),
        Path(two_rate_holdout.__file__),
        Path(prior.__file__),
        Path(prior.roster.__file__),
        Path(prior.support_cross_trial.__file__),
        Path(prior.support_cross_trial.margin_admission_trial.__file__),
        report / "PROTOCOL.md",
    )
    return {str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): _sha(p) for p in sources}


def columns(rows):
    return {(row["id"], row["condition"]): row for row in rows}


def controls(groups, release):
    fast, _ = prior.reuse_controls(groups, release)
    lock = read(checked(prior.REPORT / "prediction-lock.json", PARENT_PREDICTIONS))
    plan = read(prior.fixed.member(prior.REPORT, lock, "source-lock.json"))
    if any(plan[k] != v for k, v in release.items()):
        raise ValueError("prior full original control used a different receiver release")
    first = columns(
        prior.rows_from(prior.fixed.member(prior.REPORT, lock, "positions-first.jsonl.gz"))
    )
    final = columns(prior.rows_from(prior.fixed.member(prior.REPORT, lock, "positions.jsonl.gz")))
    return fast, first, final


def verified(row, ident, binding, native_sha, policy, pin):
    match = prior.verified_control(row, binding, native_sha, policy, pin)
    if match["id"] != ident:
        raise ValueError("reused control names a different recording")
    return dict(match, method=f"rf_lane_{policy}")


def stage(report, work):
    if (report / "source-lock.json").exists() or (report / "membership-lock.json").exists():
        raise FileExistsError("whole-RF enrollment is already frozen")
    parent = prior.inventory()
    selected, ranked = enroll(parent)
    groups, media, bindings, extensions, release = prior.roster.inventory()
    if groups != parent["prior_roster_membership"] or media != parent["stock_archives"]:
        raise ValueError("authenticated source roster changed")
    fast_controls, first_controls, final_controls = controls(groups, release)
    work.mkdir(parents=True, exist_ok=False)
    save_json(
        report / "membership-lock.json",
        dict(
            selected=selected,
            retained=parent["selected"],
            prospective=selected[8:],
            anchors=parent["timing_anchors"],
            prospective_ranked=ranked,
            physical_manifest_sha256=parent["physical_manifest_sha256"],
            parent_membership_sha256=prior.MEMBERSHIP,
            protocol_sha256=_sha(report / "PROTOCOL.md"),
        ),
    )
    jobs, reused, first, audit = {}, [], [], {}
    for ident in selected:
        case, request, content, fast, original, manifests = prior.bind(
            ident, media, bindings, extensions
        )
        centers, _, _ = prior.roster.staggered_reconstruction_trial.tune_plan(case)
        plan = schedule(fast, centers)
        if plan["physical_manifest_sha256"] != parent["physical_manifest_sha256"][ident]:
            raise ValueError("enrolled physical manifest changed")
        streams, counts, lineage = project(fast, original, plan)
        schedule_path = report / "schedules" / f"{ident}.json"
        lineage_path = report / "lineage" / f"{ident}.jsonl.gz"
        save_json(schedule_path, plan)
        pack(lineage_path, lineage)
        original_sha = case["native"]["sha256"]
        fast_sha = media[ident]["native_sha256"]
        fast_path = Path(media[ident]["path"])
        fast_archive = media[ident]
        if fast_path.is_relative_to(Path("/var/tmp")):
            archived = report / "stock" / f"{ident}.json.gz"
            parent_archive = prior.REPORT / "stock" / archived.name
            if parent_archive.is_file():
                data = parent_archive.read_bytes()
                if sha256(gzip.decompress(data)).hexdigest() != fast_sha:
                    raise ValueError("preserved prior fast archive differs from source bytes")
            else:
                data = gzip.compress(fast_path.read_bytes(), mtime=0)
            write(archived, data)
            fast_archive = dict(
                path=str(archived), file_sha256=_sha(archived), native_sha256=fast_sha
            )
        fast_pin = prior.CONTROLS[ident in groups["fresh"]][2]
        reused.append(
            verified(fast_controls[ident], ident, bindings[ident], fast_sha, "fast", fast_pin)
        )
        if ident in parent["selected"]:
            key = ident, "original"
            reused.append(
                verified(
                    final_controls[key],
                    ident,
                    bindings[ident],
                    original_sha,
                    "original",
                    PARENT_PREDICTIONS,
                )
            )
            initial = first_controls[key]
            if (
                any(initial[k] != v for k, v in bindings[ident].items())
                or initial["native_sha256"] != original_sha
            ):
                raise ValueError("prior first compact attempt changed captured factors or region")
            first.append(initial)
        for policy in ("whole", "spread", *(() if ident in parent["selected"] else ("original",))):
            payload = content
            if policy != "original":
                fingerprint = "sha256:" + digest(
                    ["whole-rf-panel/v1", policy, fast_sha, original_sha, _sha(schedule_path)]
                )
                provenance = dict(
                    fast["provenance"],
                    run_id="whole-rf-" + fingerprint[7:35],
                    scope="Archived exclusive RF detector assignment",
                )
                provenance.pop("detector_sha256")
                document = dict(
                    fast,
                    source=dict(
                        fast["source"], probes=streams[policy], analysis_manifest_sha256=fingerprint
                    ),
                    provenance=provenance,
                )
                payload = encoded(document) + b"\n"
            jobs[ident, policy] = dict(
                prior.prepare(
                    work, ident, case, request, payload, bindings[ident], release, policy
                ),
                method=f"rf_lane_{policy}",
            )
        audit[ident] = dict(
            **bindings[ident],
            original_archive=case["native"],
            fast_archive=fast_archive,
            manifests=manifests,
            causal_snapshots=request["causal_snapshots"],
            counts_per_rf=counts,
            assigned_rf_hz=plan["assigned_rf_hz"],
            valid_visits=len(plan["visits"]),
            invalid_visits=len(plan["invalid"]),
            original_visits=len(plan["whole_original_visits"]),
            schedule_sha256=_sha(schedule_path),
            lineage_sha256=_sha(lineage_path),
            delivery_clocks_sha256=digest(fast["delivery_clocks"]),
            excluded_windows_sha256=digest(fast["provenance"]["excluded_windows"]),
            complete_probes_sha256={p: digest(stream) for p, stream in streams.items()},
        )
        print(
            ident,
            audit[ident]["assigned_rf_hz"],
            audit[ident]["original_visits"],
            audit[ident]["valid_visits"],
            "staged",
            flush=True,
        )
    priority = [*selected[:2], *selected[8:], *selected[2:8]]
    ordered = [jobs[i, policy] for policy in POLICIES for i in priority if (i, policy) in jobs]
    for index, job in enumerate(ordered):
        job["cpu"] = CPUS[index % len(CPUS)]
    save_json(report / "packet-audit.json", audit)
    pack(report / "reused-controls.jsonl.gz", reused)
    pack(report / "prior-original-first-attempts.jsonl.gz", first)
    files = (
        "membership-lock.json",
        "packet-audit.json",
        "reused-controls.jsonl.gz",
        "prior-original-first-attempts.jsonl.gz",
        "PROTOCOL.md",
        *(
            f"{folder}/{p.name}"
            for folder in ("schedules", "lineage", "stock")
            for p in sorted((report / folder).glob("*"))
        ),
    )
    save_json(
        report / "source-lock.json",
        dict(
            cases=selected,
            jobs=ordered,
            cpus=CPUS,
            limit_s=LIMIT,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
            sources=source_files(report),
            files={name: _sha(report / name) for name in files},
            **release,
        ),
    )
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(report / "source-lock.json")))


def attempt(work, report, row, plan):
    folder = work / row["id"] / row["condition"]
    receipt = folder / "attempt.json"
    outcome = read(receipt) if receipt.is_file() else prior.support_cross_trial.service(work, row)
    if any(outcome[k] != v for k, v in row.items()):
        raise ValueError("terminal row differs from its sealed numerical request")
    resources = outcome["position_resources"]
    if outcome["terminal"] == "success" and not resources:
        raise ValueError("successful position has no measured service resources")
    for mark in (resources or {}).get("start"), (resources or {}).get("end"):
        if mark and (
            mark["cpus"] != [row["cpu"]]
            or mark["memory.max"] != plan["memory_bytes"]
            or mark["memory.swap.max"]
            or mark["memory.swap.current"]
        ):
            raise ValueError("worker escaped its authorized CPU or no-swap cap")
    log = checked(folder / "service.log", outcome["log_sha256"])
    write(
        report / "logs" / f"{row['id']}-{row['condition']}.log.gz",
        gzip.compress(log.read_bytes(), mtime=0),
    )
    return outcome


def run(report, work):
    plan_sha = read(work / "launch-lock.json")["source_lock_sha256"]
    plan = read(checked(report / "source-lock.json", plan_sha))
    if plan["limit_s"] != prior.support_cross_trial.LIMIT or plan["sources"] != source_files(
        report
    ):
        raise ValueError("staged worker code or limit changed")
    check_release(plan)
    for name, fingerprint in plan["files"].items():
        checked(report / name, fingerprint)

    def lane(cpu):
        return [attempt(work, report, row, plan) for row in plan["jobs"] if row["cpu"] == cpu]

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        completed = [row for rows in pool.map(lane, CPUS) for row in rows]
    reused = prior.rows_from(report / "reused-controls.jsonl.gz")
    all_positions = columns(completed + reused)
    expected = [(ident, policy) for ident in plan["cases"] for policy in POLICIES]
    if all_positions.keys() != set(expected) or len(completed + reused) != len(expected):
        raise ValueError("missing or repeated case-policy result")
    pack(report / "positions.jsonl.gz", [all_positions[key] for key in expected])
    dependencies = dict(
        plan["files"],
        **{name: _sha(report / name) for name in ("source-lock.json", "positions.jsonl.gz")},
    )
    dependencies.update(
        {str(p.relative_to(report)): _sha(p) for p in (report / "logs").glob("*.gz")}
    )
    save_json(report / "prediction-lock.json", dict(cases=plan["cases"], files=dependencies))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--work", required=True, type=local_output)
    args = parser.parse_args()
    {"stage": stage, "run": run}[args.action](args.report, args.work)


if __name__ == "__main__":
    main()
