"""Score fixed-scaffold positions and publish independent stock branch evidence."""

import argparse
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from statistics import mean

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, sealed
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .scaffold_rescue_trial import CASES, DIAG, FFTW, METHOD, PRIMARY, REPORT, STRIDE, WHOLE, read

GRAPH = r"""
import json, runpy, sys
from pathlib import Path
root, path, digest, config, donors, algorithm = sys.argv[1:]
sys.path.insert(0, root)
from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from tools.pipeline_eval.variants.direct_lifetime_kernels import prepare_owned, read_native
source = read_native(dict(path=path, sha256='sha256:' + digest))
config = TrackConfig(**json.loads(Path(config).read_bytes())['config'])
base = prepare_owned(prepare_tracks, source, config)
abi = runpy.run_path(algorithm)
sidecar = json.loads(Path(donors).read_bytes())
adapted, proof = abi['attach'](base, sidecar['lanes'], sidecar['donors'], config.alias_spacing_hz)
original = abi['original_members'](base['tracks'])
modified = abi['original_members'](adapted['tracks'])
stock_observations = {o['observation_id']:o['measured_cfo_hz'] for o in base['observations']}
added = {item['id'] for item in proof['attachments']}
kept = {k:[r for r in v if r[0] not in added] for k,v in modified.items()}
curved = set(proof['stock_curvature_keys'])
assert kept == original and list(kept) == list(original)
groups = [dict(key=k, curved=k in curved,
    members=[(i,t,v,stock_observations[i]) for i,t,v in pts],
    added=[x for x in modified[k] if x[0] in added]) for k,pts in original.items()]
print(json.dumps(dict(proof=proof, groups=groups), allow_nan=False))
"""


def positions(rows):
    packs = {
        p: sealed(p, "prediction-lock.json", "positions.jsonl.gz")
        for p in (WHOLE, FFTW, DIAG, STRIDE)
    }
    out = []
    for parent in rows:
        ident = parent["id"]
        archives = (WHOLE, FFTW) if ident in PRIMARY else (STRIDE, DIAG)
        for index, condition in enumerate(("stock", "fftw")):
            source = archives[index]
            required = parent["parents"]["stock_sha" if condition == "stock" else "donor_sha"]
            (stock,) = [
                r for r in packs[source] if r["id"] == ident and r["native_sha256"] == required
            ]
            if any(
                stock[k] != parent[k]
                for k in (
                    "paired_capture_sha256",
                    "catalog_sha256",
                    "original_request_sha256",
                    "tile",
                )
            ):
                raise ValueError("archived FFTW or stock comparator has different inputs")
            out.append(
                dict(
                    stock,
                    condition=condition,
                    method=METHOD + "_" + condition,
                    cohort=parent["cohort"],
                    parents=parent["parents"],
                )
            )
    return out


