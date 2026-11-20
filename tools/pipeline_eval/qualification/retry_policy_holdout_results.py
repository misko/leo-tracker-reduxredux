"""Authenticate held waveform outputs, apply frozen causal retry policies, and fit positions."""

import argparse
import gzip
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from ..variants.retry_cadence import RetryCadence
from ..variants.retry_policy_holdout import TwoFailureCadence
from ..variants.selective_capture import visit_pairs
from . import capture_whole_results as whole
from . import retry_cadence_trial
from . import retry_policy_holdout as trial
from .field_exact_waveform_results import parity
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .single_pass_position_results import collect

FULL = "holdout_full"
PRIMARY = trial.METHOD
MISS = "holdout_miss_2s"
TWO = "holdout_two_failures_800ms"
CONTROL = "holdout_two_failures_hash"
MODES = (FULL, PRIMARY, MISS, TWO, CONTROL)
LABELS = (
    "Full conditional",
    "Primary only",
    "Two seconds after a failed retry",
    "0.8 seconds after two failures",
    "Physical-key count-matched hash",
)
digest = trial.BASE.recording.digest


def freeze_policy(work):
    lock, _ = trial.BASE.configure(work)
    program = Path(__file__)
    path = trial.REPORT / "policy-lock.json"
    if path.exists() or (work / "schedule.json").exists() or (work / "raw-exits.json").exists():
        raise FileExistsError("freeze retry rules before the complete raw outcomes arrive")
    save_json(
        path,
        dict(
            case=trial.IDENT,
            source_lock_sha256=_sha(work / "source-lock.json"),
            rules=dict(zip(MODES, LABELS, strict=True)),
            control_seed=lock["capture"]["input_manifest_sha256"],
            implementation={
                str(p): _sha(p)
                for p in (
                    program,
                    Path(TwoFailureCadence.observed.__code__.co_filename),
                    Path(RetryCadence.observed.__code__.co_filename),
                    Path(retry_cadence_trial.__file__),
                )
            },
        ),
    )


def schedules(events, seed):
    every, one, two = {v for v, *_ in events}, set(), set()
    by_key = defaultdict(list)
    miss, streak = RetryCadence("miss"), TwoFailureCadence()
    previous = -1
    for visit, key, now, hit in events:
        if now < previous:
            raise ValueError("authenticated delivery clock is out of order")
        previous = now
        by_key[key].append(visit)
        for timer, chosen in ((miss, one), (streak, two)):
            if timer.allows(key, now):
                chosen.add(visit)
                timer.observed(key, now, hit)
    control = set()
    for key, visits in by_key.items():
        n = sum(v in two for v in visits)
        ordered = sorted(
            visits, key=lambda v: (digest(["retry-policy-holdout-v1", seed, key, v]), v)
        )
        control.update(ordered[:n])
    return dict(zip(MODES, (every, set(), one, two, control), strict=True))


def proofs(work, lock, original, primary, selected):
    original_rows, primary_rows = (
        dict(visit_pairs(doc["source"]["probes"])) for doc in (original, primary)
    )
    prior = lock["independent"]
    earlier = trial.ASSAY.read_gzip(whole_iq.checked(Path(prior["path"]), prior["sha256"]))
    whole_iq.checked(Path(prior["input"]), prior["input_sha256"])
    if earlier["input_lock_sha256"] != prior["input_sha256"] or earlier["case"] != trial.IDENT:
        raise ValueError("old held assay changed physical lineage")
    counts = Counter()
    now = whole_iq.read(work / "smoke.json")
    if now["source_lock_sha256"] != _sha(work / "source-lock.json"):
        raise ValueError("prospective witnesses differ from the waveform plan")
    for group, rows in (("prior-assay", earlier["rows"]), ("fresh-smoke", now["rows"])):
        for row in rows:
            v = row["visit"]
            a, b = (
                (row["evidence"][k] for k in ("conditional", "primary12"))
                if group == "prior-assay"
                else (row["conditional"], row["primary"])
            )
            if (
                tuple(a["probes"]) != original_rows[v]
                or tuple(b["probes"]) != primary_rows[v]
                or a["attempts"][:2] != b["attempts"]
                or (v in selected and row["iq_sha256"] != selected[v]["iq_sha256"])
            ):
                raise ValueError(
                    "independent witness disagrees with the whole primary factor stream"
                )
            if v not in selected and (a["public"] != b["public"] or len(a["attempts"]) != 2):
                raise ValueError("retained double-negative witness had an original retry")
            counts[f"{group}_{'replayed' if v in selected else 'double_negative'}"] += 1
    return dict(counts)


