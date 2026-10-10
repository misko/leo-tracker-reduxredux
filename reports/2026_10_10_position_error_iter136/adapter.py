"""Pure join of public original-window projection and device-counter support."""

from collections import Counter

import numpy as np

from leo.contracts.digests import canonical_digest

OBSERVATION_FIELDS = ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")


def observation_signature(observations):
    return canonical_digest(
        dict(
            window_ids=list(observations.window_ids),
            **{
                name: np.asarray(getattr(observations, name)).tolist()
                for name in OBSERVATION_FIELDS
            },
        )
    )


def verify_prepared(source, prepared, binding):
    """Require upstream clean physical admission; no reference-bearing documents."""
    if not source.qualified or not source.stream_generation or source.timing is None:
        raise ValueError("Qualified stream/counter authority required")
    if (
        source.timing.session_id != source.session_id
        or source.timing.sample_rate_hz != source.sample_rate_hz
    ):
        raise ValueError("Timing session/sample rate differs")
    for field in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(source, field) != binding[field]:
            raise ValueError("Public source identity differs: " + field)
    observations = prepared.observations
    count = len(observations.window_ids)
    if (
        len(prepared.candidate_ids) != count
        or len(set(prepared.candidate_ids)) != count
        or len(set(observations.window_ids)) != count
        or any(
            np.asarray(getattr(observations, name)).shape != (count,) for name in OBSERVATION_FIELDS
        )
    ):
        raise ValueError("Prepared original membership/order malformed")
    if observation_signature(observations) != binding["observation_order_signature"]:
        raise ValueError("Original observation signature differs")
    if prepared.start_utc_ns != source.timing.first_sample_estimate_utc_ns:
        raise ValueError("Prepared timestamp origin differs")
    evidence = canonical_digest(
        dict(
            capture=source.input_manifest_sha256,
            analysis=source.analysis_manifest_sha256,
            refinement="off",
            selection="highest-original-margin-rank-id-v1",
            candidate_ids=prepared.candidate_ids,
            window_ids=observations.window_ids,
            **{
                name: np.asarray(getattr(observations, name)).tolist()
                for name in OBSERVATION_FIELDS
            },
            bootstrap_tracks=prepared.bootstrap_tracks,
            trajectory_configuration=prepared.trajectory_configuration_sha256,
        )
    )
    if evidence != prepared.evidence_sha256:
        raise ValueError("Prepared window evidence differs")
    return evidence


def edge_value(edge):
    return getattr(edge, "value", edge)


def unavailable(row, reason):
    return dict(
        row,
        support_status="unavailable",
        support_reason=reason,
        support_start_ns=None,
        support_center_ns=None,
        support_end_ns=None,
        acquisition_id=None,
    )


