"""Run two prespecified saved-detection controls for the frozen graph solver."""

import argparse
from pathlib import Path

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.qualification.paired_publication import archive_identity
from tools.pipeline_eval.scoring import distance_km
from . import covariance_transfer_trial as transfer
from .complete_family_cavity_trial import verify_archive
from .screened_stock_salvage_trial import ARMS, digest, read, require_spec
from .screened_tiled_graph_trial import MEASUREMENTS, evidence_digests, solve, write
from .solver_fused_phase_trial import saved_inputs


def score(arms, reference):
    if not arms:
        return {}
    if set(arms) != set(ARMS):
        raise ValueError("Expected positions for both calibration arms")
    return {key: distance_km(arms[key]["latlon"], reference) for key in ARMS}


def compact(result):
    return {k: v for k, v in result.items() if k != "evidence"} | {"science": evidence_digests(result)}


def dense(bench, frozen, pair_path):
    inventory = read(MEASUREMENTS / "covariance-ds30-two-pairs.json")
    case = "DS30-0008"
    entry = next(r for r in inventory["cases"] if r["case"] == case)
    if digest(pair_path) != entry["pair_sha256"]:
        raise ValueError("Unexpected DS30 pair receipt")
    pair, _, _, archive, offer, native = saved_inputs(
        pair_path, bench / "integration-covariance-posterior", None,
        expected_spec=inventory["candidate_specification_digest"])
    result = compact(solve(frozen, native, offer, archive))
    if archive_identity(archive) != pair["archive"]:
        raise ValueError("Orbit archive changed during replay")
    authority_path = MEASUREMENTS.parents[2] / "2026_11_21_ds30_full/reference-audit.json"
    station = next(r for r in read(authority_path)["cases"] if r["dataset_label"] == case)
    if not station["authority_eligible"]:
        raise ValueError("Case lacks a scoring reference")
    reference = [station["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    builds = {k: {f: run[f] for f in ("arms", "owners", "reason", "scientific_digests")}
              for k, run in pair["runs"].items()}
    return dict(case=case, pair_sha256=digest(pair_path), reference_sha256=digest(authority_path),
                native_digest=canonical_digest(native), offer=offer, archive=pair["archive"],
                builds=builds, graph=result, reference=reference,
                errors_km={k: score(run["arms"], reference) for k, run in (builds | {"graph": result}).items()})


def omitted(bench, frozen):
    path = MEASUREMENTS / "screened-stock-recovery-omitted.json"
    row = next(r for r in read(path)["rows"] if r["case"] == transfer.SOUTH and r["mode"] == "omitted-tile")
    site = bench / "portable-v5-geodiverse" / row["case"]
    if digest(site / "native.json") != row["document_sha256"] or read(site / "omitted-tile.json") != row["offer"]:
        raise ValueError("Unexpected portable detections or search region")
    verify_archive(vars(transfer), row, site)
    result = compact(solve(frozen, read(site / "native.json"), row["offer"], site / "tle"))
    verify_archive(vars(transfer), row, site)
    return dict(case=row["case"], reference_receipt_sha256=digest(path), offer=row["offer"],
                document_sha256=row["document_sha256"], history_sha256=row["history_sha256"],
                truth_clearance_km=row["reference_clearance_km"], graph=result,
                controls={k: {f: v.get(f) for f in ("status", "reason", "arms", "solver_cpu_s")}
                          for k, v in row["builds"].items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("dense", "omitted"))
    for field in ("bench", "output"):
        parser.add_argument(field, type=Path)
    parser.add_argument("--pair", type=Path)
    args = parser.parse_args()
    freeze = read(MEASUREMENTS / "screened-tiled-graph-freeze.json")
    frozen = args.bench / "integration-screened-tiled-graph"
    require_spec(frozen, freeze["specification"])
    if args.case == "dense" and args.pair is None:
        parser.error("the dense control requires --pair")
    row = dense(args.bench, frozen, args.pair) if args.case == "dense" else omitted(args.bench, frozen)
    write(args.output, dict(row, specification=freeze["specification"]))