def assemble(work, lock):
    original = trial.signed_archive(lock)
    rows = dict(visit_pairs(original["source"]["probes"]))
    replayed, raw = collect(work, lock)
    if set(replayed) != trial.roster(rows):
        raise ValueError("fresh primary outputs do not cover the frozen final-positive roster")
    complete = []
    for v, pair in rows.items():
        if v in replayed:
            record = replayed[v]
            now = record["probes"]
            inferred = [[rx, 12, trial.ASSAY.positive(p)] for rx, p in enumerate(now)]
            if record["attempts"] != inferred or len(now) != 2:
                raise ValueError("fresh raw visit did not complete both original primaries")
            complete.extend(now)
        else:
            complete.extend(pair)
    primary = dict(original, source=dict(original["source"], probes=complete))
    factor_check = parity(primary, original)
    if (
        factor_check["unmatched_probes"]
        or not factor_check["probe_order_exact"]
        or not all(factor_check["clock_fields_exact"].values())
        or not all(factor_check["capture_validity_fields_exact"].values())
        or any(
            r["gate_formula_errors"] or r["candidate_schema_errors"]
            for r in factor_check["counts"].values()
        )
    ):
        raise ValueError("fresh waveform primary factors changed physical support")
    raw["witnesses"] = proofs(work, lock, original, primary, replayed)
    raw["detector_cpu_s"] = sum(r["cpu_ns"] for r in replayed.values()) * 1e-9
    raw["coarse_cpu_s"] = sum(r["coarse_cpu_ns"] for r in replayed.values()) * 1e-9
    raw["primary_cpu_ms"] = distribution([r["cpu_ns"] * 1e-6 for r in replayed.values()])
    raw["detector_wall_ms"] = distribution([r["wall_ns"] * 1e-6 for r in replayed.values()])
    return original, primary, raw, factor_check


def counters(ident, original, primary):
    full, initial = (dict(visit_pairs(doc["source"]["probes"])) for doc in (original, primary))
    events = retry_cadence_trial.opportunities(full, initial, original["delivery_clocks"])
    active = schedules(events, original["source"]["input_manifest_sha256"])
    hits = {v for v, _, _, gated in events if gated}
    positives = sum(trial.ASSAY.positive(p) for pair in initial.values() for p in pair)
    opportunities = {v: key for v, key, _, _ in events}
    keys = Counter(opportunities[v] for v in active[TWO])
    if keys != Counter(opportunities[v] for v in active[CONTROL]):
        raise ValueError("conservative and hash control work differ by physical key")
    support = []
    for mode, visits in active.items():
        support.append(
            dict(
                id=ident,
                policy=mode,
                valid_visits=len(initial),
                opportunities=len(events),
                attempts=len(visits),
                failures=len(visits - hits),
                rescues=len(visits & hits),
                original_rescues=len(hits),
                positives=positives + len(visits & hits),
                rx0_attempts=sum(opportunities[v][0] == 0 for v in visits),
                rx1_attempts=sum(opportunities[v][0] == 1 for v in visits),
            )
        )
    return full, initial, events, active, support


def policy_input(original, initial, full, selected, mode, binding):
    probes = [p for v, pair in initial.items() for p in (full[v] if v in selected else pair)]
    if mode == FULL:
        if probes != original["source"]["probes"]:
            raise ValueError("full conditional comparator does not reproduce its signed factors")
        return original
    provenance, source = original["provenance"], original["source"]
    detector = digest([provenance.get("detector_sha256"), mode, binding])
    analysis = digest([source["analysis_manifest_sha256"], detector, probes])
    return dict(
        original,
        source=dict(source, probes=probes, analysis_manifest_sha256=analysis),
        provenance=dict(
            provenance,
            detector_sha256=detector,
            run_id="retry-" + analysis[7:39],
            scope="Complete physical DS26-0162 support with policy " + mode,
        ),
    )


