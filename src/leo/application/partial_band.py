"""Bounded saved-IQ replay through public capture/product ports."""

import hashlib
import time

import numpy as np

from leo.analysis.starlink.partial_band import analyze_partial_band_probe
from leo.contracts.digests import sha256_digest
from leo.contracts.partial_band import (
    PartialBandBindingV1,
    PartialBandConfigurationV1,
    PartialBandProbeV1,
    PartialBandVisitPlanV1,
    PartialBandVisitV1,
)


def binding_for_capture(capture, configuration=None):
    receipt = capture.manifest.receipt
    geometry = receipt.plan.geometry
    if (
        geometry.sample_rate_hz != 1_250_000
        or tuple(geometry.receiver_ids) != (0, 1)
        or geometry.bandwidth_hz != 1_250_000
    ):
        raise ValueError("partial-band replay requires native 1.25 MS/s dual-RX capture")
    visits = receipt.visits
    return PartialBandBindingV1(
        session_id=capture.session_id,
        input_manifest_sha256=capture.manifest_sha256,
        configuration=configuration or PartialBandConfigurationV1(),
        first_counter=receipt.terminal.first_counter,
        visits=tuple(
            PartialBandVisitPlanV1(
                visit_index=i,
                channel=v.event.target.channel,
                edge=v.event.target.edge,
                start_counter=v.event.valid_start_counter,
                sample_count=v.valid_sample_count,
                reported_lo_frequency_hz=v.event.actual_lo_frequency_hz,
            )
            for i, v in enumerate(visits)
        ),
    )


def analyze_visit(task):
    identity, cfg, first_counter, visit, ci16 = task
    if ci16.dtype != np.dtype("<i2") or ci16.shape != (visit.sample_count, 2, 2):
        raise ValueError("saved IQ shape or encoding differs from receipt")
    raw_digest = sha256_digest(np.ascontiguousarray(ci16).tobytes())
    samples = ci16[:, :, 0].astype(np.float32) + 1j * ci16[:, :, 1].astype(np.float32)
    rows = []
    for rx in (0, 1):
        for p in range(visit.probe_count):
            seed = int.from_bytes(
                hashlib.sha256(
                    f"{cfg.split_seed}:{identity}:{visit.visit_index}:{rx}:{p}".encode()
                ).digest()[:4],
                "little",
            )
            result = analyze_partial_band_probe(
                samples[p * 25_000 : (p + 1) * 25_000, rx],
                edge=visit.edge,
                configuration=cfg,
                split_seed=seed,
            )
            start = visit.start_counter + p * 25_000
            rows.append(
                PartialBandProbeV1(
                    visit_index=visit.visit_index,
                    receiver_id=rx,
                    channel=visit.channel,
                    edge=visit.edge,
                    probe_index=p,
                    sample_start_counter=start,
                    time_s=(start - first_counter) / 1_250_000,
                    reported_lo_frequency_hz=visit.reported_lo_frequency_hz,
                    configuration_sha256=cfg.digest,
                    training_frames=result.training_frames,
                    evaluation_frames=result.evaluation_frames,
                    control_training_score=result.control_training_score,
                    candidates=result.candidates,
                    state=(
                        "zero_energy"
                        if result.zero_energy
                        else "candidate"
                        if any(c.passed for c in result.candidates)
                        else "no_detection"
                    ),
                )
            )
    return PartialBandVisitV1(
        binding_sha256=identity,
        visit_index=visit.visit_index,
        raw_ci16_sha256=raw_digest,
        probes=tuple(rows),
    )


def replay_partial_band(
    *,
    captures,
    products,
    session_id,
    maximum_seconds=560.0,
    maximum_visits=3000,
    maximum_workers=1,
    progress=None,
):
    if not 0 < maximum_seconds <= 600 or maximum_workers != 1 or maximum_visits < 1:
        raise ValueError("invalid bounded partial-band replay budget")
    started = time.monotonic()
    capture = captures.inspect(session_id)
    binding = binding_for_capture(capture, products.configuration)
    processed = 0
    with products.writer(binding) as job:
        missing = [v for v in binding.visits if job.checkpoint(v.visit_index) is None]
        with captures.reader(session_id, expected=capture) as reader:
            for offset in range(0, min(len(missing), maximum_visits), maximum_workers):
                if time.monotonic() - started >= maximum_seconds:
                    break
                batch = missing[offset : min(offset + maximum_workers, maximum_visits)]
                tasks = []
                for visit in batch:
                    evidence, ci16 = reader.read_visit_ci16(visit.visit_index)
                    if (
                        evidence.event.valid_start_counter != visit.start_counter
                        or evidence.valid_sample_count != visit.sample_count
                        or evidence.event.target.channel != visit.channel
                        or str(evidence.event.target.edge) != visit.edge
                    ):
                        raise ValueError("capture reader changed visit identity")
                    tasks.append(
                        (binding.digest, binding.configuration, binding.first_counter, visit, ci16)
                    )
                results = map(analyze_visit, tasks)
                for result in results:
                    job.publish_checkpoint(result)
                    processed += 1
                if progress:
                    progress(
                        dict(
                            session_id=session_id,
                            processed_visits=processed,
                            total_visits=len(binding.visits),
                            elapsed_s=time.monotonic() - started,
                        )
                    )
        visits = [job.checkpoint(i) for i in range(len(binding.visits))]
        if any(v is None for v in visits):
            return dict(
                state="partial",
                processed_visits=processed,
                completed_visits=sum(v is not None for v in visits),
                total_visits=len(visits),
            )
        from leo.presentation.partial_band import render_partial_band

        artifacts = render_partial_band(binding, visits)
        manifest = job.finish(artifacts)
        return dict(
            state="figures_ready",
            processed_visits=processed,
            completed_visits=len(visits),
            probe_count=manifest.probe_count,
            candidate_probe_count=manifest.candidate_probe_count,
            binding_sha256=binding.digest,
            scientific_status="candidate_only",
            phase_and_position_status=manifest.phase_and_position_status,
        )
