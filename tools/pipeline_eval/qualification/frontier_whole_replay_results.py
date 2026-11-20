"""Seal, compare and chart a prospective whole-recording acquisition pair."""

import argparse
import gzip
import io
import json
import tarfile
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import figure_books, whole_iq
from .. import iq_comparison_results as publication
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ARMS, ROLES, distance_km
from . import frontier_whole_replay as study
from .exact_wide_iq_results import detector_rows, encoded, timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .winner_stream_results import csv_file, scientific_result

NATIVE = "probe-audit.json"
TRACE = "visits.jsonl.gz"
DEADLINES = "deadlines.csv"
POSITIONS = "positions.jsonl.gz"
MEASURED = "as-measured-sources.tar.gz"
RESOURCES = ("resources.png", "resources.pdf")
PREFLIGHT = (
    "preflight-source-lock.json",
    "preflight-attempt-plan.json",
    "preflight-rejection.json",
    "preflight-differential-runtime.py.gz",
)


def fingerprint(value):
    return sha256(encoded(value)).hexdigest()


def probe_summary(probe):
    candidates = probe["candidates"]
    positive = [
        candidate for candidate in candidates if candidate["passed_fractional_margin_gate"] is True
    ]
    winner = max(
        positive, key=lambda row: (row["fractional_margin"], -row["candidate_rank"]), default=None
    )
    return dict(
        receiver_id=probe["receiver_id"],
        payload_sha256=fingerprint(candidates),
        candidates=len(candidates),
        positive=len(positive),
        winner_sha256=fingerprint(winner) if winner is not None else None,
        winner=winner,
    )


def trace_rows(ident, role, data):
    visits, timings, _ = data
    clock = {row["visit"]: row for row in timings}
    for visit in visits:
        footprint = dict(
            visit,
            probes=[{k: v for k, v in p.items() if k != "candidates"} for p in visit["probes"]],
        )
        yield dict(
            **clock.get(visit["visit"], dict(visit=visit["visit"], lane=visit["segment"] % 2)),
            id=ident,
            role=role,
            status=visit["status"],
            visit_metadata_sha256=fingerprint(footprint),
            full_visit_sha256=fingerprint(visit),
            probes=[probe_summary(probe) for probe in visit["probes"]],
        )


def compare_probes(control, candidate):
    counts = Counter()
    if len(control) != len(candidate):
        raise ValueError("stock and candidate did not process the same visit inventory")
    for stock, new in zip(control, candidate, strict=True):
        if stock["visit_metadata_sha256"] != new["visit_metadata_sha256"]:
            raise ValueError(f"noncandidate visit/counter/clock drift at visit {stock['visit']}")
        counts["visits"] += 1
        counts["visits_with_changed_candidates"] += (
            stock["full_visit_sha256"] != new["full_visit_sha256"]
        )
        counts["invalid_visits"] += stock["status"] == "invalid_capture"
        for left, right in zip(stock["probes"], new["probes"], strict=True):
            counts["probes"] += 1
            counts["changed_candidate_arrays"] += left["payload_sha256"] != right["payload_sha256"]
            counts["stock_gated_candidates"] += left["positive"]
            counts["candidate_gated_candidates"] += right["positive"]
            counts["stock_positive_probes"] += left["winner_sha256"] is not None
            counts["candidate_positive_probes"] += right["winner_sha256"] is not None
            counts["new_positive_probes"] += (
                left["winner_sha256"] is None and right["winner_sha256"] is not None
            )
            counts["lost_positive_probes"] += (
                left["winner_sha256"] is not None and right["winner_sha256"] is None
            )
            counts["changed_positive_winners"] += (
                left["winner_sha256"] is not None
                and right["winner_sha256"] is not None
                and left["winner_sha256"] != right["winner_sha256"]
            )
    return dict(counts)