def prepare(work):
    lock, _ = trial.BASE.configure(work)
    policy = whole_iq.read(trial.REPORT / "policy-lock.json")
    if policy["source_lock_sha256"] != _sha(work / "source-lock.json"):
        raise ValueError("causal rules were frozen for another waveform plan")
    for path, expected in policy["implementation"].items():
        whole_iq.checked(Path(path), expected)
    original, primary, raw, factor_check = assemble(work, lock)
    full, initial, events, by_mode, rows = counters(trial.IDENT, original, primary)
    if len(events) != len(set(by_mode[FULL])) or len(full) != len(initial):
        raise ValueError("all eligible physical retry visits are required")
    binding = _sha(work / "source-lock.json")
    native, fingerprints, seen = {}, {}, {}
    for mode, visits in by_mode.items():
        document = policy_input(original, initial, full, visits, mode, binding)
        fingerprint = digest(document["source"]["probes"])
        fingerprints[mode] = fingerprint
        path = work / (seen.setdefault(fingerprint, mode) + ".json")
        if not path.exists():
            write(path, encoded(document) + b"\n")
        elif seen[fingerprint] == mode and path.read_bytes() != encoded(document) + b"\n":
            raise ValueError("policy input changed since replay")
        native[mode] = dict(path=str(path), sha256=_sha(path), shared_with=seen[fingerprint])
    save_json(
        work / "schedule.json",
        dict(
            source_lock_sha256=binding,
            native=native,
            fingerprints=fingerprints,
            support=rows,
            raw=raw,
            factor_parity=factor_check,
            policy_sha256=_sha(Path(__file__)),
            events=[
                dict(
                    visit=v,
                    rx=key[0],
                    rf=key[1],
                    ns=t,
                    rescue=hit,
                    **{mode: v in chosen for mode, chosen in by_mode.items()},
                )
                for v, key, t, hit in events
            ],
        ),
    )
    print(rows, flush=True)


def positions(work):
    lock, _ = trial.BASE.configure(work)
    plan = whole_iq.read(work / "schedule.json")
    if plan["source_lock_sha256"] != _sha(work / "source-lock.json"):
        raise ValueError("position schedule is missing its frozen waveform bind")
    case, original = whole_iq.binding(trial.IDENT)
    jobs = [(mode, row) for mode, row in plan["native"].items() if row["shared_with"] == mode]
    buckets = [jobs[i :: len(trial.CPUS)] for i in range(len(trial.CPUS))]

    def worker(items, cpu):
        for mode, row in items:
            path = whole_iq.checked(Path(row["path"]), row["sha256"])
            directory = work / f"position-{mode}"
            if not directory.exists():
                whole.terminal_position(work, mode, path, directory, cpu, lock, case, original)
            print(mode, whole_iq.read(directory / "terminal.json")["exit_code"], flush=True)

    with ThreadPoolExecutor(max_workers=len(trial.CPUS)) as pool:
        calls = [
            pool.submit(worker, items, cpu) for cpu, items in zip(trial.CPUS, buckets, strict=True)
        ]
        for call in calls:
            call.result()


def position_receipts(work, plan, lock):
    _, original = whole_iq.binding(trial.IDENT)
    common = dict(
        id=trial.IDENT,
        mode="matched-tile",
        cohort="DS26-0162 prospective retry holdout",
        paired_capture_sha256=lock["original"]["native"]["sha256"],
        original_request_sha256=lock["original"]["request"]["sha256"],
        catalog_sha256=lock["original"]["catalog"]["sha256"],
        tile=lock["original"]["tile"],
    )
    rows, clocks = [], {}
    for mode, source in plan["native"].items():
        folder = work / f"position-{source['shared_with']}"
        terminal = whole_iq.read(folder / "terminal.json")
        whole_iq.checked(folder / "service.log", terminal["log_sha256"])
        start = whole_iq.read(folder / "plan.json")
        raw = whole_iq.read(folder / "raw.json")
        request = whole_iq.checked(folder / "recording/request.json", raw["request_sha256"])
        path = whole_iq.checked(Path(source["path"]), source["sha256"])
        if (
            start["source_lock_sha256"] != plan["source_lock_sha256"]
            or raw["native_sha256"] != "sha256:" + source["sha256"]
        ):
            raise ValueError("compact terminal does not bind its policy factors")
        whole_iq.verify_request(
            whole_iq.read(request),
            original,
            native_path=str(path),
            native_sha256=raw["native_sha256"],
        )
        clocks[mode] = dict(
            wall_s=terminal["wall_s"],
            reused=source["shared_with"] != mode,
            exit_code=terminal["exit_code"],
            cpu=start["cpu"],
        )
        if terminal["exit_code"] == 0:
            end = whole_iq.read(folder / "end.json")
            if (
                end["cpus"] != [start["cpu"]]
                or end["memory.max"] != whole_iq.MEMORY
                or end["memory.swap.max"]
                or end["memory.swap.current"]
                or end["memory.events.oom_kill"]
            ):
                raise ValueError("compact service escaped its requested resource cap")
            clocks[mode]["end"] = end
            result = whole_iq.read(folder / "position.json")
        else:
            result = dict(
                status="timed_out" if terminal["exit_code"] == 124 else "failed",
                reason="Compact position returned a nonzero terminal",
                boundary="Whole recording with selected original retry factors",
                metrics={},
                arms={a: {"latlon": None} for a in ARMS},
            )
        validate_result(result)
        rows.append(dict(common, method=mode, result=result, native_sha256=source["sha256"]))
    return rows, clocks


