import numpy as np
from common import circular as circular_residual

GATE_HZ = 1000.0
AMBIGUITY_MARGIN_HZ = 200.0
MIN_COHERENT_POINTS = 8
MIN_COHERENT_SPAN_S = 10.0
MAX_MISSED_OBSERVED_EPOCHS = 2
COINCIDENT_EPOCH_TOLERANCE_S = 0.002
MAX_COUNTED_SUPPORT_GAP_S = 2.0
START_STOP_PENALTY = 1.25
RESIDUAL_STEP_HZ = 500.0


def _json_scalar(value):
    return value.item() if isinstance(value, np.generic) else value


def _allowed_indices(data, allowed_satellites, satellite_count):
    if allowed_satellites is None:
        return None
    values = np.asarray(allowed_satellites)
    if values.dtype == bool:
        if values.shape != (satellite_count,):
            raise ValueError("boolean allowed_satellites must match prediction columns")
        return np.flatnonzero(values)
    values = np.asarray(values, dtype=int).reshape(-1)
    if np.any((values < 0) | (values >= satellite_count)):
        raise ValueError("allowed_satellites contains an invalid prediction-column index")
    return np.unique(values)


def _prepare_anchors(data, anchors, satellite_count):
    rows = np.asarray(anchors.get("rows", []), dtype=int).reshape(-1)
    satellites = np.asarray(anchors.get("satellites", []), dtype=int).reshape(-1)
    weights = np.asarray(anchors.get("weights", []), dtype=float).reshape(-1)
    if not (len(rows) == len(satellites) == len(weights)):
        raise ValueError("anchor rows, satellites, and weights must have equal lengths")
    if np.any((rows < 0) | (rows >= len(data.times))):
        raise ValueError("anchor row is outside the data")
    if np.any((satellites < 0) | (satellites >= satellite_count)):
        raise ValueError("anchor satellite is outside the prediction columns")
    if np.any(~np.isfinite(weights)) or np.any(weights <= 0):
        raise ValueError("anchor weights must be finite and positive")
    groups = np.asarray(data.group)[rows]
    if len(np.unique(groups)) != len(groups):
        raise ValueError("anchors must allocate each observed group at most once")
    return rows, satellites, weights, groups


def _build_group_epochs(data):
    groups = np.asarray(data.group)
    times = np.asarray(data.times, dtype=float)
    receivers = np.asarray(data.receiver)
    channels = np.asarray(data.channel)
    group_rows = {}
    by_stream = {}
    for raw_group in np.unique(groups):
        group_value = _json_scalar(raw_group)
        rows = np.flatnonzero(groups == raw_group)
        group_receivers = np.unique(receivers[rows])
        group_channels = np.unique(channels[rows])
        if len(group_receivers) != 1 or len(group_channels) != 1:
            raise ValueError("a source group must belong to one receiver/channel stream")
        stream = (_json_scalar(group_receivers[0]), _json_scalar(group_channels[0]))
        representative = float(np.median(times[rows]))
        group_rows[group_value] = rows
        by_stream.setdefault(stream, []).append((representative, group_value))

    epochs_by_stream = {}
    group_epoch = {}
    group_epoch_index = {}
    for stream, records in by_stream.items():
        records.sort(key=lambda item: (item[0], repr(item[1])))
        clusters = []
        for representative, group_value in records:
            if not clusters or representative - clusters[-1][0][0] > COINCIDENT_EPOCH_TOLERANCE_S:
                clusters.append([])
            clusters[-1].append((representative, group_value))
        epochs = []
        for epoch_index, cluster in enumerate(clusters):
            epoch_time = float(np.median([item[0] for item in cluster]))
            epoch_groups = tuple(sorted((item[1] for item in cluster), key=repr))
            epochs.append((epoch_time, epoch_groups))
            for group_value in epoch_groups:
                group_epoch[group_value] = epoch_time
                group_epoch_index[group_value] = epoch_index
        epochs_by_stream[stream] = epochs
    return group_rows, group_epoch, group_epoch_index, epochs_by_stream


