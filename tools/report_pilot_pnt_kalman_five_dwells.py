#!/usr/bin/env python3
"""Evaluate the pilot PNT Kalman on five newly reprocessed recorded dwells."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import report_pilot_pnt_kalman as base  # noqa: E402

from leo.analysis.qam import PilotPntKalmanConfig  # noqa: E402
from leo.analysis.starlink import StarlinkEdge  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

OUTPUT_ROOT = Path("reports/figures/2026_08_22_pilot_pnt_kalman")
PIPELINE_RELEASE_ID = "9f45c2aefc60b355ad1da173211c9c1255a13395"
WINDOW_COUNT = 8
MINIMUM_GLRT_MARGIN = 0.05
MINIMUM_WINDOW_SEPARATION_S = 0.15
MAXIMUM_WINDOW_START_S = 59.85


@dataclass(frozen=True, slots=True)
class PathSpec:
    scope_key: str
    stream: str
    receiver: int
    edge: StarlinkEdge


@dataclass(frozen=True, slots=True)
class DwellSpec:
    label: str
    session_id: str
    run_id: str
    recording_manifest_digest: str
    run_manifest_digest: str
    paths: tuple[PathSpec, ...]


@dataclass(frozen=True, slots=True)
class PathSelection:
    path: PathSpec
    cases: tuple[base.Case, ...]
    median_selected_qam_accuracy: float
    minimum_selected_qam_accuracy: float
    median_selected_glrt_margin: float


DWELLS = (
    DwellSpec(
        "D1",
        "cap-20260822T063151-ec37ad3aa3dd",
        "reprocess-6da96e09e3d546deb3f0fa361e1ae046",
        "sha256:9c22d71882f792db99a16d71dde26d621bb0a180a68538ae762a51aadb5af8cc",
        "sha256:dfa0026b93e0361fdb27fe0d1fc900824117f4d3532ff096e51a3e267e2dfbd4",
        (
            PathSpec(
                "sha256:02b0689814961636827aba40325988b03579462ca836a531c0cb4c08244e1cc8",
                "stream-0",
                0,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:64705ad0ac88ab4059a5ef41b3a20ac5b53949447789ffc067610edfa2feaf76",
                "stream-0",
                1,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:dd1f3db9207832329b3c4d45abf67c182400cf2831d46bca9106bb6018bfa75b",
                "stream-1",
                0,
                StarlinkEdge.UPPER,
            ),
            PathSpec(
                "sha256:6fb8c5f300edc3236754da1eda17b0380c534e93896032bd3b1c838a6d3f02c7",
                "stream-1",
                1,
                StarlinkEdge.UPPER,
            ),
        ),
    ),
    DwellSpec(
        "D2",
        "cap-20260822T061249-c24dfe90b587",
        "reprocess-408701f8525a406d97fa01af9433fe67",
        "sha256:b7310d5b8c0aa5c3041172930e66085ef173ede733225a6c199fb87ca6e0ddf2",
        "sha256:5a89ba64c0bde7bcd36945cd9429d8109e041cffff37f92696fae2871d1df724",
        (
            PathSpec(
                "sha256:cac5f7a93e8563441cfb6c3f9a08808e3cf08d76be25500c28d79429291de853",
                "stream-0",
                0,
                StarlinkEdge.UPPER,
            ),
            PathSpec(
                "sha256:991ba748a9ced223d5dc2f61a100e18adcab9521a0f65eb120a85153eb36aea6",
                "stream-0",
                1,
                StarlinkEdge.UPPER,
            ),
            PathSpec(
                "sha256:293b6038254ca743d84b6894becf6eca2be4f5598d1cb5e36c82aeaefc53ae8f",
                "stream-1",
                0,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:8acb0b4692dcd14f22735e1de9fc8a540cb849b8df6338791960a3f671a38a59",
                "stream-1",
                1,
                StarlinkEdge.LOWER,
            ),
        ),
    ),
    DwellSpec(
        "D3",
        "cap-20260822T060835-48b398fac634",
        "reprocess-add19254bda248f59ed03cccbe301f37",
        "sha256:5b7cc17600001c7884ecba8bd9d4566b5ed7b7662e11130974b7407243cd2a03",
        "sha256:5504ffc0d72f3d17ce2b31f4c2142d948e6f3d13ef9159073fb4096e923aaf8f",
        (
            PathSpec(
                "sha256:ced2dd4c2e2fc4dde803b8b846f3ca9ae9a73871128fcc9324d4e718383a881c",
                "stream-0",
                0,
                StarlinkEdge.UPPER,
            ),
            PathSpec(
                "sha256:05046ae1ea1fda238b35ae486f5538d9e03f0331f7a627e82269c09aa0717587",
                "stream-0",
                1,
                StarlinkEdge.UPPER,
            ),
            PathSpec(
                "sha256:74069badb9d5e0d6fb7341f76633f1c1d03247405ffa944f15c42d621a67559f",
                "stream-1",
                0,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:7725c352bd8e2a3c24bbe8b7d0c10a48eb4bc96f00642099593c043e6682902e",
                "stream-1",
                1,
                StarlinkEdge.LOWER,
            ),
        ),
    ),
    DwellSpec(
        "D4",
        "cap-20260822T060421-f5439202e6ea",
        "reprocess-c9566fe29a224c4eaab8a41300a4d13a",
        "sha256:4b33542016393dddbe73023e89882dc3f25c6c1821ae16a2eb8de2e661be8590",
        "sha256:9e77166671fa0dc9ee22b2d6688d75d4a1d6d94e039a7301120b8fdcbef21991",
        (
            PathSpec(
                "sha256:15bf3e8bb8b3cf8a26b528073abe6c1155b7d36b8bd24cd18acf90bc93c9614c",
                "stream-0",
                0,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:1bd299380f4f2f29d0389fa3e88cedfec2717477f0889e0d9b14633b9fba3543",
                "stream-0",
                1,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:86ca5856bff108031bc76bf6cbac9a52442935eda1f3df2290d279c4a183809c",
                "stream-1",
                0,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:59ae9198f3a8b1080d8e73209c031960d5bad38c5d9f92f19f6fb981b1f9e042",
                "stream-1",
                1,
                StarlinkEdge.LOWER,
            ),
        ),
    ),
    DwellSpec(
        "D5",
        "cap-20260822T054347-4a2ebc75cd57",
        "reprocess-bdff7ddf4c81447ca486144675a6a40e",
        "sha256:bbe84700f46901fd39d1e1ed7ad08daddcec881c0b3da90ca15bfdcd549b3275",
        "sha256:3c763f32793f69c949e1e10f12d27eef2f7e1c1cfb1a6fe277f026f05a781779",
        (
            PathSpec(
                "sha256:8a59674a8847e5768449bd122f0a9433ac8c25205514cba504707a90bc98d33e",
                "stream-0",
                0,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:0811731266a3e0a1899501f6947dfe6c1c70048a2c15ddd0382e3005253777bf",
                "stream-0",
                1,
                StarlinkEdge.LOWER,
            ),
            PathSpec(
                "sha256:5f6f63e7ae1f108a48e01779196f250891a75a7bef2ddb730af22dbbb6bf736f",
                "stream-1",
                0,
                StarlinkEdge.UPPER,
            ),
            PathSpec(
                "sha256:516a58b8fdb6bad5dbdd0e171ae8d717ee6bfb68a78a9e7a33285b3616f11a50",
                "stream-1",
                1,
                StarlinkEdge.UPPER,
            ),
        ),
    ),
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args()


def _path_root(bulk_root: Path, dwell: DwellSpec, path: PathSpec) -> Path:
    return (
        bulk_root
        / "analysis"
        / dwell.session_id
        / dwell.run_id
        / "scientific"
        / "path-standard"
        / path.scope_key
    )


def _validate_run_manifest(bulk_root: Path, dwell: DwellSpec) -> dict[str, Any]:
    path = bulk_root / "analysis" / dwell.session_id / dwell.run_id / "manifest.json"
    manifest = base._read_json(path)
    expected = {
        "run_id": dwell.run_id,
        "session_id": dwell.session_id,
        "pipeline_release_id": PIPELINE_RELEASE_ID,
        "input_manifest_digest": dwell.recording_manifest_digest,
        "pipeline_lane": "standard",
    }
    mismatches = {
        key: (manifest.get(key), value)
        for key, value in expected.items()
        if manifest.get(key) != value
    }
    if mismatches:
        raise ValueError(f"run manifest provenance mismatch for {dwell.label}: {mismatches}")
    if not manifest.get("products"):
        raise ValueError(f"run {dwell.run_id} is not sealed with products")
    actual_digest = _file_digest(path)
    if actual_digest != dwell.run_manifest_digest:
        raise ValueError(
            f"run manifest digest mismatch for {dwell.label}: "
            f"{actual_digest} != {dwell.run_manifest_digest}"
        )
    return manifest


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _candidate_pool(
    scan: dict[str, Any],
) -> list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    pool = []
    for detection in scan["detections"]:
        time_s = float(detection["time_s"])
        if time_s > MAXIMUM_WINDOW_START_S:
            continue
        for candidate in detection["candidates"]:
            accuracy = candidate.get("qam_accuracy")
            if accuracy is None:
                continue
            glrt = base._glrt(candidate)
            if float(glrt["margin"]) < MINIMUM_GLRT_MARGIN:
                continue
            pool.append((float(accuracy), detection, candidate, glrt))
    pool.sort(key=lambda item: (-item[0], float(item[1]["time_s"]), int(item[2]["rank"])))
    return pool


def _separated_candidates(
    pool: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]],
) -> tuple[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]], ...]:
    selected: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for item in pool:
        time_s = float(item[1]["time_s"])
        if all(
            abs(time_s - float(other[1]["time_s"])) >= MINIMUM_WINDOW_SEPARATION_S
            for other in selected
        ):
            selected.append(item)
        if len(selected) == WINDOW_COUNT:
            break
    return tuple(selected)


def _path_selection(bulk_root: Path, dwell: DwellSpec) -> PathSelection:
    choices: list[PathSelection] = []
    for path in dwell.paths:
        root = _path_root(bulk_root, dwell, path)
        scan = base._read_json(root / "standard.pilot-scan.v3.json")
        final_bank = base._read_json(root / "standard.final-trajectory-bank.v3.json")
        selected = _separated_candidates(_candidate_pool(scan))
        if len(selected) != WINDOW_COUNT:
            continue
        cases = []
        for index, (accuracy, detection, candidate, glrt) in enumerate(selected, start=1):
            time_s = float(detection["time_s"])
            cfo_hz = float(glrt["tracking_cfo_hz"])
            cases.append(
                base.Case(
                    label=f"W{index}",
                    role="newest-pipeline five-dwell holdout",
                    session_id=dwell.session_id,
                    run_id=dwell.run_id,
                    scope_key=path.scope_key,
                    stream=path.stream,
                    receiver=path.receiver,
                    edge=path.edge,
                    detection_time_s=time_s,
                    sample_start=int(detection["sample_start"]),
                    local_epoch_sample=int(candidate["local_epoch_sample"]),
                    candidate_rank=int(candidate["rank"]),
                    initial_cfo_hz=cfo_hz,
                    qam_accuracy=accuracy,
                    glrt_margin=float(glrt["margin"]),
                    standard_degree_one_rate_hz_s=base._standard_rate(
                        final_bank,
                        time_s=time_s,
                        cfo_hz=cfo_hz,
                    ),
                )
            )
        accuracies = np.asarray([item[0] for item in selected])
        margins = np.asarray([float(item[3]["margin"]) for item in selected])
        choices.append(
            PathSelection(
                path,
                tuple(cases),
                float(np.median(accuracies)),
                float(np.min(accuracies)),
                float(np.median(margins)),
            )
        )
    if not choices:
        raise ValueError(f"no path in {dwell.label} supplies {WINDOW_COUNT} eligible windows")
    return max(
        choices,
        key=lambda item: (
            item.median_selected_qam_accuracy,
            item.minimum_selected_qam_accuracy,
            item.median_selected_glrt_margin,
            item.path.scope_key,
        ),
    )


def _plot_aggregate(
    by_dwell: dict[str, tuple[base.CaseResult, ...]],
    path: Path,
) -> None:
    labels = list(by_dwell)
    positions = np.arange(len(labels))
    results = [by_dwell[label] for label in labels]
    all_results = [item for group in results for item in group]
    uniform_rms = math.pi / math.sqrt(12)
    with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": 0.22}):
        figure, axes = plt.subplots(2, 2, figsize=(15, 9.2), constrained_layout=True)
        support, locks, rates, innovations = axes.flat
        support.bar(
            positions - 0.18,
            [sum(item.modulo_pi.supported_frame_count for item in group) for group in results],
            0.36,
            color="#2a9d62",
            label="exact Qin pilot",
        )
        support.bar(
            positions + 0.18,
            [sum(item.rolled.supported_frame_count for item in group) for group in results],
            0.36,
            color="#8d99ae",
            label="17-symbol-rolled control",
        )
        support.set_title("A · Exact-pilot support versus matched control")
        support.set_ylabel("supported actual frames / 8 windows")
        support.legend()

        locks.bar(
            positions,
            [sum(item.modulo_pi.phase_lock_qualified for item in group) for group in results],
            color="#247ba0",
        )
        locks.set_title("B · Qualified modulo-π phase locks")
        locks.set_ylabel("qualified windows / 8")
        locks.set_ylim(0, WINDOW_COUNT + 0.5)

        for dwell_index, group in enumerate(results):
            jitter = np.linspace(-0.12, 0.12, len(group))
            rates.scatter(
                dwell_index + jitter,
                [item.measured_frequency_line.slope_hz_per_s / 1e3 for item in group],
                s=35,
                facecolor="none",
                edgecolor="#e28b2d",
                label="frame-CFO degree-1 line" if dwell_index == 0 else None,
            )
            qualified = [item for item in group if item.modulo_pi.phase_lock_qualified]
            if qualified:
                rates.scatter(
                    [dwell_index] * len(qualified),
                    [
                        item.modulo_pi.frames[-1].tracked_doppler_rate_hz_s / 1e3
                        for item in qualified
                    ],
                    s=28,
                    color="#247ba0",
                    label="qualified Kalman rate" if dwell_index == 0 else None,
                )
        rates.axhline(0, color="black", linewidth=0.7)
        rates.set_title("C · Linear pilot-frequency rates and qualified Kalman states")
        rates.set_ylabel("frequency rate (kHz/s)")
        rates.legend(fontsize=8)

        for dwell_index, group in enumerate(results):
            jitter = np.linspace(-0.12, 0.12, len(group))
            innovations.scatter(
                dwell_index + jitter,
                [item.modulo_supported_innovation_rms_rad for item in group],
                s=35,
                color=[
                    "#2a9d62" if item.modulo_pi.phase_lock_qualified else "#8d99ae"
                    for item in group
                ],
            )
        innovations.axhline(0.5, color="#2a9d62", linestyle=":", label="lock threshold")
        innovations.axhline(uniform_rms, color="black", linestyle="--", label="uniform RMS")
        innovations.set_title("D · Modulo-π pre-update innovation")
        innovations.set_ylabel("RMS (rad)")
        innovations.legend()
        for axis in axes.flat:
            axis.set_xticks(positions, labels)
            axis.set_xlabel("newly reprocessed dwell")
        figure.suptitle(
            "Pilot-only PNT Kalman · five additional verified dwells\n"
            f"all Standard inputs rerun with deployed release {PIPELINE_RELEASE_ID[:12]}",
            fontsize=14,
        )
        figure.savefig(path, dpi=190, metadata={"Software": "leo-tracker"})
        plt.close(figure)
    if len(all_results) != len(DWELLS) * WINDOW_COUNT:
        raise AssertionError("aggregate plot did not receive the complete five-dwell inventory")


def _selection_document(selection: PathSelection) -> dict[str, Any]:
    return {
        "path": {
            "scope_key": selection.path.scope_key,
            "stream": selection.path.stream,
            "receiver": selection.path.receiver,
            "edge": selection.path.edge.value,
        },
        "median_selected_qam_accuracy": selection.median_selected_qam_accuracy,
        "minimum_selected_qam_accuracy": selection.minimum_selected_qam_accuracy,
        "median_selected_glrt_margin": selection.median_selected_glrt_margin,
    }


def main() -> int:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    selections = {}
    manifests = {}
    for dwell in DWELLS:
        manifests[dwell.label] = _validate_run_manifest(args.bulk_root, dwell)
        selections[dwell.label] = _path_selection(args.bulk_root, dwell)

    store = RecordingStore.open_pinned(PinnedLocalRoot(args.bulk_root))
    by_dwell: dict[str, tuple[base.CaseResult, ...]] = {}
    try:
        for dwell in DWELLS:
            selection = selections[dwell.label]
            bundle = store.inspect(dwell.session_id)
            if bundle.manifest_sha256 != dwell.recording_manifest_digest:
                raise ValueError(f"recording manifest digest changed for {dwell.label}")
            reader = store.reader(bundle, selection.path.stream, verify=True)
            by_dwell[dwell.label] = tuple(
                base._analyze_case(reader, case) for case in selection.cases
            )
    finally:
        store.close()

    figure_names = []
    for dwell in DWELLS:
        selection = selections[dwell.label]
        path = args.output_root / f"pilot-pnt-kalman-{dwell.label.lower()}.png"
        base._plot_holdouts(
            by_dwell[dwell.label],
            path,
            title=(
                f"{dwell.label} · current-deployed-pipeline pilot PNT Kalman · "
                f"{dwell.session_id}\n"
                f"{selection.path.stream}/RX{selection.path.receiver} · "
                f"{selection.path.edge.value} edge · eight phase-blind selected windows"
            ),
            x_label=f"{dwell.label} selected window",
        )
        figure_names.append(path.name)
    aggregate_path = args.output_root / "pilot-pnt-kalman-five-dwell-summary.png"
    _plot_aggregate(by_dwell, aggregate_path)
    figure_names.append(aggregate_path.name)

    document = {
        "schema_version": 1,
        "algorithm": "pilot-pnt-kalman-modulo-pi-five-dwell-v1",
        "pipeline_release_id": PIPELINE_RELEASE_ID,
        "candidate_only": True,
        "known_pilots_only": True,
        "absolute_carrier_phase_resolved": False,
        "pseudorange_claimed": False,
        "frequency_trajectory_orders": [1],
        "pipeline_run_audit": {
            "catalog_current_at_analysis": True,
            "duplicate_key_fields": [
                "session_id",
                "input_manifest_digest",
                "pipeline_release_id",
                "pipeline_lane",
            ],
            "exact_run_count_per_key": 1,
            "succeeded_job_count_per_run": 12,
        },
        "analysis_config": asdict(PilotPntKalmanConfig()),
        "window_s": base.WINDOW_S,
        "selection": {
            "path": (
                "maximize the median QAM accuracy of each path's eight best eligible, "
                "separated windows; tie-break by minimum QAM, median GLRT margin and scope key"
            ),
            "window": (
                "QAM accuracy present, GLRT margin >= 0.05, starts by 59.85 s, greedily "
                "separated by >= 0.15 s; no phase or Kalman statistic used"
            ),
        },
        "dwells": [
            {
                "label": dwell.label,
                "session_id": dwell.session_id,
                "run_id": dwell.run_id,
                "recording_manifest_digest": dwell.recording_manifest_digest,
                "run_manifest_digest": dwell.run_manifest_digest,
                "pipeline_release_id": manifests[dwell.label]["pipeline_release_id"],
                "selected": _selection_document(selections[dwell.label]),
                "cases": [base._serialize_result(item) for item in by_dwell[dwell.label]],
            }
            for dwell in DWELLS
        ],
        "figures": figure_names,
    }
    result_path = args.output_root / "pilot-pnt-kalman-five-dwell-results.json"
    result_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output_root": str(args.output_root),
                "pipeline_release_id": PIPELINE_RELEASE_ID,
                "dwell_count": len(DWELLS),
                "window_count": sum(len(group) for group in by_dwell.values()),
                "qualified_lock_count": sum(
                    item.modulo_pi.phase_lock_qualified
                    for group in by_dwell.values()
                    for item in group
                ),
                "rolled_supported_frame_count": sum(
                    item.rolled.supported_frame_count
                    for group in by_dwell.values()
                    for item in group
                ),
                "result": str(result_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
