"""Authenticate, fit and score the complete DS29-0082 primary-only factor stream."""

import argparse
import csv
import gzip
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from . import capture_whole_results as whole
from . import scout_stage_figures as plot
from . import single_pass_position_results as lower
from . import upper_primary as trial
from .field_exact_waveform_results import parity
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .selector_waveform_results import endpoint

NATIVE = "primary.json"
EARLY = "primary-lock.json"
METHODS = (
    ("one", trial.METHOD, "12 anchors only"),
    ("one_native_factors", trial.field.METHOD, "Original conditional 12/22"),
    ("stock", whole.FOUR, "Full wide four-region"),
)


def factor_evidence(work, lock):
    replacements, raw = lower.collect(work, lock)
    parent = trial.archive(lock)
    with patch.object(lower.trial, "METHOD", trial.METHOD):
        document, edits = lower.merge(
            parent, replacements, lock["selected"], _sha(work / "source-lock.json")
        )
    evidence = parity(document, parent)
    expected = {
        "reference": (9736, 1868),
        "fresh": (9736, 1640),
    }
    if (
        evidence["unmatched_probes"]
        or not evidence["probe_order_exact"]
        or not all(evidence["clock_fields_exact"].values())
        or not all(evidence["capture_validity_fields_exact"].values())
        or any(
            (r["probes"], r["probes_with_gate_pass"]) != expected[k]
            or r["gate_formula_errors"]
            or r["candidate_schema_errors"]
            for k, r in evidence["counts"].items()
        )
        or any(r["primary_positive"] and not r["conditional_positive"] for r in edits)
        or sum(r["conditional_positive"] and not r["primary_positive"] for r in edits)
        != lock["rescued"]
    ):
        raise ValueError("the complete primary-only factors changed the frozen physical support")
    return document, replacements, edits, raw, evidence


def native_binding(work, lock):
    receipt = whole_iq.read(whole_iq.checked(work / EARLY, _sha(trial.REPORT / EARLY)))
    if (
        receipt["source_lock_sha256"] != _sha(work / "source-lock.json")
        or receipt["raw_exits_sha256"] != _sha(work / "raw-exits.json")
        or receipt["conditional_native_sha256"] != lock["parent_files"]["native.json.gz"]
        or receipt["publisher_sha256"] != _sha(Path(__file__))
    ):
        raise ValueError("early native receipt differs from the measured replay")
    native = whole_iq.checked(work / NATIVE, receipt["primary_native_sha256"])
    whole_iq.checked(trial.REPORT / "native.json.gz", receipt["primary_gzip_sha256"])
    return native, receipt


def assemble(work, lock):
    if (work / EARLY).exists():
        native_binding(work, lock)
        return
    document, _, _, raw, evidence = factor_evidence(work, lock)
    payload = encoded(document) + b"\n"
    native, packed = work / NATIVE, trial.REPORT / "native.json.gz"
    if packed.exists() and gzip.decompress(packed.read_bytes()) != payload:
        raise ValueError("published native input differs from this replay")
    for path, data in (
        (native, payload),
        (packed, gzip.compress(payload, compresslevel=5, mtime=0)),
    ):
        if not path.exists():
            write(path, data)
        elif path.read_bytes() != data:
            raise ValueError("assembled primary input changed between execution and publication")
    receipt = dict(
        case=trial.IDENT,
        primary_native_sha256=_sha(native),
        primary_gzip_sha256=_sha(packed),
        conditional_native_sha256=lock["parent_files"]["native.json.gz"],
        original_native_sha256=lock["original"]["native"]["sha256"],
        source_lock_sha256=_sha(work / "source-lock.json"),
        raw_exits_sha256=_sha(work / "raw-exits.json"),
        publisher_sha256=_sha(Path(__file__)),
        replayed_visits=len(lock["selected"]),
        workers=raw["workers"],
        census=evidence["counts"],
    )
    for dest in (trial.REPORT / EARLY, work / EARLY):
        save_json(dest, receipt)
    print(
        f"Primary-native input sealed at {native} ({receipt['primary_native_sha256']})", flush=True
    )


def position(work, lock):
    native, _ = native_binding(work, lock)
    case, original = whole_iq.binding(trial.IDENT)
    whole.terminal_position(
        work, "upper-primary", native, work / "actual", lock["workers"][0][0], lock, case, original
    )
    if whole_iq.read(work / "actual/terminal.json")["exit_code"]:
        raise RuntimeError("upper primary compact service ended unsuccessfully")