def adapt_support(source, prepared, projected_candidates, binding):
    """No storage, IQ or model calls: caller supplies public projection values.

    Missing support never substitutes another candidate or drops an observation.
    Identity/evidence mismatch raises; unavailable acquisition authority is explicit.
    """
    evidence = verify_prepared(source, prepared, binding)
    candidates = {}
    for point in projected_candidates:
        if point.candidate_id in candidates:
            raise ValueError("Duplicate projected candidate identity")
        candidates[point.candidate_id] = point
    probes = {}
    for probe in source.probes:
        key = probe.visit_index, probe.receiver_id, probe.probe_index
        if key in probes:
            raise ValueError("Ambiguous public probe identity")
        probes[key] = probe
    observations, rows = prepared.observations, []
    for index, (candidate_id, window_id) in enumerate(
        zip(prepared.candidate_ids, observations.window_ids, strict=True)
    ):
        row = dict(
            index=index,
            window_id=window_id,
            candidate_id=candidate_id,
            receiver=int(observations.receiver[index]),
            channel=int(observations.channel[index]),
            actual_rf_hz=float(observations.rf_hz[index]),
            edge=None,
        )
        point = candidates.get(candidate_id)
        if point is None:
            rows.append(unavailable(row, "selected-candidate-not-projected"))
            continue
        for field, expected in (
            ("session_id", source.session_id),
            ("input_manifest_digest", source.input_manifest_sha256),
            ("raw_recording_authority_digest", source.raw_recording_authority_digest),
            ("radio_id", source.radio_id),
            ("stream_generation", source.stream_generation),
            ("source_group_id", window_id),
        ):
            if getattr(point, field) != expected:
                raise ValueError("Projected candidate identity differs: " + field)
        comparisons = dict(
            receiver_id=observations.receiver[index],
            channel=observations.channel[index],
            actual_rf_hz=observations.rf_hz[index],
            measured_cfo_hz=observations.measured_hz[index],
            margin=observations.margin[index],
        )
        for field, expected in comparisons.items():
            if getattr(point, field) != expected:
                raise ValueError("Original observation field differs: " + field)
        if (point.support_center_utc_ns - prepared.start_utc_ns) / 1e9 != observations.times_s[
            index
        ]:
            raise ValueError("Original observation time/order differs")
        row["edge"] = edge_value(point.edge)
        probe = probes.get((point.visit_index, point.receiver_id, point.probe_index))
        if probe is None:
            rows.append(unavailable(row, "public-probe-authority-missing"))
            continue
        if (
            probe.actual_rf_hz != point.actual_rf_hz
            or edge_value(probe.edge) != row["edge"]
            or probe.channel != point.channel
        ):
            raise ValueError("Public RF/edge/channel identity differs")
        group = canonical_digest(
            dict(
                capture=source.input_manifest_sha256,
                visit=point.visit_index,
                rx=point.receiver_id,
                probe=point.probe_index,
            )
        )
        identity = canonical_digest(
            dict(group=group, rank=point.candidate_rank, analysis=source.analysis_manifest_sha256)
        )
        if group != window_id or identity != candidate_id:
            raise ValueError("Original candidate/group identity differs")
        bounds = (
            point.source_sample_start,
            point.source_sample_end,
            probe.payload_start_sample,
            probe.valid_start_counter,
        )
        if any(value is None for value in bounds):
            rows.append(unavailable(row, "device-sample-support-missing"))
            continue
        if not all(isinstance(v, (int, np.integer)) for v in bounds):
            raise ValueError("Device/sample boundaries must be integers")
        start = (
            int(probe.valid_start_counter)
            + int(point.source_sample_start)
            - int(probe.payload_start_sample)
        )
        end = (
            int(probe.valid_start_counter)
            + int(point.source_sample_end)
            - int(probe.payload_start_sample)
        )
        if end <= start or point.source_sample_start < probe.payload_start_sample:
            raise ValueError("Invalid physical sample support")
        timing, fs = source.timing, source.sample_rate_hz
        expected_ns = [
            timing.first_sample_estimate_utc_ns
            + round((counter - timing.session_start_device_sample_counter) * 1e9 / fs)
            for counter in (start, end)
        ]
        if expected_ns != [point.support_start_utc_ns, point.support_end_utc_ns]:
            raise ValueError("Device sample/UTC support differs")
        if not expected_ns[0] <= point.support_center_utc_ns < expected_ns[1]:
            raise ValueError("Support center outside device interval")
        acquisition = canonical_digest(
            dict(
                capture=source.input_manifest_sha256,
                raw_authority=source.raw_recording_authority_digest,
                radio=source.radio_id,
                stream_generation=source.stream_generation,
                receiver=point.receiver_id,
                sample_rate_hz=fs,
                device_sample_start=start,
                device_sample_end=end,
            )
        )
        rows.append(
            dict(
                row,
                support_status="available",
                support_reason=None,
                support_start_ns=expected_ns[0],
                support_center_ns=point.support_center_utc_ns,
                support_end_ns=expected_ns[1],
                device_sample_start=start,
                device_sample_end=end,
                acquisition_id=acquisition,
                visit_index=point.visit_index,
                probe_index=point.probe_index,
            )
        )
    return dict(
        rows=rows,
        observations=len(rows),
        available=sum(row["support_status"] == "available" for row in rows),
        unavailable_reasons=dict(
            Counter(row["support_reason"] for row in rows if row["support_status"] != "available")
        ),
        observation_order_signature=binding["observation_order_signature"],
        window_evidence_sha256=evidence,
    )