def retrospective():
    result = []
    for ident in retry_cadence_trial.PARENTS:
        original, earlier, _, _ = retry_cadence_trial.sources(ident)
        _, _, _, _, rows = counters(ident, original, earlier)
        result.extend(rows)
    return result


def publish(work):
    from .retry_policy_holdout_figures import render

    report = trial.REPORT
    lock, _ = trial.BASE.configure(work)
    plan = whole_iq.read(work / "schedule.json")
    if plan["policy_sha256"] != _sha(Path(__file__)) or plan["source_lock_sha256"] != _sha(
        work / "source-lock.json"
    ):
        raise ValueError("prospective scheduling proof differs from locked inputs")
    rows, clocks = position_receipts(work, plan, lock)
    files = ["PROTOCOL.md", "source-lock.json", "policy-lock.json"]
    for f in ("launch.json", "raw-exits.json", "smoke.json", "schedule.json"):
        destination = Path("receipts") / f
        write(report / destination, (work / f).read_bytes())
        files.append(str(destination))
    for source in sorted(work.glob("position-*/*")) + sorted(
        work.glob("position-*/recording/request.json")
    ):
        if source.is_file():
            path = Path("receipts") / source.relative_to(work)
            write(report / path, source.read_bytes())
            files.append(str(path))
    for mode, row in plan["native"].items():
        path = Path("factors") / f"{mode}.json.gz"
        write(
            report / path, gzip.compress(Path(row["path"]).read_bytes(), compresslevel=4, mtime=0)
        )
        files.append(str(path))
    for cpu, _, _ in lock["workers"]:
        for suffix in (".jsonl", ".log"):
            source = work / f"cpu-{cpu}{suffix}"
            body = source.read_bytes()
            path = Path("receipts") / source.name
            if suffix == ".jsonl":
                path = path.with_suffix(".jsonl.gz")
                body = gzip.compress(body, compresslevel=4, mtime=0)
            write(report / path, body)
            files.append(str(path))
    support = plan["support"]
    csv_file(report / "retry-counts.csv", support)
    csv_file(report / "retrospective-counts.csv", retrospective())
    save_json(
        report / "resources.json",
        dict(raw=plan["raw"], compact=clocks, parity=plan["factor_parity"]),
    )
    whole.pack(report / whole.POS, rows)
    files.extend(("retry-counts.csv", "retrospective-counts.csv", "resources.json", whole.POS))
    save_json(
        report / "prediction-lock.json",
        dict(cases=[trial.IDENT], files={f: _sha(report / f) for f in files}),
    )
    _, (reference,) = held_references(None, [trial.IDENT])
    scores = whole.geographic(rows, {trial.IDENT: reference})
    csv_file(report / "scores.csv", scores)
    csv_file(
        report / "v5-controls.csv",
        [
            dict(
                id=trial.IDENT,
                role=role,
                arm=arm,
                **{k: r.get(k) for k in ("status", "error_km", "rf_rms_hz")},
            )
            for role in ROLES
            for arm in ARMS
            for r in [reference["reference"][role][arm]]
        ],
    )
    render(report, support)
    save_json(
        report / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(report / "prediction-lock.json"),
            files={f: _sha(report / f) for f in ("scores.csv", "v5-controls.csv", "figures.json")},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze-policy", "prepare", "position", "publish"))
    parser.add_argument("work", type=Path, nargs="?", default=trial.WORK)
    args = parser.parse_args()
    with trial.configured():
        {
            "freeze-policy": freeze_policy,
            "prepare": prepare,
            "position": positions,
            "publish": publish,
        }[args.action](args.work)