def positions(work, lock):
    native, input_receipt = native_binding(work, lock)
    home = work / "actual"
    terminal = whole_iq.read(home / "terminal.json")
    end = whole_iq.read(home / "end.json")
    plan = whole_iq.read(home / "plan.json")
    raw = whole_iq.read(home / "raw.json")
    whole_iq.checked(home / "service.log", terminal["log_sha256"])
    if (
        terminal["exit_code"]
        or end["cpus"] != [lock["workers"][0][0]]
        or end["memory.max"] != whole_iq.MEMORY
        or end["memory.swap.max"]
        or end["memory.swap.current"]
        or end["memory.events.oom_kill"]
        or plan["source_lock_sha256"] != input_receipt["source_lock_sha256"]
        or raw["native_sha256"] != "sha256:" + input_receipt["primary_native_sha256"]
    ):
        raise ValueError("compact terminal does not bind the primary waveform and capped service")
    _, original = whole_iq.binding(trial.IDENT)
    request = whole_iq.checked(home / "recording/request.json", raw["request_sha256"])
    whole_iq.verify_request(
        whole_iq.read(request),
        original,
        native_path=str(native),
        native_sha256=raw["native_sha256"],
    )
    common = dict(
        id=trial.IDENT,
        mode="matched-tile",
        cohort="upper-edge primary-only factors",
        paired_capture_sha256=lock["original"]["native"]["sha256"],
        original_request_sha256=lock["original"]["request"]["sha256"],
        catalog_sha256=lock["original"]["catalog"]["sha256"],
        tile=lock["original"]["tile"],
    )
    result = whole_iq.read(home / "position.json")
    rows = [dict(common, method=trial.METHOD, result=result, native_sha256=_sha(native))]
    historic = list(whole.rows_from(trial.parent_path(lock, whole.POS)))
    for _, method, _ in METHODS[1:]:
        (row,) = [r for r in historic if r["id"] == trial.IDENT and r["method"] == method]
        if any(row[k] != common[k] for k in whole.MINIMAL):
            raise ValueError("position comparison changed its causal request, recording or offer")
        rows.append(dict(row, cohort=common["cohort"]))
    for row in rows:
        validate_result(row["result"])
    return rows, dict(terminal, end=end)


def timing(lock, replacements):
    path = trial.parent_path(lock, "timing.csv")
    with path.open(newline="") as stream:
        historical = {
            int(r["visit"]): r for r in csv.DictReader(stream) if r["status"] == "processed"
        }
    if len(historical) != 4868 or not replacements.keys() <= historical.keys():
        raise ValueError("historical timing does not bind the replayed slots")
    paired = [
        dict(
            visit=v,
            conditional_cpu_ms=float(historical[v]["cpu_ms"]),
            conditional_wall_ms=float(historical[v]["wall_ms"]),
            primary_cpu_ms=r["cpu_ns"] / 1e6,
            primary_wall_ms=r["wall_ns"] / 1e6,
            historical_grids=int(historical[v]["folded_calls"]),
            primary_grids=r["primary_grids"],
            **{f"fine_{key}": value for key, value in r["fine"].items()},
        )
        for v, r in sorted(replacements.items())
    ]
    complete = sum(float(r["cpu_ms"]) for r in historical.values()) / 1e3
    old = sum(r["conditional_cpu_ms"] for r in paired) / 1e3
    measured = sum(r["primary_cpu_ms"] for r in paired) / 1e3
    prior_grids = sum(int(r["folded_calls"]) for r in historical.values())
    count = prior_grids + sum(r["primary_grids"] - r["historical_grids"] for r in paired)
    if count != sum(s["primary"] * s["visits"] for s in lock["census"]):
        raise ValueError("newly measured 12-anchor grid totals differ from the historical census")
    summary = dict(
        conditional_historical_complete_cpu_s=complete,
        conditional_historical_selected_cpu_s=old,
        primary_selected_cpu_s=measured,
        complete_primary_cross_execution_cpu_s=complete - old + measured,
        complete_primary_ideal_four_core_detector_wall_s=(complete - old + measured) / 4,
        primary_selected_within_20_ms=sum(r["primary_wall_ms"] <= 20 for r in paired),
        complete_primary_grids=count,
        complete_conditional_grids=prior_grids,
        fine={k: sum(r[f"fine_{k}"] for r in paired) for k in trial.field.FINE_COUNTERS},
    )
    summary.update(
        {
            f: distribution([r[f] for r in paired])
            for f in (
                "conditional_cpu_ms",
                "conditional_wall_ms",
                "primary_cpu_ms",
                "primary_wall_ms",
            )
        }
    )
    return paired, summary