def scout_trace(folder, trace):
    """Authenticate the wrapper's lane-local call sequence against physical visit records."""
    extra = {}
    for lane in range(2):
        path = folder / f"recording/replayed-{lane}.log"
        if not path.is_file():
            continue
        visits, footers = [], []
        for line in path.read_text().splitlines():
            if line.startswith("differential-visit: "):
                visits.append(json.loads(line.removeprefix("differential-visit: ")))
            elif line.startswith("differential-runtime-result: "):
                footers.append(json.loads(line.removeprefix("differential-runtime-result: ")))
        call_rows = [row for row in trace if row["lane"] == lane and row["status"] == "processed"]
        if len(visits) != len(call_rows) or len(footers) != 1:
            raise ValueError("differential telemetry omits calls from its completed raw lane")
        hint_count, changed_count = [0, 0], [0, 0]
        for i, (event, row) in enumerate(zip(visits, call_rows, strict=True)):
            hints, changed = event["hints"], event["changed"]
            names = ("scout_wall_ns", "scout_cpu_ns", "native_wall_ns", "native_cpu_ns")
            if (
                event["visit"] != i
                or len(hints) != 2
                or len(changed) != 2
                or any(
                    (hint is not None and not (type(hint) is int and 0 <= hint < 13333))
                    or not isinstance(replaced, bool)
                    or (replaced and hint is None)
                    for hint, replaced in zip(hints, changed, strict=True)
                )
                or any(type(event[name]) is not int or event[name] < 0 for name in names)
                or event["scout_wall_ns"] + event["native_wall_ns"] > row["wall_s"] * 1e9
            ):
                raise ValueError("differential hints or measured call clocks are invalid")
            for rx in range(2):
                hint_count[rx] += hints[rx] is not None
                changed_count[rx] += changed[rx]
            row["differential"] = {key: value for key, value in event.items() if key != "visit"}
        footer = footers[0]
        if (footer["visits"], footer["lanes_with_hint"], footer["changed_lanes"]) != (
            len(visits),
            hint_count,
            changed_count,
        ):
            raise ValueError("differential telemetry counters disagree with emitted hints")
        extra[lane] = dict(footer, raw_telemetry_sha256=_sha(path))
    if set(extra) != {0, 1}:
        raise ValueError("completed differential acquisition lacked a detector lane trace")
    return extra


def protect_resources(resources):
    for pair in resources.values():
        for item in pair.values():
            for stage in item.get("stages", []):
                if not (
                    stage["memory.max"] == whole_iq.MEMORY
                    and stage["memory.swap.max"] == stage["memory.swap.current"] == 0
                    and stage["memory.peak"] <= whole_iq.MEMORY
                ):
                    raise ValueError("resource receipt cannot establish the physical 512 MiB cap")


def archive_sources(base, out, plan):
    prospective = study.prospective(base)
    stock_launcher = base / "frontier_whole_replay.as-frozen.py"
    launcher = str(Path(study.__file__).relative_to(ROOT))
    items = {
        name: (ROOT / name, digest)
        for name, digest in (plan["programs"] | plan["activation"].get("programs", {})).items()
    }
    items[launcher] = stock_launcher, prospective["spec"]["launcher_sha256"]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, (source, expected) in sorted(items.items()):
            content = whole_iq.checked(source, expected).read_bytes()
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    (out / MEASURED).write_bytes(gzip.compress(buffer.getvalue(), mtime=0))


def audit(base, out):
    pins = publication.sealed(out)
    plan = whole_iq.read(out / "source-lock.json")
    rows = indexed(out / POSITIONS, plan)
    traces, observations = [], {}
    for ident in pins["cases"]:
        case = observations[ident] = dict(roles={})
        pair = {}
        for role in publication.BRANCHES:
            folder = base / "runs" / ident / role
            data = detector_rows(folder)
            if data is None:
                case["roles"][role] = dict(raw_complete=False)
                continue
            pair[role] = list(trace_rows(ident, role, data))
            case["roles"][role] = dict(
                raw_complete=True,
                logical_native_sha256=data[2],
                detector_calls=len(data[1]),
                native_sha256=rows[ident, role]["native_sha256"],
            )
            if role == "candidate" and plan["activation"]["policy"] == "unprivileged-differential":
                case["roles"][role]["intervention"] = scout_trace(folder, pair[role])
            traces.extend(pair[role])
        if not all(role in pair for role in publication.BRANCHES):
            continue
        stock, new = (rows[ident, role]["result"] for role in publication.BRANCHES)
        both = all(result["status"] in ("ok", "withheld") for result in (stock, new))
        case.update(compare_probes(pair["control"], pair["candidate"]))
        case["normalized_solver_exact"] = (
            encoded(scientific_result(stock)) == encoded(scientific_result(new)) if both else None
        )
        case["position_shift_m"] = {
            arm: 1000 * dx
            for arm in ARMS
            if (dx := distance_km(stock["arms"][arm]["latlon"], new["arms"][arm]["latlon"]))
            is not None
        }
    save_json(out / NATIVE, observations)
    (out / TRACE).write_bytes(
        gzip.compress(b"".join(encoded(row) + b"\n" for row in traces), mtime=0)
    )
    archive_sources(base, out, plan)
    extra_files = [NATIVE, TRACE, MEASURED, "prospective-lock.json", "selection.json"]
    extra_files.extend(plan["activation"]["receipt_files"])
    if (out / PREFLIGHT[0]).is_file():
        before = whole_iq.read(out / PREFLIGHT[0])
        expected = before["activation"]["programs"][
            "tools/pipeline_eval/qualification/differential_runtime.py"
        ]
        original = base / "differential_runtime.as-rejected.py"
        (out / PREFLIGHT[-1]).write_bytes(
            gzip.compress(whole_iq.checked(original, expected).read_bytes(), mtime=0)
        )
        extra_files.extend(PREFLIGHT)
    pins["files"].update({name: _sha(out / name) for name in extra_files})
    save_json(out / "prediction-lock.json", pins)


