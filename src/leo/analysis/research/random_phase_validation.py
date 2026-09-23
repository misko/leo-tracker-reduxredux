"""Random whole-group phase transfer checks on two simultaneous receivers.

Research only: evidence for a coherent receiver link, not satellite identity or
calibrated geometric phase. A in a held block is an explicit tracking input;
B in that block is the held target. All carrier/response selection uses train.
"""

import numpy as np

from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment
from leo.analysis.starlink.relative_phase import normalize_response


def random_phase_groups(
    sample_count,
    sample_rate_hz,
    *,
    seed,
    group_ms=20,
    block_duration_s=4096 / 2500000,
    boundary_guard_s=0.0002,
):
    """Seeded 50/50 complete-group assignment, excluding boundary-crossing FFTs."""
    group_samples = round(group_ms * sample_rate_hz / 1000)
    block_samples = round(block_duration_s * sample_rate_hz)
    guard = round(boundary_guard_s * sample_rate_hz)
    count = sample_count // group_samples
    if count < 6 or block_samples < 64 or 2 * guard + block_samples > group_samples:
        raise ValueError("at least six groups with interior FFT support are required")
    # Random assignment within strata spreads training across the recording;
    # a chance draw cannot recreate the old first-half/second-half split.
    rng = np.random.default_rng(seed)
    strata = np.array_split(np.arange(count), count // 2)
    train = sorted(int(rng.choice(stratum)) for stratum in strata)
    held = [group for group in range(count) if group not in train]
    blocks = []
    for index in range(sample_count // block_samples):
        start = index * block_samples
        group = start // group_samples
        if (
            group >= count
            or start < group * group_samples + guard
            or start + block_samples > (group + 1) * group_samples - guard
        ):
            continue
        blocks.append(
            dict(index=index, group=int(group), partition="train" if group in train else "held")
        )
    return dict(
        seed=int(seed),
        split_kind="random_whole_groups_stratified_over_dwell",
        strata=[list(map(int, s)) for s in strata],
        group_ms=group_ms,
        group_samples=group_samples,
        block_samples=block_samples,
        boundary_guard_samples=guard,
        training_groups=train,
        held_groups=held,
        blocks=blocks,
    )


def _complex_metric(predictions, observations):
    p = np.concatenate(predictions)
    y = np.concatenate(observations)
    cross = np.vdot(p, y)
    denominator = np.sqrt(max(float(np.vdot(p, p).real * np.vdot(y, y).real), 1e-30))
    return complex(cross / denominator)


def _metric(predictions, observations):
    return float(abs(_complex_metric(predictions, observations)))


def _balanced_controls(held):
    """Data-blind, one-to-one cross-group permutation with equal group counts."""
    groups = sorted({b["group"] for b in held})
    members = [[b for b in held if b["group"] == g] for g in groups]
    count = min(map(len, members))
    selected = [
        [blocks[i] for i in np.linspace(0, len(blocks) - 1, count, dtype=int)] for blocks in members
    ]
    blocks = [b for group in selected for b in group]
    controls = list(range(count, len(blocks))) + list(range(count))
    return blocks, controls


def extract_random_phase(iq, sample_rate_hz, *, receiver_cfo_seed_hz, seed=20260923):
    """Train-only normalization; random-held A→B phase, frozen-H and null checks."""
    values = np.asarray(iq)
    split = random_phase_groups(len(values), sample_rate_hz, seed=seed)
    train = [b for b in split["blocks"] if b["partition"] == "train"]
    held = [b for b in split["blocks"] if b["partition"] == "held"]
    n = split["block_samples"]
    fit = estimate_broadband_alignment(
        values,
        sample_rate_hz,
        receiver_cfo_seed_hz=receiver_cfo_seed_hz,
        cfo_search_half_width_hz=900000,
        block_samples=n,
        training_block_indices=tuple(b["index"] for b in train),
        training_group_ids=tuple(b["group"] for b in train),
        heldout_block_indices=tuple(b["index"] for b in held),
        heldout_group_ids=tuple(b["group"] for b in held),
        random_seed=seed + 1,
    )
    model = fit.model
    frequency = np.fft.fftshift(np.fft.fftfreq(n, 1 / sample_rate_hz))
    window = np.hanning(n)

    def spectra(block):
        start = block["index"] * n
        t = (np.arange(start, start + n) - model.reference_sample) / sample_rate_hz
        rotation = np.exp(
            -2j * np.pi * (model.relative_cfo_hz * t + 0.5 * model.relative_cfo_rate_hz_s * t * t)
        )
        return (
            np.fft.fftshift(np.fft.fft(values[start : start + n, 0] * window)),
            np.fft.fftshift(np.fft.fft(values[start : start + n, 1] * rotation * window)),
        )

    train_spectra = [spectra(b) for b in train]
    eligible = abs(frequency) < sample_rate_hz / 2 - 40000
    for sample in (0, len(values) - 1):
        shift = (
            model.relative_cfo_hz
            + model.relative_cfo_rate_hz_s * (sample - model.reference_sample) / sample_rate_hz
        )
        eligible &= abs(frequency + shift) < sample_rate_hz / 2 - 40000
    ids, transfer = normalize_response(
        np.array([s[0] for s in train_spectra]),
        np.array([s[1] for s in train_spectra]),
        frequency,
        np.searchsorted(frequency, model.frequency_hz),
        model.channel_transfer,
        eligible,
    )
    a = ((ids // 64) % 2 == 0) & (ids % 64 >= 4) & (ids % 64 < 60)
    b = ((ids // 64) % 2 == 1) & (ids % 64 >= 4) & (ids % 64 < 60)
    if min(a.sum(), b.sum()) < 8:
        raise ValueError("insufficient disjoint frequency support")
    cap = np.percentile(abs(transfer), 90)
    weights = np.minimum(1, cap / np.maximum(abs(transfer), 1e-30))
    available_held_count = len(held)
    held, control_indices = _balanced_controls(held)
    held_spectra = [spectra(block) for block in held]
    predictions = []
    observations = []
    baselines = []
    controls = []
    wrong_predictions = []
    rows = []
    for i, (block, (left, right)) in enumerate(zip(held, held_spectra, strict=True)):
        # Deliberately mismatched RX1 from a different held group. Null phase is
        # itself estimated on its A bins, so the wrong pair gets equal flexibility.
        wrong_index = control_indices[i]
        wrong = held_spectra[wrong_index][1][ids]
        predicted = left[ids] * transfer
        actual = right[ids]
        phase = float(np.angle(np.sum(weights[a] * predicted[a].conj() * actual[a])))
        wrong_phase = float(np.angle(np.sum(weights[a] * predicted[a].conj() * wrong[a])))
        p = predicted[b] * np.exp(1j * phase)
        wp = predicted[b] * np.exp(1j * wrong_phase)
        y = actual[b]
        w = wrong[b]
        z = np.vdot(p, y)
        wz = np.vdot(wp, w)
        rows.append(
            dict(
                group_id=block["group"],
                block_index=block["index"],
                center_sample=block["index"] * n + (n - 1) / 2,
                a_phase_rad=phase,
                residual_phase_rad=float(np.angle(z)),
                wrong_group_id=held[wrong_index]["group"],
                wrong_block_index=held[wrong_index]["index"],
                wrong_residual_phase_rad=float(np.angle(wz)),
                coherence=_metric([p], [y]),
                wrong_coherence=_metric([wp], [w]),
            )
        )
        predictions.append(p)
        observations.append(y)
        baselines.append(predicted[b])
        controls.append(w)
        wrong_predictions.append(wp)
    group_summaries = []
    group_metrics = []
    for group in split["held_groups"]:
        positions = [i for i, row in enumerate(rows) if row["group_id"] == group]

        def metric(left, right, positions=positions):
            return _complex_metric([left[i] for i in positions], [right[i] for i in positions])

        tracked = metric(predictions, observations)
        null = metric(wrong_predictions, controls)
        frozen = metric(baselines, observations)
        phasor = np.mean([np.exp(1j * rows[i]["residual_phase_rad"]) for i in positions])
        group_metrics.append((tracked, null, frozen, phasor))
        group_summaries.append(
            dict(
                group_id=group,
                block_count=len(positions),
                tracked_coherence=abs(tracked),
                wrong_coherence=abs(null),
                frozen_coherence=abs(frozen),
                phase_resultant=abs(phasor),
            )
        )
    exact, wrong, frozen, resultant = map(float, abs(np.mean(group_metrics, axis=0)))
    return dict(
        split=split,
        reference_sample=model.reference_sample,
        relative_cfo_hz=model.relative_cfo_hz,
        relative_cfo_rate_hz_s=model.relative_cfo_rate_hz_s,
        normalized_frequency_hz=frequency[ids].tolist(),
        normalized_transfer=[[float(z.real), float(z.imag)] for z in transfer],
        training_block_phase_rad=list(fit.training_block_phase_rad),
        training_block_time_s=list(fit.training_block_time_s),
        held_rows=rows,
        group_summaries=group_summaries,
        omitted_held_evaluation_blocks=available_held_count - len(held),
        aggregation="equal_weight_group_complex_coherence_and_mean_phase_phasor",
        tracked_coherence=exact,
        wrong_pair_coherence=wrong,
        frozen_coherence=frozen,
        band_phase_resultant=resultant,
        supported=bool(exact > max(0.05, 3 * wrong) and resultant > 0.8),
        retained_bandwidth_hz=len(ids) * sample_rate_hz / n,
        validation_kind="random_group_held_B_conditioned_on_same_block_A",
        geometric_phase_claimed=False,
    )