def timing(rows):
    ledgers = {p: sealed(p, "prediction-lock.json", "visits.jsonl.gz") for p in (WHOLE, FFTW, DIAG)}
    costs = []
    for row in rows:
        ident = row["id"]
        stock_source, donor_source = (WHOLE, FFTW) if ident in PRIMARY else (DIAG, DIAG)
        donor_role = "fftw" if ident in PRIMARY else "candidate"
        a, b = (
            [r for r in ledgers[folder] if (r["id"], r["role"]) == (ident, label)]
            for folder, label in ((stock_source, "control"), (donor_source, donor_role))
        )
        paired = []
        for x, y in zip(a, b, strict=True):
            if (x["visit"], x["status"], x["visit_metadata_sha256"]) != (
                y["visit"],
                y["status"],
                y["visit_metadata_sha256"],
            ):
                raise ValueError("raw timing sources did not cover matching physical visits")
            if x["status"] == "processed":
                paired.append((x, y, any(p["winner_sha256"] is None for p in x["probes"])))
        if len(paired) * 2 != sum(row["paired_roster"].values()):
            raise ValueError("clock count differs from the exact native receiver census")
        phased = [x["wall_s"] + call * y["wall_s"] for x, y, call in paired]
        fitted = row.get("scaffold") or {}
        proof = fitted.get("attachments", [])
        buffered = [fitted["capture_duration_s"] - p["time_s"] for p in proof]
        delay = distribution(buffered)
        costs.append(
            dict(
                id=ident,
                valid_visits=len(paired),
                modeled_second_pass_visits=sum(call for _, _, call in paired),
                stock_cpu_ms=1e3 * mean(x["cpu_s"] for x, _, _ in paired),
                full_fftw_cpu_ms=1e3 * mean(y["cpu_s"] for _, y, _ in paired),
                both_full_streams_mean_cpu_ms=1e3
                * mean(x["cpu_s"] + y["cpu_s"] for x, y, _ in paired),
                modeled_stock_first_mean_cpu_ms=1e3
                * mean(x["cpu_s"] + call * y["cpu_s"] for x, y, call in paired),
                stock_within_20ms=sum(x["wall_s"] <= 0.020 for x, _, _ in paired),
                fftw_within_20ms=sum(y["wall_s"] <= 0.020 for _, y, _ in paired),
                modeled_serial_within_20ms=sum(w <= 0.020 for w in phased),
                full_sample_frontier_s=fitted.get("capture_duration_s"),
                attached_buffer_min_s=delay["min"],
                attached_buffer_median_s=delay["p50"],
                attached_buffer_max_s=delay["max"],
                stock_preparation_cpu_s=fitted.get("stock_preparation_cpu_s"),
                stock_preparation_wall_s=fitted.get("stock_preparation_wall_s"),
                attachment_cpu_s=fitted.get("attachment_cpu_s"),
                attachment_wall_s=fitted.get("attachment_wall_s"),
            )
        )
    return costs


def graph_audit(work, plan, rows):
    members, summary = [], []
    variant = "tools/pipeline_eval/variants/scaffold_rescue.py"
    whole_iq.checked(ROOT / variant, plan["files"][variant])
    for row in rows:
        ident, measured = row["id"], row["scaffold"]
        if measured is None:
            continue
        _, request = whole_iq.binding(ident)
        config = request["job"]["track_config"]
        folder = work / ident / "scaffold"
        native, donor = folder / "recording/native.json", folder / "donors.json"
        whole_iq.checked(native, row["native_sha256"])
        whole_iq.checked(donor, row["sidecar_sha256"])
        whole_iq.checked(Path(config["path"]), config["sha256"])
        command = [
            "taskset",
            "-c",
            str(row["cpu"]),
            sys.executable,
            "-IB",
            "-c",
            GRAPH,
            plan["receiver"],
            str(native),
            row["native_sha256"],
            config["path"],
            str(donor),
            str(ROOT / variant),
        ]
        audit = json.loads(
            subprocess.check_output(command, env={**os.environ, **THREAD_ENV}, timeout=40)
        )
        bounds, proofs = audit["groups"], audit["proof"]
        if any(measured[k] != proof for k, proof in proofs.items()):
            raise ValueError("fit-time attachment differs from the independent installed Graph")
        result = row["result"]["metrics"]
        if "observations" in result and (result["observations"], result["tracks"]) != (
            measured["stock_observations"] + len(measured["attachments"]),
            measured["stock_groups"],
        ):
            raise ValueError("actual position receiver did not retain the specified scaffold")
        members.extend(dict(id=ident, **group) for group in bounds)
        n = len(measured["attachments"])
        summary.append(
            dict(
                id=ident,
                cohort=row["cohort"],
                stock_groups=measured["stock_groups"],
                stock_curved_groups=len(measured["stock_curvature_keys"]),
                stock_members=measured["stock_members"],
                preserved_members=measured["stock_members"],
                preserved_raw_cfo=measured["stock_observations"],
                added=n,
                gap_reject=proofs["census"].get("no_close_bracket", 0),
                piece_reject=proofs["census"].get("missing_single_piece", 0),
                cfo_reject=proofs["census"].get("cfo_outside_gate", 0),
                ambiguous=proofs["census"].get("ambiguous_tracks", 0),
                donor_proposals=row["paired_roster"].get("01", 0),
                lifts=sum(a["lift"] != 0 for a in measured["attachments"]),
                max_abs_residual_hz=max(
                    (abs(a["residual_hz"]) for a in measured["attachments"]), default=None
                ),
                original_group_and_branch_sha256=sha256(
                    encoded([dict(key=g["key"], members=g["members"]) for g in bounds])
                ).hexdigest(),
                stock_sky_norads=measured["stock_sky_norads"],
                stock_sky_norad_sha256=measured["stock_sky_norad_sha256"],
            )
        )
    csv_file(REPORT / "group-support.csv", summary)
    write(REPORT / "group-branches.jsonl.gz", compressed_rows(members))