def indexed(path, plan):
    rows = load_rows(path)
    keys = {
        (case, publication.method(plan["spec"]["id"], role)): (case, role)
        for case in plan["cases"]
        for role in publication.BRANCHES
    }
    if len(rows) != len(keys) or {(row["id"], row["method"]) for row in rows} != keys.keys():
        raise ValueError("sealed attempts differ from the prospective two-branch roster")
    return {keys[row["id"], row["method"]]: row for row in rows}


def load_rows(path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream]


def score(root, out):
    pins = publication.sealed(root)
    plan = whole_iq.read(root / "source-lock.json")
    trials = list(indexed(root / POSITIONS, plan).values())
    resources = whole_iq.read(root / "resources.json")
    protect_resources(resources)
    _, refs = held_references(None, pins["cases"])
    reference = {row["id"]: row["reference"] for row in refs}
    scores = publication.score_rows(trials, resources, refs, plan["spec"]["id"])
    for row in scores:
        for role in ROLES:
            original = reference[row["id"]][role][row["arm"]]
            row[f"{role}_km"] = original["error_km"]
            row[f"{role}_status"] = original["status"]
            row[f"{role}_archived_rms_hz"] = original.get("rf_rms_hz")
    traces = [row for row in load_rows(root / TRACE) if row["status"] == "processed"]
    times = timing_rows(resources, traces)
    for row in times:
        metrics = resources[row["id"]][row["role"]]
        row["physical_peak_mib"] = (
            metrics.get("max_bytes", metrics.get("charged_peak_to_failure_bytes", 0)) / 2**20
            or None
        )
        row["service_returned_before_deadline"] = (
            row["full_s"] is not None and row["full_s"] <= plan["limit_s"]
        )
        row["wall_to_failure_s"] = metrics.get("wall_to_failure_s")
        row["cpu_to_failure_s"] = metrics.get("cpu_to_failure_s")
        calls = [
            t["differential"]
            for t in traces
            if t["id"] == row["id"] and t["role"] == row["role"] and "differential" in t
        ]
        row["scout_total_cpu_s"] = sum(i["scout_cpu_ns"] for i in calls) / 1e9 if calls else None
        row["scout_total_wall_s_across_lanes"] = (
            sum(i["scout_wall_ns"] for i in calls) / 1e9 if calls else None
        )
        row["hint_lanes_proposed"] = (
            sum(hint is not None for call in calls for hint in call["hints"]) if calls else None
        )
        row["hint_lanes_replaced"] = sum(sum(call["changed"]) for call in calls) if calls else None
    out.mkdir(exist_ok=True, parents=True)
    csv_file(out / "scores.csv", scores)
    csv_file(out / DEADLINES, times)
    draw_resources(out, pins["cases"], times, traces)
    return trials


