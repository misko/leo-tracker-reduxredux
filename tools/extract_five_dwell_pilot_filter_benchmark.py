#!/usr/bin/env python3
"""Replay the frozen pilot-filter benchmark on five sealed sibling dwells.

The seed lane is deliberately TLE blind.  Within each sample-zero 100 ms bin,
the tool selects the strongest exact-minus-rolled GLRT-64 candidate from the
sealed Standard 25 ms pilot scan.  Missing bins remain explicit in the seed
and summary JSON documents.  Even-numbered bins form the predeclared raw-IQ
disjoint scoring lane.

The five inputs are the other captures in the exact six-dwell release used by
the D3 development analysis.  Session, run, receiver-path scope, manifest,
pilot product, tuning tag, RF center, continuity, and release identities all
fail closed before replay.  No TLE, trajectory, or final-track product enters
seed selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd

from leo.acquisition.starlink_tuning import (
    STARLINK_LNB_LO_HZ,
    starlink_edge_rf_center_frequency_hz,
)
from leo.analysis.qam import pilot_pnt_kalman as pnt
from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL
from leo.contracts.states import StarlinkEdge
from leo.pipeline.scopes import ScopeIdentityV1

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_five_dwell_pilot_filter_benchmark/source")
EXPECTED_RELEASE = "058576ec74b7dae9ae3ad2a9798679fcf2c934c3"
STREAM_ID = "stream-1"
RADIO_ID = "radio_pluto_19f2"
RECEIVER_ID = 1
SAMPLE_RATE_HZ = 2_500_000
SAMPLE_COUNT = 150_000_000
REPLAY_WINDOW_SAMPLES = 250_000
BIN_SAMPLES = 250_000
PILOT_PROBE_SAMPLES = 50_000
PILOT_STRIDE_SAMPLES = 62_500
RF_TOLERANCE_HZ = 10
PILOT_SCHEDULE_DIGEST = "sha256:0a972025511f0f651e48c263d43579bff034a0b9d169bcb237cf801d732aba76"


@dataclass(frozen=True, slots=True)
class DwellSpec:
    label: str
    session_id: str
    run_id: str
    scope_digest: str
    channel: int
    edge: StarlinkEdge
    rf_hz: int
    recording_manifest_sha256: str
    analysis_manifest_sha256: str
    pilot_scan_sha256: str

    @property
    def slug(self) -> str:
        time_code = self.session_id.split("T", maxsplit=1)[1].split("-", maxsplit=1)[0]
        return f"{self.label.lower()}-{time_code}-radio1-rx1-{self.edge.value}"


def _dwell(
    label: str,
    session_id: str,
    run_id: str,
    scope: str,
    channel: int,
    edge: str,
    recording_sha256: str,
    analysis_sha256: str,
    pilot_sha256: str,
) -> DwellSpec:
    selected_edge = StarlinkEdge(edge)
    return DwellSpec(
        label=label,
        session_id=session_id,
        run_id=run_id,
        scope_digest=f"sha256:{scope}",
        channel=channel,
        edge=selected_edge,
        rf_hz=starlink_edge_rf_center_frequency_hz(channel, selected_edge),
        recording_manifest_sha256=recording_sha256,
        analysis_manifest_sha256=analysis_sha256,
        pilot_scan_sha256=pilot_sha256,
    )


# Labels preserve the original six-dwell series.  Development D3 (192531) is
# intentionally absent, leaving the prospective sibling set D1/D2/D4/D5/D6.
DWELLS = (
    _dwell(
        "D1",
        "cap-20260824T192019-9023840c8e9f",
        "capture-a7c71070425e4aa596da41af5397be52",
        "04dde0b31f70301eb0e0d334fd2ca752a484aeda323c3d1c4638933bbfed6332",
        2,
        "lower",
        "cd0049f00d83f328de1cb0105a54f5492448d6b60ae71d7848a4554fcb618717",
        "e4f595e4dbcd96c0990ce938c1f7ec959b4d62c8abb1b3cddfbde47da7659822",
        "fb6af22dbce3d570a25ea7e57ad34e95c778486d5788a511155a79d42d7d91d7",
    ),
    _dwell(
        "D2",
        "cap-20260824T192252-9981b9c27853",
        "capture-6f6c7e02f16b4f6dbcb260e92864adfa",
        "0ecd53e974bbdb9f85effaa67457c5b57799726f36d14386a1a3bfef3c7a9cd0",
        3,
        "upper",
        "afaecccd1130c09d4604bdebc99ff8fbb4089c9dd031602b117312739be094e3",
        "eaf70acbb00dbea85379a5389af3f73ba5eee8176c61d149ff99dfa350bad1b8",
        "e4674515184305ce87a6b81bd6c00b74728289516877a4f8298e2434295126a9",
    ),
    _dwell(
        "D4",
        "cap-20260824T193733-1454b499b8bb",
        "capture-433e7ae26bac4afc83993e1b819a70a1",
        "20d5df0919e160222c4baf7aa61702e07e69e35abfc7b4358b3573c3c03e3395",
        3,
        "lower",
        "0797ece2aaba53fe19b0834da20681a489fced0041428e72afa5a88bf39fda14",
        "75de40096bbd5cd36c6723fad1572e071016b672a4f99da98b74be1a00d5414d",
        "308fd65bc0ea645c7d676611900abfb5acdf95a46695b1588dc4e441ddbfbf86",
    ),
    _dwell(
        "D5",
        "cap-20260824T194009-34ae34f129bc",
        "capture-199a841b06bb403fb6d07c26ea911a6a",
        "ead57ca0bbf3447e4900735643fee4ca835281072890d8bbf9bd254c93fd5d2e",
        2,
        "lower",
        "36d5aff52be690816bf1a0e98e29421204fded2ffa133f464864a6e9cb09c764",
        "35d71825bb7d957263f60d90bee13189be35d4cdbffc5fec50b983cf357df43d",
        "b1e8cb0306ce060ceedf7940b4db3edd23ed55c137c3f87be268720867018b5e",
    ),
    _dwell(
        "D6",
        "cap-20260824T194245-1dfbc879df2b",
        "capture-0fd511c099d9427b9057e7ce6b0d4878",
        "5440de03e8d21a68396259a57809a94db974a306544efb68dbfe7608d5a6f8aa",
        3,
        "lower",
        "90a15636bead27e955e6009f71b6cecb3dd207e05fd8633b49d469c7585e3213",
        "e0bef80e095dc9d83f3043baebdf70f34f5dc9dcd3385558c0837bb66c9be565",
        "587a415da84f4c2642d82f3e6ed8a0da8dec9e66451ceeb0c5cc87a4cafd7591",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatedInput:
    spec: DwellSpec
    recording_root: Path
    recording_manifest_path: Path
    analysis_manifest_path: Path
    pilot_scan_path: Path
    recording_manifest: dict[str, Any]
    analysis_manifest: dict[str, Any]
    pilot_scan: dict[str, Any]
    stream: dict[str, Any]
    continuity: dict[str, Any]
    tuned_if_hz: int


@dataclass(frozen=True, slots=True)
class ReplaySourceFile:
    logical_name: str
    path: str
    sha256: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class ReplaySourceSnapshot:
    """Parent-captured identity of every loaded repository analysis source."""

    schema: str
    inventory_sha256: str
    files: tuple[ReplaySourceFile, ...]

    def document(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "inventory_sha256": self.inventory_sha256,
            "files": [asdict(row) for row in self.files],
        }

    def file(self, logical_name: str) -> ReplaySourceFile:
        return _one(
            [row for row in self.files if row.logical_name == logical_name],
            f"replay source snapshot lacks one {logical_name} entry",
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _stable_source_digest(path: Path) -> tuple[str, int]:
    """Hash one source only if its file identity stays stable during the read."""

    canonical = path.resolve(strict=True)
    before = canonical.stat()
    payload = canonical.read_bytes()
    after = canonical.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != before.st_size:
        raise RuntimeError(f"replay source changed while it was being hashed: {canonical}")
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _source_inventory_digest(files: tuple[ReplaySourceFile, ...]) -> str:
    payload = json.dumps(
        [asdict(row) for row in files],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _default_replay_source_files() -> tuple[tuple[str, Path], ...]:
    """Inventory all analysis modules loaded by this replay plus narrow bindings."""

    rows: dict[str, Path] = {}
    for module_name, module in tuple(sys.modules.items()):
        module_path = getattr(module, "__file__", None)
        if (
            module_name == "leo.analysis" or module_name.startswith("leo.analysis.")
        ) and module_path is not None:
            rows[module_name] = Path(module_path).resolve(strict=True)
    for module_name in (
        "leo.acquisition.starlink_tuning",
        "leo.contracts.states",
        "leo.pipeline.scopes",
    ):
        required_module = sys.modules.get(module_name)
        module_path = (
            None if required_module is None else getattr(required_module, "__file__", None)
        )
        if module_path is None:
            raise RuntimeError(f"required replay binding module is not loaded: {module_name}")
        rows[module_name] = Path(module_path).resolve(strict=True)
    rows["tools.extract_five_dwell_pilot_filter_benchmark"] = Path(__file__).resolve(strict=True)
    return tuple(sorted(rows.items()))


def capture_replay_source_snapshot(
    source_files: tuple[tuple[str, Path], ...] | None = None,
) -> ReplaySourceSnapshot:
    """Capture the parent-process source identity passed unchanged to workers."""

    selected = _default_replay_source_files() if source_files is None else source_files
    if not selected or len({name for name, _ in selected}) != len(selected):
        raise ValueError("replay source inventory must be non-empty and unique by logical name")
    files = []
    for logical_name, path in sorted(selected):
        digest, byte_size = _stable_source_digest(path)
        files.append(
            ReplaySourceFile(
                logical_name=logical_name,
                path=str(path.resolve(strict=True)),
                sha256=digest,
                byte_size=byte_size,
            )
        )
    frozen = tuple(files)
    return ReplaySourceSnapshot(
        schema="org.leo.research.replay-source-snapshot/v1",
        inventory_sha256=_source_inventory_digest(frozen),
        files=frozen,
    )


def verify_replay_source_snapshot(snapshot: ReplaySourceSnapshot) -> None:
    """Fail closed if any parent-captured source changed or disappeared."""

    if snapshot.schema != "org.leo.research.replay-source-snapshot/v1":
        raise RuntimeError("replay source snapshot schema changed")
    if snapshot.inventory_sha256 != _source_inventory_digest(snapshot.files):
        raise RuntimeError("replay source snapshot inventory digest is internally inconsistent")
    failures = []
    for expected in snapshot.files:
        try:
            observed_digest, observed_size = _stable_source_digest(Path(expected.path))
        except (OSError, RuntimeError) as error:
            failures.append(f"{expected.logical_name}: {error}")
            continue
        if (observed_digest, observed_size) != (expected.sha256, expected.byte_size):
            failures.append(
                f"{expected.logical_name}: expected {expected.sha256}/{expected.byte_size}, "
                f"observed {observed_digest}/{observed_size}"
            )
    if failures:
        raise RuntimeError("replay source mutation detected; " + "; ".join(failures))


def _read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON document is not an object: {path}")
    return document


def _one(rows: list[Any], message: str) -> Any:
    if len(rows) != 1:
        raise ValueError(message)
    return rows[0]


def _recording_path(bulk_root: Path, session_id: str) -> Path:
    matches = list((bulk_root / "recordings").glob(f"*/*/*/{session_id}"))
    return _one(matches, f"expected one recording directory for {session_id}")


def _tuning_from_manifest(manifest: dict[str, Any], stream_id: str) -> tuple[int, StarlinkEdge]:
    prefix = f"tuning:{stream_id}:"
    matches = [tag for tag in manifest.get("tags", ()) if str(tag).startswith(prefix)]
    tag = str(_one(matches, f"recording does not declare one tuning tag for {stream_id}"))
    parts = tag.split(":")
    if len(parts) != 4 or not parts[2].startswith("ch"):
        raise ValueError(f"malformed per-stream tuning tag: {tag}")
    try:
        channel = int(parts[2][2:])
        edge = StarlinkEdge(parts[3])
    except (ValueError, TypeError) as error:
        raise ValueError(f"malformed per-stream tuning tag: {tag}") from error
    return channel, edge


def _validate_continuity(stream: dict[str, Any]) -> dict[str, Any]:
    continuity = stream.get("continuity")
    if not isinstance(continuity, dict):
        raise ValueError("recording stream has no continuity evidence")
    if continuity.get("sample_loss_observable") is not True:
        raise ValueError("replay requires counter-authoritative continuity")
    zero_fields = (
        "gap_count",
        "missing_sample_count",
        "overflow_count",
        "enqueue_failure_count",
        "clipped_sample_count",
        "constant_iq_refill_count",
        "terminal_rejected_gap_count",
        "terminal_rejected_missing_sample_count",
        "terminal_rejected_overflow_count",
    )
    if any(int(continuity.get(key, -1)) != 0 for key in zero_fields):
        raise ValueError("replay requires gap-free, overflow-free, unclipped IQ")
    expected_count = int(stream["captured_sample_count"])
    if any(
        int(continuity.get(key, -1)) != expected_count
        for key in ("device_span_sample_count", "observed_sample_count")
    ):
        raise ValueError("continuity sample counts disagree with the captured stream")
    if int(continuity.get("segment_count", -1)) != 1:
        raise ValueError("replay requires one continuous segment")
    return continuity


def _validate_chunks(recording_root: Path, stream: dict[str, Any]) -> None:
    chunks = stream.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("recording stream has no chunks")
    receiver_ids = tuple(int(value) for value in stream["applied_settings"]["receiver_ids"])
    cursor = 0
    canonical_root = recording_root.resolve(strict=True)
    for expected_index, chunk in enumerate(chunks):
        if int(chunk["chunk_index"]) != expected_index or int(chunk["sample_start"]) != cursor:
            raise ValueError("recording chunk inventory is not ordered and contiguous")
        if chunk.get("sample_format") != "ci16_le":
            raise ValueError("replay requires little-endian CI16 chunks")
        if chunk.get("sample_layout") != "sample_receiver_iq":
            raise ValueError("replay requires sample/receiver/IQ chunk layout")
        if int(chunk.get("segment_index", -1)) != 0:
            raise ValueError("replay chunk is outside the sole continuous segment")
        sample_count = int(chunk["sample_count"])
        if int(chunk["uncompressed_bytes"]) != sample_count * len(receiver_ids) * 4:
            raise ValueError("recording chunk byte geometry is inconsistent")
        path = (recording_root / str(chunk["relative_path"])).resolve(strict=True)
        try:
            path.relative_to(canonical_root)
        except ValueError as error:
            raise ValueError("recording chunk escapes its sealed bundle") from error
        if not path.is_file() or path.stat().st_size != int(chunk["compressed_bytes"]):
            raise ValueError("recording chunk size or type disagrees with its manifest")
        cursor += sample_count
    if cursor != int(stream["captured_sample_count"]):
        raise ValueError("recording chunk inventory does not cover the captured stream")


def _validate_analysis_manifest(
    spec: DwellSpec,
    manifest: dict[str, Any],
    pilot_scan_path: Path,
) -> None:
    if manifest.get("pipeline_release_id") != EXPECTED_RELEASE:
        raise ValueError("analysis release identity changed")
    if manifest.get("pipeline_lane") != "standard":
        raise ValueError("analysis run is not sealed in the Standard lane")
    if manifest.get("input_manifest_digest") != f"sha256:{spec.recording_manifest_sha256}":
        raise ValueError("analysis input manifest does not bind the frozen recording")
    jobs = [
        row
        for row in manifest.get("jobs", ())
        if row.get("stage_key") == "path-standard" and row.get("scope_key") == spec.scope_digest
    ]
    job = _one(jobs, "analysis manifest lacks one exact path-standard job")
    allowed_outcomes = {"complete", "partial_coverage", "no_result"}
    if job.get("outcome") not in allowed_outcomes:
        raise ValueError("frozen path-standard job has no sealed terminal outcome")
    products = [
        row
        for row in manifest.get("products", ())
        if row.get("kind") == "standard.pilot-scan"
        and row.get("product_schema_version") == 3
        and row.get("stage_key") == "path-standard"
        and row.get("scope_key") == spec.scope_digest
    ]
    product = _one(products, "analysis manifest lacks one exact pilot-scan V3 product")
    if product.get("status") != job.get("outcome"):
        raise ValueError("pilot-scan status disagrees with its sealed path job")
    if product.get("digest") != f"sha256:{spec.pilot_scan_sha256}":
        raise ValueError("pilot-scan product digest changed")
    if not str(product.get("logical_uri", "")).endswith(
        f"/{spec.scope_digest}/standard.pilot-scan.v3.json"
    ):
        raise ValueError("pilot-scan product URI does not bind the exact receiver path")
    if int(product.get("byte_size", -1)) != pilot_scan_path.stat().st_size:
        raise ValueError("pilot-scan product size changed")


def _validate_pilot_scan(scan: dict[str, Any]) -> None:
    expected = {
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "candidate_only": True,
        "probe_samples": PILOT_PROBE_SAMPLES,
        "subwindow_samples": 125_000,
        "coarse_window_samples": 2_500_000,
        "maximum_scored_candidates_per_probe": 10,
        "probe_schedule_digest": PILOT_SCHEDULE_DIGEST,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
    }
    if any(scan.get(key) != value for key, value in expected.items()):
        raise ValueError("pilot-scan V3 configuration changed")
    if tuple(scan.get("methods", ())) != ("anchor8", "glrt64", "symbolwise"):
        raise ValueError("pilot-scan method inventory changed")
    detections = scan.get("detections")
    if not isinstance(detections, list) or len(detections) != 2_400:
        raise ValueError("pilot-scan schedule must contain exactly 2,400 probes")
    for index, detection in enumerate(detections):
        start = int(detection["sample_start"])
        if start != index * PILOT_STRIDE_SAMPLES:
            raise ValueError("pilot-scan is not on the frozen 25 ms sample lattice")
        if not math.isclose(float(detection["time_s"]), start / SAMPLE_RATE_HZ, abs_tol=1e-12):
            raise ValueError("pilot-scan time and sample coordinates disagree")


def validate_input(spec: DwellSpec, bulk_root: Path) -> ValidatedInput:
    recording_root = _recording_path(bulk_root, spec.session_id)
    recording_manifest_path = recording_root / "manifest.json"
    analysis_root = bulk_root / "analysis" / spec.session_id / spec.run_id
    analysis_manifest_path = analysis_root / "manifest.json"
    pilot_scan_path = (
        analysis_root
        / "scientific"
        / "path-standard"
        / spec.scope_digest
        / "standard.pilot-scan.v3.json"
    )
    expected_paths = (recording_manifest_path, analysis_manifest_path, pilot_scan_path)
    if not all(path.is_file() for path in expected_paths):
        raise ValueError(f"one or more sealed inputs are absent for {spec.label}")
    observed_digests = tuple(sha256(path) for path in expected_paths)
    expected_digests = (
        spec.recording_manifest_sha256,
        spec.analysis_manifest_sha256,
        spec.pilot_scan_sha256,
    )
    if observed_digests != expected_digests:
        raise ValueError(f"sealed input digest changed for {spec.label}")

    recording = _read_json(recording_manifest_path)
    analysis = _read_json(analysis_manifest_path)
    scan = _read_json(pilot_scan_path)
    if recording.get("schema_version") != 2 or recording.get("state") != "committed":
        raise ValueError("recording manifest is not one committed V2 bundle")
    if recording.get("session_id") != spec.session_id:
        raise ValueError("recording manifest session identity changed")
    computed_scope = ScopeIdentityV1.receiver_path(
        session_id=spec.session_id,
        stream_id=STREAM_ID,
        receiver_id=RECEIVER_ID,
    ).canonical_digest
    if computed_scope != spec.scope_digest:
        raise ValueError("receiver-path scope digest changed")
    stream = _one(
        [row for row in recording.get("streams", ()) if row.get("stream_id") == STREAM_ID],
        "recording lacks one exact stream",
    )
    if stream.get("state") != "complete" or stream.get("radio", {}).get("radio_id") != RADIO_ID:
        raise ValueError("recording stream/radio binding changed")
    settings = stream.get("applied_settings")
    if not isinstance(settings, dict):
        raise ValueError("recording stream has no applied settings")
    if int(settings.get("sample_rate_hz", -1)) != SAMPLE_RATE_HZ:
        raise ValueError("recording sample rate changed")
    if int(stream.get("captured_sample_count", -1)) != SAMPLE_COUNT:
        raise ValueError("recording sample count changed")
    if RECEIVER_ID not in tuple(int(value) for value in settings.get("receiver_ids", ())):
        raise ValueError("recording stream does not contain RX1")
    channel, edge = _tuning_from_manifest(recording, STREAM_ID)
    if (channel, edge) != (spec.channel, spec.edge):
        raise ValueError("authoritative per-stream tuning tag changed")
    rf_hz = starlink_edge_rf_center_frequency_hz(channel, edge)
    if rf_hz != spec.rf_hz:
        raise ValueError("authoritative channel/edge RF identity changed")
    tuned_if_hz = int(settings["center_frequency_hz"])
    if abs((tuned_if_hz + STARLINK_LNB_LO_HZ) - rf_hz) > RF_TOLERANCE_HZ:
        raise ValueError("applied IF does not reconstruct the tagged channel-edge RF")
    continuity = _validate_continuity(stream)
    _validate_chunks(recording_root, stream)
    _validate_analysis_manifest(spec, analysis, pilot_scan_path)
    _validate_pilot_scan(scan)
    return ValidatedInput(
        spec=spec,
        recording_root=recording_root,
        recording_manifest_path=recording_manifest_path,
        analysis_manifest_path=analysis_manifest_path,
        pilot_scan_path=pilot_scan_path,
        recording_manifest=recording,
        analysis_manifest=analysis,
        pilot_scan=scan,
        stream=stream,
        continuity=continuity,
        tuned_if_hz=tuned_if_hz,
    )


def _finite_float(value: Any, field: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"pilot candidate {field} is not finite")
    return result


def select_seed_bins(
    scan: dict[str, Any],
    *,
    sample_rate_hz: int,
    sample_count: int,
    replay_window_samples: int,
) -> list[dict[str, Any]]:
    """Return one deterministic GLRT-64 seed or an explicit miss per 100 ms bin."""

    bin_samples = round(0.100 * sample_rate_hz)
    probe_samples = int(scan["probe_samples"])
    if bin_samples <= 0 or replay_window_samples <= 0 or sample_count < replay_window_samples:
        raise ValueError("invalid seed-bin sample geometry")
    bin_count = sample_count // bin_samples
    candidates_by_bin: list[list[dict[str, Any]]] = [[] for _ in range(bin_count)]
    for detection_index, detection in enumerate(scan.get("detections", ())):
        start = int(detection["sample_start"])
        if start < 0 or start >= sample_count:
            raise ValueError("pilot detection start is outside the recording")
        if start + replay_window_samples > sample_count:
            continue
        bin_index = start // bin_samples
        for candidate in detection.get("candidates", ()):
            glrt_scores = [
                row for row in candidate.get("scores", ()) if row.get("method") == "glrt64"
            ]
            score = _one(glrt_scores, "pilot candidate does not contain one GLRT-64 score")
            rank = int(candidate["rank"])
            epoch = int(candidate["local_epoch_sample"])
            if rank < 0 or not 0 <= epoch < probe_samples:
                raise ValueError("pilot candidate rank or epoch is outside its probe")
            row = {
                "probe_index": detection_index,
                "source_detection_index": detection_index,
                "candidate_rank": rank,
                "source_candidate_count": int(detection.get("source_candidate_count", 0)),
                "sample_start": start,
                "source_time_s": _finite_float(detection["time_s"], "time_s"),
                "center_time_s": (start + probe_samples / 2) / sample_rate_hz,
                "replay_center_time_s": (start + replay_window_samples / 2) / sample_rate_hz,
                "epoch_sample": epoch,
                "acquired_cfo_hz": _finite_float(candidate["acquired_cfo_hz"], "acquired_cfo_hz"),
                "tracking_cfo_hz": _finite_float(score["tracking_cfo_hz"], "tracking_cfo_hz"),
                "residual_cfo_hz": _finite_float(score["residual_cfo_hz"], "residual_cfo_hz"),
                "glrt_exact_score": _finite_float(score["exact_score"], "exact_score"),
                "glrt_control_score": _finite_float(score["control_score"], "control_score"),
                "glrt_margin": _finite_float(score["margin"], "margin"),
            }
            candidates_by_bin[bin_index].append(row)

    result: list[dict[str, Any]] = []
    for bin_index, candidates in enumerate(candidates_by_bin):
        selected = (
            max(
                candidates,
                key=lambda row: (
                    row["glrt_margin"],
                    row["glrt_exact_score"],
                    -row["candidate_rank"],
                    -abs(row["tracking_cfo_hz"]),
                    -row["sample_start"],
                    -row["epoch_sample"],
                ),
            )
            if candidates
            else None
        )
        result.append(
            {
                "bin_index": bin_index,
                "bin_sample_start": bin_index * bin_samples,
                "bin_sample_end": (bin_index + 1) * bin_samples,
                "bin_center_time_s": (bin_index + 0.5) * bin_samples / sample_rate_hz,
                "raw_disjoint": bin_index % 2 == 0,
                "candidate_count": len(candidates),
                "status": "selected" if selected is not None else "missing",
                "missing_reason": (
                    None
                    if selected is not None
                    else "no complete-window sealed GLRT-64 candidate in sample-zero bin"
                ),
                "seed": selected,
            }
        )
    return result


class VerifiedCi16Reader:
    """Small read-only V2-manifest adapter with one verified chunk cache."""

    def __init__(self, recording_root: Path, stream: dict[str, Any]) -> None:
        self._root = recording_root.resolve(strict=True)
        self._stream = stream
        self._chunks = tuple(stream["chunks"])
        settings = stream["applied_settings"]
        self._receiver_ids = tuple(int(value) for value in settings["receiver_ids"])
        self._cache_index: int | None = None
        self._cache_values: np.ndarray | None = None

    def _chunk_values(self, index: int) -> np.ndarray:
        if self._cache_index == index and self._cache_values is not None:
            return self._cache_values
        chunk = self._chunks[index]
        path = (self._root / str(chunk["relative_path"])).resolve(strict=True)
        try:
            path.relative_to(self._root)
        except ValueError as error:
            raise ValueError("recording chunk escapes its sealed bundle") from error
        compressed = path.read_bytes()
        if len(compressed) != int(chunk["compressed_bytes"]):
            raise ValueError("compressed chunk byte count changed")
        if hashlib.sha256(compressed).hexdigest() != str(chunk["compressed_sha256"]).removeprefix(
            "sha256:"
        ):
            raise ValueError("compressed chunk digest changed")
        try:
            payload = zstd.ZstdDecompressor().decompress(
                compressed,
                max_output_size=int(chunk["uncompressed_bytes"]),
            )
        except zstd.ZstdError as error:
            raise ValueError("recording chunk cannot be decompressed") from error
        if len(payload) != int(chunk["uncompressed_bytes"]):
            raise ValueError("uncompressed chunk byte count changed")
        if hashlib.sha256(payload).hexdigest() != str(chunk["uncompressed_sha256"]).removeprefix(
            "sha256:"
        ):
            raise ValueError("uncompressed chunk digest changed")
        values = np.frombuffer(payload, dtype="<i2").reshape(
            int(chunk["sample_count"]), len(self._receiver_ids), 2
        )
        self._cache_index = index
        self._cache_values = values
        return values

    def read_complex(self, sample_start: int, sample_count: int, receiver_id: int) -> np.ndarray:
        if sample_start < 0 or sample_count < 0:
            raise ValueError("sample range cannot be negative")
        sample_end = sample_start + sample_count
        if sample_end > int(self._stream["captured_sample_count"]):
            raise ValueError("sample range exceeds the captured stream")
        try:
            receiver_column = self._receiver_ids.index(receiver_id)
        except ValueError as error:
            raise ValueError("selected receiver is absent from the stream") from error
        pieces: list[np.ndarray] = []
        for index, chunk in enumerate(self._chunks):
            chunk_start = int(chunk["sample_start"])
            chunk_end = chunk_start + int(chunk["sample_count"])
            overlap_start = max(sample_start, chunk_start)
            overlap_end = min(sample_end, chunk_end)
            if overlap_start >= overlap_end:
                continue
            values = self._chunk_values(index)
            left = overlap_start - chunk_start
            right = overlap_end - chunk_start
            selected = values[left:right, receiver_column, :]
            pieces.append(
                (selected[:, 0].astype(np.float64) + 1j * selected[:, 1].astype(np.float64))
                / 32_768.0
            )
        if sum(len(piece) for piece in pieces) != sample_count:
            raise ValueError("chunk inventory did not cover the requested sample range")
        if not pieces:
            return np.empty(0, dtype=np.complex128)
        return pieces[0] if len(pieces) == 1 else np.concatenate(pieces)


FRAME_KEYS = (
    "window_index",
    "window_center_time_s",
    "window_raw_disjoint",
    "bin_index",
    "seed_present",
    "seed_sample_start",
    "seed_glrt_margin",
    "frame_index",
    "frame_start_sample",
    "absolute_time_s",
    "measurement_supported",
    "exact_coherence",
    "control_coherence",
    "coherence_margin",
    "absolute_cfo_measurement_hz",
    "measurement_sigma_hz",
    "frequency_innovation_hz",
    "tracked_absolute_cfo_hz",
    "tracked_rate_hz_s",
    "tracked_frequency_sigma_hz",
    "tracked_rate_sigma_hz_s",
    "phase_innovation_rad",
    "phase_sigma_rad",
    "phase_update",
    "frequency_update",
    "timing_update",
    "reacquired",
)
BOOLEAN_FRAME_KEYS = {
    "window_raw_disjoint",
    "seed_present",
    "measurement_supported",
    "phase_update",
    "frequency_update",
    "timing_update",
    "reacquired",
}
INTEGER_FRAME_KEYS = {
    "window_index",
    "bin_index",
    "seed_sample_start",
    "frame_index",
    "frame_start_sample",
}


def empty_frame_arrays() -> dict[str, list[float | int | bool]]:
    return {key: [] for key in FRAME_KEYS}


def append_exact_frames(
    arrays: dict[str, list[float | int | bool]],
    *,
    bin_row: dict[str, Any],
    result: Any,
    sample_rate_hz: int,
) -> None:
    seed = bin_row["seed"]
    if seed is None:
        raise ValueError("cannot append frames for a missing seed")
    start = int(seed["sample_start"])
    for frame in result.frames:
        values = {
            "window_index": int(bin_row["bin_index"]),
            "window_center_time_s": float(seed["center_time_s"]),
            "window_raw_disjoint": bool(bin_row["raw_disjoint"]),
            "bin_index": int(bin_row["bin_index"]),
            "seed_present": True,
            "seed_sample_start": start,
            "seed_glrt_margin": float(seed["glrt_margin"]),
            "frame_index": int(frame.frame_index),
            "frame_start_sample": start + int(frame.frame_start_sample),
            "absolute_time_s": start / sample_rate_hz + float(frame.time_s),
            "measurement_supported": bool(frame.measurement_supported),
            "exact_coherence": float(frame.exact_coherence),
            "control_coherence": float(frame.control_coherence),
            "coherence_margin": float(frame.coherence_margin),
            "absolute_cfo_measurement_hz": float(frame.absolute_cfo_measurement_hz),
            "measurement_sigma_hz": max(float(frame.frequency_sigma_hz), 1.0),
            "frequency_innovation_hz": float(frame.frequency_innovation_hz),
            "tracked_absolute_cfo_hz": float(frame.tracked_absolute_cfo_hz),
            "tracked_rate_hz_s": float(frame.tracked_doppler_rate_hz_s),
            "tracked_frequency_sigma_hz": float(frame.frequency_sigma_hz),
            "tracked_rate_sigma_hz_s": float(frame.doppler_rate_sigma_hz_s),
            "phase_innovation_rad": float(frame.phase_innovation_modulo_pi_rad),
            "phase_sigma_rad": float(frame.phase_sigma_rad),
            "phase_update": bool(frame.phase_update_applied),
            "frequency_update": bool(frame.frequency_update_applied),
            "timing_update": bool(frame.timing_update_applied),
            "reacquired": bool(frame.reacquired),
        }
        for key, value in values.items():
            arrays[key].append(value)


def phase_rms(result: Any) -> float | None:
    supported = [frame for frame in result.frames if frame.measurement_supported]
    if not supported:
        return None
    return math.sqrt(
        sum(float(frame.phase_innovation_modulo_pi_rad) ** 2 for frame in supported)
        / len(supported)
    )


def _missing_window_row(bin_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "window_index": int(bin_row["bin_index"]),
        "bin_index": int(bin_row["bin_index"]),
        "center_time_s": float(bin_row["bin_center_time_s"]),
        "sample_start": None,
        "raw_disjoint": bool(bin_row["raw_disjoint"]),
        "missing": True,
        "skip_reason": str(bin_row["missing_reason"]),
        "qualified": False,
        "supported": 0,
        "phase_updates": 0,
        "reacquisitions": 0,
        "phase_rms_rad": None,
    }


def _window_row(bin_row: dict[str, Any], result: Any) -> dict[str, Any]:
    seed = bin_row["seed"]
    if seed is None:
        return _missing_window_row(bin_row)
    return {
        "window_index": int(bin_row["bin_index"]),
        "bin_index": int(bin_row["bin_index"]),
        "center_time_s": float(seed["center_time_s"]),
        "sample_start": int(seed["sample_start"]),
        "raw_disjoint": bool(bin_row["raw_disjoint"]),
        "missing": False,
        "skip_reason": None,
        "qualified": bool(result.phase_lock_qualified),
        "supported": int(result.supported_frame_count),
        "phase_updates": int(result.phase_update_count),
        "reacquisitions": int(result.reacquisition_count),
        "phase_rms_rad": phase_rms(result),
        "status": result.status.value,
        "reason": str(result.reason),
        "phase_lock_reason": str(result.phase_lock_reason),
    }


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as destination:
            json.dump(document, destination, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _commit_summary(
    path: Path,
    document: dict[str, Any],
    replay_sources: ReplaySourceSnapshot,
) -> None:
    """Publish a summary only while its parent-captured sources remain exact."""

    if document.get("replay_source_inventory_sha256") != (replay_sources.inventory_sha256):
        raise RuntimeError("summary does not carry the parent replay source digest")
    if document.get("replay_source_snapshot") != replay_sources.document():
        raise RuntimeError("summary does not carry the parent replay source snapshot")
    verify_replay_source_snapshot(replay_sources)
    _atomic_json(path, document)


def _atomic_npz(path: Path, arrays: dict[str, list[float | int | bool]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as destination:
            np.savez_compressed(
                destination,
                **{  # type: ignore[arg-type]
                    key: np.asarray(
                        values,
                        dtype=(
                            bool
                            if key in BOOLEAN_FRAME_KEYS
                            else np.int64
                            if key in INTEGER_FRAME_KEYS
                            else np.float64
                        ),
                    )
                    for key, values in arrays.items()
                },
            )
            destination.flush()
            os.fsync(destination.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def extract_dwell(
    spec: DwellSpec,
    *,
    bulk_root: Path,
    output_root: Path,
    max_bins: int | None = None,
    replay_sources: ReplaySourceSnapshot | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    source_snapshot = replay_sources or capture_replay_source_snapshot()
    verify_replay_source_snapshot(source_snapshot)
    source = validate_input(spec, bulk_root)
    seed_bins = select_seed_bins(
        source.pilot_scan,
        sample_rate_hz=SAMPLE_RATE_HZ,
        sample_count=SAMPLE_COUNT,
        replay_window_samples=REPLAY_WINDOW_SAMPLES,
    )
    if len(seed_bins) != 600:
        raise ValueError("frozen 60 s capture did not produce 600 sample-zero bins")
    if max_bins is not None and not 1 <= max_bins <= len(seed_bins):
        raise ValueError("max_bins must lie in 1..600")
    replay_bins = seed_bins if max_bins is None else seed_bins[:max_bins]

    seed_path = output_root / f"{spec.slug}-seeds.json"
    npz_path = output_root / f"{spec.slug}-filter-benchmark.npz"
    summary_path = output_root / f"{spec.slug}-filter-benchmark-summary.json"
    seed_document = {
        "schema": "org.leo.research.sealed-standard-100ms-glrt64-seeds/v1",
        "label": spec.label,
        "session_id": spec.session_id,
        "run_id": spec.run_id,
        "scope_sha256": spec.scope_digest,
        "stream_id": STREAM_ID,
        "radio_id": RADIO_ID,
        "receiver_id": RECEIVER_ID,
        "channel": spec.channel,
        "edge": spec.edge.value,
        "rf_hz": spec.rf_hz,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "sample_count": SAMPLE_COUNT,
        "selection": (
            "maximum sealed Standard GLRT-64 exact-minus-rolled-control margin in each "
            "sample-zero 100 ms bin; ties by exact score, lowest candidate rank, lowest "
            "absolute tracking CFO, earliest probe start, then earliest epoch"
        ),
        "raw_disjoint_lane": "even sample-zero bin_index values",
        "tle_or_track_used_in_selection": False,
        "recording_manifest_sha256": spec.recording_manifest_sha256,
        "analysis_manifest_sha256": spec.analysis_manifest_sha256,
        "pilot_scan_sha256": spec.pilot_scan_sha256,
        "pilot_probe_schedule_digest": source.pilot_scan["probe_schedule_digest"],
        "replay_source_inventory_sha256": source_snapshot.inventory_sha256,
        "replay_source_snapshot": source_snapshot.document(),
        "bin_count": len(seed_bins),
        "selected_bin_count": sum(row["seed"] is not None for row in seed_bins),
        "missing_bin_count": sum(row["seed"] is None for row in seed_bins),
        "bins": seed_bins,
    }
    verify_replay_source_snapshot(source_snapshot)
    _atomic_json(seed_path, seed_document)

    reader = VerifiedCi16Reader(source.recording_root, source.stream)
    arrays = empty_frame_arrays()
    exact_windows: list[dict[str, Any]] = []
    rolled_windows: list[dict[str, Any]] = []
    for offset, bin_row in enumerate(replay_bins):
        seed = bin_row["seed"]
        if seed is None:
            exact_windows.append(_missing_window_row(bin_row))
            rolled_windows.append(_missing_window_row(bin_row))
            continue
        start = int(seed["sample_start"])
        values = reader.read_complex(start, REPLAY_WINDOW_SAMPLES, RECEIVER_ID)
        exact = pnt.analyze_contiguous_pilot_pnt_kalman_v2(
            values,
            SAMPLE_RATE_HZ,
            epoch_sample=int(seed["epoch_sample"]),
            initial_absolute_cfo_hz=float(seed["tracking_cfo_hz"]),
            edge=spec.edge,
        )
        rolled = pnt.analyze_contiguous_pilot_pnt_kalman_v2(
            values,
            SAMPLE_RATE_HZ,
            epoch_sample=int(seed["epoch_sample"]),
            initial_absolute_cfo_hz=float(seed["tracking_cfo_hz"]),
            edge=spec.edge,
            expected_symbol_roll=CONTROL_SYMBOL_ROLL,
        )
        exact_windows.append(_window_row(bin_row, exact))
        rolled_windows.append(_window_row(bin_row, rolled))
        append_exact_frames(
            arrays,
            bin_row=bin_row,
            result=exact,
            sample_rate_hz=SAMPLE_RATE_HZ,
        )
        if (offset + 1) % 50 == 0 or offset + 1 == len(replay_bins):
            print(f"{spec.label}: {offset + 1}/{len(replay_bins)} bins", flush=True)

    verify_replay_source_snapshot(source_snapshot)
    _atomic_npz(npz_path, arrays)
    pnt_source = source_snapshot.file("leo.analysis.qam.pilot_pnt_kalman")
    selected_replay_bins = [row for row in replay_bins if row["seed"] is not None]
    summary = {
        "schema": "org.leo.research.five-dwell-filter-benchmark-source/v1",
        "label": spec.label,
        "session_id": spec.session_id,
        "run_id": spec.run_id,
        "scope_sha256": spec.scope_digest,
        "pipeline_release_id": EXPECTED_RELEASE,
        "stream_id": STREAM_ID,
        "radio_id": RADIO_ID,
        "receiver_id": RECEIVER_ID,
        "channel": spec.channel,
        "edge": spec.edge.value,
        "rf_hz": spec.rf_hz,
        "tuned_if_hz": source.tuned_if_hz,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "sample_count": SAMPLE_COUNT,
        "selection": seed_document["selection"],
        "recording_manifest_sha256": spec.recording_manifest_sha256,
        "analysis_manifest_sha256": spec.analysis_manifest_sha256,
        "pilot_scan_sha256": spec.pilot_scan_sha256,
        "seed_path": str(seed_path.resolve()),
        "seed_relative_path": seed_path.name,
        "seed_sha256": sha256(seed_path),
        "npz_path": str(npz_path.resolve()),
        "npz_relative_path": npz_path.name,
        "npz_sha256": sha256(npz_path),
        "summary_path": str(summary_path.resolve()),
        "summary_relative_path": summary_path.name,
        "source_path": str(source.pilot_scan_path),
        "source_sha256": spec.pilot_scan_sha256,
        "pnt_source_path": pnt_source.path,
        "pnt_source_sha256": pnt_source.sha256,
        "replay_source_inventory_sha256": source_snapshot.inventory_sha256,
        "replay_source_snapshot": source_snapshot.document(),
        "window_count": len(replay_bins),
        "selected_window_count": len(selected_replay_bins),
        "missing_window_count": len(replay_bins) - len(selected_replay_bins),
        "raw_disjoint_window_count": sum(
            bool(row["raw_disjoint"]) and row["seed"] is not None for row in replay_bins
        ),
        "frame_count": len(arrays["frame_index"]),
        "exact": {
            "qualified_count": sum(row["qualified"] for row in exact_windows),
            "supported_frames": sum(row["supported"] for row in exact_windows),
        },
        "rolled": {
            "qualified_count": sum(row["qualified"] for row in rolled_windows),
            "supported_frames": sum(row["supported"] for row in rolled_windows),
        },
        "exact_windows": exact_windows,
        "rolled_windows": rolled_windows,
        "continuity": source.continuity,
        "runtime_s": time.perf_counter() - started,
    }
    _commit_summary(summary_path, summary, source_snapshot)
    print(
        json.dumps(
            {
                "label": spec.label,
                "exact": summary["exact"],
                "rolled": summary["rolled"],
                "runtime_s": summary["runtime_s"],
                "summary": str(summary_path),
            }
        ),
        flush=True,
    )
    return summary


def _extract_worker(
    spec: DwellSpec,
    bulk_root: str,
    output_root: str,
    max_bins: int | None,
    replay_sources: ReplaySourceSnapshot,
) -> dict[str, Any]:
    verify_replay_source_snapshot(replay_sources)
    return extract_dwell(
        spec,
        bulk_root=Path(bulk_root),
        output_root=Path(output_root),
        max_bins=max_bins,
        replay_sources=replay_sources,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--labels",
        nargs="+",
        choices=tuple(spec.label for spec in DWELLS),
        default=tuple(spec.label for spec in DWELLS),
        help="frozen series labels to replay (default: all five)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="dwell-level worker processes; use 1..5 (default: 1)",
    )
    parser.add_argument(
        "--max-bins-per-dwell",
        type=int,
        default=None,
        help="bounded smoke mode; seed all bins but replay only the first N",
    )
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    selected_labels = set(arguments.labels)
    selected = tuple(spec for spec in DWELLS if spec.label in selected_labels)
    if not selected or len(selected) != len(selected_labels):
        raise ValueError("labels must select distinct frozen dwells")
    if not 1 <= arguments.workers <= len(selected):
        raise ValueError("workers must lie between one and the selected dwell count")
    replay_sources = capture_replay_source_snapshot()
    verify_replay_source_snapshot(replay_sources)
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    try:
        if arguments.workers == 1:
            summaries = [
                extract_dwell(
                    spec,
                    bulk_root=arguments.bulk_root,
                    output_root=arguments.output_root,
                    max_bins=arguments.max_bins_per_dwell,
                    replay_sources=replay_sources,
                )
                for spec in selected
            ]
        else:
            summaries = []
            with ProcessPoolExecutor(max_workers=arguments.workers) as executor:
                futures = {
                    executor.submit(
                        _extract_worker,
                        spec,
                        str(arguments.bulk_root),
                        str(arguments.output_root),
                        arguments.max_bins_per_dwell,
                        replay_sources,
                    ): spec
                    for spec in selected
                }
                for future in as_completed(futures):
                    summaries.append(future.result())
            label_order = tuple(spec.label for spec in DWELLS)
            summaries.sort(key=lambda row: label_order.index(row["label"]))
        if any(
            row.get("replay_source_inventory_sha256") != replay_sources.inventory_sha256
            or row.get("replay_source_snapshot") != replay_sources.document()
            for row in summaries
        ):
            raise RuntimeError("a dwell summary does not carry the parent source snapshot")
        verify_replay_source_snapshot(replay_sources)
    finally:
        verify_replay_source_snapshot(replay_sources)
    print(
        json.dumps(
            {
                "schema": "org.leo.research.five-dwell-filter-benchmark-run/v1",
                "output_root": str(arguments.output_root.resolve()),
                "labels": [row["label"] for row in summaries],
                "summary_paths": [row["summary_path"] for row in summaries],
                "replay_source_inventory_sha256": (replay_sources.inventory_sha256),
                "replay_source_snapshot": replay_sources.document(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