def figures():
    names = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "group-support.csv",
        "time-work.csv",
        "scores.csv",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(CASES), files={p: _sha(REPORT / p) for p in names}),
    )
    rows = [
        dict(
            key=key,
            label=label,
            value=method,
            file=names[0],
            native_field="paired_capture_sha256",
            match=["catalog_sha256", "original_request_sha256", "tile", "parents"],
        )
        for key, label, method in (
            ("one", "Fixed Graph rescue", METHOD),
            ("stock", "Exact stock wide", METHOD + "_stock"),
            ("one_native_factors", "Complete unfiltered FFTW", METHOD + "_fftw"),
        )
    ]
    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="fixed-scaffold-rescue",
                    method=METHOD,
                    scope="roof",
                    cases="sealed",
                    seal="figure-lock.json",
                    title="Rescue measured pilots inside stock track brackets",
                    caption=(
                        "All original track members and CFO branches stay fixed. Complete stock "
                        "and FFTW pairs supply two diagnostic and two replication recordings."
                    ),
                    provenance=list(names[1:]),
                    series=rows,
                )
            ],
        ),
    )


def publish(work):
    plan = read(REPORT / "plan.json")
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    if (
        len(rows) != len(CASES)
        or {r["id"] for r in rows} != set(CASES)
        or any(_sha(ROOT / p) != d for p, d in plan["files"].items())
    ):
        raise ValueError("trial plan, source, or attempt roster changed")
    combined = rows + positions(rows)
    graph_audit(work, plan, rows)
    csv_file(REPORT / "time-work.csv", timing(rows))
    refs = {r["id"]: r for r in held_references(None, CASES)[1]}
    scored = []
    for row in combined:
        for arm in ARMS:
            stats = fit(row, refs[row["id"]], arm)
            original = refs[row["id"]]["reference"]["baseline"][arm]["error_km"]
            scored.append(
                dict(
                    stats,
                    condition=row["condition"],
                    cohort=row["cohort"],
                    original_v5_km=original,
                    within_10pct_original=stats["error_km"] is not None
                    and stats["error_km"] <= original * 1.1,
                )
            )
    csv_file(REPORT / "scores.csv", scored)
    csv_file(
        REPORT / "capture-era-v5.csv",
        [
            dict(
                id=ident,
                arm=arm,
                method=role,
                **{
                    k: ref["reference"][role][arm].get(k)
                    for k in ("status", "error_km", "rf_rms_hz")
                },
            )
            for ident, ref in refs.items()
            for role in ROLES
            for arm in ARMS
        ],
    )
    csv_file(
        REPORT / "position-work.csv",
        [
            dict(
                id=r["id"],
                status=r["result"]["status"],
                wall_s=(usage := r["position_resources"] or {}).get("wall_s"),
                cpu_s=usage.get("cpu_s"),
                peak_bytes=usage.get("peak_bytes"),
                swap_bytes=usage.get("end", {}).get("memory.swap.current"),
            )
            for r in rows
        ],
    )
    write(REPORT / "positions.jsonl.gz", compressed_rows(combined))
    figures()
    names = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "group-support.csv",
        "group-branches.jsonl.gz",
        "time-work.csv",
        "position-work.csv",
        "scores.csv",
        "capture-era-v5.csv",
        "figure-lock.json",
        "figures.json",
        "INTEGRATION.md",
    )
    save_json(
        REPORT / "score-lock.json",
        dict(files={n: _sha(REPORT / n) for n in names}, exporter_sha256=_sha(Path(__file__))),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=REPORT)
