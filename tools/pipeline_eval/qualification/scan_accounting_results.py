"""Publish collector timing, exact factor checks, and fresh compact positions."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from .. import original_receiver, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from . import scan_accounting_trial as trial
from . import scout_stage_figures as plot
from .fresh_replay_results import geographic
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .selector_waveform_results import endpoint

FRESH = "scan_accounting_shared_compact"
HISTORICAL = "scan_accounting_prior_compact"
SMOKE = Path("/var/tmp/leo-coarse-nav-20261120")


def samples(clocks, plan):
    rows, summary = [], {}
    for ident, case_rows in clocks.items():
        pairs = []
        for pair, sequence in enumerate(plan["pairs"]):
            measured = sorted((r for r in case_rows if r["pair"] == pair), key=lambda r: r["order"])
            if (
                [r["mode"] for r in measured] != sequence
                or any(r["cpu"] != plan["cpu"] for r in measured)
                or len({r["collection_sha256"] for r in measured}) != 1
            ):
                raise ValueError("paired subprocess receipt differs from its frozen order")
            modes = {r["mode"]: r for r in measured}
            pairs.append(
                dict(
                    id=ident,
                    pair=pair,
                    order="/".join(sequence),
                    **{
                        f"{mode}_{clock}_ms": row[f"{clock}_ns"] / 1e6
                        for mode, row in modes.items()
                        for clock in ("cpu", "wall")
                    },
                    cpu_saved_ms=(modes["baseline"]["cpu_ns"] - modes["candidate"]["cpu_ns"]) / 1e6,
                    wall_saved_ms=(modes["baseline"]["wall_ns"] - modes["candidate"]["wall_ns"])
                    / 1e6,
                )
            )
        if len(case_rows) != 2 * len(pairs):
            raise ValueError("collector timing has unexpected extra samples")
        # Use a fixed column order even when the candidate was measured first.
        rows.extend(
            {
                key: row[key]
                for key in (
                    "id",
                    "pair",
                    "order",
                    "baseline_cpu_ms",
                    "candidate_cpu_ms",
                    "baseline_wall_ms",
                    "candidate_wall_ms",
                    "cpu_saved_ms",
                    "wall_saved_ms",
                )
            }
            for row in pairs
        )
        summary[ident] = {
            k: distribution([p[k] for p in pairs])
            for k in (
                "baseline_cpu_ms",
                "candidate_cpu_ms",
                "baseline_wall_ms",
                "candidate_wall_ms",
                "cpu_saved_ms",
                "wall_saved_ms",
            )
        }
    return rows, summary


def normal_smoke(out):
    summaries, visits, sealed = {}, {}, []
    for mode, folder in (("baseline", "original-smoke"), ("candidate", "compact-smoke")):
        home = SMOKE / folder
        summary = whole_iq.read(home / "summary.json")
        with (home / "cpu-12.jsonl").open() as stream:
            rows = [row for row in map(json.loads, stream) if row["kind"] == "visit"]
        probes = [p for r in rows for p in r["probes"]]
        candidates = sum(len(p["candidates"]) for p in probes)
        if (
            summary["completed_visits"],
            summary["valid_visits"],
            summary["grid_calls"],
            len(probes),
            candidates,
        ) != (64, 64, 147, 128, 569) or summary["status"] != "stage_only":
            raise ValueError("normal smoke escaped its independently verified physical scope")
        visits[mode] = [
            {k: v for k, v in r.items() if k not in ("detector_cpu_s", "detector_wall_s")}
            for r in rows
        ]
        summaries[mode] = dict(
            wall_s=summary["raw_wall_s"],
            probes=len(probes),
            candidates=candidates,
            visits=len(rows),
            grid_calls=summary["grid_calls"],
            detector_cpu_s=sum(r["detector_cpu_s"] for r in rows),
        )
        for name in (
            "summary.json",
            "source-lock.json",
            "raw-exits.json",
            "cpu-12.jsonl",
            "cpu-12.log",
            "launch.json",
        ):
            file = f"receipts/normal-smoke/{mode}/{name}.gz"
            write(out / file, gzip.compress((home / name).read_bytes(), mtime=0))
            sealed.append(file)
    if encoded(visits["baseline"]) != encoded(visits["candidate"]):
        raise ValueError("normal raw smoke changed a physical factor or gate")
    return dict(exact_raw_visits=True, runs=summaries), sealed


def position_record(work, ident, bound, cfg):
    folder = work / f"{ident}-position"
    terminal = whole_iq.read(folder / "terminal.json")
    end = whole_iq.read(folder / "end.json")
    raw = whole_iq.read(folder / "raw.json")
    plan = whole_iq.read(folder / "plan.json")
    whole_iq.checked(folder / "service.log", terminal["log_sha256"])
    data = Path(cfg["work"])
    if (
        terminal["exit_code"]
        or end["cpus"] != [plan["cpu"]]
        or end["memory.max"] != whole_iq.MEMORY
        or end["memory.swap.max"]
        or end["memory.swap.current"]
        or end["memory.events.oom_kill"]
        or plan["source_lock_sha256"] != _sha(work / "plan.json")
        or raw["native_sha256"] != "sha256:" + bound["native_sha256"]
    ):
        raise ValueError(
            "fresh compact terminal does not bind the measured native and capped worker"
        )
    lock = whole_iq.read(data / "source-lock.json")
    case = original_receiver.input_case(ident, None, None)
    original = original_receiver.binding(case)
    native = whole_iq.checked(work / f"{ident}-native.json", bound["native_sha256"])
    request = whole_iq.checked(folder / "recording/request.json", raw["request_sha256"])
    whole_iq.verify_request(
        whole_iq.read(request),
        original,
        native_path=str(native),
        native_sha256=raw["native_sha256"],
    )
    fresh = whole_iq.read(folder / "position.json")
    validate_result(fresh)
    fields = dict(
        paired_capture_sha256=lock["original"]["native"]["sha256"],
        original_request_sha256=lock["original"]["request"]["sha256"],
        catalog_sha256=lock["original"]["catalog"]["sha256"],
        tile=lock["original"]["tile"],
    )
    history = whole_iq.checked(Path(cfg["report"]) / "positions.jsonl.gz", cfg["positions_sha256"])
    (prior,) = [r for r in trial.common.rows_from(history) if r["method"] == cfg["method"]]
    if (
        prior["id"] != ident
        or any(prior[k] != v for k, v in fields.items())
        or prior["native_sha256"] != bound["historical_native_sha256"]
        or endpoint(fresh) != endpoint(prior["result"])
    ):
        raise ValueError("fresh compact endpoint differs from the matched historical fresh replay")
    shared = dict(id=ident, mode="matched-tile", cohort="normal acquisition accounting", **fields)
    endpoints = [
        dict(shared, method=FRESH, result=fresh, native_sha256=bound["native_sha256"]),
        dict(
            shared, method=HISTORICAL, result=prior["result"], native_sha256=prior["native_sha256"]
        ),
    ]
    return endpoints, dict(
        terminal=terminal, end=end, reference_method=cfg["method"], endpoint_identical=True
    )


def render(out, summaries):
    fig, axes = plot.canvas(
        "Normal original receiver collection",
        "Three authenticated complete waveform outputs · four fresh alternating pairs each",
        "The clock starts at collection. It measures shard decoding, checks and digests. "
        "Detector execution, index prepass, native assembly and position are separate.",
    )
    ids = list(summaries)
    for ax, clock, title in zip(
        axes, ("cpu", "wall"), ("Collector CPU", "Collector wall"), strict=True
    ):
        results = [
            tuple(summaries[ident][f"{m}_{clock}_ms"]["p50"] for m in ("baseline", "candidate"))
            for ident in ids
        ]
        plot.paired(ax, ids, results, title=title, xlabel="Host milliseconds", fmt=".1f")
    plot.key(fig, "Previous collector", "Single-pass collector")
    fig.savefig(out / "timing.png", dpi=165, facecolor="white")
    fig.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)


def publish(work):
    out = trial.REPORT
    plan = trial.plan_for(work)
    rows, timing = samples(whole_iq.read(work / "collect.json"), plan)
    assembly = whole_iq.read(work / "assembly.json")
    predictions, fresh, indices = [], {}, {}
    for ident, cfg in plan["cases"].items():
        panels, details = position_record(work, ident, assembly[ident], cfg)
        predictions.extend(panels)
        fresh[ident] = details
        index = work / f"{ident}-index.json"
        if index.exists():
            indices[ident] = whole_iq.read(index)
    csv_file(out / "stage.csv", rows)
    smoke, files = normal_smoke(out)
    save_json(
        out / "audit.json",
        dict(
            assembly=assembly,
            collector=timing,
            compact=fresh,
            index_only=indices,
            normal_smoke=smoke,
            source_net_lines=sum(r["net_change"] for r in plan["diff"].values()),
        ),
    )
    trial.common.pack(out / "positions.jsonl.gz", predictions)
    files.extend(str(p.relative_to(out)) for p in sorted((out / "sources").rglob("*.gz")))
    files.extend(("plan.json", "PROTOCOL.md", "audit.json", "positions.jsonl.gz", "stage.csv"))
    for name in ("collect.json", "assembly.json"):
        receipt = f"receipts/{name}"
        write(out / receipt, (work / name).read_bytes())
        files.append(receipt)
    for ident in plan["cases"]:
        native = work / f"{ident}-native.json"
        packed = f"receipts/{ident}-native.json.gz"
        write(out / packed, gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
        files.append(packed)
        evidence = [
            source for source in sorted((work / f"{ident}-position").rglob("*")) if source.is_file()
        ]
        evidence.extend(work.glob(f"{ident}-index*"))
        for source in evidence:
            name = str(Path("receipts") / source.relative_to(work))
            write(out / name, source.read_bytes())
            files.append(name)
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(plan["cases"]),
            files={name: _sha(out / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    _, references = held_references(None, list(plan["cases"]))
    refs = {r["id"]: r for r in references}
    csv_file(out / "scores.csv", geographic(predictions, refs))
    csv_file(
        out / "v5-controls.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                error_km=ref["reference"][role][arm]["error_km"],
                conditional_rms_hz=ref["reference"][role][arm].get("rf_rms_hz"),
            )
            for ident, ref in refs.items()
            for role in ROLES
            for arm in ARMS
        ],
    )
    save_json(
        out / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(out / "prediction-lock.json"),
            files={name: _sha(out / name) for name in ("scores.csv", "v5-controls.csv")},
        ),
    )
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="scan-accounting-position",
                    method=FRESH,
                    scope="roof",
                    cases="sealed",
                    seal="prediction-lock.json",
                    title="Position after normal receiver accounting changes",
                    caption="Both collectors reproduced the same complete native input. "
                    "Each recording has one fresh compact fit and a matched prior waveform fit.",
                    provenance=["plan.json", "audit.json"],
                    series=[
                        dict(
                            key=key,
                            file="positions.jsonl.gz",
                            value=mode,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=trial.common.MINIMAL,
                        )
                        for key, mode, label in (
                            ("one", FRESH, "Fresh compact on shared factors"),
                            ("stock", HISTORICAL, "Prior matched fresh waveform"),
                        )
                    ],
                )
            ],
        ),
    )
    render(out, timing)
    save_json(
        out / "timing-lock.json",
        {
            "files": {
                name: _sha(out / name)
                for name in ("timing.png", "timing.pdf", "stage.csv", "prediction-lock.json")
            }
        },
    )
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="scan-accounting-collector-timing",
            title="Normal receiver collector timing",
            sample="Three full authenticated waveforms with four alternating pairs each",
            boundary="Read, decode, verify and hash complete original receiver shards",
            note="Fresh CPU-pinned processes read the same raw receipts. Detector and compact CPU "
            "lie outside the collector clock.",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="stage.csv",
        ),
    )
    trial.common.generate(out / "charts", evidence=out)


def position_on(work, ident, cpu):
    read = trial.plan_for
    with patch.object(trial, "plan_for", side_effect=lambda path: dict(read(path), cpu=cpu)):
        trial.position(work, ident)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("publish", "position-on"))
    parser.add_argument("work", type=local_output, nargs="?", default=trial.WORK)
    parser.add_argument("--case", choices=tuple(trial.CASES))
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    trial.REPORT = args.report
    if args.action == "publish":
        publish(args.work)
    elif args.case is not None and args.cpu is not None:
        position_on(args.work, args.case, args.cpu)
    else:
        parser.error("position-on requires a case and CPU")
