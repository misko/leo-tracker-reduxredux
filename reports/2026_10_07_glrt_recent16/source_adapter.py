"""Read-only archived-bank adapter; numerical extraction is explicitly injected."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np


def normalize_bank(probe: dict) -> tuple[list[dict], dict]:
    bank = []
    for c in probe["candidates"]:
        bank.append({"candidate_id": c["candidate_rank"], "candidate_rank": c["candidate_rank"],
            "epoch_sample": c["integer_epoch_sample"], "seed_cfo_hz": c["acquired_cfo_hz"],
            "persisted_integer_exact_score": c["integer_exact_score"],
            "persisted_integer_control_score": c["integer_control_score"],
            "persisted_integer_margin": c["integer_margin"],
            "persisted_integer_tracking_cfo_hz": c["integer_tracking_cfo_hz"],
            "persisted_integer_compatible": True,
            "published_fractional_epoch_offset_samples": c["fractional_epoch_offset_samples"]})
    unavailable = probe.get("unavailable_candidates", [])
    ranks = [c["candidate_id"] for c in bank] + [c["candidate_rank"] for c in unavailable]
    if len(ranks) != probe["candidate_count"] or len(set(ranks)) != len(ranks):
        raise ValueError("archived candidate accounting differs")
    return bank, {"saved_candidate_count": probe["candidate_count"],
                  "available_candidate_count": len(bank), "unavailable_candidates": unavailable}


class ArchivedSource:
    """Accept public reader ports, never derive another component's storage path."""

    def __init__(self, iq_store, analysis_store, binder):
        self.iq = iq_store
        self.analysis = analysis_store
        self.binder = binder

    @contextmanager
    def scan(self, frozen: dict):
        sid = frozen["session_id"]
        session = self.iq.inspect(sid)
        if session.manifest_sha256 != frozen["recording_manifest_sha256"]:
            raise ValueError("recording differs from frozen cohort")
        binding = self.binder(session.manifest.receipt,
            input_manifest_sha256=session.manifest_sha256, probe_stride_ms=120)
        if binding.sha256 != frozen["binding_sha256"]:
            raise ValueError("analysis binding differs from frozen cohort")
        with self.analysis.job(binding) as job:
            metrics = job.manifest()
            if metrics is None or len(metrics.visits) != frozen["total_visits"]:
                raise ValueError("sealed complete GLRT metrics unavailable")
            status = job.status()
            if status.metrics_manifest_sha256 != frozen["metrics_manifest_sha256"]:
                raise ValueError("GLRT metrics differ from frozen cohort")
            with self.iq.reader(sid, expected=session) as reader:
                yield session, metrics, job, reader


def ci16_window(raw, rate: int, receiver: int, start_ms: int):
    left, right = rate * start_ms // 1000, rate * (start_ms + 20) // 1000
    if (raw.ndim != 3 or raw.dtype != np.dtype("<i2") or raw.shape[1:] != (2, 2)
            or receiver not in (0, 1) or left < 0 or right > len(raw)):
        raise ValueError("raw/window geometry differs")
    return raw[left:right, receiver, 0].astype(float) + 1j * raw[left:right, receiver, 1]


def correlations64(pm, templates, samples, rate: int, edge, epoch: int, cfo: float):
    symbols = np.arange(2, 66)
    workspace = pm._conditioned_correlation_workspace(
        samples, rate, epoch, cfo, edge=templates.StarlinkEdge(edge), selected_symbols=symbols,
    )
    exact = workspace.select(symbols).values
    control = workspace.select(symbols, control=True).values
    if exact.shape != control.shape or exact.shape[1] != 64 or len(exact) < 2:
        raise ValueError("unsupported matched64-symbol candidate")
    exact.setflags(write=False)
    control.setflags(write=False)
    return exact, control


def template_energies(pm, templates, rate: int, edge):
    geometry = pm._conditioned_workspace_geometry(rate, templates.StarlinkEdge(edge))
    exact, control = np.zeros(300), np.zeros(300)
    for group in geometry.groups:
        exact[group.positions], control[group.positions] = group.exact_energy, group.control_energy
    return exact[:64], control[:64]


def preflight(source: ArchivedSource, scan: dict, pm, templates, output: Path) -> dict:
    """Four fixed visits, both RX/all archived candidates; no new acquisition."""
    output.mkdir(parents=True, exist_ok=True)
    wall_started, cpu_started = time.monotonic(), time.process_time()
    rows, arrays, timings = [], {}, {"metadata_cpu_s": 0., "raw_cpu_s": 0.,
                                    "extraction_cpu_s": 0.}
    started = time.process_time()
    with source.scan(scan) as (session, metrics, job, reader):
        timings["metadata_cpu_s"] += time.process_time() - started
        count = len(metrics.visits)
        indexes = [0, count // 3, 2 * count // 3, count - 1]
        rate, edge = scan["sample_rate_hz"], scan["edge"]
        energies = template_energies(pm, templates, rate, edge)
        arrays["exact_template_energy"], arrays["control_template_energy"] = energies
        for index in indexes:
            started = time.process_time()
            product = job.read_visit(index).model_dump(mode="json")
            timings["metadata_cpu_s"] += time.process_time() - started
            started = time.process_time()
            visit, raw = reader.read_visit_ci16(index)
            timings["raw_cpu_s"] += time.process_time() - started
            if product["input_manifest_sha256"] != session.manifest_sha256:
                raise ValueError("saved GLRT visit source differs")
            if int(product["valid_start_counter"]) != visit.event.valid_start_counter:
                raise ValueError("GLRT/raw visit counters differ")
            for probe in product["probes"]:
                if probe["probe_index"] != 0:
                    continue
                rx = probe["receiver_id"]
                bank, coverage = normalize_bank(probe)
                row = {"scan_id": scan["session_id"], "session_id": scan["session_id"],
                    "label": scan["label"],
                    "case_id": f"{scan['session_id']}:v{index:06d}:rx{rx}:p0",
                    "visit_index": index, "receiver": rx, "probe_index": 0,
                    "first_window_start_ms": 0, "later_window_start_ms": 40,
                    "sample_rate_hz": rate, "edge": edge, "candidate_bank": bank, **coverage,
                    "status": "complete" if bank else "no_available_candidates"}
                started = time.process_time()
                for wi, ms in enumerate((0, 40)):
                    samples = ci16_window(raw, rate, rx, ms)
                    for candidate in bank:
                        cid = candidate["candidate_id"]
                        exact, control = correlations64(pm, templates, samples, rate, edge,
                            candidate["epoch_sample"], candidate["seed_cfo_hz"])
                        arrays[f"v{index}_rx{rx}_w{wi}_c{cid}_exact"] = exact
                        arrays[f"v{index}_rx{rx}_w{wi}_c{cid}_control"] = control
                timings["extraction_cpu_s"] += time.process_time() - started
                rows.append(row)
    np.savez_compressed(output / "matrices.npz", **arrays)
    result = {"scan": scan, "visit_indexes": indexes, "rows": rows, "timings": timings,
              "cpu_s": time.process_time() - cpu_started,
              "wall_s": time.monotonic() - wall_started,
              "extraction_source": str(Path(pm.__file__)),
              "template_source": str(Path(templates.__file__))}
    (output / "preflight.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