def draw_resources(out, cases, times, traces):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    color = {"control": "#255784", "candidate": "#b32e43"}
    labels = {"control": "Stock wide", "candidate": "Differential hint"}
    pairs = {(r["id"], r["role"]): r for r in times}
    fig, axes = plt.subplots(len(cases), 2, figsize=(10.6, 3.7 * len(cases)), squeeze=False)
    for ident, (left, right) in zip(cases, axes, strict=True):
        for role in publication.BRANCHES:
            row = pairs[ident, role]
            t = sorted(1000 * r["wall_s"] for r in traces if r["id"] == ident and r["role"] == role)
            if t:
                left.plot(
                    t,
                    [(i + 1) / len(t) for i in range(len(t))],
                    label=labels[role],
                    color=color[role],
                    lw=1.65,
                )
            index = publication.BRANCHES.index(role)
            elapsed = row["full_s"]
            if elapsed is None:
                elapsed = row["wall_to_failure_s"]
                if elapsed is not None:
                    right.barh(
                        index,
                        elapsed,
                        color="white",
                        edgecolor=color[role],
                        hatch="///",
                        height=0.5,
                    )
            else:
                widths = [row[name] for name in ("raw_s", "assembly_s", "position_s")]
                for width, alpha, offset in zip(
                    widths, (0.55, 0.3, 1), (0, widths[0], sum(widths[:2])), strict=True
                ):
                    right.barh(
                        index, width, left=offset, color=color[role], alpha=alpha, height=0.5
                    )
            if elapsed is not None:
                offset = 8 if elapsed <= 395 else -8
                right.text(
                    elapsed + offset,
                    index,
                    f"{elapsed:.1f} s",
                    va="center",
                    ha="left" if offset > 0 else "right",
                    color=color[role] if offset > 0 or row["full_s"] is None else "white",
                )
        left.axvline(20, color="#555555", ls="--", lw=1, label="20 ms target")
        left.set(
            xscale="log",
            ylim=(0, 1.02),
            xlabel="Dual-RX call wall (ms)",
            ylabel="Fraction of measured calls",
            title=f"{ident} · detector calls",
        )
        left.legend(frameon=False, fontsize=9, loc="lower right")
        right.axvline(450, color="#555555", ls="--", lw=1)
        right.set(
            xlim=(0, 510),
            xlabel="Elapsed seconds",
            title="Complete replay · acquisition, assembly and fit",
            yticks=(0, 1),
            yticklabels=[labels[r] for r in publication.BRANCHES],
        )
        right.invert_yaxis()
    fig.suptitle("Whole-recording acquisition under a 512 MiB, zero-swap cap")
    fig.tight_layout()
    fig.savefig(out / RESOURCES[0], dpi=160)
    fig.savefig(out / RESOURCES[1], metadata={"CreationDate": None})
    plt.close(fig)


def build(base, out):
    publication.seal(base / "runs", out)
    audit(base, out)
    rows = score(out, out)
    plan = whole_iq.read(out / "source-lock.json")
    spec = plan["spec"]
    chart = publication.chart(out, spec, spec["title"], "all", list(plan["cases"]), rows)
    chart["provenance"].extend([NATIVE, TRACE, DEADLINES, "prospective-lock.json"])
    chart["source_lock"] = dict(file="source-lock.json", digest_key="source_lock_sha256")
    seal_path = out / chart["seal"]
    lock = whole_iq.read(seal_path)
    lock["files"].update({name: _sha(out / name) for name in chart["provenance"]})
    save_json(seal_path, dict(lock, source_lock_sha256=_sha(out / "source-lock.json")))
    save_json(out / "figures.json", dict(version=1, charts=[chart]))
    seal_resources(out)
    figure_books.generate(out / "charts", ARMS, panel="screening", evidence=out)


def seal_resources(out):
    stage = "stage-figure.json"
    receipt = "stage-figure-lock.json"
    save_json(
        out / stage,
        dict(
            version=1,
            id="frontier-whole-iq-resources",
            title="Differential hint timing on complete stored IQ",
            sample="Two held recordings, two complete arms, 27,060 measured dual-RX calls",
            boundary="Authenticated full saved IQ → detector → unchanged phase-release position",
            note=(
                "Same-recording 512 MiB zero-swap pairs. Every candidate call exceeded 20 ms, "
                "while both candidate services finished inside their 450-second cap. "
                "The visit-level development study is separate."
            ),
            seal=receipt,
            image=RESOURCES[0],
            pdf=RESOURCES[1],
            csv=DEADLINES,
        ),
    )
    save_json(
        out / receipt,
        dict(
            cases=publication.sealed(out)["cases"],
            files={
                name: _sha(out / name)
                for name in (stage, *RESOURCES, DEADLINES, "prediction-lock.json")
            },
            scorer_sha256=_sha(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    run = modes.add_parser("build")
    run.add_argument("base", type=local_output)
    offline = modes.add_parser("score")
    offline.add_argument("out", type=local_output)
    args = parser.parse_args()
    if args.mode == "build":
        build(args.base, study.REPORT)
    else:
        score(study.REPORT, args.out)


if __name__ == "__main__":
    main()