def _best_group_candidate(
    satellite,
    group_value,
    group_rows,
    residual,
    visible,
    competing_satellites,
):
    rows = group_rows[group_value]
    valid = visible[rows, satellite] & np.isfinite(residual[rows, satellite])
    if not np.any(valid):
        return None, False
    candidates = rows[valid]
    row = int(candidates[np.argmin(np.abs(residual[candidates, satellite]))])
    error = float(abs(residual[row, satellite]))
    if error > GATE_HZ:
        return None, False
    competitors = competing_satellites[competing_satellites != satellite]
    if len(competitors):
        competitor_values = np.abs(residual[rows[:, None], competitors[None, :]])
        competitor_visible = visible[rows[:, None], competitors[None, :]]
        competitor_error = float(np.min(np.where(competitor_visible, competitor_values, np.inf)))
    else:
        competitor_error = np.inf
    margin = competitor_error - error
    ambiguous = abs(margin) < AMBIGUITY_MARGIN_HZ
    if ambiguous:
        return None, True
    if margin < 0:
        return None, False
    confidence = max(0.0, 1.0 - (error / GATE_HZ) ** 2)
    confidence *= min(1.0, max(0.0, margin / GATE_HZ))
    return {
        "row": row,
        "group": group_value,
        "residual_hz": float(residual[row, satellite]),
        "confidence": float(confidence),
    }, False


def _viterbi_path(epochs, candidates, forced):
    count = len(epochs)
    if not count:
        return []
    off_score = np.full(count, -np.inf)
    on_score = np.full(count, -np.inf)
    off_parent = np.zeros(count, dtype=np.int8)
    on_parent = np.zeros(count, dtype=np.int8)
    off_score[0] = 0.0 if 0 not in forced else -np.inf
    if candidates[0] is not None:
        on_score[0] = candidates[0]["confidence"]
    for index in range(1, count):
        if index not in forced:
            from_off = off_score[index - 1]
            from_on = on_score[index - 1] - START_STOP_PENALTY
            off_parent[index] = int(from_on > from_off)
            off_score[index] = max(from_off, from_on)
        candidate = candidates[index]
        if candidate is None:
            continue
        from_off = off_score[index - 1] - START_STOP_PENALTY
        from_on = on_score[index - 1]
        previous = candidates[index - 1]
        if previous is not None and np.isfinite(from_on):
            change = abs(candidate["residual_hz"] - previous["residual_hz"])
            from_on -= min(1.0, (change / RESIDUAL_STEP_HZ) ** 2)
        on_parent[index] = int(from_on >= from_off)
        on_score[index] = max(from_off, from_on) + candidate["confidence"]
    state = 1 if on_score[-1] >= off_score[-1] else 0
    selected = []
    for index in range(count - 1, -1, -1):
        if state and candidates[index] is not None:
            selected.append(index)
        if index:
            state = int(on_parent[index]) if state else int(off_parent[index])
    selected.reverse()
    return selected


def _coherent_sections(items):
    if not items:
        return []
    sections = []
    start = 0
    for index in range(1, len(items)):
        if items[index]["epoch_index"] - items[index - 1]["epoch_index"] > (
            MAX_MISSED_OBSERVED_EPOCHS + 1
        ):
            sections.append(items[start:index])
            start = index
    sections.append(items[start:])
    return sections


def _qualifies(section):
    if len({item["group"] for item in section}) < MIN_COHERENT_POINTS:
        return False
    return _supported_duration(section) >= MIN_COHERENT_SPAN_S


def _supported_duration(section):
    times = np.unique(np.asarray([item["time_s"] for item in section], dtype=float))
    if len(times) < 2:
        return 0.0
    return float(np.sum(np.minimum(np.diff(times), MAX_COUNTED_SUPPORT_GAP_S)))


def _segment_summary(section, satellite, data, segment_index):
    extension = [item for item in section if not item["anchor"]]
    anchor = [item for item in section if item["anchor"]]
    residuals = np.asarray([item["residual_hz"] for item in section], dtype=float)
    finite_residuals = residuals[np.isfinite(residuals)]
    numbers = np.asarray(data.numbers)
    return {
        "segment_index": int(segment_index),
        "satellite_index": int(satellite),
        "catalog_number": int(numbers[satellite]),
        "receiver": _json_scalar(section[0]["receiver"]),
        "channel": _json_scalar(section[0]["channel"]),
        "start_s": float(section[0]["time_s"]),
        "end_s": float(section[-1]["time_s"]),
        "span_s": float(section[-1]["time_s"] - section[0]["time_s"]),
        "supported_duration_s": _supported_duration(section),
        "points": int(len({item["group"] for item in section})),
        "anchor_points": int(len(anchor)),
        "extension_points": int(len(extension)),
        "rms_residual_hz": (
            float(np.sqrt(np.mean(np.square(finite_residuals)))) if len(finite_residuals) else None
        ),
        "rows": [int(item["row"]) for item in section],
    }


