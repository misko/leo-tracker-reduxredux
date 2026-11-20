"""Bind fresh serial benchmarks and describe the archive's per-attempt cap sensitivity."""

import argparse
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km
from . import failed_only_benchmark as route
from . import failed_only_results as archived
from . import full_receiver_comparison as auth
from .phase_support_results import pack


def cap_effect(stock, routed, cap):
    pending = [
        row
        for row in routed.values()
        if (
            (row["routing"]["stock_wall_s"] or 0) > cap
            or (row["routing"]["repair_wall_s"] or 0) > cap
        )
        and row["result"]["status"] != "timed_out"
    ]
    return dict(
        cap_s=cap,
        archived_completed_over_cap=[row["id"] for row in pending],
        archive_stock_publications_over_cap={
            arm: [
                row["id"]
                for row in pending
                if stock[row["id"]]["result"]["arms"][arm]["latlon"] is not None
            ]
            for arm in ARMS
        },
        archive_routed_publications_over_cap={
            arm: [row["id"] for row in pending if row["result"]["arms"][arm]["latlon"] is not None]
            for arm in ARMS
        },
        scope="Observed archived stage intervals only. Runtime on a new launch may differ.",
    )


def read_cli(root):
    records = []
    for file in sorted((root / "runs").rglob("predictions.jsonl")):
        if not file.is_symlink():
            records.extend(read_predictions(file).values())
    return records


def publish(fresh, initial, out):
    seal = auth.seal(
        out,
        "prediction-lock.json",
        (
            archived.POSITIONS,
            archived.STOCK,
            "source-lock.json",
            "original-four-scores.json",
        ),
    )
    source = auth.read(out / "source-lock.json")
    refs = auth.read(out / "original-four-scores.json")
    stock, routed = (read_predictions(out / name) for name in (archived.STOCK, archived.POSITIONS))
    lock = auth.read(fresh / "fresh-lock.json")
    if (
        lock["method"] != source["method_sha256"]
        or lock["protocol_sha256"] != source["routing_sources"]["PROTOCOL.md"]
        or lock["sources"] != source["corpus"]
        or lock["worker_cap_s"] != route.CAP_S
    ):
        raise ValueError("fresh cases differ from the frozen archive and router")
    rows = read_cli(fresh)
    auth.roster_matches([r["id"] for r in rows], lock["cases"], "fresh router serial attempts")
    details = []
    for row in rows:
        ident = row["id"]
        candidate, result = routed[ident], row["result"]
        state = row["routing"]
        if row["implementation_sha256"] != lock["method"] or state["cap_s"] != route.CAP_S:
            raise ValueError(f"{ident} fresh result was measured with different source or cap")
        if candidate["result"]["status"] != "unavailable":
            auth.require_fields(
                row["input_binding"],
                {
                    **{
                        k: candidate[k]
                        for k in (
                            "native_sha256",
                            "catalog_sha256",
                            "frozen_request_sha256",
                            "tile",
                        )
                    },
                    "track_config_sha256": source["track_config_sha256"][ident],
                },
            )
        else:
            auth.require_fields(row, dict(input_binding=None, input_sha256=None))
        attempts = {}
        for label, attempt in state["attempts"].items():
            value = attempt["result"]
            attempts[label] = dict(
                status=value["status"],
                reason=value.get("reason"),
                launch_wall_s=attempt["worker_wall_s"],
                numerical_wall_s=value["metrics"].get("candidate_s"),
            )
        details.append(
            dict(
                id=ident,
                cpu=lock["cases"][ident],
                cause=state["cause"],
                selected=state["selected"],
                result_status=result["status"],
                total_worker_wall_s=row["worker_wall_s"],
                attempts=attempts,
                same_archive_status=result["status"] == candidate["result"]["status"],
                arms={
                    arm: dict(
                        error_km=distance_km(result["arms"][arm]["latlon"], refs[ident]["truth"]),
                        rf_rms_hz=archived.rf(result, arm),
                        same_archive_position=result["arms"][arm]["latlon"]
                        == candidate["result"]["arms"][arm]["latlon"],
                    )
                    for arm in ARMS
                },
            )
        )
    files = [
        "fresh-positions.jsonl.gz",
        "fresh-lock.json",
        "fresh-summary.json",
        "cap-sensitivity.json",
    ]
    pack(out / files[0], rows)
    write(out / files[1], (fresh / "fresh-lock.json").read_bytes())
    save_json(out / files[2], details)
    save_json(out / files[3], cap_effect(stock, routed, lock["worker_cap_s"]))
    if initial:
        pack(out / "initial-fresh-positions.jsonl.gz", read_cli(initial))
        write(out / "initial-fresh-lock.json", (initial / "fresh-lock.json").read_bytes())
        files.extend(("initial-fresh-positions.jsonl.gz", "initial-fresh-lock.json"))
    save_json(
        out / "fresh-prediction-lock.json",
        dict(
            files={name: auth.sha(out / name) for name in files},
            archive_prediction_files=seal["files"],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fresh", type=Path)
    parser.add_argument("--initial", type=Path)
    parser.add_argument("--out", type=Path, default=archived.REPORT)
    args = parser.parse_args()
    publish(args.fresh, args.initial, local_output(args.out))
