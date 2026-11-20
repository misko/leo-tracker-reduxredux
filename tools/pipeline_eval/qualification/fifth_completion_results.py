"""Archive terminal fifth-center services, then score paired replay endpoints."""

import argparse
import gzip
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distribution
from . import fifth_completion as trial
from . import frontier_whole_replay_results as traces
from . import screening_figures
from . import whole_band_results as measured
from . import whole_center_union_results as union
from .diagnostic_whole_results import PHYSICAL_KEYS, passing
from .exact_wide_iq_results import detector_rows
from .fresh_replay_results import geographic, sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from
from .wide_roster_results import COMMON, PRIMARY, same_receiver, whole_support

BRANCH = "candidate"
POSITIONS = "positions.jsonl.gz"
PREDICTION_LOCK = "prediction-lock.json"
FIGURE_LOCK = "figure-lock.json"
PUBLISHER = "as-sealed-publisher.py.gz"
STOCK_LOCK = "966d07bc1faedd04f83fd61aa8beb90cf1237bd6414ea309f9bb9a6df6c2eb42"


def ready(work, ident):
    branch = work / ident / BRANCH
    return (branch / "service.json").exists() or (branch.parent / f"{BRANCH}-failure.json").exists()


def archive_case(work, out, ident, plan):
    branch = work / ident / BRANCH
    row, resources, native = measured.attempt(work, ident, BRANCH, plan, method=trial.METHOD)
    case = plan["cases"][ident]
    traces.protect_resources({ident: {BRANCH: resources}})
    authority = {"complete_raw": native is not None}
    saved = []
    plan_file = branch / "plan.json"
    if plan_file.is_file():
        actual = whole_iq.read(plan_file)
        if (
            actual["differential_sources"] != plan["programs"]
            or actual["native_sources"] != plan["native_sources"]
            or actual["limit_s"] != plan["limit_s"]
        ):
            raise ValueError("complete IQ launch differs from fixed fifth-center plan")
    for source in (
        plan_file,
        branch / "service.json",
        branch / "service-launch.json",
        branch / "service.log",
        branch.parent / f"{BRANCH}-failure.json",
    ):
        if source.is_file():
            if source.name == "service.log" and "log_sha256" in resources["service"]:
                whole_iq.checked(source, resources["service"]["log_sha256"])
            name = f"receipts/{ident}/{source.name}"
            write(out / name, source.read_bytes())
            saved.append(name)
    if native is not None:
        visits, timings, logical = detector_rows(branch)
        whole_support(resources, case, case["clock_authority"])
        trace = list(traces.trace_rows(ident, BRANCH, (visits, timings, logical)))
        authority.update(
            scout_trace=traces.scout_trace(branch, trace),
            union_admissions=union.union_telemetry(trace),
            logical_native_sha256=logical,
            native_sha256=row["native_sha256"],
            raw_receipt_sha256=_sha(branch / "raw.json"),
            **{key: resources[key] for key in COMMON},
        )
        name = f"native/{BRANCH}/{ident}.json.gz"
        write(out / name, gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
        saved.append(name)
    else:
        row["native_sha256"] = None
    save_json(
        out / f"attempts/{ident}.json",
        dict(
            row=row,
            resources=resources,
            authority=authority,
            files={n: _sha(out / n) for n in saved},
        ),
    )
    print(ident, row["result"]["status"], "complete IQ" if native else "incomplete IQ", flush=True)


def collect(work, out):
    plan = trial.source(work)
    for ident in plan["cases"]:
        if ready(work, ident) and not (out / f"attempts/{ident}.json").is_file():
            archive_case(work, out, ident, plan)


def seal(work, out):
    if (out / PREDICTION_LOCK).exists():
        raise FileExistsError("the cohort predictions were already sealed")
    collect(work, out)
    plan = trial.source(work)
    source = Path(trial.__file__)
    launcher_name = "as-measured-launcher.py.gz"
    digest = plan["programs"][str(source.relative_to(trial.ROOT))]
    write(
        out / launcher_name, gzip.compress(whole_iq.checked(source, digest).read_bytes(), mtime=0)
    )
    publisher = Path(__file__)
    write(out / PUBLISHER, gzip.compress(publisher.read_bytes(), mtime=0))
    files = ["source-lock.json", "PROTOCOL.md", launcher_name, PUBLISHER]
    rows, resources, authority = [], {}, {}
    for ident in plan["cases"]:
        name = f"attempts/{ident}.json"
        case = sealed(out, name)
        if case["row"]["id"] != ident:
            raise ValueError("recording was crossed in the candidate attempt archive")
        rows.append(case["row"])
        resources[ident] = {BRANCH: case["resources"]}
        authority[ident] = case["authority"]
        files.extend((name, *case["files"]))
    pack(out / POSITIONS, rows)
    save_json(out / "resources.json", resources)
    save_json(out / "raw-authority.json", authority)
    files.extend((POSITIONS, "resources.json", "raw-authority.json"))
    save_json(
        out / PREDICTION_LOCK,
        dict(
            cases=list(plan["cases"]),
            files={name: _sha(out / name) for name in files},
            publisher_sha256=_sha(publisher),
        ),
    )


def native_data(path, digest):
    content = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    if sha256(content).hexdigest() != digest:
        raise ValueError("native export does not match the measured uncompressed bytes")
    return json.loads(content)


def stock_native(case, row, attempt, out):
    original = Path(attempt["native_archive"])
    if not original.is_absolute():
        return native_data(trial.SCREEN / original, row["native_sha256"]), None
    # The exact-wide snapshots existed only in the original attempt directory.
    name = f"native/stock/{case['id']}.json.gz"
    portable = out / name
    if not portable.is_file():
        native = whole_iq.checked(original, row["native_sha256"])
        write(portable, gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
    return native_data(portable, row["native_sha256"]), name


def comparable_probes(stock, candidate):
    """Compare the gate payloads with input ordering checked even on negatives."""
    before, after = stock["source"], candidate["source"]

    def outside_candidates(doc, source):
        return dict(
            clock=[doc[key] for key in ("clock_anchor", "delivery_clocks", "last_sample_counter")],
            provenance={
                key: value
                for key, value in doc["provenance"].items()
                if key not in {"run_id", "detector_sha256"}
            },
            source={
                key: value
                for key, value in source.items()
                if key not in {"analysis_manifest_sha256", "probes"}
            },
        )

    if outside_candidates(stock, before) != outside_candidates(candidate, after):
        raise ValueError("native waveform clock, RF mapping or exclusions differ")
    counts = Counter()
    for old, new in zip(before["probes"], after["probes"], strict=True):
        if {k: v for k, v in old.items() if k != "candidates"} != {
            k: v for k, v in new.items() if k != "candidates"
        }:
            raise ValueError("physical receiver probe metadata or order differs")
        previous, current = passing(old["candidates"]), passing(new["candidates"])
        counts.update(
            probes=1,
            stock_positive_probes=bool(previous),
            fifth_positive_probes=bool(current),
            new_positive_probes=not previous and bool(current),
            lost_positive_probes=bool(previous) and not current,
            retained_stock_gate_payloads=sum((previous & current).values()),
            lost_stock_gate_payloads=sum((previous - current).values()),
            new_gate_payloads=sum((current - previous).values()),
        )
    return dict(counts)


def stock_control(candidate, case, row, attempt, cur, plan, out):
    keys = {
        "capture_era_native_sha256": candidate["paired_capture_sha256"],
        **{k: candidate[k] for k in PHYSICAL_KEYS if k != "paired_capture_sha256"},
    }
    if (
        any(row[key] != value or attempt[key] != value for key, value in keys.items())
        or any(row[key] != attempt[key] for key in ("id", "result", "native_sha256"))
        or attempt["study_prediction_sha256"] != case["stock"]["prediction_sha256"]
        or attempt["study_source_sha256"] != case["stock"]["source_sha256"]
        or attempt["detector_sha256"] != plan["detectors"]["control"]["sha256"]
        or not attempt["full_raw_verified"]
    ):
        raise ValueError("stock position provenance differs from fixed primary paired input")
    old_source = whole_iq.read(
        whole_iq.checked(
            trial.SCREEN / case["stock"]["path"] / "source-lock.json",
            case["stock"]["source_sha256"],
        )
    )
    same_receiver(old_source["receiver_files"], plan, Path(old_source["receiver"]))
    if old_source["native_sources"] != plan["native_sources"]:
        raise ValueError("compiled stock receiver dependencies differ from candidate")
    audit, exported = None, None
    if candidate["native_sha256"] is not None:
        if any(attempt[key] != cur[key] for key in (*COMMON, "dual_calls")):
            raise ValueError(
                "fourth- and fifth-center runs used different physical recording support"
            )
        original, exported = stock_native(case, row, attempt, out)
        audit = comparable_probes(
            original,
            native_data(out / f"native/{BRANCH}/{row['id']}.json.gz", candidate["native_sha256"]),
        )
    binding = dict(
        row, paired_capture_sha256=keys["capture_era_native_sha256"], cohort="completion"
    )
    return binding, audit, exported


def timing_row(ident, method, data, detector):
    return dict(
        id=ident,
        method=method,
        cpus=",".join(map(str, detector["cpus"])),
        deadline_s=detector["deadline_s"],
        service_result=detector["terminal"],
        **{
            key: data.get(key)
            for key in (
                "dual_calls",
                "within_20ms",
                "wall_s",
                "cpu_s",
                "raw_s",
                "position_s",
                "assembly_s",
                "wall_to_failure_s",
                "cpu_to_failure_s",
                "max_bytes",
                "charged_peak_to_failure_bytes",
            )
        },
        detector_wall_ms_p50=data.get("detector_call_wall_ms", {}).get("p50"),
        detector_wall_ms_p95=data.get("detector_call_wall_ms", {}).get("p95"),
        detector_cpu_ms_p50=data.get("detector_call_cpu_ms", {}).get("p50"),
        detector_cpu_ms_p95=data.get("detector_call_cpu_ms", {}).get("p95"),
    )


def summarize(rows, timings):
    return {
        method: dict(
            **{
                arm: dict(
                    attempted=len(group),
                    published=sum(row["error_km"] is not None for row in group),
                    within_5pct=sum(row["within_5pct"] for row in group),
                    within_10pct=sum(row["within_10pct"] for row in group),
                    error_km=distribution([row["error_km"] for row in group]),
                    conditional_rms_hz=distribution([row["conditional_rms_hz"] for row in group]),
                    frequency_score=distribution([row["frequency_score"] for row in group]),
                )
                for arm in ARMS
                if (group := [row for row in rows if row["method"] == method and row["arm"] == arm])
            },
            **{
                key: distribution([row[key] for row in timings if row["method"] == method])
                for key in (
                    "wall_s",
                    "cpu_s",
                    "raw_s",
                    "position_s",
                    "max_bytes",
                    "detector_wall_ms_p95",
                )
            },
            calls=sum(row["dual_calls"] or 0 for row in timings if row["method"] == method),
            calls_within_20ms=sum(
                row["within_20ms"] or 0 for row in timings if row["method"] == method
            ),
        )
        for method in (trial.METHOD, PRIMARY)
    }


def paired_scores(rows):
    """Keep the matched arms explicit and summarize only the measured pairwise deltas."""
    index = {(row["id"], row["method"], row["arm"]): row for row in rows}
    fields = ("error_km", "conditional_rms_hz", "frequency_score", "observations", "tracks")
    pairs = []
    for ident in dict.fromkeys(row["id"] for row in rows):
        for arm in ARMS:
            fifth, stock = (index[ident, method, arm] for method in (trial.METHOD, PRIMARY))
            row = dict(
                id=ident, arm=arm, fifth_status=fifth["status"], stock_status=stock["status"]
            )
            for key in fields:
                a, b = fifth[key], stock[key]
                row[f"fifth_{key}"] = a
                row[f"stock_{key}"] = b
                row[f"delta_{key}"] = a - b if a is not None and b is not None else None
            pairs.append(row)
    stats = {
        arm: {
            key: distribution([row[f"delta_{key}"] for row in pairs if row["arm"] == arm])
            for key in fields
        }
        for arm in ARMS
    }
    return pairs, stats


def timing_figure(out, ids, timing):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.patches import Patch

    index = {(r["id"], r["method"]): r for r in timing}
    palette = ((PRIMARY, "Archived four", "#24557d"), (trial.METHOD, "Optional fifth", "#ad3a37"))
    fig, (whole, calls) = plt.subplots(1, 2, figsize=(10.8, 6.55), sharey=True)
    for j, (method, _, color) in enumerate(palette):
        for i, ident in enumerate(ids):
            row = index[ident, method]
            y = i + (j - 0.5) * 0.32
            full, failed = row["wall_s"], row["wall_to_failure_s"]
            if full is not None:
                whole.barh(y, full, height=0.28, color=color)
            elif failed is not None:
                whole.barh(y, failed, height=0.28, facecolor="white", edgecolor=color, hatch="///")
            if row["dual_calls"]:
                fast = 100 * row["within_20ms"] / row["dual_calls"]
                calls.barh(y, fast, height=0.28, color=color)
    whole.set(yticks=list(range(len(ids))), yticklabels=ids, xlabel="Complete replay wall (s)")
    calls.set(xlabel="Recorded dual-RX calls ≤20 ms (%)", xlim=(0, 100))
    whole.invert_yaxis()
    fig.legend(
        handles=[Patch(color=color, label=label) for _, label, color in palette],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.94),
        ncols=2,
        frameon=False,
    )
    for ax in (whole, calls):
        ax.grid(axis="x", alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Recorded-IQ replay and detector timing on ten matched recordings")
    fast_totals = [
        (
            label,
            sum(r["within_20ms"] or 0 for r in timing if r["method"] == method),
            sum(r["dual_calls"] or 0 for r in timing if r["method"] == method),
        )
        for method, label, _ in palette
    ]
    call_note = "   |   ".join(f"{label} {fast:,}/{count:,}" for label, fast, count in fast_totals)
    fig.text(
        0.5,
        0.018,
        f"Calls ≤20 ms: {call_note}\nStock and fifth ran on different CPU pairs and deadlines.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.066, 1, 0.922))
    image, csv, proof = "timing.png", "timing.csv", "timing-figure-lock.json"
    fig.savefig(out / image, dpi=160)
    plt.close(fig)
    save_json(out / proof, dict(files={name: _sha(out / name) for name in (image, csv)}))
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="fifth-completion-host-timing",
            title="Recorded-IQ wall and detector timing with an optional fifth center",
            sample="Ten matched, five-minute archived IQ recordings from one roof",
            boundary="Saved IQ through compact position, 512 MiB and zero swap",
            note="Archived stock and new fifth were measured on different CPU pairs and deadlines. "
            "The detector-call wall times come from unpaced saved IQ. "
            "A striped pipeline bar, when present, is observed time to failure.",
            seal=proof,
            image=image,
            csv=csv,
        ),
    )


def score(out):
    lock = sealed(out, PREDICTION_LOCK)
    publisher = out / PUBLISHER
    if sha256(gzip.decompress(publisher.read_bytes())).hexdigest() != lock["publisher_sha256"]:
        raise ValueError("prediction publisher snapshot has changed since numerical sealing")
    stock = sealed(trial.STOCK, PREDICTION_LOCK, STOCK_LOCK)
    plan = whole_iq.read(out / "source-lock.json")
    old = {row["id"]: row for row in rows_from(trial.STOCK / POSITIONS) if row["method"] == PRIMARY}
    attempts = {
        row["id"]: row for row in whole_iq.read(trial.STOCK / "attempts.json") if row["primary"]
    }
    new = rows_from(out / POSITIONS)
    if [row["id"] for row in new] != lock["cases"] or any(
        row["method"] != trial.METHOD for row in new
    ):
        raise ValueError("candidate export differs from the sealed ten-recording roster")
    resources = whole_iq.read(out / "resources.json")
    _, refs = held_references(None, lock["cases"])
    paired, audit, timing, stock_exports = [], {}, [], []
    for row in new:
        ident = row["id"]
        case, past, cur = plan["cases"][ident], attempts[ident], resources[ident][BRANCH]
        matched, audit[ident], export = stock_control(row, case, old[ident], past, cur, plan, out)
        if export:
            stock_exports.append(export)
        paired.extend((row, matched))
        timing.append(
            timing_row(
                ident,
                PRIMARY,
                past,
                dict(
                    cpus=past["cpu_pins"],
                    deadline_s=past["deadline_s"],
                    terminal=past["service_result"],
                ),
            )
        )
        timing.append(
            timing_row(
                ident,
                trial.METHOD,
                cur,
                dict(
                    cpus=case["cpus"],
                    deadline_s=plan["limit_s"],
                    terminal=cur["service"]
                    .get("systemd", {})
                    .get("Result", row["result"]["status"]),
                ),
            )
        )
    paired_name = "paired-positions.jsonl.gz"
    pack(out / paired_name, paired)
    scores = geographic(paired, {row["id"]: row for row in refs})
    metrics = {(row["id"], row["method"]): row["result"]["metrics"] for row in paired}
    for row in scores:
        result = metrics[row["id"], row["method"]]
        row.update({key: result.get(key) for key in ("observations", "tracks")})
    differences, stats = paired_scores(scores)
    calibration, _ = union.paired_scores(scores)
    csv_file(out / "scores.csv", scores)
    csv_file(out / "paired-deltas.csv", differences)
    csv_file(out / "calibration.csv", calibration)
    csv_file(out / "timing.csv", timing)
    save_json(out / "probe-audit.json", audit)
    save_json(
        out / "stock-authority.json",
        dict(
            path=str(trial.STOCK.relative_to(trial.SCREEN)),
            prediction_sha256=STOCK_LOCK,
            files=stock["files"],
            portable_stock_replay_exports={name: _sha(out / name) for name in stock_exports},
        ),
    )
    save_json(out / "summary.json", dict(summarize(scores, timing), fifth_minus_stock=stats))
    provenance = [
        PREDICTION_LOCK,
        publisher.name,
        "source-lock.json",
        "stock-authority.json",
        "probe-audit.json",
        "scores.csv",
        "paired-deltas.csv",
        "calibration.csv",
        "timing.csv",
        "summary.json",
    ]
    save_json(
        out / FIGURE_LOCK,
        dict(
            cases=lock["cases"],
            files={name: _sha(out / name) for name in [paired_name, *provenance, *stock_exports]},
        ),
    )
    spec = dict(
        id="fifth-completion",
        method=trial.METHOD,
        scope="roof",
        cases="sealed",
        title="Fifth center on ten newly matched complete-IQ recordings",
        caption="Same saved IQ, compact phase release and surveyed roof. The earlier four-center "
        "services ran on different CPU pairs and deadlines. Four original capture-era v5 options "
        "share each recording. Both calibration arms and all terminal outcomes are included.",
        seal=FIGURE_LOCK,
        provenance=provenance,
        series=[
            dict(
                key="one",
                file=paired_name,
                value=trial.METHOD,
                label="Four + optional fifth",
                native_field="paired_capture_sha256",
            ),
            dict(
                key="stock",
                file=paired_name,
                value=PRIMARY,
                label="Stock wide",
                native_field="paired_capture_sha256",
                match=list(PHYSICAL_KEYS),
            ),
        ],
    )
    save_json(out / "figures.json", dict(version=2, charts=[spec]))
    screening_figures.generate(out / "charts", evidence=out)
    timing_figure(out, lock["cases"], timing)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "seal", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    if args.action == "score":
        score(trial.REPORT)
    else:
        {"collect": collect, "seal": seal}[args.action](args.work, trial.REPORT)