def associate(data, parameters, anchors, allowed_satellites=None):
    """Extend fixed anchor allocations with conservative coherent group matches."""
    prediction, visible = data.predict(parameters)
    prediction = np.asarray(prediction, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    if prediction.ndim != 2 or prediction.shape != visible.shape:
        raise ValueError("data.predict must return equally shaped two-dimensional arrays")
    if prediction.shape[0] != len(data.times):
        raise ValueError("prediction rows must match the raw candidate rows")
    satellite_count = prediction.shape[1]
    anchor_rows, anchor_satellites, anchor_weights, anchor_groups = _prepare_anchors(
        data, anchors, satellite_count
    )
    allowed = _allowed_indices(data, allowed_satellites, satellite_count)
    anchored_identities = np.unique(anchor_satellites)
    satellites = anchored_identities if allowed is None else allowed
    measured = np.asarray(data.measured, dtype=float)
    residual = circular_residual(measured[:, None], prediction)
    residual = np.where(visible, residual, np.inf)
    groups = np.asarray(data.group)
    group_rows, group_epoch, group_epoch_index, epochs_by_stream = _build_group_epochs(data)
    reserved = {_json_scalar(group): index for index, group in enumerate(anchor_groups)}

    proposals = []
    ambiguous_groups = set()
    stream_count = 0
    for satellite in satellites:
        ordered_streams = sorted(epochs_by_stream.items(), key=lambda item: repr(item[0]))
        for (receiver, channel), epochs in ordered_streams:
            stream_count += 1
            candidates = []
            forced = set()
            for epoch_index, (_time_s, epoch_groups) in enumerate(epochs):
                anchor_indices = [
                    reserved[group_value]
                    for group_value in epoch_groups
                    if group_value in reserved
                    and anchor_satellites[reserved[group_value]] == satellite
                ]
                if anchor_indices:
                    anchor_index = min(anchor_indices)
                    row = int(anchor_rows[anchor_index])
                    candidates.append(
                        {
                            "row": row,
                            "group": _json_scalar(groups[row]),
                            "residual_hz": float(residual[row, satellite]),
                            "confidence": 0.0,
                            "anchor": True,
                            "anchor_index": int(anchor_index),
                        }
                    )
                    forced.add(epoch_index)
                    continue
                best = None
                for group_value in epoch_groups:
                    if group_value in reserved:
                        continue
                    candidate, ambiguous = _best_group_candidate(
                        int(satellite),
                        group_value,
                        group_rows,
                        residual,
                        visible,
                        satellites,
                    )
                    if ambiguous:
                        ambiguous_groups.add(group_value)
                    if candidate is not None and (
                        best is None
                        or candidate["confidence"] > best["confidence"]
                        or (
                            candidate["confidence"] == best["confidence"]
                            and candidate["row"] < best["row"]
                        )
                    ):
                        best = candidate
                if best is not None:
                    best["anchor"] = False
                    best["anchor_index"] = None
                candidates.append(best)
            selected_epochs = _viterbi_path(epochs, candidates, forced)
            items = []
            for epoch_index in selected_epochs:
                candidate = candidates[epoch_index]
                items.append(
                    {
                        **candidate,
                        "satellite": int(satellite),
                        "receiver": receiver,
                        "channel": channel,
                        "time_s": float(epochs[epoch_index][0]),
                        "epoch_index": int(epoch_index),
                    }
                )
            for section in _coherent_sections(items):
                if not _qualifies(section):
                    continue
                for item in section:
                    if not item["anchor"]:
                        proposals.append(item)

    best_by_group = {}
    conflict_count = 0
    for proposal in proposals:
        group_value = proposal["group"]
        incumbent = best_by_group.get(group_value)
        key = (proposal["confidence"], -abs(proposal["residual_hz"]), -proposal["satellite"])
        if incumbent is None:
            best_by_group[group_value] = proposal
            continue
        conflict_count += 1
        incumbent_key = (
            incumbent["confidence"],
            -abs(incumbent["residual_hz"]),
            -incumbent["satellite"],
        )
        if key > incumbent_key:
            best_by_group[group_value] = proposal

    selected_items = []
    for anchor_index, (row, satellite) in enumerate(
        zip(anchor_rows, anchor_satellites, strict=True)
    ):
        selected_items.append(
            {
                "row": int(row),
                "group": _json_scalar(groups[row]),
                "satellite": int(satellite),
                "receiver": _json_scalar(np.asarray(data.receiver)[row]),
                "channel": _json_scalar(np.asarray(data.channel)[row]),
                "time_s": group_epoch[_json_scalar(groups[row])],
                "residual_hz": float(residual[row, satellite]),
                "confidence": 1.0,
                "anchor": True,
                "anchor_index": int(anchor_index),
                "epoch_index": -1,
            }
        )
    selected_items.extend(best_by_group.values())

    final_items = [item for item in selected_items if item["anchor"]]
    segments = []
    segment_members = []
    stream_keys = sorted(
        {(item["satellite"], item["receiver"], item["channel"]) for item in selected_items},
        key=repr,
    )
    for satellite, receiver, channel in stream_keys:
        stream = [
            item
            for item in selected_items
            if item["satellite"] == satellite
            and item["receiver"] == receiver
            and item["channel"] == channel
        ]
        for item in stream:
            item["epoch_index"] = group_epoch_index[item["group"]]
        stream.sort(key=lambda item: (item["epoch_index"], item["anchor"] is False, item["row"]))
        for section in _coherent_sections(stream):
            if not _qualifies(section):
                continue
            extension = [item for item in section if not item["anchor"]]
            if extension:
                final_items.extend(extension)
            summary = _segment_summary(section, satellite, data, len(segments))
            segments.append(summary)
            segment_members.append(extension)

    unique_items = {}
    for item in final_items:
        group_value = item["group"]
        if group_value not in unique_items or item["anchor"]:
            unique_items[group_value] = item
    final_items = sorted(
        unique_items.values(),
        key=lambda item: (
            item["time_s"],
            repr(item["receiver"]),
            repr(item["channel"]),
            repr(item["group"]),
        ),
    )
    final_index = {item["group"]: index for index, item in enumerate(final_items)}
    output_weights = np.zeros(len(final_items), dtype=float)
    anchor_mask = np.zeros(len(final_items), dtype=bool)
    for item in final_items:
        index = final_index[item["group"]]
        if item["anchor"]:
            output_weights[index] = anchor_weights[item["anchor_index"]]
            anchor_mask[index] = True

    weighted_segments = []
    for members in segment_members:
        eligible = [item for item in members if item["group"] in final_index]
        if eligible:
            weighted_segments.append(eligible)
    anchor_total = float(anchor_weights.sum())
    if anchor_total > 0 and weighted_segments:
        segment_budget = anchor_total / len(weighted_segments)
        for members in weighted_segments:
            quality = np.asarray([max(item["confidence"], 0.05) for item in members])
            quality /= quality.sum()
            for item, fraction in zip(members, quality, strict=True):
                output_weights[final_index[item["group"]]] = segment_budget * fraction

    positive = output_weights > 0
    if not np.all(positive):
        final_items = [item for item, keep in zip(final_items, positive, strict=True) if keep]
        output_weights = output_weights[positive]
        anchor_mask = anchor_mask[positive]

    output_rows = np.asarray([item["row"] for item in final_items], dtype=int)
    output_satellites = np.asarray([item["satellite"] for item in final_items], dtype=int)
    extension_weight = float(output_weights[~anchor_mask].sum())
    anchor_weight = float(output_weights[anchor_mask].sum())
    diagnostics = {
        "method": "independent anchored-satellite Viterbi paths followed by group exclusivity",
        "approximation": (
            "Satellite paths are solved independently per receiver/channel and conflicts are "
            "resolved deterministically; this is not a joint multi-target optimum. Distinct "
            "source groups at one timestamp may be assigned to different satellites."
        ),
        "gate_hz": GATE_HZ,
        "ambiguity_margin_hz": AMBIGUITY_MARGIN_HZ,
        "minimum_coherent_points": MIN_COHERENT_POINTS,
        "minimum_coherent_span_s": MIN_COHERENT_SPAN_S,
        "max_missed_observed_epochs": MAX_MISSED_OBSERVED_EPOCHS,
        "coincident_epoch_tolerance_s": COINCIDENT_EPOCH_TOLERANCE_S,
        "maximum_counted_support_gap_s": MAX_COUNTED_SUPPORT_GAP_S,
        "anchored_satellite_indices": [int(value) for value in anchored_identities],
        "extended_satellite_indices": [int(value) for value in satellites],
        "anchor_groups": int(len(anchor_rows)),
        "candidate_path_proposals": int(len(proposals)),
        "proposal_conflicts": int(conflict_count),
        "ambiguous_groups_rejected": int(len(ambiguous_groups)),
        "streams_evaluated": int(stream_count),
        "selected_groups": int(len(final_items)),
        "selected_extensions": int(np.sum(~anchor_mask)),
        "anchor_weight_total": anchor_weight,
        "extension_weight_total": extension_weight,
        "extension_weight_cap_respected": bool(extension_weight <= anchor_weight + 1e-12),
        "anchor_track_entries": int(len(anchors.get("tracks", []))),
        "anchor_diagnostics_present": bool(anchors.get("diagnostics") is not None),
    }
    return {
        "rows": output_rows,
        "satellites": output_satellites,
        "weights": output_weights,
        "anchor_mask": anchor_mask,
        "segments": segments,
        "diagnostics": diagnostics,
    }
