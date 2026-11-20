"""Seal matching whole-IQ trials and publish both compact position distributions."""

import argparse
import gzip
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, distribution
from . import hard_pilots_eval as witness
from . import multilag_whole_trial as trial
from . import whole_band_results as measured
from .exact_wide_iq_results import detector_rows
from .fresh_replay_results import geographic
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
ROLES = ("four", "five", "candidate")
POSITION = "positions.jsonl.gz"
MATCH = ("paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile")
METHOD = {"four": "multilag_whole_four", "five": "multilag_whole_five", "candidate": trial.METHOD}


def historical(ident, authorities):
    results, resources = {}, {}
    for role, bound in authorities.items():
        folder = ROOT / bound["folder"]
        whole_iq.checked(folder / "prediction-lock.json", bound["prediction_lock_sha256"])
        for file, digest in bound["files"].items():
            whole_iq.checked(folder / file, digest)
        selected = [
            row
            for row in rows_from(folder / POSITION)
            if row["id"] == ident and row["method"] == bound["method"]
        ]
        if len(selected) != 1:
            raise ValueError("historical position branch does not resolve to one terminal result")
        results[role] = dict(selected[0], original_method=bound["method"], method=METHOD[role])
        resource = whole_iq.read(folder / "resources.json")[ident]
        entry = bound["branch"] if bound["branch"] in ("control", "candidate") else "candidate"
        resources[role] = resource[entry]
    return results, resources


def aligned(original, proposed):
    if witness.support(original) != witness.support(proposed):
        raise ValueError("capture clocks, validity, radio support or measurement geometry changed")
    for before, after in zip(
        original["source"]["probes"], proposed["source"]["probes"], strict=True
    ):
        if witness.metadata(before) != witness.metadata(after):
            raise ValueError("physical probe clock, channel or tuned RF differs")
        yield before, after


def physical_counts(original, stock, fifth, candidate):
    counters = Counter()
    roles = dict(four=stock, five=fifth, candidate=candidate)
    capture = original["source"]["probes"]
    paired = [aligned(original, doc) for doc in roles.values()]
    for expected, *visits in zip(capture, *paired, strict=True):
        counters["probes"] += 1
        values = dict(zip(roles, (pair[1]["candidates"] for pair in visits), strict=True))
        winner = witness.factor_cross.winner(expected["candidates"])
        hits = {}
        for role, candidates in values.items():
            ok = [p for p in candidates if p[witness.GATE]]
            counters[f"{role}:gate_candidates"] += len(ok)
            counters[f"{role}:positive_probes"] += bool(ok)
            if winner is not None:
                target = expected["candidates"][winner]
                decision = witness.classify(target, candidates)
                hits[role] = decision["category"] == "physical_gated"
                counters[f"{role}:physical_original_winner_available"] += hits[role]
                counters[f"{role}:actual_winner_matches"] += decision["actual_winner_matches"]
        if winner is not None:
            counters["original_winning_probes"] += 1
            counters["old_common_original_misses"] += not hits["four"] and not hits["five"]
            counters["recoveries_from_both_old_misses"] += (
                hits["candidate"] and not hits["four"] and not hits["five"]
            )
            counters["original_winners_lost_vs_five"] += hits["five"] and not hits["candidate"]
            counters["original_winners_gained_vs_five"] += hits["candidate"] and not hits["five"]
    return dict(counters)


def attempt(work, ident, lock):
    """Validate the sorted service affinity against the ordered raw-lane assignment."""
    path = work / ident / "candidate/start.json"
    read = whole_iq.read
    if not path.is_file():
        return measured.attempt(work, ident, "candidate", lock, method=trial.METHOD)
    active, planned = read(path), lock["cases"][ident]["cpus"]
    if active["cpus"] != sorted(planned):
        raise ValueError("service entry affinity differs from frozen raw lane assignment")

    def in_plan_order(receipt):
        value = read(receipt)
        return dict(value, cpus=planned) if receipt == path else value

    # The shared verifier compares both the entry mask and ordered lane assignments.
    # Retain the unmodified entry receipt in all published diagnostics.
    if not (path.parent / "service.json").is_file():
        with patch.multiple(iq_service, _read=in_plan_order, MODULE=trial.MODULE):
            iq_service.reconcile(path.parent)
    with patch.object(whole_iq, "read", in_plan_order):
        row, diagnostics, artifact = measured.attempt(
            work, ident, "candidate", lock, method=trial.METHOD
        )
    if "stages" in diagnostics:
        diagnostics["stages"][0] = active
    return row, diagnostics, artifact


