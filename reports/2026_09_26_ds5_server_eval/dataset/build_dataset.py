"""Materialize the bounded DS5 server-evaluation dataset from read-only archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import zstandard

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402

SPLITS = ("dev", "validation", "holdout")
RATES = (2_500_000, 5_000_000, 7_500_000, 10_000_000)
DWELL_MS = 120
CONTROL_SEED_BASES = {
    ("pilot", "lower"): (1901, 1902),
    ("pilot", "upper"): (1903, 1904),
    ("noise", "lower"): (2901, 2902),
    ("noise", "upper"): (2903, 2904),
    ("tone", "lower"): (3901, 3902),
    ("tone", "upper"): (3903, 3904),
}


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


class Deadline:
    def __init__(self, seconds: int) -> None:
        if type(seconds) is not int or not 1 <= seconds <= 300:
            raise ValueError("deadline must be an integer from 1 through 300 seconds")
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        value = self.end - time.monotonic()
        if value <= 0:
            raise TimeoutError("dataset build exceeded its bounded deadline")
        return value

    def read_archive(self, path: Path) -> bytes:
        result = subprocess.run(
            ["sudo", "-n", "cat", str(path)],
            check=True,
            capture_output=True,
            timeout=min(30.0, self.remaining()),
        )
        return result.stdout


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def save_npy(path: Path, values: np.ndarray) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, values, allow_pickle=False)
    expected = digest_file(temporary)
    if path.exists():
        if digest_file(path) != expected:
            temporary.unlink()
            raise ValueError(f"existing generated file differs: {path}")
        temporary.unlink()
    else:
        os.replace(temporary, path)
    return {
        "path": path.relative_to(HERE).as_posix(),
        "dtype": values.dtype.str,
        "shape": list(values.shape),
        "sha256": expected,
        "bytes": path.stat().st_size,
    }


def source_sessions(dataset: dict) -> dict[str, dict]:
    included = [item for item in dataset["captures"] if item["admission_status"] == "included"]
    by_id = {item["session_id"]: item for item in included}
    if len(by_id) != 42 or sorted({item["sample_rate_hz"] for item in included}) != list(RATES):
        raise ValueError("unexpected frozen DS5 inventory")
    return by_id


def extract_real_cases(plan: dict, inventory: dict[str, dict], deadline: Deadline) -> list[dict]:
    cases: list[dict] = []
    manifest_cache: dict[str, tuple[dict, bytes]] = {}
    for selected in plan["sessions"]:
        source = inventory[selected["session_id"]]
        manifest_bytes = deadline.read_archive(Path(source["recording_manifest_path"]))
        if digest_bytes(manifest_bytes) != source["recording_manifest_file_sha256"]:
            raise ValueError(f"recording manifest hash mismatch: {selected['session_id']}")
        wrapped = json.loads(manifest_bytes)
        manifest = wrapped["manifest"]
        manifest_cache[selected["session_id"]] = (manifest, manifest_bytes)
        if (
            manifest["session_id"] != selected["session_id"]
            or source["sample_rate_hz"] != selected["rate_hz"]
            or manifest["sample_format"] != "ci16_le"
            or manifest["sample_layout"] != "sample_receiver_iq"
        ):
            raise ValueError(f"source identity mismatch: {selected['session_id']}")
        chunks = {item["first_visit_index"]: item for item in manifest["chunks"]}
        events = {item["visit_index"]: item for item in manifest["receipt"]["events"]}
        expected_indices = range(
            selected["first_visit_index"],
            selected["first_visit_index"] + selected["visit_count"],
        )
        block = [events[index] for index in expected_indices]
        if (
            selected["visit_count"] != 8
            or {item["target"]["edge"] for item in block} != {selected["edge"]}
            or {item["target"]["channel"] for item in block} != {1, 2, 3, 4}
        ):
            raise ValueError(f"selected block geometry changed: {selected['session_id']}")
        for event in block:
            visit_index = event["visit_index"]
            chunk = chunks[visit_index]
            expected_samples = selected["rate_hz"] * DWELL_MS // 1000
            if (
                chunk["visit_count"] != 1
                or chunk["sample_count"] != expected_samples
                or event["valid_end_counter_exclusive"] - event["valid_start_counter"]
                != expected_samples
            ):
                raise ValueError(
                    f"visit/source geometry mismatch: {selected['session_id']}:{visit_index}"
                )
            compressed_path = (
                Path(source["recording_manifest_path"]).parent / chunk["relative_path"]
            )
            compressed = deadline.read_archive(compressed_path)
            if (
                len(compressed) != chunk["compressed_bytes"]
                or digest_bytes(compressed) != chunk["compressed_sha256"]
            ):
                raise ValueError(f"compressed chunk mismatch: {compressed_path}")
            raw = zstandard.ZstdDecompressor().decompress(
                compressed,
                max_output_size=chunk["uncompressed_bytes"],
            )
            if (
                len(raw) != chunk["uncompressed_bytes"]
                or digest_bytes(raw) != chunk["uncompressed_sha256"]
            ):
                raise ValueError(f"uncompressed chunk mismatch: {compressed_path}")
            iq = np.frombuffer(raw, dtype="<i2").reshape(expected_samples, 2, 2)
            case_id = (
                f"real-{selected['split']}-r{selected['rate_hz']}-"
                f"{selected['session_id']}-v{visit_index:06d}"
            )
            raw_npy = save_npy(HERE / "iq" / selected["split"] / f"{case_id}.npy", iq)
            cases.append(
                {
                    "case_id": case_id,
                    "origin": "real_ds5",
                    "split": selected["split"],
                    "test_stratum": "real_unlabeled_causal_visit",
                    "rate_hz": selected["rate_hz"],
                    "dwell_ms": DWELL_MS,
                    "edge": event["target"]["edge"],
                    "channel": event["target"]["channel"],
                    "session_id": selected["session_id"],
                    "visit_index": visit_index,
                    "source_start_counter": event["valid_start_counter"],
                    "source_end_counter_exclusive": event["valid_end_counter_exclusive"],
                    "truth_status": "unknown",
                    "raw_npy": raw_npy,
                    "source": {
                        "recording_manifest_file_sha256": source["recording_manifest_file_sha256"],
                        "recording_manifest_content_sha256": source[
                            "recording_manifest_content_sha256"
                        ],
                        "relative_path": chunk["relative_path"],
                        "compressed_sha256": chunk["compressed_sha256"],
                        "uncompressed_sha256": chunk["uncompressed_sha256"],
                        "sample_start": chunk["sample_start"],
                        "sample_count": chunk["sample_count"],
                    },
                }
            )
    return cases


def control_receiver(
    kind: str, edge: str, rate: int, seed: int, receiver: int
) -> tuple[np.ndarray, dict]:
    count = rate * DWELL_MS // 1000
    rng = np.random.default_rng(seed)
    noise = 800.0 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    values = noise.copy()
    time_s = np.arange(count, dtype=np.float64) / rate
    carrier_hz = -173_123 + 137 * (seed % 7)
    if kind == "tone":
        values += 8_000 * np.exp(2j * np.pi * carrier_hz * time_s)
    truth: dict = {
        "receiver": receiver,
        "seed": seed,
        "carrier_hz": carrier_hz if kind == "tone" else None,
    }
    if kind == "pilot":
        template = qin_edge_pilot_frame(rate, edge).astype(np.complex128)
        fractional_delay = 0.35
        template = np.fft.ifft(
            np.fft.fft(template)
            * np.exp(-2j * np.pi * np.fft.fftfreq(len(template)) * fractional_delay)
        )
        window = 1 if edge == "lower" else 4
        window_length = rate // 50
        epoch = 317 + seed % 13
        cfo_hz = 312_345 - 371 * (seed % 9)
        for frame in range(15):
            start = epoch + round(frame * rate / 750)
            stop = min(start + len(template), window_length)
            if stop > start:
                positions = window * window_length + np.arange(start, stop)
                values[positions] += (
                    4_000
                    * template[: stop - start]
                    * np.exp(2j * np.pi * cfo_hz * positions / rate)
                )
        truth.update(
            window=window,
            epoch_samples=epoch,
            fractional_delay_samples=fractional_delay,
            cfo_hz=cfo_hz,
        )
    components = np.rint(np.column_stack((values.real, values.imag)))
    truth["clipped_components"] = int(
        np.count_nonzero((components < -32768) | (components > 32767))
    )
    return np.clip(components, -32768, 32767).astype("<i2"), truth


def extract_control_cases() -> list[dict]:
    cases = []
    for rate_index, rate in enumerate(RATES):
        for (kind, edge), base_seeds in CONTROL_SEED_BASES.items():
            seeds = tuple(seed + 10_000 * rate_index for seed in base_seeds)
            receivers, receiver_truth = zip(
                *(
                    control_receiver(kind, edge, rate, seed, receiver)
                    for receiver, seed in enumerate(seeds)
                ),
                strict=True,
            )
            iq = np.stack(receivers, axis=1)
            rate_part = "" if rate == RATES[0] else f"-r{rate}"
            case_id = f"control-{kind}-{edge}{rate_part}-s{seeds[0]}-{seeds[1]}"
            raw_npy = save_npy(HERE / "iq" / "controls" / f"{case_id}.npy", iq)
            cases.append(
                {
                    "case_id": case_id,
                    "origin": "synthetic_control",
                    "split": "control",
                    "test_stratum": f"synthetic_{kind}",
                    "rate_hz": rate,
                    "dwell_ms": DWELL_MS,
                    "edge": edge,
                    "channel": 1,
                    "session_id": None,
                    "visit_index": None,
                    "source_start_counter": None,
                    "source_end_counter_exclusive": None,
                    "truth_status": "constructed_control",
                    "truth": {
                        "kind": kind,
                        "starlink_model_present": kind == "pilot",
                        "expected_detector_decision": None,
                        "receivers": list(receiver_truth),
                    },
                    "raw_npy": raw_npy,
                    "source": {
                        "generator": "build_dataset.py:control_receiver/v1",
                        "seeds": list(seeds),
                    },
                }
            )
    return cases


def validate_cases(cases: list[dict], plan: dict) -> None:
    real = [case for case in cases if case["origin"] == "real_ds5"]
    controls = [case for case in cases if case["origin"] == "synthetic_control"]
    if (
        len(real) != 96
        or len(controls) != 24
        or len({case["case_id"] for case in cases}) != len(cases)
    ):
        raise ValueError("unexpected case inventory")
    sessions_by_split = {
        split: {case["session_id"] for case in real if case["split"] == split} for split in SPLITS
    }
    if any(
        sessions_by_split[a] & sessions_by_split[b]
        for a, b in (("dev", "validation"), ("dev", "holdout"), ("validation", "holdout"))
    ):
        raise ValueError("session leakage across splits")
    forbidden = set(plan["prior_probe_sessions_forbidden_in_holdout"])
    if sessions_by_split["holdout"] & forbidden:
        raise ValueError("prior probe session leaked into holdout")
    for split in SPLITS:
        selected = [case for case in real if case["split"] == split]
        if {case["rate_hz"] for case in selected} != set(RATES):
            raise ValueError(f"missing rate in {split}")
        if {case["edge"] for case in selected} != {"lower", "upper"}:
            raise ValueError(f"missing edge in {split}")


def write_cases(cases: list[dict], plan: dict, dataset_manifest_sha256: str) -> None:
    real = [case for case in cases if case["origin"] == "real_ds5"]
    complete_rate_edge = [[rate, edge] for rate in RATES for edge in ("lower", "upper")]
    coverage = {}
    for split in SPLITS:
        selected = [case for case in real if case["split"] == split]
        observed_rate_edge = sorted({(case["rate_hz"], case["edge"]) for case in selected})
        coverage[split] = {
            "real_visits": len(selected),
            "sessions": sorted({case["session_id"] for case in selected}),
            "rates_hz": sorted({case["rate_hz"] for case in selected}),
            "edges": sorted({case["edge"] for case in selected}),
            "channels": sorted({case["channel"] for case in selected}),
            "receivers": ["RX0", "RX1"],
            "observed_rate_edge_pairs": [list(value) for value in observed_rate_edge],
            "missing_rate_edge_pairs": [
                value
                for value in complete_rate_edge
                if value not in [list(item) for item in observed_rate_edge]
            ],
        }
    payload = {
        "schema": "org.leo.research.ds5-server-eval-cases.v1",
        "dataset": "DS5 server-side evaluation cuts",
        "source_dataset_manifest_sha256": dataset_manifest_sha256,
        "selection_plan_sha256": digest_file(HERE / "selection_plan.json"),
        "builder_sha256": digest_file(Path(__file__)),
        "pilot_template_source_sha256": digest_file(
            REPOSITORY / "src/leo/analysis/starlink/templates.py"
        ),
        "array_contract": {
            "loader": "numpy.load(dataset_directory / raw_npy.path, allow_pickle=False)",
            "dtype": "<i2",
            "axes": ["sample", "receiver", "component"],
            "receiver_axis": ["RX0", "RX1"],
            "component_axis": ["I", "Q"],
            "real_shape": ["rate_hz * dwell_ms // 1000", 2, 2],
        },
        "truth_contract": {
            "real_cases": (
                "unknown: a baseline positive is not ground truth and a baseline miss "
                "is not a negative"
            ),
            "synthetic_controls": (
                "constructed model truth only; not false-alarm or RF-specificity calibration"
            ),
            "detector_outcomes_included": False,
            "holdout_outcomes_included": False,
        },
        "selection_contract": {
            "session_disjoint": True,
            "visits_per_rate_per_split": 8,
            "both_receivers_grouped": True,
            "causal_blocks": "eight consecutive source visit indices from one session",
            "selection_independent_of_detector_outcomes": True,
        },
        "counts": {
            "real_cases": 96,
            "synthetic_controls": 24,
            "by_split": {
                split: sum(case["split"] == split for case in cases)
                for split in (*SPLITS, "control")
            },
        },
        "coverage_audit": {
            "by_split": coverage,
            "limitation": (
                "Every split covers both edges overall, but each rate uses one single-edge "
                "session; rate-by-edge is not fully crossed. Each block is only eight "
                "consecutive visits (0.96 seconds of valid IQ), so it cannot establish "
                "long-track continuity, rare-event rates, or p99 latency."
            ),
        },
        "cases": cases,
    }
    temporary = HERE / "cases.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    os.replace(temporary, HERE / "cases.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-seconds", type=int, default=300)
    args = parser.parse_args()
    signal.alarm(args.deadline_seconds)
    deadline = Deadline(args.deadline_seconds)
    plan = load_json(HERE / "selection_plan.json")
    dataset_path = Path(plan["source_dataset_manifest"])
    dataset_bytes = dataset_path.read_bytes()
    dataset_sha256 = digest_bytes(dataset_bytes)
    if dataset_sha256 != plan["source_dataset_manifest_sha256"]:
        raise ValueError("frozen DS5 source manifest hash mismatch")
    inventory = source_sessions(json.loads(dataset_bytes))
    cases = extract_real_cases(plan, inventory, deadline) + extract_control_cases()
    validate_cases(cases, plan)
    write_cases(cases, plan, dataset_sha256)
    total_bytes = sum(case["raw_npy"]["bytes"] for case in cases)
    print(
        json.dumps(
            {"cases": len(cases), "bytes": total_bytes, "cases_path": str(HERE / "cases.json")}
        )
    )


if __name__ == "__main__":
    main()