def render(out, summary):
    fig, axes = plot.canvas(
        "DS29-0082 detector costs on original retry visits",
        "1,010 authenticated visits · both physical receivers per visit",
        "The conditional costs are historical timings from CPUs 0, 1, 4–7, 20 and 21. "
        "The selected primary-only replay used CPUs 12–15.",
    )
    for ax, metric, title in zip(
        axes, ("cpu", "wall"), ("CPU cost", "Monotonic wall"), strict=True
    ):
        bins = [summary[f"{key}_{metric}_ms"] for key in ("conditional", "primary")]
        plot.paired(
            ax,
            ["Conditional 12/22", "Primary 12 only"],
            [(v["p50"], v["p95"]) for v in bins],
            title=title,
            xlabel="Host milliseconds",
            fmt=".1f",
        )
    plot.key(fig, "Median", "95th percentile")
    fig.savefig(out / "timing.png", dpi=165, facecolor="white")
    fig.savefig(out / "timing.pdf", facecolor="white", metadata={"CreationDate": None})
    plot.plt.close(fig)
    files = ("timing.csv", "timing.pdf", "timing.png", "audit.json", "prediction-lock.json")
    save_json(out / "timing-lock.json", {"files": {f: _sha(out / f) for f in files}})
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="upper-primary-ds29-timing",
            title="Upper-edge primary-only detector timing",
            sample="1,010 DS29-0082 original retry visits",
            boundary="Resident CI16 through both original detector projections",
            note="The historical and selected timings came from different host executions. "
            "Detector timings exclude chunk decoding, authentication and compact position.",
            seal="timing-lock.json",
            image="timing.png",
            pdf="timing.pdf",
            csv="timing.csv",
        ),
    )


def publish(work, lock):
    out = trial.REPORT
    native, _ = native_binding(work, lock)
    endpoints, compact = positions(work, lock)
    document, replacements, changes, raw, evidence = factor_evidence(work, lock)
    if encoded(document) + b"\n" != native.read_bytes():
        raise ValueError("the complete primary factor stream differs from the position input")
    paired, summary = timing(lock, replacements)
    path = out / "prediction-lock.json"
    if path.exists():
        for name, digest in whole_iq.read(path)["files"].items():
            whole_iq.checked(out / name, digest)
        whole_iq.checked(
            work / "actual/position.json",
            whole_iq.read(path)["files"]["receipts/actual/position.json"],
        )
    whole.pack(out / whole.POS, endpoints)
    csv_file(out / "timing.csv", paired)
    csv_file(out / "changed-visits.csv", changes)
    save_json(
        out / "audit.json",
        dict(
            raw=raw,
            timing=summary,
            compact=compact,
            factor_comparison=evidence,
            position_endpoints={r["method"]: endpoint(r["result"]) for r in endpoints},
        ),
    )
    files = [
        "PROTOCOL.md",
        "source-lock.json",
        EARLY,
        "native.json.gz",
        whole.POS,
        "timing.csv",
        "changed-visits.csv",
        "audit.json",
    ]
    evidence_paths = [
        work / f for f in ("smoke.json", "smoke-input.json", "launch.json", "raw-exits.json")
    ]
    evidence_paths.extend(p for p in (work / "actual").rglob("*") if p.is_file())
    evidence_paths.extend(p for p in work.glob("cpu-*") if p.is_file())
    for src in sorted(evidence_paths):
        dest = Path("receipts") / src.relative_to(work)
        data = src.read_bytes()
        if src.suffix == ".jsonl":
            dest = dest.with_suffix(".jsonl.gz")
            data = gzip.compress(data, compresslevel=5, mtime=0)
        write(out / dest, data)
        files.append(str(dest))
    save_json(
        path,
        dict(
            cases=[trial.IDENT],
            files={name: _sha(out / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    _, (truth,) = held_references(None, [trial.IDENT])
    csv_file(out / "scores.csv", whole.geographic(endpoints, {trial.IDENT: truth}))
    csv_file(
        out / "v5-controls.csv",
        [
            dict(
                role=role,
                arm=arm,
                error_km=truth["reference"][role][arm]["error_km"],
                conditional_rms_hz=truth["reference"][role][arm].get("rf_rms_hz"),
            )
            for role in ROLES
            for arm in ARMS
        ],
    )
    save_json(
        out / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(path),
            files={f: _sha(out / f) for f in ("scores.csv", "v5-controls.csv")},
        ),
    )
    save_json(
        out / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="upper-primary-position",
                    title="Upper-edge position with the original primary anchors",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal=path.name,
                    caption="Both receivers were recomputed at all original retry visits. "
                    "Positions use the same original causal request, catalogue and 25 km offer.",
                    provenance=["source-lock.json", EARLY, "audit.json"],
                    series=[
                        dict(
                            key=key,
                            file=whole.POS,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=whole.MINIMAL,
                        )
                        for key, method, label in METHODS
                    ],
                )
            ],
        ),
    )
    render(out, summary)
    whole.generate(out / "charts", evidence=out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("assemble", "position", "publish"))
    parser.add_argument("work", nargs="?", type=local_output, default=trial.WORK)
    args = parser.parse_args()
    with trial.configured():
        lock, _ = trial.base.configure(args.work)
        dict(assemble=assemble, position=position, publish=publish)[args.action](args.work, lock)


if __name__ == "__main__":
    main()