def seal(work):
    if (REPORT / "prediction-lock.json").exists():
        raise FileExistsError("the completed services are already sealed")
    lock = trial.bound(work)
    cases, pool, resource, probe_audit, files = lock["cases"], [], {}, {}, []
    for ident, expected in cases.items():
        prior, clocks = historical(ident, lock["historical"][ident])
        row, terminal, native = attempt(work, ident, lock)
        if any(row[k] != control[k] for control in prior.values() for k in MATCH):
            raise ValueError(
                "historical compact fit used a different frozen request or physical offer"
            )
        pool.extend([*(dict(p, cohort=expected["cohort"]) for p in prior.values()), row])
        resource[ident] = dict(clocks, candidate=terminal)
        folder = work / ident / "candidate"
        archive = REPORT / "receipts" / ident
        for receipt in (
            "service.log",
            "start.json",
            "service.json",
            "raw.json",
            "end.json",
            "plan.json",
            "service-launch.json",
        ):
            point = folder / receipt
            if not point.is_file():
                continue
            if receipt == "service.log":
                whole_iq.checked(point, terminal["service"]["log_sha256"])
            write(archive / receipt, point.read_bytes())
            files.append(str((archive / receipt).relative_to(REPORT)))
        missing = folder.parent / "candidate-failure.json"
        if missing.is_file():
            write(archive / missing.name, missing.read_bytes())
            files.append(str((archive / missing.name).relative_to(REPORT)))
        if native is not None:
            launch = whole_iq.read(folder / "plan.json")
            if launch["differential_sources"] != lock["programs"]:
                raise ValueError("actual native work did not bind the frozen scout program")
            for parent in clocks.values():
                measured.pair_geometry(parent, terminal)
            original, bindings = witness.resolve(ident, witness._load_case(ident))
            if any(
                bindings[role]["native_sha256"] != prior[role]["native_sha256"] for role in prior
            ):
                raise ValueError(
                    "reference native arrays do not bind exactly to the matched positions"
                )
            target = f"native/{ident}.json.gz"
            write(REPORT / target, gzip.compress(native.read_bytes(), compresslevel=5, mtime=0))
            files.append(target)
            probe_audit[ident] = physical_counts(
                *(original[k] for k in ("capture", "four", "five")), whole_iq.read(native)
            )
            _, clocks, logical = detector_rows(folder)
            if len(clocks) != terminal["dual_calls"]:
                raise ValueError("raw visit and solver input accounting differ")
            probe_audit[ident].update(
                logical_native_sha256=logical, native_sha256=row["native_sha256"]
            )
    pack(REPORT / POSITION, pool)
    save_json(REPORT / "resources.json", resource)
    save_json(REPORT / "probe-audit.json", probe_audit)
    files.extend(
        ("PROTOCOL.md", "source-lock.json", POSITION, "resources.json", "probe-audit.json")
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(cases),
            files={f: _sha(REPORT / f) for f in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def publish():
    lock = whole_iq.read(REPORT / "prediction-lock.json")
    for name, source in lock["files"].items():
        whole_iq.checked(REPORT / name, source)
    positions = rows_from(REPORT / POSITION)
    _, refs = held_references(None, lock["cases"])
    scores = geographic(positions, {r["id"]: r for r in refs})
    csv_file(REPORT / "scores.csv", scores)
    index = {m: r for r, m in METHOD.items()}
    resources = whole_iq.read(REPORT / "resources.json")
    timings = []
    for item in positions:
        ident, role = item["id"], index[item["method"]]
        previous = resources[ident][role]
        timings.append(
            dict(
                id=ident,
                role=role,
                status=item["result"]["status"],
                **{
                    key: previous.get(key)
                    for key in (
                        "wall_s",
                        "cpu_s",
                        "raw_s",
                        "assembly_s",
                        "position_s",
                        "wall_to_failure_s",
                        "dual_calls",
                        "within_20ms",
                        "max_bytes",
                        "swap_bytes",
                    )
                },
                wall_p50_ms=previous.get("detector_call_wall_ms", {}).get("p50"),
                wall_p95_ms=previous.get("detector_call_wall_ms", {}).get("p95"),
                cpu_p50_ms=previous.get("detector_call_cpu_ms", {}).get("p50"),
            )
        )
    csv_file(REPORT / "timing.csv", timings)
    counts = {}
    for role, method in METHOD.items():
        counts[role] = {}
        for arm in ARMS:
            panel = [r for r in scores if (r["method"], r["arm"]) == (method, arm)]
            counts[role][arm] = dict(
                attempted=len(panel),
                published=sum(r["error_km"] is not None for r in panel),
                within_5pct=sum(r["within_5pct"] for r in panel),
                within_10pct=sum(r["within_10pct"] for r in panel),
                position_km=distribution([r["error_km"] for r in panel]),
                rf_hz=distribution([r["conditional_rms_hz"] for r in panel]),
            )
    save_json(REPORT / "summary.json", dict(arms=counts, timings=timings))
    certificate = (
        POSITION,
        "scores.csv",
        "timing.csv",
        "summary.json",
        "prediction-lock.json",
        "probe-audit.json",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=lock["cases"], files={name: _sha(REPORT / name) for name in certificate}),
    )
    methods = [
        ("candidate", "one", "Three-lag fifth center"),
        ("four", "stock", "Archived four centers"),
        ("five", "one_native_factors", "Archived fifth center"),
    ]
    save_json(
        REPORT / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="multilag-whole",
                    method=trial.METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    provenance=certificate[1:],
                    title="Three-lag pilot timing on two complete saved-IQ recordings",
                    caption=(
                        "Same compact receiver, original 25 km offers and matched calibration. "
                        "Earlier four and five are measured controls. All attempts stay visible."
                    ),
                    series=[
                        dict(
                            value=METHOD[role],
                            key=key,
                            label=label,
                            file=POSITION,
                            native_field="paired_capture_sha256",
                            match=MATCH,
                        )
                        for role, key, label in methods
                    ],
                )
            ],
        ),
    )
    generate(REPORT / "charts", evidence=REPORT)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("seal", "publish"))
    p.add_argument("--work", type=local_output, default=trial.WORK)
    args = p.parse_args()
    if args.stage == "seal":
        seal(args.work)
    else:
        publish()
