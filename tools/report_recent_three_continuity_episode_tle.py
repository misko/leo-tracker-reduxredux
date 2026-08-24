#!/usr/bin/env python3
"""Read-only exploratory joint TLE matching for three continuity-v2 dwells.

Inputs are immutable Standard final/dealiased products and the latest causal
Space-Track snapshot.  The radio-only group definitions below were chosen from
time overlap and slope agreement before inspecting candidate identities.

This is deliberately an external research audit, not a pipeline product.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.acquisition.starlink_tuning import STARLINK_LNB_LO_HZ
from leo.catalog.database import create_catalog_engine
from leo.catalog.models import AnalysisProduct, AnalysisScope, RunSubjectBinding
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.sky.doppler import SPEED_OF_LIGHT_KM_S, doppler_shift_hz
from leo.sky.propagation import MINIMUM_PLAUSIBLE_ALTITUDE_KM, parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid
from leo.storage import BulkUriResolver

DATABASE_URL = "postgresql+psycopg:///leo_tracker"
BULK_ROOT = Path("/srv/bulk/leo")
TLE_PATH = Path(
    "/var/lib/leo/tle/archive/space-track/"
    "1787594647459418079-ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee.tle"
)
PREVIOUS_TLE_PATH = Path(
    "/var/lib/leo/tle/archive/space-track/"
    "1787591027717437476-6e95375c6427c1e9b567dbc30fc0b55f4f387580afbd08251b65c3cc69695de5.tle"
)
SITE = ObserverSiteV1(
    latitude_deg=37.858988,
    longitude_deg=-122.478103,
    altitude_m=-29.0,
    label="reviewed-spinnaker-sausalito-not-capture-bound",
)
HORIZON_DEG = 10.0
HIGH_ELEVATION_DEG = 60.0
TRAIN_FRACTION = 0.60
EPOCH_SHIFTS_S = np.arange(-0.30, 0.3000001, 0.05)
NUISANCE_BOUNDS_HZ_S = (25.0, 200.0, 1_000_000.0)
WRONG_TIME_SHIFTS_S = tuple(float(x) for x in range(-600, 0, 30)) + tuple(
    float(x) for x in range(30, 601, 30)
)
RESAMPLE_S = 0.10
SIGMA_FLOOR_HZ = 50.0
HUBER_K = 1.345
FRAME_LATTICE_PHASE_PERIOD_THIRDS = 10_000
SCANNER_PHASE_CLUSTER_GATE_SAMPLES = 50.0
SCANNER_CFO_CONTINUATION_GATE_HZ = 20_000.0
SPECIAL_EPOCH_BOUNDS_S = (0.30, 1.0, 2.0)
SPECIAL_EPOCH_STEP_S = 0.05
SPECIAL_RATE_NUISANCE_BOUND_HZ_S = 200.0
SPECIAL_CFO_DRIFT_BOUND_HZ_S = 200.0
SPECIAL_WRONG_TIME_SHIFTS_S = (-600.0, -300.0, -120.0, -60.0, 60.0, 120.0, 300.0, 600.0)
SCANNER_ROOT = BULK_ROOT / "scanner-analysis"
SCANNER_RECORDING_ROOT = BULK_ROOT / "scanner-recordings/2026/08/24"
SCANNER_ANALYZER_ID = "standard-scan-analysis-continuity-v2"
SCANNER_IDS = tuple(f"scan-burst-85008f44b116499c-{index:02d}" for index in range(1, 5))
D2_LATE_TRAJECTORY_ID = "sha256:909bc973b525664a8851d13e4f902db6d105be00a772cea0c1f4d3be3d9aad77"
D2_SCANNER_RF_HZ = 11_459_687_500

RUNS = {
    "D1": (
        "cap-20260824T192019-9023840c8e9f",
        "capture-a7c71070425e4aa596da41af5397be52",
    ),
    "D2": (
        "cap-20260824T192252-9981b9c27853",
        "capture-6f6c7e02f16b4f6dbcb260e92864adfa",
    ),
    "D3": (
        "cap-20260824T192531-491832825b97",
        "capture-f75a853e526844e29893f125d4a58940",
    ),
}


def _ids(*values: str) -> tuple[str, ...]:
    return tuple("sha256:" + value for value in values)


# Each group is a radio-only hypothesis that multiple reset-separated pieces
# belong to one physical Doppler episode.  Alias-equivalent duplicate tracks
# are intentionally represented once.  D2-high joins two LNB chains on one
# Pluto; groups marked cross_radio include both Plutos.
GROUPS: dict[str, dict[str, Any]] = {
    "D1-early-replica": {
        "dwell": "D1",
        "cross_radio": True,
        "wrong_time": False,
        "members": {
            "stream-0/RX0": _ids(
                "3f1ddaab2d4317bcebb84029cb1c36aa66f0129ed5fb84ecf8f6c839fbddaa36"
            ),
            "stream-1/RX1": _ids(
                "3d8556bacbab56858cd8b8d77ef6e743ef755a8c1e9433761d03078cbe7d4ca6"
            ),
        },
    },
    "D1-main-replica": {
        "dwell": "D1",
        "cross_radio": True,
        "wrong_time": True,
        "members": {
            "stream-0/RX1": _ids(
                "6da831b803ea1a39f5dc09e129f7d0180875f107ecd77b9b0f57d8360f525acc",
                "c153a72ab0c62eee6e46ca3a68920045b9886c1d99a486ce3edf862be6f08ca7",
                "1d3654fa81d5226f5ebabae3470ec876631923437ab5907a96ce911022b1a2e6",
            ),
            "stream-1/RX1": _ids(
                "d188936dfffe6f1a48e58b7b6983fc112aa3ea10856a0aeeccfd78a6d34f8271",
                "75cc38abf9e4778cbfefc5305893e0dd6c0a493da145402e1a4f2545c3385af7",
            ),
        },
    },
    "D1-late-replica": {
        "dwell": "D1",
        "cross_radio": True,
        "wrong_time": False,
        "members": {
            "stream-0/RX1": _ids(
                "935ba491534c36641a86eca13e546d4abda993254ef48298a6a1a6a72fc76dee"
            ),
            "stream-1/RX1": _ids(
                "1a3da137fd98158dcdadac420bef6b101da35a060468340dca36a5c52563a7b3"
            ),
        },
    },
    "D2-radio19-C1": {
        "dwell": "D2",
        "cross_radio": False,
        "wrong_time": True,
        "members": {
            "stream-1/RX0": _ids(
                "1929c5b3bd83d1fffe9842ab7ef012bb0912544b416a8630abecd744b9a89c5a",
                "f91cc1f5b7e32e25cc0a016987e0846cae92d843f336d8788cab8fe71d3082c9",
                "7c8611d1a7b689b0837c7c53e8b367cb463f0cadda7a660fa296dad3535787c3",
            ),
            "stream-1/RX1": _ids(
                "132413f96a6cbd32a98443d5661b96e05a12a5d273fce8de80175c0aea864cda",
                "40750904924b19c0200f9d74755be46b35506893099b61b185e16a312ad6ea82",
                "2fc5afbb7c87550477473b0d679f72cbdd9cf1b41df60a74ae0ab0b8129adac2",
                "05fbbfb3d0569282b0c1a8f6e807ed8779677b00e02a553668d597375f5a51e2",
                "51a6041647f9e2f096b239cb15fd88ef9e4587ace5d9f424cd56a441be190a1d",
            ),
        },
    },
    "D2-radio5-C1": {
        "dwell": "D2",
        "cross_radio": False,
        "wrong_time": True,
        "members": {
            "stream-0/RX1": _ids(
                "06f4bb3b4ec20ee1c691dc434f166661a2b7bf436e2d79c3a5635e3a223f3c50",
                "9e3e1238b64f05743b7a2656b76b0801b8d4ca80b918fb476215b91fb4a60785",
                "bb9ec34a67c498ef63efae1acb7e700c5161ea7bf02e1122630ed594051aaa25",
                "1ffbc97769a62ed1ebaf0f0eb70aa07dd2d3403b0b8813b8c1b96a83dca4e5e0",
                "09b5e660df37e9565a0b46e4bf7a07d51942455fd8ef69a2a09b026808a8a133",
                "6506c4e6f9f9a2a6481fba9d862951ef98a61742b4abfd9034129206c2909535",
            ),
        },
    },
    "D2-radio5-C2": {
        "dwell": "D2",
        "cross_radio": False,
        "wrong_time": False,
        "members": {
            "stream-0/RX0": _ids(
                "ece2c132fe8b055276a694303b3195278ae2329e11fda1e073945ff486ace3a7"
            ),
            "stream-0/RX1": _ids(
                "4fffaef3b988bfc9ee866389a1f75f382c6a27647690571041e392ad542c75fd",
                "97f00acb7c58a6e5d98b13430b358d0c08b27d820bd85cd2be7114cdc7cb9c27",
                "8117d2ae2e8a08dc35beac24c3c197502dd43072cc59d6177c97a06771bf7120",
            ),
        },
    },
    "D2-radio5-C3": {
        "dwell": "D2",
        "cross_radio": False,
        "wrong_time": True,
        "members": {
            "stream-0/RX1": _ids(
                "0de1b61119fb6e27fad1c1ffa88a6a149f5d9e9e0f76a60828bb55e0d5145658",
                "b366df2665666ec4a83d43ce59827a1e8912224c35befb946050ffa212172440",
                "909bc973b525664a8851d13e4f902db6d105be00a772cea0c1f4d3be3d9aad77",
            ),
        },
    },
    "D2-radio19-C3": {
        "dwell": "D2",
        "cross_radio": False,
        "wrong_time": False,
        "members": {
            "stream-1/RX1": _ids(
                "ee44554d49edfc11050aba0fbdb8c1bcfed2a65c3d54a67a77c496536d5803e9",
                "935b191ac92d6f6d775604fc40c55930a6620d7728dc9966bea1f1e15a44e613",
                "17961f89753332218d16d6b74495a6793b5d3c9f6234ff34bab121cc418782a4",
            ),
        },
    },
    "D3-episode-A": {
        "dwell": "D3",
        "cross_radio": True,
        "wrong_time": True,
        "members": {
            "stream-0/RX1": _ids(
                "61bf5da58bd89a6df6993e6f56c5869a3f82647d1dc64dd99a263b6d1545a50f",
                "52079094bd5981c8b14c7f5b184bcd88b98405df54a82bbda4251f0a50d95bd6",
                "882ba3c9c25e5a376b56b38100300997195f104b0f822f17510dd1a29a49b9d0",
            ),
            "stream-1/RX1": _ids(
                "70d955e89596eda4042fbaab1007d5ea3689cdece9541e2103dd8fa20482c967",
                "72196ab86ef83d092e73a61c8c69c032412de6d484fa51049547d4bf995b0a33",
                "05c72dc8791d44f37d90b3ad8e57d0b1dd079fe117ef3760a7b81cadda83ec8b",
            ),
        },
    },
    "D3-episode-B": {
        "dwell": "D3",
        "cross_radio": True,
        "wrong_time": False,
        "members": {
            "stream-0/RX1": _ids(
                "23a30d42e8c3b3e9569ed0909e0b8a71bc46f083e82b5145e8f6b8f93b15330e",
                "46d3e2eeea26db70e164fe98557c480e6d863f0648f513d8c35e5e430e5f920a",
                "5f5e2d7e047c50e7c5eac9f72b28fd93b78420e5db3ff59ed66ce3109dfd83f6",
            ),
            "stream-1/RX1": _ids(
                "cade3bee943b557ac00162699217fe8cf5f6c1ef1d89d326857aed170ad448bd",
                "405dc6196ec1a4061eeb8959b67d5cb8322850e442a56800a555c7cec3cd7ef2",
            ),
        },
    },
    "D3-episode-E-four-path": {
        "dwell": "D3",
        "cross_radio": True,
        "wrong_time": True,
        "members": {
            "stream-0/RX0": _ids(
                "bcd9c4a54c62ae747abcf61487d2a3014e9fbc29f77e04b93f045ed5491efbbf",
                "aeb6fe8f379cc09eb39aa4312a1106b5211457b839e9da7076415bc05397ad1a",
                "3fb6a9f97b888ade935cfc24e52e82ef64b27b6212dfd0597aa2dacd3d76ba3c",
            ),
            "stream-0/RX1": _ids(
                "d855bbd66b412e5b21267a80f371a9d7eac3c0feb438c2a79ef30fb16fa780f7",
                "003d095af1916048ce7192feb7ee20a6906d34312b4a36a751fc65de2c71202c",
                "622da1cdcf99cb27bc2689e3b0131399672ddd6b4c85e466aeabd4dc93602e08",
                "6203d7388bc9408d3a8e366fbd2f43b10bf662d10067ce867f23399b06baf98d",
                "c90ce4ed05d332b1e507f4bf860f8d40ed4efdccd508184e1c9357859fdc8ae7",
                "b8b4133bb6f05e763438ac9aa093cb4f3b6bea361683c9ca49e8e15bdfb48679",
            ),
            "stream-1/RX0": _ids(
                "1f678f24899df97fbbde349440161c8d6ce477740e474259cd3466fd37efac02"
            ),
            "stream-1/RX1": _ids(
                "23eae1a96996e5946767f05aa665e0fbcbaf81558f553947fbd91e4e876c3c18",
                "3234857f0129272b12f606dbf3febc1518ad5aa6ac41d7944e0da43544020022",
                "6c452e3c453a37a1d5fb254a5aac4d62e70804b6b6158dda3122b047d211d802",
                "0fd65fe32d4689e6887b6ff836b442200124e7536af6260b93fd6851fa9fb9ce",
                "a33e3f524a7aebb55e0e643401dff8bbbdeb4c62c8431ffc84aa48d3e96c737b",
                "9d94a67c6b6e3e14e01a45930901271008b6648b97f8fc258adfbc191097f0b2",
            ),
        },
    },
}


@dataclass(slots=True)
class Segment:
    dwell: str
    path: str
    trajectory_id: str
    stream_id: str
    receiver_id: int
    radio_id: str
    rf_hz: float
    first_utc_ns: int
    timing_half_width_s: float
    source_times_s: np.ndarray
    source_cfo_hz: np.ndarray
    time_s: np.ndarray
    cfo_hz: np.ndarray
    train: np.ndarray
    sigma_hz: float
    source_product_digests: dict[str, str]
    source_product_uris: dict[str, str]


@dataclass(slots=True)
class DwellInputs:
    dwell: str
    session_id: str
    run_id: str
    reference_utc_ns: int
    bindings: dict[str, StandardPathInputBindV3]
    trajectories: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any], dict[str, str]]]
    pilot_products: dict[str, tuple[dict[str, Any], dict[str, str]]]


@dataclass(slots=True)
class RateObservation:
    acquisition: str
    path: str
    receiver_id: int
    rf_hz: float
    utc_ns: int
    time_s: float
    value_hz_s: float
    sigma_hz_s: float
    train: bool
    source_kind: str
    source_id: str
    qualified: bool
    phase_lock_qualified: bool
    cfo_hz: float | None
    cfo_sigma_hz: float | None
    source_epoch_sample: int | None
    source_probe_start_ms: int | None
    absolute_lattice_phase_sample: float | None
    supported_frame_count: int | None
    lattice_epoch_utc_ns: int | None
    source_product_uri: str
    source_product_sha256: str
    metrics_uri: str | None = None
    metrics_sha256: str | None = None
    input_manifest_uri: str | None = None
    input_manifest_sha256: str | None = None


@dataclass(slots=True)
class CfoObservation:
    acquisition: str
    path: str
    rf_hz: float
    utc_ns: int
    time_s: float
    value_hz: float
    sigma_hz: float
    train: bool
    source_id: str
    source_product_uri: str
    source_product_sha256: str


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read_verified(resolver: BulkUriResolver, product: AnalysisProduct) -> dict[str, Any]:
    payload = resolver.resolve(product.logical_uri).read_bytes()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if digest != product.digest:
        raise ValueError(f"digest mismatch for {product.logical_uri}")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"non-object JSON product {product.logical_uri}")
    return value


def read_json_file(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError(f"non-object JSON file {path}")
    return value, "sha256:" + hashlib.sha256(payload).hexdigest()


def absolute_lattice_phase_sample(
    device_sample: int,
    probe_start_ms: int,
    local_epoch_sample: int,
) -> float:
    """Return frame phase without rounding the 10,000/3-sample lattice period."""

    probe_offset_samples = probe_start_ms * 2_500
    phase_thirds = (
        3 * (device_sample + probe_offset_samples + local_epoch_sample)
    ) % FRAME_LATTICE_PHASE_PERIOD_THIRDS
    return phase_thirds / 3.0


def circular_phase_span_samples(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    period = FRAME_LATTICE_PHASE_PERIOD_THIRDS / 3.0
    ordered = np.sort(np.mod(np.asarray(values, dtype=float), period))
    gaps = np.diff(np.concatenate((ordered, ordered[:1] + period)))
    return float(period - np.max(gaps))


def largest_phase_cluster(
    observations: list[RateObservation],
    maximum_span_samples: float = SCANNER_PHASE_CLUSTER_GATE_SAMPLES,
) -> list[RateObservation]:
    """Select a deterministic largest circular interval, independent of TLE/CFO."""

    if not observations:
        return []
    period = FRAME_LATTICE_PHASE_PERIOD_THIRDS / 3.0
    ordered = sorted(
        observations,
        key=lambda item: (
            float(item.absolute_lattice_phase_sample),
            item.receiver_id,
            item.rf_hz,
            item.source_id,
        ),
    )
    phases = np.asarray([float(item.absolute_lattice_phase_sample) for item in ordered])
    extended = np.concatenate((phases, phases + period))
    choices: list[tuple[int, float, float, int]] = []
    for start in range(len(ordered)):
        stop = start
        while stop + 1 < start + len(ordered) and (
            extended[stop + 1] - extended[start] <= maximum_span_samples + 1e-9
        ):
            stop += 1
        choices.append(
            (
                stop - start + 1,
                -(extended[stop] - extended[start]),
                -extended[start],
                start,
            )
        )
    _, _, _, best_start = max(choices)
    best_count = max(choices)[0]
    return [ordered[index % len(ordered)] for index in range(best_start, best_start + best_count)]


def load_scanner_rate_observations(
    inputs: DwellInputs,
) -> tuple[list[RateObservation], list[dict[str, Any]]]:
    observations: list[RateObservation] = []
    provenance: list[dict[str, Any]] = []
    for visit_index, scan_id in enumerate(SCANNER_IDS, start=1):
        analysis_root = SCANNER_ROOT / scan_id / SCANNER_ANALYZER_ID
        product_path = analysis_root / "scanner-pilot-doppler-segments.v1.json"
        metrics_path = analysis_root / "scanner-metrics.v2.json"
        input_manifest_path = SCANNER_RECORDING_ROOT / scan_id / "manifest.json"
        product, product_sha = read_json_file(product_path)
        metrics, metrics_sha = read_json_file(metrics_path)
        input_manifest, input_manifest_sha = read_json_file(input_manifest_path)
        if product["scan_id"] != scan_id or metrics["scan_id"] != scan_id:
            raise ValueError(f"scan identity mismatch for {scan_id}")
        if input_manifest["scan_id"] != scan_id:
            raise ValueError(f"input manifest identity mismatch for {scan_id}")
        if product["scanner_metrics_sha256"] != metrics_sha:
            raise ValueError(f"scanner metrics digest mismatch for {scan_id}")
        if product["input_manifest_sha256"] != input_manifest_sha:
            raise ValueError(f"scanner input manifest digest mismatch for {scan_id}")
        if input_manifest["radio_id"] != "radio_pluto_5d4d":
            raise ValueError(f"unexpected scanner radio for {scan_id}")
        evidence_by_target = {
            int(item["target_index"]): item for item in metrics["continuity_evidence"]
        }
        provenance.append(
            {
                "visit_index": visit_index,
                "scan_id": scan_id,
                "product_uri": str(product_path),
                "product_sha256": product_sha,
                "metrics_uri": str(metrics_path),
                "metrics_sha256": metrics_sha,
                "input_manifest_uri": str(input_manifest_path),
                "input_manifest_sha256": input_manifest_sha,
                "retune_boundaries_are_discontinuous": product[
                    "retune_boundaries_are_discontinuous"
                ],
            }
        )
        for segment in product["segments"]:
            rate = segment.get("local_doppler_rate_hz_s")
            sigma = segment.get("local_doppler_rate_sigma_hz_s")
            if rate is None or sigma is None:
                continue
            target_index = int(segment["target_index"])
            continuity = evidence_by_target[target_index]
            if continuity["status"] != "attested":
                raise ValueError(f"unattested scanner frame {scan_id} target {target_index}")
            if continuity["within_frame_continuity"] != "proven_within_returned_buffer":
                raise ValueError(f"unproven scanner frame {scan_id} target {target_index}")
            if continuity["missing_samples_before"] != 0 or continuity["overflow_observed"]:
                raise ValueError(f"discontinuous scanner frame {scan_id} target {target_index}")
            reference_utc_ns = int(continuity["sample_time_realtime_start_ns"]) + int(
                round(float(segment["reference_time_since_retune_s"]) * 1e9)
            )
            epoch_sample = int(segment["source_epoch_sample"])
            probe_start_ms = int(segment["source_probe_start_ms"])
            receiver_id = int(segment["receiver_id"])
            observations.append(
                RateObservation(
                    acquisition=f"scan{visit_index:02d}",
                    path=f"radio_pluto_5d4d/RX{receiver_id}",
                    receiver_id=receiver_id,
                    rf_hz=float(segment["target"]["rf_center_hz"]),
                    utc_ns=reference_utc_ns,
                    time_s=(reference_utc_ns - inputs.reference_utc_ns) / 1e9,
                    value_hz_s=float(rate),
                    sigma_hz_s=float(sigma),
                    train=visit_index <= 2,
                    source_kind="scanner.pilot-doppler-segments",
                    source_id=str(segment["segment_id"]),
                    qualified=bool(segment["qualified"]),
                    phase_lock_qualified=bool(segment["phase_lock_qualified"]),
                    cfo_hz=float(segment["local_cfo_at_reference_hz"]),
                    cfo_sigma_hz=float(segment["frequency_line_rms_hz"]),
                    source_epoch_sample=epoch_sample,
                    source_probe_start_ms=probe_start_ms,
                    absolute_lattice_phase_sample=absolute_lattice_phase_sample(
                        int(continuity["first_sample_sequence"]),
                        probe_start_ms,
                        epoch_sample,
                    ),
                    supported_frame_count=int(segment["supported_frame_count"]),
                    lattice_epoch_utc_ns=int(continuity["sample_time_realtime_start_ns"])
                    + probe_start_ms * 1_000_000
                    + epoch_sample * 400,
                    source_product_uri=str(product_path),
                    source_product_sha256=product_sha,
                    metrics_uri=str(metrics_path),
                    metrics_sha256=metrics_sha,
                    input_manifest_uri=str(input_manifest_path),
                    input_manifest_sha256=input_manifest_sha,
                )
            )
    return observations, provenance


def d2_late_rate_observations(inputs: DwellInputs) -> list[RateObservation]:
    path = "stream-0/RX1"
    binding = inputs.bindings[path]
    product, provenance = inputs.pilot_products[path]
    relative_start = (binding.timing.first_estimate_utc_ns - inputs.reference_utc_ns) / 1e9
    rows = [
        item
        for item in product["segments"]
        if item["source_trajectory_id"] == D2_LATE_TRAJECTORY_ID
    ]
    if len(rows) != 16:
        raise ValueError(f"expected 16 D2 late pilot rows, found {len(rows)}")
    result = []
    for item in sorted(rows, key=lambda row: float(row["reference_time_s"])):
        time_s = relative_start + float(item["reference_time_s"])
        result.append(
            RateObservation(
                acquisition="dwell-late-C3",
                path="radio_pluto_5d4d/RX1",
                receiver_id=1,
                rf_hz=float(binding.tuned_center_frequency_hz + STARLINK_LNB_LO_HZ),
                utc_ns=inputs.reference_utc_ns + int(round(time_s * 1e9)),
                time_s=time_s,
                value_hz_s=float(item["local_doppler_rate_hz_s"]),
                sigma_hz_s=float(item["local_doppler_rate_sigma_hz_s"]),
                train=True,
                source_kind="standard.pilot-doppler-segments",
                source_id=f"{D2_LATE_TRAJECTORY_ID}#segment-{item['segment_index']}",
                qualified=bool(item["qualified"]),
                phase_lock_qualified=bool(item["phase_lock_qualified"]),
                cfo_hz=float(item["local_cfo_at_reference_hz"]),
                cfo_sigma_hz=float(item["frequency_line_rms_hz"]),
                source_epoch_sample=None,
                source_probe_start_ms=None,
                absolute_lattice_phase_sample=None,
                supported_frame_count=int(item["supported_frame_count"]),
                lattice_epoch_utc_ns=None,
                source_product_uri=provenance["uri"],
                source_product_sha256=provenance["digest"],
            )
        )
    if any(round(item.rf_hz) != D2_SCANNER_RF_HZ for item in result):
        raise ValueError("D2 late pilot rows are not CH4-lower RF")
    return result


def select_cfo_continuations(
    dwell_rows: list[RateObservation],
    scanner_rows: list[RateObservation],
    *,
    innovation_gate_hz: float = SCANNER_CFO_CONTINUATION_GATE_HZ,
) -> dict[int, list[dict[str, Any]]]:
    """TLE-blind sequential nearest-branch selection at one fixed RF."""

    result: dict[int, list[dict[str, Any]]] = {}
    for receiver_id in (0, 1):
        candidates_by_acquisition: dict[str, list[RateObservation]] = defaultdict(list)
        for item in scanner_rows:
            if item.receiver_id == receiver_id and round(item.rf_hz) == D2_SCANNER_RF_HZ:
                candidates_by_acquisition[item.acquisition].append(item)
        accepted: list[dict[str, Any]] = []
        if receiver_id == 1:
            anchor = max(dwell_rows, key=lambda item: item.time_s)
            last_time = anchor.time_s
            last_cfo = float(anchor.cfo_hz)
            last_rate = anchor.value_hz_s
        else:
            last_time = last_cfo = last_rate = None
        for acquisition in sorted(candidates_by_acquisition):
            choices = candidates_by_acquisition[acquisition]
            if last_time is None:
                choice = min(choices, key=lambda item: (item.source_id, item.receiver_id))
                predicted = None
                innovation = None
                within_gate = True
            else:
                scored = [
                    (
                        abs(
                            float(item.cfo_hz) - (last_cfo + last_rate * (item.time_s - last_time))
                        ),
                        item,
                    )
                    for item in choices
                ]
                _, choice = min(scored, key=lambda value: (value[0], value[1].source_id))
                predicted = last_cfo + last_rate * (choice.time_s - last_time)
                innovation = float(choice.cfo_hz) - predicted
                within_gate = abs(innovation) <= innovation_gate_hz
            accepted.append(
                {
                    "observation": choice,
                    "predicted_cfo_hz": predicted,
                    "innovation_hz": innovation,
                    "accepted": within_gate,
                }
            )
            if within_gate:
                last_time = choice.time_s
                last_cfo = float(choice.cfo_hz)
                last_rate = choice.value_hz_s
        result[receiver_id] = accepted
    return result


def robust_affine_sigma(time_s: np.ndarray, value: np.ndarray, train: np.ndarray) -> float:
    x = time_s - float(np.mean(time_s[train]))
    design = np.column_stack((np.ones(time_s.size), x))
    coeff = np.linalg.lstsq(design[train], value[train], rcond=None)[0]
    residual = value[train] - design[train] @ coeff
    median = float(np.median(residual))
    mad = 1.4826 * float(np.median(np.abs(residual - median)))
    return max(SIGMA_FLOOR_HZ, mad)


def resample(time_s: np.ndarray, cfo_hz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(time_s, kind="stable")
    time_s = np.asarray(time_s[order], dtype=float)
    cfo_hz = np.asarray(cfo_hz[order], dtype=float)
    bins = np.floor((time_s - time_s[0]) / RESAMPLE_S + 1e-9).astype(int)
    unique = np.unique(bins)
    return (
        np.asarray([np.median(time_s[bins == item]) for item in unique]),
        np.asarray([np.median(cfo_hz[bins == item]) for item in unique]),
    )


def temporal_split(count: int) -> np.ndarray:
    if count < 6:
        raise ValueError("segment has too few resampled points")
    cutoff = int(np.clip(math.ceil(TRAIN_FRACTION * count), 3, count - 3))
    result = np.zeros(count, dtype=bool)
    result[:cutoff] = True
    return result


def load_inputs() -> dict[str, DwellInputs]:
    resolver = BulkUriResolver(BULK_ROOT)
    result: dict[str, DwellInputs] = {}
    with Session(create_catalog_engine(DATABASE_URL)) as database:
        for dwell, (session_id, run_id) in RUNS.items():
            binding_rows = database.execute(
                select(RunSubjectBinding, AnalysisScope)
                .join(AnalysisScope, AnalysisScope.id == RunSubjectBinding.scope_id)
                .where(
                    RunSubjectBinding.run_id == run_id,
                    AnalysisScope.kind == "receiver_path",
                )
            ).all()
            product_rows = database.execute(
                select(AnalysisProduct, AnalysisScope)
                .join(AnalysisScope, AnalysisScope.id == AnalysisProduct.scope_id)
                .where(
                    AnalysisProduct.run_id == run_id,
                    AnalysisProduct.kind.in_(
                        (
                            "standard.final-trajectory-bank",
                            "standard.dealiased-trajectory-bank",
                            "standard.pilot-doppler-segments",
                        )
                    ),
                    AnalysisProduct.available.is_(True),
                )
            ).all()
            products = {(scope.id, product.kind): product for product, scope in product_rows}
            bindings: dict[str, StandardPathInputBindV3] = {}
            trajectories: dict[
                tuple[str, str], tuple[dict[str, Any], dict[str, Any], dict[str, str]]
            ] = {}
            pilot_products: dict[str, tuple[dict[str, Any], dict[str, str]]] = {}
            first_times = []
            for registration, scope in binding_rows:
                binding = StandardPathInputBindV3.model_validate(registration.document)
                label = f"{binding.stream_id}/RX{binding.receiver_id}"
                bindings[label] = binding
                first_times.append(binding.timing.first_estimate_utc_ns)
                final_product = products[(scope.id, "standard.final-trajectory-bank")]
                dealiased_product = products[(scope.id, "standard.dealiased-trajectory-bank")]
                pilot_product = products[(scope.id, "standard.pilot-doppler-segments")]
                final = read_verified(resolver, final_product)
                dealiased = read_verified(resolver, dealiased_product)
                pilot = read_verified(resolver, pilot_product)
                if final.get("schema_version") != 3 or dealiased.get("schema_version") != 4:
                    raise ValueError(f"unexpected trajectory schemas on {session_id} {label}")
                if pilot.get("schema_version") != 1:
                    raise ValueError(f"unexpected pilot-segment schema on {session_id} {label}")
                observations = {item["observation_id"]: item for item in dealiased["observations"]}
                provenance = {
                    "final_digest": final_product.digest,
                    "dealiased_digest": dealiased_product.digest,
                    "final_uri": final_product.logical_uri,
                    "dealiased_uri": dealiased_product.logical_uri,
                }
                for trajectory in final["trajectories"]:
                    trajectories[(label, trajectory["trajectory_id"])] = (
                        trajectory,
                        observations,
                        provenance,
                    )
                pilot_products[label] = (
                    pilot,
                    {
                        "digest": pilot_product.digest,
                        "uri": pilot_product.logical_uri,
                    },
                )
            result[dwell] = DwellInputs(
                dwell,
                session_id,
                run_id,
                min(first_times),
                bindings,
                trajectories,
                pilot_products,
            )
    return result


def make_segment(inputs: DwellInputs, path: str, trajectory_id: str) -> Segment:
    trajectory, observation_by_id, provenance = inputs.trajectories[(path, trajectory_id)]
    binding = inputs.bindings[path]
    observations = [observation_by_id[item] for item in trajectory["observation_ids"]]
    if len(observations) != len(trajectory["observation_ids"]):
        raise ValueError("trajectory observations are incomplete")
    lift = float(
        trajectory["absolute_coefficients_hz"][-1] - trajectory["canonical_coefficients_hz"][-1]
    )
    source_time = np.asarray([float(item["time_s"]) for item in observations])
    source_cfo = np.asarray([float(item["component_cfo_hz"]) + lift for item in observations])
    relative_start = (binding.timing.first_estimate_utc_ns - inputs.reference_utc_ns) / 1e9
    time, cfo = resample(relative_start + source_time, source_cfo)
    train = temporal_split(time.size)
    sigma = robust_affine_sigma(time, cfo, train)
    half_width = (
        max(
            binding.timing.first_estimate_utc_ns - binding.timing.first_earliest_utc_ns,
            binding.timing.first_latest_utc_ns - binding.timing.first_estimate_utc_ns,
        )
        / 1e9
    )
    return Segment(
        inputs.dwell,
        path,
        trajectory_id,
        binding.stream_id,
        binding.receiver_id,
        binding.radio_id,
        float(binding.tuned_center_frequency_hz + STARLINK_LNB_LO_HZ),
        binding.timing.first_estimate_utc_ns,
        half_width,
        source_time,
        source_cfo,
        time,
        cfo,
        train,
        sigma,
        {
            "final": provenance["final_digest"],
            "dealiased": provenance["dealiased_digest"],
        },
        {
            "final": provenance["final_uri"],
            "dealiased": provenance["dealiased_uri"],
        },
    )


def sampling_grid(
    reference_ns: int, low_s: float, high_s: float, step_s: float
) -> tuple[SamplingGrid, np.ndarray]:
    count = max(3, int(math.ceil((high_s - low_s) / step_s)) + 1)
    rel = low_s + step_s * np.arange(count)
    utc = tuple(reference_ns + int(round(item * 1e9)) for item in rel)
    return SamplingGrid(utc, count // 2, step_s), rel


def build_prediction_bank(
    catalogue,
    epochs: tuple[int, ...],
    inputs: DwellInputs,
    segments: list[Segment],
    *,
    sky_shift_s: float = 0.0,
    site: ObserverSiteV1 = SITE,
) -> dict[str, Any]:
    low = min(float(item.time_s.min()) for item in segments) - 1.0
    high = max(float(item.time_s.max()) for item in segments) + 1.0
    coarse, coarse_rel = sampling_grid(
        inputs.reference_utc_ns, low + sky_shift_s, high + sky_shift_s, 0.5
    )
    propagated = propagate_grid(catalogue, coarse)
    observed = observe_grid(propagated, site, coarse)
    starlink = np.asarray([name.startswith("STARLINK") for name in catalogue.names])
    plausible = observed.altitude_km.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    selected = np.flatnonzero(
        propagated.usable
        & plausible
        & starlink
        & (observed.elevation_deg.max(axis=1) >= HORIZON_DEG)
    )
    fine, fine_sky_rel = sampling_grid(
        inputs.reference_utc_ns,
        low + sky_shift_s,
        high + sky_shift_s,
        0.05,
    )
    fine_propagated = propagate_grid(catalogue, fine, indices=selected)
    fine_observed = observe_grid(fine_propagated, site, fine)
    # Curves are indexed by radio-relative time; UTC evaluation is shifted.
    fine_radio_rel = fine_sky_rel - sky_shift_s
    keep = []
    metadata = []
    for row, catalogue_index in enumerate(selected):
        fractions = []
        for segment in segments:
            elevation = np.interp(segment.time_s, fine_radio_rel, fine_observed.elevation_deg[row])
            fractions.append(float(np.mean(elevation >= HORIZON_DEG)))
        if min(fractions) < 0.95:
            continue
        keep.append(row)
        midpoint = float(np.mean([np.mean(item.time_s) for item in segments]))
        elevation_mid = float(np.interp(midpoint, fine_radio_rel, fine_observed.elevation_deg[row]))
        range_mid = float(np.interp(midpoint, fine_radio_rel, fine_observed.range_km[row]))
        range_rate_mid = float(
            np.interp(midpoint, fine_radio_rel, fine_observed.range_rate_km_s[row])
        )
        metadata.append(
            {
                "catalogue_index": int(catalogue_index),
                "catalog_number": int(catalogue.satellite_numbers[catalogue_index]),
                "object_name": catalogue.names[catalogue_index],
                "element_epoch_utc_ns": int(epochs[catalogue_index]),
                "element_age_s": float(
                    abs(inputs.reference_utc_ns + round(midpoint * 1e9) - epochs[catalogue_index])
                    / 1e9
                ),
                "minimum_visibility_fraction": min(fractions),
                "minimum_elevation_deg": float(fine_observed.elevation_deg[row].min()),
                "peak_elevation_deg": float(fine_observed.elevation_deg[row].max()),
                "midpoint_elevation_deg": elevation_mid,
                "midpoint_range_km": range_mid,
                "midpoint_range_rate_km_s": range_rate_mid,
            }
        )
    keep_array = np.asarray(keep, dtype=int)
    range_rate = fine_observed.range_rate_km_s[keep_array]
    slant_range = fine_observed.range_km[keep_array]
    # Independent finite-difference audit of rotating-frame range-rate output.
    fd_range_rate = np.gradient(slant_range, fine_radio_rel, axis=1, edge_order=2)
    derivative_audit = {
        "maximum_range_derivative_minus_range_rate_km_s": float(
            np.max(np.abs(fd_range_rate[:, 1:-1] - range_rate[:, 1:-1]))
        )
        if range_rate.size
        else None,
        "grid_spacing_s": 0.05,
    }
    curves_by_path = {
        path: doppler_shift_hz(segments_for_path[0].rf_hz, range_rate)
        for path in sorted({item.path for item in segments})
        if (segments_for_path := [item for item in segments if item.path == path])
    }
    return {
        "time_s": fine_radio_rel,
        "range_rate_km_s": range_rate,
        "metadata": metadata,
        "curves_by_path": curves_by_path,
        "derivative_audit": derivative_audit,
        "coarse_candidate_count": int(selected.size),
        "candidate_count": len(metadata),
    }


def build_observation_prediction_bank(
    catalogue,
    epochs: tuple[int, ...],
    reference_ns: int,
    observations: list[RateObservation] | list[CfoObservation],
    *,
    maximum_epoch_s: float,
    sky_shift_s: float = 0.0,
    visibility_over_complete_interval: bool = True,
) -> dict[str, Any]:
    """Build exact-RF Doppler and Doppler-rate curves for scalar observations."""

    low = min(item.time_s for item in observations) - maximum_epoch_s - 1.0
    high = max(item.time_s for item in observations) + maximum_epoch_s + 1.0
    coarse, _ = sampling_grid(reference_ns, low + sky_shift_s, high + sky_shift_s, 0.5)
    propagated = propagate_grid(catalogue, coarse)
    observed = observe_grid(propagated, SITE, coarse)
    starlink = np.asarray([name.startswith("STARLINK") for name in catalogue.names])
    plausible = observed.altitude_km.min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    selected = np.flatnonzero(
        propagated.usable
        & plausible
        & starlink
        & (
            (observed.elevation_deg.min(axis=1) >= HORIZON_DEG)
            if visibility_over_complete_interval
            else (observed.elevation_deg.max(axis=1) >= HORIZON_DEG)
        )
    )
    fine, fine_sky_rel = sampling_grid(reference_ns, low + sky_shift_s, high + sky_shift_s, 0.05)
    fine_propagated = propagate_grid(catalogue, fine, indices=selected)
    fine_observed = observe_grid(fine_propagated, SITE, fine)
    fine_radio_rel = fine_sky_rel - sky_shift_s
    if visibility_over_complete_interval:
        keep = np.flatnonzero(fine_observed.elevation_deg.min(axis=1) >= HORIZON_DEG)
    else:
        observed_times = np.asarray([item.time_s for item in observations])
        keep = np.flatnonzero(
            np.asarray(
                [
                    np.min(np.interp(observed_times, fine_radio_rel, row)) >= HORIZON_DEG
                    for row in fine_observed.elevation_deg
                ]
            )
        )
    selected = selected[keep]
    elevation = fine_observed.elevation_deg[keep]
    slant_range = fine_observed.range_km[keep]
    range_rate = fine_observed.range_rate_km_s[keep]
    midpoint = float(np.mean([item.time_s for item in observations]))
    metadata = []
    for row, catalogue_index in enumerate(selected):
        metadata.append(
            {
                "catalogue_index": int(catalogue_index),
                "catalog_number": int(catalogue.satellite_numbers[catalogue_index]),
                "object_name": catalogue.names[catalogue_index],
                "element_epoch_utc_ns": int(epochs[catalogue_index]),
                "element_age_s": float(
                    abs(reference_ns + round(midpoint * 1e9) - epochs[catalogue_index]) / 1e9
                ),
                "minimum_elevation_deg": float(elevation[row].min()),
                "peak_elevation_deg": float(elevation[row].max()),
                "midpoint_elevation_deg": float(
                    np.interp(midpoint, fine_radio_rel, elevation[row])
                ),
                "midpoint_range_km": float(np.interp(midpoint, fine_radio_rel, slant_range[row])),
                "midpoint_range_rate_km_s": float(
                    np.interp(midpoint, fine_radio_rel, range_rate[row])
                ),
            }
        )
    rf_values = sorted({int(round(item.rf_hz)) for item in observations})
    cfo_by_rf = {rf_hz: doppler_shift_hz(float(rf_hz), range_rate) for rf_hz in rf_values}
    rate_by_rf = {
        rf_hz: np.gradient(curves, fine_radio_rel, axis=1, edge_order=2)
        for rf_hz, curves in cfo_by_rf.items()
    }
    finite_difference_range_rate = np.gradient(slant_range, fine_radio_rel, axis=1, edge_order=2)
    return {
        "time_s": fine_radio_rel,
        "metadata": metadata,
        "range_km": slant_range,
        "range_rate_km_s": range_rate,
        "cfo_by_rf": cfo_by_rf,
        "rate_by_rf": rate_by_rf,
        "candidate_count": len(metadata),
        "coarse_candidate_count": int(keep.size),
        "derivative_audit": {
            "maximum_range_derivative_minus_range_rate_km_s": float(
                np.max(np.abs(finite_difference_range_rate[:, 1:-1] - range_rate[:, 1:-1]))
            )
            if range_rate.size
            else None,
            "grid_spacing_s": 0.05,
        },
    }


def scalar_metrics(
    residual: np.ndarray,
    sigma: np.ndarray,
    train: np.ndarray,
    *,
    unit: str,
) -> dict[str, float]:
    def rms(value: np.ndarray) -> float:
        return float(np.sqrt(np.mean(value**2)))

    return {
        f"train_rms_{unit}": rms(residual[train]),
        f"holdout_rms_{unit}": rms(residual[~train]),
        f"full_rms_{unit}": rms(residual),
        "train_standardized_rms": rms(residual[train] / sigma[train]),
        "holdout_standardized_rms": rms(residual[~train] / sigma[~train]),
        "full_standardized_rms": rms(residual / sigma),
    }


def robust_location(
    values: np.ndarray,
    sigma: np.ndarray,
    *,
    lower: float = -math.inf,
    upper: float = math.inf,
) -> float:
    base = 1.0 / np.square(sigma)
    effective = base.copy()
    location = float(np.average(values, weights=effective))
    for _ in range(20):
        location = float(np.clip(np.average(values, weights=effective), lower, upper))
        normalized = np.abs(values - location) / (HUBER_K * sigma)
        huber = np.ones(values.size)
        tail = normalized > 1.0
        huber[tail] = 1.0 / normalized[tail]
        updated = base * huber
        if float(np.max(np.abs(updated - effective))) < 1e-15:
            break
        effective = updated
    return location


def fit_rate_candidate(
    observations: list[RateObservation],
    bank: dict[str, Any],
    candidate_index: int,
    epoch_bound_s: float,
    *,
    sign: float = 1.0,
    nuisance_bound_hz_s: float = SPECIAL_RATE_NUISANCE_BOUND_HZ_S,
) -> dict[str, Any]:
    values = np.asarray([item.value_hz_s for item in observations])
    sigma = np.asarray([item.sigma_hz_s for item in observations])
    train = np.asarray([item.train for item in observations])
    paths = np.asarray([item.path for item in observations])
    choices = []
    epoch_grid = np.arange(
        -epoch_bound_s,
        epoch_bound_s + SPECIAL_EPOCH_STEP_S * 0.5,
        SPECIAL_EPOCH_STEP_S,
    )
    for epoch_shift in epoch_grid:
        prediction = np.asarray(
            [
                sign
                * np.interp(
                    item.time_s + epoch_shift,
                    bank["time_s"],
                    bank["rate_by_rf"][int(round(item.rf_hz))][candidate_index],
                )
                for item in observations
            ]
        )
        target = values - prediction
        nuisances = {}
        fitted = np.zeros(values.size)
        for path in sorted(set(paths)):
            selected = (paths == path) & train
            nuisance = robust_location(
                target[selected],
                sigma[selected],
                lower=-nuisance_bound_hz_s,
                upper=nuisance_bound_hz_s,
            )
            nuisances[path] = nuisance
            fitted[paths == path] = nuisance
        residual = target - fitted
        choices.append(
            {
                "epoch_adjustment_s": float(epoch_shift),
                "path_rate_nuisance_hz_s": nuisances,
                **scalar_metrics(residual, sigma, train, unit="hz_s"),
            }
        )
    return min(
        choices,
        key=lambda item: (
            item["train_standardized_rms"],
            abs(item["epoch_adjustment_s"]),
            item["epoch_adjustment_s"],
        ),
    )


def rank_rate_bank(
    observations: list[RateObservation],
    bank: dict[str, Any],
    epoch_bound_s: float,
    *,
    sign: float = 1.0,
) -> list[dict[str, Any]]:
    rows = []
    for index, metadata in enumerate(bank["metadata"]):
        rows.append(
            {
                **metadata,
                **fit_rate_candidate(
                    observations,
                    bank,
                    index,
                    epoch_bound_s,
                    sign=sign,
                ),
            }
        )
    return sorted(rows, key=lambda item: (item["train_standardized_rms"], item["catalog_number"]))


def _weighted_linear_residual(
    time_s: np.ndarray,
    values: np.ndarray,
    sigma: np.ndarray,
    train: np.ndarray,
    groups: np.ndarray,
    *,
    affine: bool,
) -> tuple[np.ndarray, dict[str, float], float | None]:
    labels = sorted(set(groups))
    centered_time = time_s - float(np.mean(time_s[train]))
    columns = [(groups == label).astype(float) for label in labels]
    if affine:
        columns.append(centered_time)
    design = np.column_stack(columns)
    base = 1.0 / np.square(sigma[train])
    effective = base.copy()
    coeff = np.zeros(design.shape[1])
    for _ in range(20):
        weighted_design = design[train] * np.sqrt(effective)[:, None]
        weighted_value = values[train] * np.sqrt(effective)
        coeff = np.linalg.lstsq(weighted_design, weighted_value, rcond=None)[0]
        train_residual = values[train] - design[train] @ coeff
        normalized = np.abs(train_residual) / (HUBER_K * sigma[train])
        huber = np.ones(train_residual.size)
        tail = normalized > 1.0
        huber[tail] = 1.0 / normalized[tail]
        updated = base * huber
        if float(np.max(np.abs(updated - effective))) < 1e-15:
            break
        effective = updated
    return (
        values - design @ coeff,
        {label: float(coeff[index]) for index, label in enumerate(labels)},
        float(coeff[-1]) if affine else None,
    )


def rate_nulls(observations: list[RateObservation]) -> dict[str, Any]:
    time_s = np.asarray([item.time_s for item in observations])
    values = np.asarray([item.value_hz_s for item in observations])
    sigma = np.asarray([item.sigma_hz_s for item in observations])
    train = np.asarray([item.train for item in observations])
    paths = np.asarray([item.path for item in observations])
    constant_residual, constant_offsets, _ = _weighted_linear_residual(
        time_s, values, sigma, train, paths, affine=False
    )
    shared_residual, shared_offsets, shared_slope = _weighted_linear_residual(
        time_s, values, sigma, train, paths, affine=True
    )
    independent_residual = np.zeros(values.size)
    independent = {}
    for path in sorted(set(paths)):
        selected = paths == path
        row_residual, offsets, slope = _weighted_linear_residual(
            time_s[selected],
            values[selected],
            sigma[selected],
            train[selected],
            np.full(int(selected.sum()), path),
            affine=True,
        )
        independent_residual[selected] = row_residual
        independent[path] = {"intercept_hz_s": offsets[path], "slope_hz_s2": slope}
    return {
        "per_path_constant": {
            "path_offsets_hz_s": constant_offsets,
            **scalar_metrics(constant_residual, sigma, train, unit="hz_s"),
        },
        "shared_slope_affine": {
            "path_offsets_hz_s": shared_offsets,
            "shared_slope_hz_s2": shared_slope,
            **scalar_metrics(shared_residual, sigma, train, unit="hz_s"),
        },
        "independent_path_affine": {
            "path_coefficients": independent,
            **scalar_metrics(independent_residual, sigma, train, unit="hz_s"),
        },
    }


def rate_candidate_public(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "object_name",
        "catalog_number",
        "element_epoch_utc_ns",
        "element_age_s",
        "minimum_elevation_deg",
        "peak_elevation_deg",
        "midpoint_elevation_deg",
        "midpoint_range_km",
        "midpoint_range_rate_km_s",
        "epoch_adjustment_s",
        "path_rate_nuisance_hz_s",
        "train_rms_hz_s",
        "holdout_rms_hz_s",
        "full_rms_hz_s",
        "train_standardized_rms",
        "holdout_standardized_rms",
        "full_standardized_rms",
    )
    return {key: row[key] for key in keys}


def fit_cfo_candidate(
    observations: list[CfoObservation],
    bank: dict[str, Any],
    candidate_index: int,
    epoch_bound_s: float,
) -> dict[str, Any]:
    time_s = np.asarray([item.time_s for item in observations])
    values = np.asarray([item.value_hz for item in observations])
    sigma = np.asarray([item.sigma_hz for item in observations])
    train = np.asarray([item.train for item in observations])
    centered = time_s - float(np.mean(time_s[train]))
    choices = []
    epoch_grid = np.arange(
        -epoch_bound_s,
        epoch_bound_s + SPECIAL_EPOCH_STEP_S * 0.5,
        SPECIAL_EPOCH_STEP_S,
    )
    for epoch_shift in epoch_grid:
        prediction = np.asarray(
            [
                np.interp(
                    item.time_s + epoch_shift,
                    bank["time_s"],
                    bank["cfo_by_rf"][int(round(item.rf_hz))][candidate_index],
                )
                for item in observations
            ]
        )
        target = values - prediction
        base = 1.0 / np.square(sigma[train])
        effective = base.copy()
        intercept = 0.0
        drift = 0.0
        for _ in range(20):
            selected_time = centered[train]
            selected_target = target[train]
            mean_t = float(np.average(selected_time, weights=effective))
            mean_y = float(np.average(selected_target, weights=effective))
            denominator = float(np.sum(effective * np.square(selected_time - mean_t)))
            slope = (
                0.0
                if denominator == 0.0
                else float(
                    np.sum(effective * (selected_time - mean_t) * (selected_target - mean_y))
                    / denominator
                )
            )
            drift = float(
                np.clip(slope, -SPECIAL_CFO_DRIFT_BOUND_HZ_S, SPECIAL_CFO_DRIFT_BOUND_HZ_S)
            )
            intercept = float(
                np.average(selected_target - drift * selected_time, weights=effective)
            )
            train_residual = selected_target - intercept - drift * selected_time
            normalized = np.abs(train_residual) / (HUBER_K * sigma[train])
            huber = np.ones(train_residual.size)
            tail = normalized > 1.0
            huber[tail] = 1.0 / normalized[tail]
            updated = base * huber
            if float(np.max(np.abs(updated - effective))) < 1e-15:
                break
            effective = updated
        residual = target - intercept - drift * centered
        choices.append(
            {
                "epoch_adjustment_s": float(epoch_shift),
                "global_cfo_intercept_hz": intercept,
                "global_cfo_drift_hz_s": drift,
                **scalar_metrics(residual, sigma, train, unit="hz"),
            }
        )
    return min(
        choices,
        key=lambda item: (
            item["train_standardized_rms"],
            abs(item["epoch_adjustment_s"]),
            item["epoch_adjustment_s"],
        ),
    )


def rank_cfo_bank(
    observations: list[CfoObservation],
    bank: dict[str, Any],
    epoch_bound_s: float,
) -> list[dict[str, Any]]:
    rows = [
        {
            **metadata,
            **fit_cfo_candidate(observations, bank, index, epoch_bound_s),
        }
        for index, metadata in enumerate(bank["metadata"])
    ]
    return sorted(rows, key=lambda item: (item["train_standardized_rms"], item["catalog_number"]))


def phase_cluster_partition(
    observations: list[RateObservation],
    maximum_span_samples: float = SCANNER_PHASE_CLUSTER_GATE_SAMPLES,
) -> list[list[RateObservation]]:
    """Partition circular phases after cutting at the largest empty arc."""

    if not observations:
        return []
    period = FRAME_LATTICE_PHASE_PERIOD_THIRDS / 3.0
    ordered = sorted(observations, key=lambda item: float(item.absolute_lattice_phase_sample))
    phases = np.asarray([float(item.absolute_lattice_phase_sample) for item in ordered])
    gaps = np.diff(np.concatenate((phases, phases[:1] + period)))
    start = (int(np.argmax(gaps)) + 1) % len(ordered)
    unwrapped_items = [ordered[(start + index) % len(ordered)] for index in range(len(ordered))]
    unwrapped_phases = []
    previous = None
    for item in unwrapped_items:
        value = float(item.absolute_lattice_phase_sample)
        if previous is not None and value < previous:
            value += period
        unwrapped_phases.append(value)
        previous = value
    clusters: list[list[RateObservation]] = []
    cluster: list[RateObservation] = []
    cluster_start = 0.0
    for item, phase in zip(unwrapped_items, unwrapped_phases, strict=True):
        if cluster and phase - cluster_start > maximum_span_samples + 1e-9:
            clusters.append(cluster)
            cluster = []
        if not cluster:
            cluster_start = phase
        cluster.append(item)
    if cluster:
        clusters.append(cluster)
    return sorted(
        clusters,
        key=lambda rows: (
            -len(rows),
            circular_phase_span_samples(
                [float(item.absolute_lattice_phase_sample) for item in rows]
            ),
            min(float(item.absolute_lattice_phase_sample) for item in rows),
        ),
    )


def rate_observation_public(item: RateObservation) -> dict[str, Any]:
    return {
        "acquisition": item.acquisition,
        "path": item.path,
        "receiver_id": item.receiver_id,
        "rf_hz": int(round(item.rf_hz)),
        "utc_ns": item.utc_ns,
        "relative_time_s": item.time_s,
        "local_doppler_rate_hz_s": item.value_hz_s,
        "local_doppler_rate_sigma_hz_s": item.sigma_hz_s,
        "training": item.train,
        "source_kind": item.source_kind,
        "source_id": item.source_id,
        "qualified": item.qualified,
        "phase_lock_qualified": item.phase_lock_qualified,
        "local_cfo_hz": item.cfo_hz,
        "source_epoch_sample": item.source_epoch_sample,
        "source_probe_start_ms": item.source_probe_start_ms,
        "absolute_lattice_phase_sample": item.absolute_lattice_phase_sample,
        "supported_frame_count": item.supported_frame_count,
        "lattice_epoch_utc_ns": item.lattice_epoch_utc_ns,
        "source_product_uri": item.source_product_uri,
        "source_product_sha256": item.source_product_sha256,
        "metrics_uri": item.metrics_uri,
        "metrics_sha256": item.metrics_sha256,
        "input_manifest_uri": item.input_manifest_uri,
        "input_manifest_sha256": item.input_manifest_sha256,
    }


def cfo_candidate_public(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "object_name",
        "catalog_number",
        "element_epoch_utc_ns",
        "element_age_s",
        "minimum_elevation_deg",
        "peak_elevation_deg",
        "midpoint_elevation_deg",
        "midpoint_range_km",
        "midpoint_range_rate_km_s",
        "epoch_adjustment_s",
        "global_cfo_intercept_hz",
        "global_cfo_drift_hz_s",
        "train_rms_hz",
        "holdout_rms_hz",
        "full_rms_hz",
        "train_standardized_rms",
        "holdout_standardized_rms",
        "full_standardized_rms",
    )
    return {key: row[key] for key in keys}


def tle_records(path: Path) -> dict[int, tuple[str, str]]:
    lines = [line.rstrip() for line in path.read_text().splitlines() if line.strip()]
    result: dict[int, tuple[str, str]] = {}
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("1 ") or not lines[index + 1].startswith("2 "):
            continue
        satellite_field = line[2:7]
        if not satellite_field.isdigit():
            # Alpha-5 catalogue IDs are irrelevant to the numeric Starlink
            # candidates in this audit and cannot be keyed by int directly.
            continue
        satellite_number = int(satellite_field)
        result[satellite_number] = (line, lines[index + 1])
    return result


def exact_record_stable(catalog_number: int) -> bool:
    current = tle_records(TLE_PATH)
    previous = tle_records(PREVIOUS_TLE_PATH)
    return catalog_number in current and current[catalog_number] == previous.get(catalog_number)


def analyze_rate_series(
    name: str,
    observations: list[RateObservation],
    reference_ns: int,
    catalogue,
    epochs: tuple[int, ...],
    *,
    run_wrong_time: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not any(item.train for item in observations) or not any(
        not item.train for item in observations
    ):
        raise ValueError(f"{name} needs both training and held-out rate observations")
    bank = build_observation_prediction_bank(
        catalogue,
        epochs,
        reference_ns,
        observations,
        maximum_epoch_s=max(SPECIAL_EPOCH_BOUNDS_S),
    )
    nulls = rate_nulls(observations)
    models = {}
    internal_rankings = {}
    for bound in SPECIAL_EPOCH_BOUNDS_S:
        ranked = rank_rate_bank(observations, bank, bound)
        key = f"plus_minus_{bound:g}s"
        target = next((row for row in ranked if row["catalog_number"] == 57902), None)
        models[key] = {
            "best": rate_candidate_public(ranked[0]),
            "runner": rate_candidate_public(ranked[1]),
            "runner_train_standardized_margin": float(
                ranked[1]["train_standardized_rms"] - ranked[0]["train_standardized_rms"]
            ),
            "candidate_57902_rank": (
                None
                if target is None
                else 1 + next(index for index, row in enumerate(ranked) if row is target)
            ),
            "candidate_57902": None if target is None else rate_candidate_public(target),
        }
        internal_rankings[key] = ranked
    reversed_ranked = rank_rate_bank(observations, bank, max(SPECIAL_EPOCH_BOUNDS_S), sign=-1.0)
    wrong_time = []
    if run_wrong_time:
        true_advantage = (
            nulls["shared_slope_affine"]["holdout_rms_hz_s"]
            - models["plus_minus_2s"]["best"]["holdout_rms_hz_s"]
        )
        for shift in SPECIAL_WRONG_TIME_SHIFTS_S:
            shifted_bank = build_observation_prediction_bank(
                catalogue,
                epochs,
                reference_ns,
                observations,
                maximum_epoch_s=max(SPECIAL_EPOCH_BOUNDS_S),
                sky_shift_s=shift,
            )
            ranked = rank_rate_bank(observations, shifted_bank, max(SPECIAL_EPOCH_BOUNDS_S))
            wrong_time.append(
                {
                    "sky_time_shift_s": shift,
                    "best": rate_candidate_public(ranked[0]),
                    "holdout_advantage_over_shared_affine_null_hz_s": float(
                        nulls["shared_slope_affine"]["holdout_rms_hz_s"]
                        - ranked[0]["holdout_rms_hz_s"]
                    ),
                }
            )
        empirical_p = float(
            (
                1
                + sum(
                    item["holdout_advantage_over_shared_affine_null_hz_s"] >= true_advantage
                    for item in wrong_time
                )
            )
            / (1 + len(wrong_time))
        )
    else:
        empirical_p = None
    best = models["plus_minus_2s"]["best"]
    public = {
        "analysis": name,
        "observable": "independently fitted local Doppler rate; no CFO intercept is bridged",
        "selection_is_tle_blind": True,
        "observation_count": len(observations),
        "training_count": sum(item.train for item in observations),
        "holdout_count": sum(not item.train for item in observations),
        "path_count": len({item.path for item in observations}),
        "rf_hz": sorted({int(round(item.rf_hz)) for item in observations}),
        "unqualified_observation_count": sum(not item.qualified for item in observations),
        "observations": [rate_observation_public(item) for item in observations],
        "candidate_screen": {
            "horizon_deg": HORIZON_DEG,
            "visibility_requirement": "above horizon over the complete observed interval",
            "candidate_count": bank["candidate_count"],
            "derivative_audit": bank["derivative_audit"],
        },
        "nuisance": {
            "state": "one additive local-rate offset per RX chain",
            "bound_hz_s": SPECIAL_RATE_NUISANCE_BOUND_HZ_S,
        },
        "nulls": nulls,
        "models": models,
        "reversed_sign_falsifier": rate_candidate_public(reversed_ranked[0]),
        "wrong_time_controls": wrong_time,
        "wrong_time_holdout_advantage_empirical_p": empirical_p,
        "primary_best_exact_tle_record_stable_in_previous_snapshot": exact_record_stable(
            best["catalog_number"]
        ),
    }
    return public, {"bank": bank, "rankings": internal_rankings, "observations": observations}


def make_d2_cfo_observations(
    dwell_rows: list[RateObservation],
    continuations: dict[int, list[dict[str, Any]]],
) -> list[CfoObservation]:
    rows = [
        CfoObservation(
            acquisition=item.acquisition,
            path=item.path,
            rf_hz=item.rf_hz,
            utc_ns=item.utc_ns,
            time_s=item.time_s,
            value_hz=float(item.cfo_hz),
            sigma_hz=max(10.0, float(item.cfo_sigma_hz)),
            train=True,
            source_id=item.source_id,
            source_product_uri=item.source_product_uri,
            source_product_sha256=item.source_product_sha256,
        )
        for item in dwell_rows
    ]
    for selection in continuations[1]:
        item = selection["observation"]
        if not selection["accepted"]:
            continue
        rows.append(
            CfoObservation(
                acquisition=item.acquisition,
                path=item.path,
                rf_hz=item.rf_hz,
                utc_ns=item.utc_ns,
                time_s=item.time_s,
                value_hz=float(item.cfo_hz),
                sigma_hz=max(10.0, float(item.cfo_sigma_hz)),
                train=item.acquisition in {"scan01", "scan02"},
                source_id=item.source_id,
                source_product_uri=item.source_product_uri,
                source_product_sha256=item.source_product_sha256,
            )
        )
    return sorted(rows, key=lambda item: item.time_s)


def analyze_cfo_continuity_hypothesis(
    observations: list[CfoObservation],
    reference_ns: int,
    catalogue,
    epochs: tuple[int, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    bank = build_observation_prediction_bank(
        catalogue,
        epochs,
        reference_ns,
        observations,
        maximum_epoch_s=max(SPECIAL_EPOCH_BOUNDS_S),
    )
    time_s = np.asarray([item.time_s for item in observations])
    values = np.asarray([item.value_hz for item in observations])
    sigma = np.asarray([item.sigma_hz for item in observations])
    train = np.asarray([item.train for item in observations])
    residual, offsets, slope = _weighted_linear_residual(
        time_s,
        values,
        sigma,
        train,
        np.full(len(observations), "RX1-global"),
        affine=True,
    )
    null = {
        "global_intercept_hz": offsets["RX1-global"],
        "global_drift_hz_s": slope,
        **scalar_metrics(residual, sigma, train, unit="hz"),
    }
    centered_time = time_s - float(np.mean(time_s[train]))
    ordinary_design = np.column_stack((np.ones(time_s.size), centered_time))
    ordinary_coefficients = np.linalg.lstsq(ordinary_design[train], values[train], rcond=None)[0]
    ordinary_residual = values - ordinary_design @ ordinary_coefficients
    ordinary_null = {
        "global_intercept_hz": float(ordinary_coefficients[0]),
        "global_drift_hz_s": float(ordinary_coefficients[1]),
        **scalar_metrics(ordinary_residual, sigma, train, unit="hz"),
    }
    models = {}
    rankings = {}
    for bound in SPECIAL_EPOCH_BOUNDS_S:
        ranked = rank_cfo_bank(observations, bank, bound)
        target = next((row for row in ranked if row["catalog_number"] == 57902), None)
        key = f"plus_minus_{bound:g}s"
        models[key] = {
            "best": cfo_candidate_public(ranked[0]),
            "runner": cfo_candidate_public(ranked[1]),
            "candidate_57902_rank": (
                None
                if target is None
                else 1 + next(index for index, row in enumerate(ranked) if row is target)
            ),
            "candidate_57902": None if target is None else cfo_candidate_public(target),
        }
        rankings[key] = ranked
    return (
        {
            "analysis": "D2-CH4-lower-RX1-dwell-to-scanner-CFO-continuity-hypothesis",
            "observable": "absolute local CFO at 16 dwell windows and four scanner visits",
            "selection_is_tle_blind": True,
            "critical_assumption": (
                "one CFO intercept and one bounded drift remain meaningful across four "
                "retune/reset acquisitions"
            ),
            "not_reset_safe": True,
            "training_rule": "16 dwell rows plus scanner visits 1-2",
            "holdout_rule": "scanner visits 3-4",
            "cfo_drift_bound_hz_s": SPECIAL_CFO_DRIFT_BOUND_HZ_S,
            "observations": [
                {
                    "acquisition": item.acquisition,
                    "path": item.path,
                    "rf_hz": int(round(item.rf_hz)),
                    "utc_ns": item.utc_ns,
                    "relative_time_s": item.time_s,
                    "cfo_hz": item.value_hz,
                    "sigma_hz": item.sigma_hz,
                    "training": item.train,
                    "source_id": item.source_id,
                    "source_product_uri": item.source_product_uri,
                    "source_product_sha256": item.source_product_sha256,
                }
                for item in observations
            ],
            "affine_cfo_null": null,
            "ordinary_least_squares_affine_cfo_null": ordinary_null,
            "models": models,
            "free_intercept_per_scanner_acquisition_sensitivity": {
                "scanner_singleton_count": sum(
                    item.acquisition.startswith("scan") for item in observations
                ),
                "identifying_scanner_cfo_residual_degrees_of_freedom": 0,
                "interpretation": (
                    "A free intercept for each scanner acquisition absorbs its sole CFO "
                    "point exactly; scanner CFO then carries no orbit-discriminating evidence."
                ),
            },
        },
        {"bank": bank, "rankings": rankings, "observations": observations},
    )


def _timing_residual(
    observations: list[CfoObservation],
    bank: dict[str, Any],
    candidate_index: int | None,
    *,
    include_global_timing_rate: bool,
    range_sign: float = -1.0,
) -> tuple[np.ndarray, dict[str, float], float | None]:
    period = FRAME_LATTICE_PHASE_PERIOD_THIRDS / 3.0
    sample_rate_hz = 2_500_000.0
    values = []
    times = []
    groups = []
    for acquisition in sorted({item.acquisition for item in observations}):
        rows = sorted(
            (item for item in observations if item.acquisition == acquisition),
            key=lambda item: item.time_s,
        )
        observed = np.asarray([item.value_hz for item in rows])
        unwrapped_observed = np.unwrap(observed / period * 2.0 * np.pi) * period / (2.0 * np.pi)
        if candidate_index is not None:
            ranges = np.asarray(
                [
                    np.interp(
                        item.time_s,
                        bank["time_s"],
                        bank["range_km"][candidate_index],
                    )
                    for item in rows
                ]
            )
            predicted = range_sign * ranges / SPEED_OF_LIGHT_KM_S * sample_rate_hz
            unwrapped_prediction = (
                np.unwrap(np.mod(predicted, period) / period * 2.0 * np.pi) * period / (2.0 * np.pi)
            )
            unwrapped_observed = unwrapped_observed - unwrapped_prediction
        values.extend(unwrapped_observed)
        times.extend(item.time_s for item in rows)
        groups.extend(acquisition for _ in rows)
    values_array = np.asarray(values)
    time_array = np.asarray(times)
    labels = sorted(set(groups))
    columns = [np.asarray(groups) == label for label in labels]
    if include_global_timing_rate:
        columns.append(time_array - float(np.mean(time_array)))
    design = np.column_stack(columns)
    coefficients = np.linalg.lstsq(design, values_array, rcond=None)[0]
    return (
        values_array - design @ coefficients,
        {label: float(coefficients[index]) for index, label in enumerate(labels)},
        float(coefficients[-1]) if include_global_timing_rate else None,
    )


def analyze_scanner_lattice_timing_falsifier(
    scanner_rows: list[RateObservation],
    reference_ns: int,
    catalogue,
    epochs: tuple[int, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = [
        item
        for item in scanner_rows
        if item.receiver_id == 1 and int(item.supported_frame_count) >= 20
    ]
    observations = [
        CfoObservation(
            acquisition=item.acquisition,
            path=item.path,
            rf_hz=item.rf_hz,
            utc_ns=int(item.lattice_epoch_utc_ns),
            time_s=(int(item.lattice_epoch_utc_ns) - reference_ns) / 1e9,
            value_hz=float(item.absolute_lattice_phase_sample),
            sigma_hz=1.0,
            train=True,
            source_id=item.source_id,
            source_product_uri=item.source_product_uri,
            source_product_sha256=item.source_product_sha256,
        )
        for item in selected
    ]
    bank = build_observation_prediction_bank(
        catalogue,
        epochs,
        reference_ns,
        observations,
        maximum_epoch_s=0.0,
        visibility_over_complete_interval=False,
    )
    null_residual, null_offsets, _ = _timing_residual(
        observations, bank, None, include_global_timing_rate=False
    )
    null_rate_residual, null_rate_offsets, null_rate = _timing_residual(
        observations, bank, None, include_global_timing_rate=True
    )

    def rank(include_rate: bool, range_sign: float = -1.0) -> list[dict[str, Any]]:
        result = []
        for index, metadata in enumerate(bank["metadata"]):
            residual, offsets, timing_rate = _timing_residual(
                observations,
                bank,
                index,
                include_global_timing_rate=include_rate,
                range_sign=range_sign,
            )
            result.append(
                {
                    **metadata,
                    "rms_samples": float(np.sqrt(np.mean(np.square(residual)))),
                    "per_sweep_offsets_samples": offsets,
                    "global_timing_rate_samples_s": timing_rate,
                }
            )
        return sorted(result, key=lambda item: (item["rms_samples"], item["catalog_number"]))

    fixed = rank(False)
    with_rate = rank(True)
    reversed_sign = rank(False, range_sign=1.0)

    def candidate_result(rows: list[dict[str, Any]], catalog_number: int) -> dict[str, Any]:
        index, row = next(
            (index, row)
            for index, row in enumerate(rows)
            if row["catalog_number"] == catalog_number
        )
        return {
            "rank": index + 1,
            "candidate_count": len(rows),
            "object_name": row["object_name"],
            "catalog_number": row["catalog_number"],
            "rms_samples": row["rms_samples"],
            "global_timing_rate_samples_s": row["global_timing_rate_samples_s"],
        }

    public = {
        "analysis": "D2-scanner-absolute-frame-lattice-timing-falsifier",
        "observable": (
            "(FPGA first_sample_sequence + probe_start_ms*2500 + source_epoch_sample) "
            "modulo 10000/3 samples"
        ),
        "selection": "all scanner RX1 segments with at least 20 supported pilot frames",
        "observation_count": len(observations),
        "candidate_screen": (
            "Starlink TLEs at or above 10 degrees at every selected observation epoch"
        ),
        "per_sweep_constant_null": {
            "rms_samples": float(np.sqrt(np.mean(np.square(null_residual)))),
            "per_sweep_offsets_samples": null_offsets,
        },
        "fixed_range_delay_model": {
            "equation": "phase = -range/c * 2,500,000 samples/s + free sweep offset",
            "best": {
                "object_name": fixed[0]["object_name"],
                "catalog_number": fixed[0]["catalog_number"],
                "rms_samples": fixed[0]["rms_samples"],
            },
            "candidate_57902": candidate_result(fixed, 57902),
        },
        "global_timing_rate_sensitivity": {
            "null_rms_samples": float(np.sqrt(np.mean(np.square(null_rate_residual)))),
            "null_global_timing_rate_samples_s": null_rate,
            "null_per_sweep_offsets_samples": null_rate_offsets,
            "best": {
                "object_name": with_rate[0]["object_name"],
                "catalog_number": with_rate[0]["catalog_number"],
                "rms_samples": with_rate[0]["rms_samples"],
            },
            "candidate_57902": candidate_result(with_rate, 57902),
        },
        "reversed_range_sign_sensitivity": {
            "best": {
                "object_name": reversed_sign[0]["object_name"],
                "catalog_number": reversed_sign[0]["catalog_number"],
                "rms_samples": reversed_sign[0]["rms_samples"],
            },
            "candidate_57902": candidate_result(reversed_sign, 57902),
        },
        "interpretation": (
            "This in-sample test is only a falsifier because RF-target resets and mixed "
            "emitters invalidate one global code-phase track. It does not independently "
            "support candidate 57902."
        ),
    }
    return public, {"bank": bank, "fixed": fixed, "with_rate": with_rate}


def analyze_d2_scanner_extension(
    inputs: DwellInputs,
    catalogue,
    epochs: tuple[int, ...],
    *,
    run_wrong_time: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dwell_rows = d2_late_rate_observations(inputs)
    scanner_rows, scanner_provenance = load_scanner_rate_observations(inputs)
    continuations = select_cfo_continuations(dwell_rows, scanner_rows)
    cfo_observations = make_d2_cfo_observations(dwell_rows, continuations)
    cfo_public, cfo_internal = analyze_cfo_continuity_hypothesis(
        cfo_observations, inputs.reference_utc_ns, catalogue, epochs
    )

    ch4_scanner = [item for item in scanner_rows if round(item.rf_hz) == D2_SCANNER_RF_HZ]
    ch4_rate_observations = dwell_rows + ch4_scanner
    ch4_public, ch4_internal = analyze_rate_series(
        "D2-CH4-lower-reset-safe-local-rate",
        ch4_rate_observations,
        inputs.reference_utc_ns,
        catalogue,
        epochs,
        run_wrong_time=run_wrong_time,
    )

    clusters_by_scan = {
        acquisition: phase_cluster_partition(
            [item for item in scanner_rows if item.acquisition == acquisition]
        )
        for acquisition in sorted({item.acquisition for item in scanner_rows})
    }
    phase_cluster_rows = [
        item
        for acquisition in ("scan01", "scan02", "scan03")
        for item in clusters_by_scan[acquisition][0]
    ]
    for item in phase_cluster_rows:
        item.train = item.acquisition in {"scan01", "scan02"}
    phase_public, phase_internal = analyze_rate_series(
        "D2-scanner-phase-clustered-multi-edge-local-rate",
        phase_cluster_rows,
        inputs.reference_utc_ns,
        catalogue,
        epochs,
        run_wrong_time=run_wrong_time,
    )
    timing_public, timing_internal = analyze_scanner_lattice_timing_falsifier(
        scanner_rows, inputs.reference_utc_ns, catalogue, epochs
    )

    continuation_public = {}
    for receiver_id, rows in continuations.items():
        continuation_public[f"RX{receiver_id}"] = [
            {
                "acquisition": row["observation"].acquisition,
                "source_id": row["observation"].source_id,
                "relative_time_s": row["observation"].time_s,
                "cfo_hz": row["observation"].cfo_hz,
                "local_rate_hz_s": row["observation"].value_hz_s,
                "predicted_cfo_hz": row["predicted_cfo_hz"],
                "innovation_hz": row["innovation_hz"],
                "accepted": row["accepted"],
            }
            for row in rows
        ]

    cluster_public = {}
    for acquisition, clusters in clusters_by_scan.items():
        cluster_public[acquisition] = [
            {
                "cluster_rank": index + 1,
                "observation_count": len(cluster),
                "phase_span_samples": circular_phase_span_samples(
                    [float(item.absolute_lattice_phase_sample) for item in cluster]
                ),
                "members": [
                    {
                        "source_id": item.source_id,
                        "receiver_id": item.receiver_id,
                        "rf_hz": int(round(item.rf_hz)),
                        "absolute_lattice_phase_sample": item.absolute_lattice_phase_sample,
                        "local_rate_hz_s": item.value_hz_s,
                        "local_rate_sigma_hz_s": item.sigma_hz_s,
                    }
                    for item in cluster
                ],
            }
            for index, cluster in enumerate(clusters)
        ]

    return (
        {
            "analysis_kind": "D2_dwell_scanner_TLE_association_sensitivity",
            "dwell": "D2",
            "session_id": inputs.session_id,
            "run_id": inputs.run_id,
            "reference_utc_ns": inputs.reference_utc_ns,
            "selection": {
                "late_dwell_trajectory_id": D2_LATE_TRAJECTORY_ID,
                "scanner_ids": list(SCANNER_IDS),
                "scanner_target_rf_hz": D2_SCANNER_RF_HZ,
                "cfo_continuation_gate_hz": SCANNER_CFO_CONTINUATION_GATE_HZ,
                "cfo_continuation_rule": (
                    "same RF and RX, then nearest local CFO to the preceding accepted "
                    "CFO advanced by its TLE-blind local rate"
                ),
                "cfo_continuations": continuation_public,
                "phase_cluster_period_samples": FRAME_LATTICE_PHASE_PERIOD_THIRDS / 3.0,
                "phase_cluster_maximum_span_samples": SCANNER_PHASE_CLUSTER_GATE_SAMPLES,
                "phase_clusters": cluster_public,
                "primary_phase_rate_test_uses_scans": ["scan01", "scan02", "scan03"],
                "scan04_handling": (
                    "kept in CH4 local-rate sensitivity, excluded from the pooled primary "
                    "cluster because its lattice phases split into multiple groups"
                ),
            },
            "scanner_provenance": scanner_provenance,
            "cfo_continuity_hypothesis": cfo_public,
            "reset_safe_ch4_local_rate": ch4_public,
            "phase_clustered_multi_edge_local_rate": phase_public,
            "absolute_lattice_timing_falsifier": timing_public,
            "interpretation_rules": [
                "The local-rate tests do not bridge CFO intercepts across retunes.",
                "Each 50-75 ms local fit has already marginalized its own carrier intercept.",
                "The CFO curve is stronger only if LO/transmitter CFO level survives resets.",
                "The frame-lattice phase test is a negative falsifier, not a satellite ID test.",
                "No result supplies beam/channel assignment or measures radio range.",
            ],
        },
        {
            "cfo": cfo_internal,
            "ch4_rate": ch4_internal,
            "phase_rate": phase_internal,
            "timing": timing_internal,
            "scanner_rows": scanner_rows,
            "clusters_by_scan": clusters_by_scan,
        },
    )


def _candidate_index(bank: dict[str, Any], catalog_number: int) -> int:
    return next(
        index
        for index, metadata in enumerate(bank["metadata"])
        if metadata["catalog_number"] == catalog_number
    )


def plot_d2_cfo_hypothesis(
    path: Path,
    public: dict[str, Any],
    internal: dict[str, Any],
) -> None:
    observations: list[CfoObservation] = internal["observations"]
    bank = internal["bank"]
    model = public["models"]["plus_minus_2s"]["candidate_57902"]
    index = _candidate_index(bank, 57902)
    training_times = np.asarray([item.time_s for item in observations if item.train])
    center = float(np.mean(training_times))
    low = min(item.time_s for item in observations) - 1.0
    high = max(item.time_s for item in observations) + 1.0
    grid = np.linspace(low, high, 1_000)
    rf_hz = int(round(observations[0].rf_hz))
    candidate = (
        np.interp(
            grid + model["epoch_adjustment_s"],
            bank["time_s"],
            bank["cfo_by_rf"][rf_hz][index],
        )
        + model["global_cfo_intercept_hz"]
        + model["global_cfo_drift_hz_s"] * (grid - center)
    )
    null = public["ordinary_least_squares_affine_cfo_null"]
    null_curve = null["global_intercept_hz"] + null["global_drift_hz_s"] * (grid - center)
    fig, axis = plt.subplots(figsize=(12, 6.5))
    for training, marker, label in (
        (True, "o", "training: dwell + scans 1-2"),
        (False, "s", "held out: scans 3-4"),
    ):
        rows = [item for item in observations if item.train is training]
        axis.scatter(
            [item.time_s for item in rows],
            [item.value_hz for item in rows],
            marker=marker,
            s=42,
            label=label,
            zorder=4,
        )
    axis.plot(grid, candidate, label="57902 / STARLINK-30462 + global CFO nuisance", lw=2.2)
    axis.plot(grid, null_curve, label="global affine CFO null", lw=1.8, ls="--")
    for item in observations:
        if item.acquisition.startswith("scan"):
            axis.axvline(item.time_s, color="#999999", lw=0.6, alpha=0.25)
    axis.set_xlabel("seconds from D2 continuity reference")
    axis.set_ylabel("local CFO (Hz)")
    axis.set_title("D2 CH4-lower dwell→scanner CFO: strong curve only under reset continuity")
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_d2_rate_tests(
    path: Path,
    public: dict[str, Any],
    internal: dict[str, Any],
) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=False)
    cases = (
        (
            axes[0],
            public["reset_safe_ch4_local_rate"],
            internal["ch4_rate"],
            "A · CH4 lower: 16 dwell windows + both RX scanner visits",
        ),
        (
            axes[1],
            public["phase_clustered_multi_edge_local_rate"],
            internal["phase_rate"],
            "B · Scanner multi-edge rates selected only by frame-lattice phase",
        ),
    )
    for axis, case_public, case_internal, title in cases:
        observations: list[RateObservation] = case_internal["observations"]
        bank = case_internal["bank"]
        model = case_public["models"]["plus_minus_2s"]["candidate_57902"]
        index = _candidate_index(bank, 57902)
        for path_name, color in (
            ("radio_pluto_5d4d/RX0", "#2ca02c"),
            ("radio_pluto_5d4d/RX1", "#1f77b4"),
        ):
            rows = [item for item in observations if item.path == path_name]
            if not rows:
                continue
            for training, marker in ((True, "o"), (False, "s")):
                selected = [item for item in rows if item.train is training]
                if not selected:
                    continue
                axis.errorbar(
                    [item.time_s for item in selected],
                    [item.value_hz_s for item in selected],
                    yerr=[item.sigma_hz_s for item in selected],
                    fmt=marker,
                    color=color,
                    alpha=0.72,
                    label=(f"{path_name.split('/')[-1]} {'train' if training else 'held out'}"),
                )
            prediction = np.asarray(
                [
                    np.interp(
                        item.time_s + model["epoch_adjustment_s"],
                        bank["time_s"],
                        bank["rate_by_rf"][int(round(item.rf_hz))][index],
                    )
                    + model["path_rate_nuisance_hz_s"][path_name]
                    for item in rows
                ]
            )
            order = np.argsort([item.time_s for item in rows])
            axis.plot(
                np.asarray([item.time_s for item in rows])[order],
                prediction[order],
                color=color,
                lw=1.6,
                ls="--",
                label=f"57902 model for {path_name.split('/')[-1]}",
            )
        axis.set_title(title)
        axis.set_ylabel("local Doppler rate (Hz/s)")
        axis.grid(alpha=0.25)
        axis.legend(ncol=2, fontsize=8)
    axes[-1].set_xlabel("seconds from D2 continuity reference")
    fig.suptitle(
        "Reset-safe tests: every acquisition contributes slope, never CFO level", weight="bold"
    )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_d2_scanner_phase_falsifier(
    path: Path,
    public: dict[str, Any],
    internal: dict[str, Any],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True, sharey=True)
    scanner_rows: list[RateObservation] = internal["scanner_rows"]
    clusters = internal["clusters_by_scan"]
    for axis, acquisition in zip(axes.flat, ("scan01", "scan02", "scan03", "scan04"), strict=True):
        rows = [item for item in scanner_rows if item.acquisition == acquisition]
        primary_ids = {item.source_id for item in clusters[acquisition][0]}
        for receiver_id, marker in ((0, "s"), (1, "o")):
            selected = [item for item in rows if item.receiver_id == receiver_id]
            axis.scatter(
                [item.rf_hz / 1e9 for item in selected],
                [item.absolute_lattice_phase_sample for item in selected],
                marker=marker,
                color="#b8b8b8",
                label=f"RX{receiver_id}",
            )
        primary = [item for item in rows if item.source_id in primary_ids]
        axis.scatter(
            [item.rf_hz / 1e9 for item in primary],
            [item.absolute_lattice_phase_sample for item in primary],
            facecolors="none",
            edgecolors="#d62728",
            s=95,
            linewidths=1.5,
            label="largest ≤50-sample cluster",
        )
        axis.set_title(acquisition)
        axis.grid(alpha=0.25)
    axes[0, 0].set_ylabel("absolute lattice phase (samples)")
    axes[1, 0].set_ylabel("absolute lattice phase (samples)")
    axes[1, 0].set_xlabel("RF (GHz)")
    axes[1, 1].set_xlabel("RF (GHz)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.945),
        ncol=3,
    )
    timing = public["absolute_lattice_timing_falsifier"]
    fig.suptitle(
        "TLE-blind scanner phase clusters; range-delay test: "
        f"null {timing['per_sweep_constant_null']['rms_samples']:.1f} vs "
        f"57902 {timing['fixed_range_delay_model']['candidate_57902']['rms_samples']:.1f} samples",
        weight="bold",
        y=0.985,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def masks_and_vectors(
    segments: list[Segment],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    times = np.concatenate([item.time_s for item in segments])
    values = np.concatenate([item.cfo_hz for item in segments])
    train = np.concatenate([item.train for item in segments])
    sigma = np.concatenate([np.full(item.time_s.size, item.sigma_hz) for item in segments])
    return times, values, train, sigma


def fit_piecewise_path_nuisance(
    segments: list[Segment],
    raw_target: list[np.ndarray],
    maximum_drift_hz_s: float,
) -> tuple[list[np.ndarray], dict[str, float], list[float]]:
    base_weights = [np.full(item.time_s.size, 1.0 / item.sigma_hz**2) for item in segments]
    effective = [item.copy() for item in base_weights]
    slopes: dict[str, float] = {}
    intercepts = [0.0] * len(segments)
    residual = [np.zeros(item.time_s.size) for item in segments]
    for _ in range(12):
        for path in sorted({item.path for item in segments}):
            numerator = 0.0
            denominator = 0.0
            for segment, target, weight in zip(segments, raw_target, effective, strict=True):
                if segment.path != path:
                    continue
                selected = segment.train
                mean_t = float(np.average(segment.time_s[selected], weights=weight[selected]))
                mean_y = float(np.average(target[selected], weights=weight[selected]))
                centered_t = segment.time_s[selected] - mean_t
                centered_y = target[selected] - mean_y
                numerator += float(np.sum(weight[selected] * centered_t * centered_y))
                denominator += float(np.sum(weight[selected] * centered_t**2))
            slope = 0.0 if denominator == 0.0 else numerator / denominator
            slopes[path] = float(np.clip(slope, -maximum_drift_hz_s, maximum_drift_hz_s))
        for index, (segment, target, weight) in enumerate(
            zip(segments, raw_target, effective, strict=True)
        ):
            centered = segment.time_s - float(np.mean(segment.time_s[segment.train]))
            slope = slopes[segment.path]
            intercepts[index] = float(
                np.average(
                    target[segment.train] - slope * centered[segment.train],
                    weights=weight[segment.train],
                )
            )
            residual[index] = target - intercepts[index] - slope * centered
        changed = 0.0
        for index, (segment, row) in enumerate(zip(segments, residual, strict=True)):
            scale = max(segment.sigma_hz, 1.0)
            normalized = np.abs(row) / (HUBER_K * scale)
            huber = np.ones(row.size)
            tail = normalized > 1.0
            huber[tail] = 1.0 / normalized[tail]
            updated = base_weights[index] * huber
            changed = max(changed, float(np.max(np.abs(updated - effective[index]))))
            effective[index] = updated
        if changed < 1e-15:
            break
    return residual, slopes, intercepts


def metrics(segments: list[Segment], residual: list[np.ndarray]) -> dict[str, float]:
    values = np.concatenate(residual)
    train = np.concatenate([item.train for item in segments])
    sigma = np.concatenate([np.full(item.time_s.size, item.sigma_hz) for item in segments])

    def rms(value: np.ndarray) -> float:
        return float(np.sqrt(np.mean(value**2)))

    return {
        "train_rms_hz": rms(values[train]),
        "holdout_rms_hz": rms(values[~train]),
        "full_rms_hz": rms(values),
        "train_standardized_rms": rms(values[train] / sigma[train]),
        "holdout_standardized_rms": rms(values[~train] / sigma[~train]),
        "full_standardized_rms": rms(values / sigma),
    }


def affine_null(segments: list[Segment]) -> dict[str, Any]:
    residual = []
    slopes = []
    for segment in segments:
        centered = segment.time_s - float(np.mean(segment.time_s[segment.train]))
        design = np.column_stack((np.ones(segment.time_s.size), centered))
        coeff = np.linalg.lstsq(design[segment.train], segment.cfo_hz[segment.train], rcond=None)[0]
        residual.append(segment.cfo_hz - design @ coeff)
        slopes.append(float(coeff[1]))
    return {**metrics(segments, residual), "segment_slopes_hz_s": slopes}


def evaluate_candidate(
    segments: list[Segment],
    bank: dict[str, Any],
    candidate_index: int,
    *,
    nuisance_bound_hz_s: float,
    sign: float = 1.0,
) -> dict[str, Any]:
    choices = []
    for epoch_shift in EPOCH_SHIFTS_S:
        predicted = [
            sign
            * np.interp(
                segment.time_s + epoch_shift,
                bank["time_s"],
                bank["curves_by_path"][segment.path][candidate_index],
            )
            for segment in segments
        ]
        target = [
            segment.cfo_hz - model for segment, model in zip(segments, predicted, strict=True)
        ]
        residual, slopes, intercepts = fit_piecewise_path_nuisance(
            segments, target, nuisance_bound_hz_s
        )
        choices.append(
            {
                "epoch_adjustment_s": float(epoch_shift),
                "path_nuisance_rate_hz_s": slopes,
                "segment_offsets_hz": intercepts,
                **metrics(segments, residual),
            }
        )
    return min(
        choices,
        key=lambda item: (
            item["train_standardized_rms"],
            abs(item["epoch_adjustment_s"]),
            item["epoch_adjustment_s"],
        ),
    )


def rank_bank(
    segments: list[Segment],
    bank: dict[str, Any],
    *,
    nuisance_bound_hz_s: float,
    sign: float = 1.0,
    high_elevation_only: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for index, metadata in enumerate(bank["metadata"]):
        if high_elevation_only and metadata["minimum_elevation_deg"] < HIGH_ELEVATION_DEG:
            continue
        fit = evaluate_candidate(
            segments,
            bank,
            index,
            nuisance_bound_hz_s=nuisance_bound_hz_s,
            sign=sign,
        )
        rows.append({**metadata, **fit})
    return sorted(
        rows,
        key=lambda item: (item["train_standardized_rms"], item["catalog_number"]),
    )


def segment_public(segment: Segment) -> dict[str, Any]:
    coeff = np.polyfit(segment.time_s[segment.train], segment.cfo_hz[segment.train], 1)
    return {
        "path": segment.path,
        "radio_id": segment.radio_id,
        "receiver_id": segment.receiver_id,
        "trajectory_id": segment.trajectory_id,
        "rf_hz": int(segment.rf_hz),
        "first_utc_ns": segment.first_utc_ns,
        "timing_half_width_s": segment.timing_half_width_s,
        "source_observation_count": int(segment.source_times_s.size),
        "resampled_observation_count": int(segment.time_s.size),
        "start_s": float(segment.time_s.min()),
        "end_s": float(segment.time_s.max()),
        "training_count": int(segment.train.sum()),
        "holdout_count": int((~segment.train).sum()),
        "radio_training_rate_hz_s": float(coeff[0]),
        "sigma_hz": segment.sigma_hz,
        "source_product_digests": segment.source_product_digests,
        "source_product_uris": segment.source_product_uris,
    }


def candidate_public(row: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "object_name",
        "catalog_number",
        "element_epoch_utc_ns",
        "element_age_s",
        "minimum_visibility_fraction",
        "minimum_elevation_deg",
        "peak_elevation_deg",
        "midpoint_elevation_deg",
        "midpoint_range_km",
        "midpoint_range_rate_km_s",
        "epoch_adjustment_s",
        "path_nuisance_rate_hz_s",
        "train_rms_hz",
        "holdout_rms_hz",
        "full_rms_hz",
        "train_standardized_rms",
        "holdout_standardized_rms",
        "full_standardized_rms",
    )
    return {key: row[key] for key in keep}


def analyze_group(
    name: str,
    definition: dict[str, Any],
    inputs: DwellInputs,
    catalogue,
    epochs: tuple[int, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    segments = [
        make_segment(inputs, path, trajectory_id)
        for path, ids in definition["members"].items()
        for trajectory_id in ids
    ]
    bank = build_prediction_bank(catalogue, epochs, inputs, segments)
    null = affine_null(segments)
    models = {}
    internals = {}
    for bound in NUISANCE_BOUNDS_HZ_S:
        ranked = rank_bank(segments, bank, nuisance_bound_hz_s=bound)
        key = "free" if bound >= 1_000_000 else f"bounded_{int(bound)}"
        models[key] = {
            "candidate_count": len(ranked),
            "best": candidate_public(ranked[0]),
            "runner": candidate_public(ranked[1]),
            "runner_train_standardized_margin": float(
                ranked[1]["train_standardized_rms"] - ranked[0]["train_standardized_rms"]
            ),
            "holdout_advantage_over_affine_null_hz": float(
                null["holdout_rms_hz"] - ranked[0]["holdout_rms_hz"]
            ),
        }
        internals[key] = ranked
    reversed_ranked = rank_bank(segments, bank, nuisance_bound_hz_s=200.0, sign=-1.0)
    high_ranked = rank_bank(
        segments,
        bank,
        nuisance_bound_hz_s=200.0,
        high_elevation_only=True,
    )
    primary_id = models["bounded_200"]["best"]["catalog_number"]
    previous_record_stable = exact_record_stable(primary_id)
    wrong_time = []
    if definition["wrong_time"]:
        true_advantage = models["bounded_200"]["holdout_advantage_over_affine_null_hz"]
        for shift in WRONG_TIME_SHIFTS_S:
            shifted_bank = build_prediction_bank(
                catalogue, epochs, inputs, segments, sky_shift_s=shift
            )
            ranked = rank_bank(segments, shifted_bank, nuisance_bound_hz_s=200.0)
            wrong_time.append(
                {
                    "shift_s": shift,
                    "candidate_count": len(ranked),
                    "best_catalog_number": ranked[0]["catalog_number"],
                    "best_object_name": ranked[0]["object_name"],
                    "train_standardized_rms": ranked[0]["train_standardized_rms"],
                    "holdout_rms_hz": ranked[0]["holdout_rms_hz"],
                    "holdout_advantage_over_affine_null_hz": float(
                        null["holdout_rms_hz"] - ranked[0]["holdout_rms_hz"]
                    ),
                }
            )
        empirical_p = float(
            (
                1
                + sum(
                    item["holdout_advantage_over_affine_null_hz"] >= true_advantage
                    for item in wrong_time
                )
            )
            / (1 + len(wrong_time))
        )
    else:
        empirical_p = None
    public = {
        "group": name,
        "dwell": definition["dwell"],
        "session_id": inputs.session_id,
        "run_id": inputs.run_id,
        "radio_only_grouping_is_post_hoc": True,
        "cross_radio": definition["cross_radio"],
        "reference_utc_ns": inputs.reference_utc_ns,
        "segments": [segment_public(item) for item in segments],
        "path_count": len({item.path for item in segments}),
        "radio_count": len({item.radio_id for item in segments}),
        "rf_hz_by_path": {item.path: int(item.rf_hz) for item in segments},
        "affine_null": null,
        "candidate_screen": {
            "horizon_deg": HORIZON_DEG,
            "minimum_visibility_fraction_per_segment": 0.95,
            "coarse_candidate_count": bank["coarse_candidate_count"],
            "candidate_count": bank["candidate_count"],
            "derivative_audit": bank["derivative_audit"],
        },
        "models": models,
        "fixed_sign_falsifier": {
            "reversed_sign_best": candidate_public(reversed_ranked[0]),
            "reversed_sign_holdout_advantage_over_affine_null_hz": float(
                null["holdout_rms_hz"] - reversed_ranked[0]["holdout_rms_hz"]
            ),
        },
        "high_elevation_sensitivity": {
            "candidate_count": len(high_ranked),
            "best": None if not high_ranked else candidate_public(high_ranked[0]),
        },
        "primary_candidate_record_matches_previous_causal_snapshot": previous_record_stable,
        "wrong_time_controls": wrong_time,
        "wrong_time_holdout_advantage_empirical_p": empirical_p,
    }
    internal = {"segments": segments, "bank": bank, "ranked": internals["bounded_200"]}
    return public, internal


def plot_summary(path: Path, groups: list[dict[str, Any]]) -> None:
    labels = [item["group"] for item in groups]
    orbit = [item["models"]["bounded_200"]["best"]["holdout_rms_hz"] for item in groups]
    null = [item["affine_null"]["holdout_rms_hz"] for item in groups]
    x = np.arange(len(groups))
    fig, axis = plt.subplots(figsize=(13, 6.5))
    width = 0.38
    axis.bar(x - width / 2, orbit, width, label="joint TLE + per-chain nuisance")
    axis.bar(x + width / 2, null, width, label="per-piece affine radio null")
    axis.set_xticks(x, labels, rotation=25, ha="right")
    axis.set_ylabel("held-out RMS (Hz)")
    axis.set_title("Joint continuous-episode TLE search: untouched-tail falsification")
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--skip-wrong-time", action="store_true")
    parser.add_argument("--skip-episode-groups", action="store_true")
    parser.add_argument("--skip-d2-scanner", action="store_true")
    parser.add_argument("--skip-special-wrong-time", action="store_true")
    parser.add_argument(
        "--groups",
        nargs="*",
        choices=tuple(GROUPS),
        help="optional subset of radio-only episode groups",
    )
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    if args.skip_wrong_time:
        for definition in GROUPS.values():
            definition["wrong_time"] = False
    inputs = load_inputs()
    catalogue = parse_element_sets(TLE_PATH.read_text())
    epochs = catalogue.element_epoch_utc_ns()
    public_groups = []
    if not args.skip_episode_groups:
        selected_groups = set(args.groups) if args.groups else set(GROUPS)
        for name, definition in GROUPS.items():
            if name not in selected_groups:
                continue
            print(f"analyzing {name}", flush=True)
            public, _internal = analyze_group(
                name, definition, inputs[definition["dwell"]], catalogue, epochs
            )
            public_groups.append(public)
    d2_scanner = None
    d2_internal = None
    if not args.skip_d2_scanner:
        print("analyzing D2 dwell-to-scanner extensions", flush=True)
        d2_scanner, d2_internal = analyze_d2_scanner_extension(
            inputs["D2"],
            catalogue,
            epochs,
            run_wrong_time=not args.skip_special_wrong_time,
        )
    result = {
        "analysis_kind": "exploratory_joint_continuous_episode_tle_redesign",
        "generated_utc": datetime.now(UTC).isoformat(),
        "script_sha256": sha256_file(Path(__file__)),
        "inputs": {
            "tle_path": str(TLE_PATH),
            "tle_sha256": sha256_file(TLE_PATH),
            "previous_tle_path": str(PREVIOUS_TLE_PATH),
            "previous_tle_sha256": sha256_file(PREVIOUS_TLE_PATH),
            "observer": SITE.model_dump(mode="json"),
            "lnb_lo_hz": STARLINK_LNB_LO_HZ,
        },
        "method": {
            "observable": "dealiased CFO samples inside radio-only continuous pieces",
            "candidate_prediction": "fixed-sign fixed-per-path-RF SGP4 topocentric Doppler",
            "piecewise_state": "free intercept per reset-separated piece",
            "nuisance_state": "one bounded rate per receiver path shared across its pieces",
            "training_fraction": TRAIN_FRACTION,
            "epoch_search_s": [-0.30, 0.30, 0.05],
            "nuisance_bounds_hz_s": list(NUISANCE_BOUNDS_HZ_S),
            "resample_s": RESAMPLE_S,
            "sigma_floor_hz": SIGMA_FLOOR_HZ,
            "huber_k": HUBER_K,
            "primary_null": "independent affine training fit per piece, untouched tail",
            "wrong_time_shifts_s": list(WRONG_TIME_SHIFTS_S),
        },
        "groups": public_groups,
        "d2_scanner_extension": d2_scanner,
        "limitations": [
            "Episode groups were assembled post hoc from radio time/rate continuity.",
            "Final-bank membership is radio-selected but not TLE-selected; alias "
            "replicas are represented once.",
            "The Sausalito site is reviewed but not capture-bound GPS authority.",
            "No antenna beam or Starlink payload/channel assignment is available.",
            "Per-path drift combines transmitter, LNB, receiver, and sample-clock effects.",
            "Absolute CFO and TLE slant range are not radio range measurements.",
            "Wrong-time controls are correlated and group definitions are not preregistered.",
        ],
    }
    json_path = args.output_root / "joint-continuous-episode-tle.json"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if d2_scanner is not None:
        d2_evidence = {
            "analysis_kind": "D2_dwell_scanner_TLE_association_sensitivity",
            "generated_utc": result["generated_utc"],
            "script_sha256": result["script_sha256"],
            "reproduction_command": (
                "sudo -u leo env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "
                ".venv/bin/python tools/report_recent_three_continuity_episode_tle.py "
                "--output-root OUTPUT --skip-episode-groups"
            ),
            "software": {
                "numpy": np.__version__,
                "sgp4": version("sgp4"),
            },
            "inputs": result["inputs"],
            "model_audit": {
                "doppler_sign": "f_rx - f_tx = -f_RF * range_rate / c",
                "earth_rotation": (
                    "repository TEME-to-ECEF observer includes the rotating-frame "
                    "omega cross r velocity term; finite-difference audit is recorded"
                ),
                "absolute_cfo_identifiability": (
                    "unknown transmitter/LNB/receiver offsets prevent absolute-CFO ID"
                ),
                "reset_safe_observable": (
                    "local line slope inside each independently continuous 50-75 ms frame"
                ),
                "clock_nuisance": ("bounded additive rate per RX chain; epoch searched separately"),
                "beam_assignment_available": False,
                "site_capture_bound": False,
                "range_claimed": False,
            },
            "d2_scanner_extension": d2_scanner,
            "limitations": result["limitations"],
        }
        (args.output_root / "d2-dwell-scanner-tle-sensitivity.json").write_text(
            json.dumps(d2_evidence, indent=2, sort_keys=True) + "\n"
        )
    if public_groups:
        plot_summary(args.output_root / "joint-heldout-vs-null.png", public_groups)
    if d2_scanner is not None and d2_internal is not None:
        plot_d2_cfo_hypothesis(
            args.output_root / "d2-dwell-scanner-cfo-hypothesis.png",
            d2_scanner["cfo_continuity_hypothesis"],
            d2_internal["cfo"],
        )
        plot_d2_rate_tests(
            args.output_root / "d2-reset-safe-local-rate-tests.png",
            d2_scanner,
            d2_internal,
        )
        plot_d2_scanner_phase_falsifier(
            args.output_root / "d2-scanner-phase-clusters-and-falsifier.png",
            d2_scanner,
            d2_internal,
        )
    print(json_path)


if __name__ == "__main__":
    main()
