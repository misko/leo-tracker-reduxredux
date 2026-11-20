"""Freeze and replay the causal fast-trajectory audit at fixed original-call counts."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean
from time import process_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json
from ..variants import adaptive_visits as policy
from . import cascade_audit_trial as prior
from . import complete_detector_roster as fixed
from . import one_lane_roster as roster
from . import support_cross_trial as compact
from . import two_rate_holdout_trial as paired
from .full_v5_check import _sha
from .phase_support_results import pack

REPORT = fixed.SCREEN / "coarse-and-navigation/adaptive-visits"
DEVELOPMENT = ("DS26-0036", "DS29-0174")
ANCHORS = ("DS26-0237", "DS29-0082")
THRESHOLDS = (1.0, 1.5, 2.5)
MODES = ("novel", "hash")
LIMIT = 150
PRIOR_ENDPOINT_SHA = "756c534674f1f63004393637336ec37b0b42eac423f672266a34665f30de6e72"


def select_holdout(cases):
    out = list(ANCHORS)
    for series in ("DS26", "DS29"):
        eligible = [i for i in cases if i.startswith(series) and i not in (*DEVELOPMENT, *ANCHORS)]
        ordered = sorted(eligible, key=lambda i: policy.digest("holdout", cases[i]["manifest"]))
        out.extend(ordered[:2])
    if len(set(out)) != 6:
        raise ValueError("the predeclared holdout requires six unique physical inputs")
    return sorted(out)


def summarize(rows):
    return dict(
        calls=len(rows) // 2,
        gained=sum(not row["fast_positive"] and row["original_positive"] for row in rows),
        lost=sum(row["fast_positive"] and not row["original_positive"] for row in rows),
        changed=sum(row["changed"] for row in rows),
        changed_winners=sum(row["winner_changed"] for row in rows),
        actions=len({row["visit"] for row in rows if row["trigger"] == "novelty"}),
    )


def selections(fast, threshold, scores):
    manifest = fast["source"]["input_manifest_sha256"]
    chosen, windows = policy.schedule(scores, threshold)
    comparison = policy.matched_control(manifest, chosen, windows)
    counts = [
        Counter((row["rf_hz"], row["token"]) for row in group) for group in (chosen, comparison)
    ]
    if counts[0] != counts[1]:
        raise ValueError("an independent hash control changed the RF or token allowance")
    return dict(novel=chosen, hash=comparison)


def develop(dev):
    trials = []
    for threshold in THRESHOLDS:
        contrasts = {}
        for ident, (fast, original, scores) in dev.items():
            selections_by_mode = selections(fast, threshold, scores)
            m = {
                mode: summarize(policy.project(fast, original, chosen)[1])
                for mode, chosen in selections_by_mode.items()
            }
            n, h = (m[mode] for mode in MODES)
            if not n["calls"] or n["calls"] != h["calls"]:
                raise ValueError("unmatched development allowance")
            contrast = (n["gained"] - n["lost"] - h["gained"] + h["lost"]) / n["calls"]
            contrasts[ident] = dict(m, difference=contrast)
        trials.append(
            dict(
                threshold=threshold,
                cases=contrasts,
                mean_difference=mean(item["difference"] for item in contrasts.values()),
            )
        )
    winning = max(trials, key=lambda item: (item["mean_difference"], item["threshold"]))
    return winning["threshold"], trials


def source_paths():
    files = (Path(__file__), Path(policy.__file__), REPORT / "PROTOCOL.md")
    return {str(p.resolve()): _sha(p.resolve()) for p in files}


def stage(work, cpus):
    if (REPORT / "source-lock.json").exists():
        raise FileExistsError("the held measure is already staged")
    proof = whole_iq.read(whole_iq.checked(prior.REPORT / "endpoint-lock.json", PRIOR_ENDPOINT_SHA))
    parent = whole_iq.read(fixed.member(prior.REPORT, proof, "source-lock.json"))
    groups, archives, bindings, extensions, release = roster.inventory()
    if parent["release"] != release or set(groups["all"]) != parent["cases"].keys():
        raise ValueError("adaptive visits require the same complete earlier release and roster")
    held = select_holdout(parent["cases"])
    work.mkdir(parents=True, exist_ok=False)
    dev = {}
    for ident in DEVELOPMENT:
        _, _, _, fast, original, _ = paired.bind(ident, archives, bindings, extensions)
        dev[ident] = (fast, original, list(policy.visit_scores(fast)))
    cut, ladder = develop(dev)
    del dev
    seal = REPORT / "rule-lock.json"
    save_json(
        seal,
        dict(
            development=DEVELOPMENT,
            held=held,
            threshold=cut,
            ladder=ladder,
            files=source_paths(),
            prior_endpoint_sha256=PRIOR_ENDPOINT_SHA,
        ),
    )
    print("Frozen", cut, "held", " ".join(held), flush=True)
    jobs, cases = [], {}
    for index, ident in enumerate(held):
        case, request, _, fast, original, _ = paired.bind(ident, archives, bindings, extensions)
        manifest = fast["source"]["input_manifest_sha256"]
        if manifest != parent["cases"][ident]["manifest"]:
            raise ValueError("held physical manifest differs from its source seal")
        start = process_time_ns()
        scores = list(policy.visit_scores(fast))
        cuts = selections(fast, cut, scores)
        selector_cpu_ms = (process_time_ns() - start) / 1e6
        plan = dict(
            manifest=manifest,
            valid_visits=fast["provenance"]["processed_windows"],
            eligible_visits=len(scores),
            selector_cpu_ms=selector_cpu_ms,
            fast_sha256=archives[ident]["native_sha256"],
            **bindings[ident],
        )
        for modes_index, mode in enumerate(MODES):
            probes, witness = policy.project(fast, original, cuts[mode])
            native_hash = whole_iq.recording.digest(
                [policy.SALT, mode, ident, _sha(seal), cuts[mode]]
            )
            source = dict(fast["source"], probes=probes, analysis_manifest_sha256=native_hash)
            provenance = dict(fast["provenance"], run_id="adaptive-visits-" + native_hash[7:31])
            provenance.pop("detector_sha256")
            materialized = dict(fast, source=source, provenance=provenance)
            cpu = cpus[(index + modes_index) % len(cpus)]
            row = paired.prepare(
                work,
                ident,
                case,
                request,
                encoded(materialized) + b"\n",
                bindings[ident],
                release,
                mode,
                cpu=cpu,
            )
            path = REPORT / "lineage" / f"{ident}-{mode}.jsonl.gz"
            pack(path, witness)
            jobs.append(dict(row, method=f"adaptive_visits_{mode}", witness_sha256=_sha(path)))
            plan[mode] = dict(summarize(witness), witness_sha256=_sha(path))
        cases[ident] = plan
        print(ident, plan["novel"], plan["hash"], flush=True)
    save_json(
        REPORT / "source-lock.json",
        dict(
            cases=cases,
            jobs=jobs,
            release=release,
            cpus=cpus,
            limit_s=LIMIT,
            rule_lock_sha256=_sha(seal),
            prior_endpoint_sha256=PRIOR_ENDPOINT_SHA,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
        ),
    )
    save_json(work / "source-lock.json", dict(sha256=_sha(REPORT / "source-lock.json")))


def run(work):
    source = whole_iq.read(
        whole_iq.checked(
            REPORT / "source-lock.json", whole_iq.read(work / "source-lock.json")["sha256"]
        )
    )
    frozen = whole_iq.read(whole_iq.checked(REPORT / "rule-lock.json", source["rule_lock_sha256"]))
    for path, digest in frozen["files"].items():
        whole_iq.checked(Path(path), digest)
    roster.check_release(source["release"])

    def lane(cpu):
        for row in source["jobs"]:
            if row["cpu"] == cpu:
                compact.service(work, row)

    with (
        patch.object(compact, "LIMIT", source["limit_s"]),
        ThreadPoolExecutor(max_workers=len(source["cpus"])) as pool,
    ):
        list(pool.map(lane, source["cpus"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("--work", required=True, type=local_output)
    parser.add_argument("--cpus", type=int, nargs="+", default=(22, 16))
    args = parser.parse_args()
    if args.action == "stage":
        if len(set(args.cpus)) != len(args.cpus) or not set(args.cpus) <= {16, 22}:
            parser.error("use the reserved CPU 22 and optionally 16")
        stage(args.work, tuple(args.cpus))
    else:
        run(args.work)
